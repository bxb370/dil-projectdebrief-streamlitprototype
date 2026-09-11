"""Load and reshape the Debrief Findings Mastersheet into tidy project/finding tables."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
SHEET_NAME = "Debrief Findings (Add here)"

# Positional layout of the mastersheet (the header row is repeated mid-sheet).
COL = {
    "debrief_date": 2,
    "business_unit": 3,
    "project_number": 4,
    "project_name": 5,
    "project_lead": 6,
    "response_rate": 7,
    "follow_up_owner": 8,
    "stage": 10,
    "path_forward": 17,
    "additional_details": 18,
}
FINDING_PAIRS = [(11, 12), (13, 14), (15, 16)]

CATEGORY_CANON = {
    "leverageable finding / best practice": "Leverageable Finding / Best Practice",
    "leverage finding / best practice": "Leverageable Finding / Best Practice",
    "leverage finding/best practice": "Leverageable Finding / Best Practice",
    "leverage finding": "Leverageable Finding / Best Practice",
    "leverage findings": "Leverageable Finding / Best Practice",
    "opportunity for improvement": "Opportunity for Improvement",
    "technical knowledge / learning": "Technical Knowledge / Learning",
    "technical knowledge/learning": "Technical Knowledge / Learning",
    "technical knowledge": "Technical Knowledge / Learning",
}
BUSINESS_UNIT_CANON = {"aerosol": "Aerosols", "tqi": "TQI"}
UNSPECIFIED = "Unspecified"


def find_workbook() -> Path:
    candidates = sorted(DATA_DIR.glob("*.xlsx"))
    candidates = [p for p in candidates if not p.name.startswith("~$")]
    if not candidates:
        raise FileNotFoundError(f"No .xlsx workbook found in {DATA_DIR}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _clean_text(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).replace("\xa0", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


def _parse_rate(value) -> float:
    """Rates arrive as fractions, percents, or malformed strings like '33%%'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float)):
        rate = float(value)
    else:
        text = _clean_text(value).replace("%", "")
        if not text:
            return np.nan
        try:
            rate = float(text)
        except ValueError:
            return np.nan
        if "%" in str(value):
            rate /= 100.0
    if rate > 1.5:
        rate /= 100.0
    return rate if 0 <= rate <= 1 else np.nan


def _canon(value: str, mapping: dict[str, str]) -> str:
    text = _clean_text(value)
    if not text:
        return UNSPECIFIED
    return mapping.get(text.lower(), text)


def _read_workbook_sheet(path: Path) -> pd.DataFrame:
    workbook = pd.ExcelFile(path)
    sheet_name = SHEET_NAME if SHEET_NAME in workbook.sheet_names else workbook.sheet_names[0]
    return pd.read_excel(path, sheet_name=sheet_name, header=None)


def _header_lookup(header: pd.Series) -> dict[str, int]:
    return {_clean_text(value).lower(): column for column, value in header.items() if _clean_text(value)}


def _column(header: pd.Series, names: list[str], fallback: int) -> int:
    lookup = _header_lookup(header)
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return fallback


def _raw_rows(path: Path) -> tuple[pd.Series, pd.DataFrame]:
    raw = _read_workbook_sheet(path)
    header_rows = raw.index[
        raw.apply(lambda row: row.astype(str).str.strip().eq("Project Name").any(), axis=1)
    ].tolist()
    start = (header_rows[-1] + 1) if header_rows else 3
    header = raw.loc[header_rows[-1]] if header_rows else raw.loc[2]
    body = raw.loc[start:].copy()
    has_content = body[[COL["project_name"], COL["debrief_date"]]].notna().any(axis=1)
    return header, body[has_content]


def load_raw_table(path: Path | None = None) -> pd.DataFrame:
    """The mastersheet rows exactly as entered, with a `Row` key matching load_debrief_data."""
    path = path or find_workbook()
    header, body = _raw_rows(path)

    keep = [c for c in body.columns if _clean_text(header.get(c))]
    table = body[keep].copy()
    table.columns = [_clean_text(header[c]) for c in keep]
    table.insert(0, "Row", range(1, len(table) + 1))

    for column in table.columns:
        if table[column].dtype == object:
            table[column] = table[column].map(_clean_text)
    return table.reset_index(drop=True)


def _project_rating(rate: float, findings: pd.DataFrame) -> float:
    """Derived 1-5 health rating: half survey engagement, half finding-mix quality.

    The mastersheet has no explicit rating column, so this is a transparent proxy.
    """
    rate_score = 0.5 if np.isnan(rate) else float(np.clip(rate, 0, 1))
    if findings.empty:
        mix_score = 0.5
    else:
        weights = {
            "Leverageable Finding / Best Practice": 1.0,
            "Technical Knowledge / Learning": 0.6,
            "Opportunity for Improvement": 0.2,
        }
        mix_score = findings["Category"].map(weights).fillna(0.5).mean()
    return round(float(np.clip(1 + 4 * (0.5 * rate_score + 0.5 * mix_score), 1, 5)), 2)


def load_debrief_data(path: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (projects, findings) tidy frames keyed by Project ID."""
    path = path or find_workbook()
    header, body = _raw_rows(path)

    columns = {
        "debrief_date": _column(header, ["Project Debrief Date", "Debrief Date"], COL["debrief_date"]),
        "business_unit": _column(header, ["Business Unit"], COL["business_unit"]),
        "project_number": _column(header, ["Project Number"], COL["project_number"]),
        "project_name": _column(header, ["Project Name"], COL["project_name"]),
        "project_lead": _column(header, ["Project Lead"], COL["project_lead"]),
        "response_rate": _column(header, ["Survey Rate Response", "Survey Response Rate"], COL["response_rate"]),
        "overall_rating": _column(header, ["Overall Project Rating", "Project Rating"], -1),
        "stage": _column(header, ["Stage"], COL["stage"]),
        "path_forward": _column(header, ["Suggested Pathforward", "Suggested Path Forward"], COL["path_forward"]),
        "additional_details": _column(header, ["Additional Details"], COL["additional_details"]),
        "follow_up_owner": _column(header, ["Follow-up Owner", "Follow Up Owner"], COL["follow_up_owner"]),
    }
    finding_pairs = [
        (
            _column(header, [f"Category {number}"], cat_col),
            _column(header, [f"Key Takeaway {number}"], take_col),
        )
        for number, (cat_col, take_col) in enumerate(FINDING_PAIRS, start=1)
    ]

    project_records: list[dict] = []
    finding_records: list[dict] = []

    for position, (_, row) in enumerate(body.iterrows(), start=1):
        name = _clean_text(row[columns["project_name"]])
        number = _clean_text(row[columns["project_number"]])
        if not name and not number:
            continue

        project_id = f"{number} — {name}" if number else name
        date = pd.to_datetime(row[columns["debrief_date"]], errors="coerce")
        rate = _parse_rate(row[columns["response_rate"]])

        base = {
            "Project ID": project_id,
            "Project Number": number or UNSPECIFIED,
            "Project Name": name or UNSPECIFIED,
            "Business Unit": _canon(row[columns["business_unit"]], BUSINESS_UNIT_CANON),
            "Project Lead": _clean_text(row[columns["project_lead"]]) or UNSPECIFIED,
            "Stage": _clean_text(row[columns["stage"]]) or UNSPECIFIED,
            "Debrief Date": date,
            "Survey Response Rate": rate,
        }

        rows = []
        for cat_col, take_col in finding_pairs:
            category = _canon(row[cat_col], CATEGORY_CANON)
            takeaway = _clean_text(row[take_col])
            if not takeaway and category == UNSPECIFIED:
                continue
            rows.append({**base, "Category": category, "Key Takeaway": takeaway})

        project_findings = pd.DataFrame(rows)
        entered_rating = pd.to_numeric(row[columns["overall_rating"]], errors="coerce") if columns["overall_rating"] >= 0 else np.nan
        rating = round(float(entered_rating), 2) if not np.isnan(entered_rating) else _project_rating(rate, project_findings)

        for record in rows:
            record["Suggested Path Forward"] = (
                _clean_text(row[columns["path_forward"]]) or UNSPECIFIED
            )
            record["Additional Details"] = _clean_text(row[columns["additional_details"]])
            record["Project Rating"] = rating
            record["Row"] = position
            finding_records.append(record)

        project_records.append(
            {
                **base,
                "Project Rating": rating,
                "Findings": len(rows),
                "Suggested Path Forward": _clean_text(row[columns["path_forward"]]) or UNSPECIFIED,
                "Additional Details": _clean_text(row[columns["additional_details"]]),
                "Follow-up Owner": _clean_text(row[columns["follow_up_owner"]]) or UNSPECIFIED,
                "Lessons Learned": " | ".join(r["Key Takeaway"] for r in rows if r["Key Takeaway"]),
                "Row": position,
            }
        )

    projects = pd.DataFrame(project_records)
    findings = pd.DataFrame(finding_records)

    if not projects.empty:
        dupe_key = ["Project ID", "Business Unit", "Debrief Date", "Lessons Learned"]
        keep_rows = set(projects.drop_duplicates(subset=dupe_key)["Row"])
        projects = projects[projects["Row"].isin(keep_rows)]
        findings = findings[findings["Row"].isin(keep_rows)]
        projects = (
            projects.sort_values("Debrief Date", ascending=False, na_position="last")
            .reset_index(drop=True)
        )
    return projects, findings
