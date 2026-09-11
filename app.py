"""Project Debrief Insights — Tableau-style Streamlit dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_loader import load_debrief_data, load_raw_table

st.set_page_config(page_title="Project Debrief Insights", page_icon="📊", layout="wide")

TABLEAU10 = [
    "#2F6B9A", "#E07A3F", "#C94C4C", "#4FA3A5", "#5B8C5A",
    "#D6A419", "#8A6FB0", "#D982A6", "#8C6D4A", "#9AA3A8",
]
CATEGORY_COLORS = {
    "Leverageable Finding / Best Practice": "#5B8C5A",
    "Opportunity for Improvement": "#E07A3F",
    "Technical Knowledge / Learning": "#2F6B9A",
    "Unspecified": "#9AA3A8",
}
DASHBOARD_YEAR = 2026
SURVEY_GOAL = 0.60
BUSINESS_UNIT_GOALS = {
    "Aerosols": 3,
    "Applicators": 4,
    "Building Materials": 3,
    "Paint-MOB": 3,
    "Paint-NPD": 4,
    "Product Technology": 3,
    "Quality": 2,
    "Woodcare": 4,
}
ESTIMATED_DATE_OFFSETS = [14, -7, 21, 0, 30, -10, 12, 5, -3, 24, 8, -14, 16, 4]

st.markdown(
    """
    <style>
            .stApp { background-color: #F7F4EE; }
            section[data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #D8D1C7; }
      div[data-testid="stMetric"] {
                    background: #FFFFFF; border: 1px solid #D8D1C7; border-radius: 4px;
          padding: 10px 14px; box-shadow: 0 1px 2px rgba(0,0,0,.08);
      }
            div[data-testid="stMetricValue"] { font-size: 26px; color: #243B53; }
    .goal-strip { display:grid; grid-template-columns:minmax(0,2fr) minmax(260px,1fr); gap:12px; margin-bottom:12px; align-items:stretch; }
            .goal-card { background:#FFFFFF; border:1px solid #D8D1C7; border-top:4px solid #2F6B9A; padding:12px 16px; box-shadow:0 1px 2px rgba(36,59,83,.10); }
            .goal-card span { display:block; color:#6B6258; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
            .goal-card strong { display:block; color:#243B53; font-size:24px; margin-top:2px; }
            .tab-header { background:#243B53; color:#FFFFFF; padding:14px 20px; border-radius:4px; margin-bottom:14px; }
      .tab-header h1 { margin:0; font-size:24px; font-weight:600; }
            .tab-header p { margin:4px 0 0 0; font-size:13px; color:#DDE8F0; }
        .callout { background:#FFFFFF; border-left:5px solid #C94C4C; padding:12px 16px;
                         margin:0 0 12px 0; color:#2F2F2F; box-shadow:0 1px 2px rgba(36,59,83,.10); }
                        .section-title { font-family:"Segoe UI",Tahoma,sans-serif; color:#243B53; font-size:22px;
                                             font-weight:700; margin:18px 0 8px 0; }
            .panel-title { font-family:"Segoe UI",Tahoma,sans-serif; color:#2F2F2F; font-size:15px;
                                         font-weight:600; border-bottom:1px solid #D8D1C7; padding-bottom:4px;
                     margin:10px 0 10px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


def panel(title: str) -> None:
    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def style_fig(fig, height: int = 340):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Segoe UI, Tahoma, sans-serif", size=12, color="#2F2F2F"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
    )
    fig.update_xaxes(gridcolor="#ECE7DF", zeroline=False)
    fig.update_yaxes(gridcolor="#ECE7DF", zeroline=False)
    return fig


def metric_band(counts: pd.Series, per_row: int = 7) -> None:
    items = list(counts.items())
    for start in range(0, len(items), per_row):
        chunk = items[start : start + per_row]
        cols = st.columns(per_row)
        for col, (label, value) in zip(cols, chunk):
            col.metric(str(label), f"{int(value):,}")


def goal_for_group(group: str, completed: int) -> int:
    return BUSINESS_UNIT_GOALS.get(group, max(completed + 1, 2))


def lighten_hex_color(hex_color: str, amount: float = 0.68) -> str:
    hex_color = hex_color.lstrip("#")
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (0, 2, 4))
    lightened = [round(channel + (255 - channel) * amount) for channel in (red, green, blue)]
    return "#" + "".join(f"{channel:02X}" for channel in lightened)


def add_goal_fields(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["Quarter"] = enriched["Debrief Date"].dt.to_period("Q").astype(str).str.replace("2026Q", "Q", regex=False)
    enriched.loc[enriched["Quarter"].eq("NaT"), "Quarter"] = "No date"

    offsets = [ESTIMATED_DATE_OFFSETS[(int(row) - 1) % len(ESTIMATED_DATE_OFFSETS)] for row in enriched["Row"]]
    fallback_date = pd.Timestamp(DASHBOARD_YEAR, 12, 31)
    enriched["Estimated Completion Date"] = [
        (date if pd.notna(date) else fallback_date) + pd.Timedelta(days=offset)
        for date, offset in zip(enriched["Debrief Date"], offsets)
    ]
    enriched["On-Time Debrief"] = [
        "On time" if pd.notna(date) and date <= due else "Late"
        for date, due in zip(enriched["Debrief Date"], enriched["Estimated Completion Date"])
    ]
    return enriched


def survey_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    survey = frame.dropna(subset=["Survey Response Rate"]).copy()
    survey["Survey Percent"] = survey["Survey Response Rate"] * 100
    survey["Bin Start"] = (survey["Survey Percent"].clip(0, 99.999) // 10 * 10).astype(int)
    survey["Bin Midpoint"] = survey["Bin Start"] + 5
    survey["Survey Range"] = survey["Bin Start"].map(lambda value: f"{value}-{value + 10}%")
    distribution = (
        survey.groupby(["Bin Start", "Bin Midpoint", "Survey Range"], observed=True)
        .agg(
            Projects=("Project Name", "count"),
            Project_List=("Project Name", lambda values: "<br>".join(sorted(values))),
            Groups=("Business Unit", lambda values: ", ".join(sorted(set(values)))),
        )
        .reset_index()
        .sort_values("Bin Start")
    )
    return distribution


@st.cache_data(show_spinner="Loading debrief mastersheet...")
def get_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    projects, findings = load_debrief_data()
    return projects, findings, load_raw_table()


projects, findings, raw_table = get_data()

if projects.empty:
    st.error("No debrief projects were found in the workbook under `data/`.")
    st.stop()

projects = add_goal_fields(projects)
projects["Year"] = projects["Debrief Date"].dt.year.astype("Int64")
findings = findings.merge(projects[["Row", "Year", "Quarter"]], on="Row", how="left")
projects_2026 = projects[projects["Year"].eq(DASHBOARD_YEAR)].copy()

if projects_2026.empty:
    st.error(f"No {DASHBOARD_YEAR} debrief projects were found in the workbook under `data/`.")
    st.stop()

st.markdown(
    """
    <div class="tab-header">
          <h1>2026 Debrief Goal Dashboard</h1>
            <p>Start with the goals, see where teams stand, and understand whether they are on track.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

f_projects = projects_2026.reset_index(drop=True)
f_findings = findings[findings["Row"].isin(f_projects["Row"])]

# ---------------------------------------------------------------- KPIs
goal_rows = []
for business_unit, completed in f_projects.groupby("Business Unit").size().items():
    goal = goal_for_group(business_unit, int(completed))
    remaining = max(goal - int(completed), 0)
    goal_rows.append(
        {
            "Business Unit": business_unit,
            "Completed": int(completed),
            "Goal": goal,
            "Remaining": remaining,
            "Progress": int(completed) / goal if goal else 0,
        }
    )
goal_status = pd.DataFrame(goal_rows).sort_values("Progress", ascending=True)

goal_overview = goal_status.sort_values("Goal", ascending=False)
goal_color_map = {
    business_unit: TABLEAU10[index % len(TABLEAU10)]
    for index, business_unit in enumerate(goal_overview["Business Unit"])
}
section("Goals")
panel("2026 project debrief completion goals by team")
left, right = st.columns([3, 1])
with left:
    fig = px.bar(
        goal_overview,
        x="Business Unit",
        y="Goal",
        color="Business Unit",
        color_discrete_map=goal_color_map,
        text="Goal",
        hover_data={"Completed": True, "Remaining": True, "Progress": ":.0%"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title=None, tickangle=-25)
    fig.update_yaxes(title="Annual debrief goal", dtick=1)
    st.plotly_chart(style_fig(fig, 300), use_container_width=True)

with right:
    st.markdown(
        f"""
                <div class="goal-card">
          <span>Survey participation goal</span>
          <strong>{SURVEY_GOAL:.0%} or higher on every project</strong>
        </div>
                <div class="goal-card" style="margin-top:12px;">
                    <span>On-time progression goal</span>
                    <strong>All project debriefs completed on time</strong>
                </div>
        """,
        unsafe_allow_html=True,
    )

section("Performance")
progress_col, quarter_col = st.columns([3, 2])
with progress_col:
    panel("How far is each team toward its debrief goal?")
    fig = go.Figure()
    fig.add_bar(
        x=goal_overview["Business Unit"],
        y=goal_overview["Completed"],
        name="Completed",
        marker_color=[goal_color_map[business_unit] for business_unit in goal_overview["Business Unit"]],
        text=goal_overview["Completed"],
        textposition="inside",
        customdata=goal_overview[["Goal", "Remaining", "Progress"]],
        hovertemplate=(
            "%{x}<br>Completed: %{y}<br>Goal: %{customdata[0]}<br>"
            "Remaining: %{customdata[1]}<br>Progress: %{customdata[2]:.0%}<extra></extra>"
        ),
    )
    fig.add_bar(
        x=goal_overview["Business Unit"],
        y=goal_overview["Remaining"],
        name="Remaining",
            marker_color="#D8D1C7",
        text=goal_overview["Remaining"],
        textposition="inside",
        customdata=goal_overview[["Goal", "Completed", "Progress"]],
        hovertemplate=(
            "%{x}<br>Remaining: %{y}<br>Goal: %{customdata[0]}<br>"
            "Completed: %{customdata[1]}<br>Progress: %{customdata[2]:.0%}<extra></extra>"
        ),
    )
    fig.update_traces(textfont_color="#243B53")
    fig.update_layout(barmode="stack", legend_title_text=None)
    fig.update_xaxes(title=None, tickangle=-25)
    fig.update_yaxes(title="Annual debrief goal", dtick=1)
    st.plotly_chart(style_fig(fig, 390), use_container_width=True)

with quarter_col:
    panel("Completed debriefs by quarter")
    quarter_matrix = pd.crosstab(f_projects["Business Unit"], f_projects["Quarter"])
    quarter_matrix = quarter_matrix.reindex(index=goal_overview["Business Unit"], columns=["Q1", "Q2", "Q3", "Q4"], fill_value=0)
    fig = go.Figure(
        data=go.Heatmap(
            z=quarter_matrix.values,
            x=quarter_matrix.columns,
            y=quarter_matrix.index,
                colorscale=[[0, "#F0ECE5"], [1, "#2F6B9A"]],
            text=quarter_matrix.values,
            texttemplate="%{text}",
            hovertemplate="%{y}<br>%{x}: %{z} completed<extra></extra>",
            showscale=False,
        )
    )
    fig.update_xaxes(title=None)
    fig.update_yaxes(title=None)
    st.plotly_chart(style_fig(fig, 390), use_container_width=True)

panel("How is each team doing on the survey response goal?")
survey_box = f_projects.dropna(subset=["Survey Response Rate"]).copy()
fig = px.box(
    survey_box,
    x="Business Unit",
    y="Survey Response Rate",
    color="Business Unit",
    color_discrete_map=goal_color_map,
    points="all",
    category_orders={"Business Unit": goal_overview["Business Unit"].tolist()},
    hover_data=["Project Name", "Project Number", "Debrief Date", "Quarter", "Survey Response Rate"],
)
fig.add_hline(
    y=SURVEY_GOAL,
    line_color="#C94C4C",
    line_width=3,
    annotation_text="60% goal",
    annotation_position="top left",
)
fig.update_layout(showlegend=False)
fig.update_xaxes(title=None, tickangle=-25)
fig.update_yaxes(title="Survey response rate", tickformat=".0%", range=[0, 1.05])
st.plotly_chart(style_fig(fig, 360), use_container_width=True)

panel("How are teams doing on completing project debriefs on time?")
on_time_points = f_projects.dropna(subset=["Debrief Date", "Estimated Completion Date"]).copy()
on_time_points["Days From Due Date"] = (
    on_time_points["Debrief Date"] - on_time_points["Estimated Completion Date"]
).dt.days
on_time_points["Timing"] = on_time_points["Days From Due Date"].map(
    lambda days: "Late" if days > 0 else "On time or early"
)
y_min = min(int(on_time_points["Days From Due Date"].min()) - 3, -3)
y_max = max(int(on_time_points["Days From Due Date"].max()) + 3, 3)
fig = px.scatter(
    on_time_points,
    x="Business Unit",
    y="Days From Due Date",
    color="Business Unit",
    symbol="Timing",
    color_discrete_map=goal_color_map,
    category_orders={"Business Unit": goal_overview["Business Unit"].tolist()},
    hover_data=[
        "Project Name",
        "Project Number",
        "Quarter",
        "Debrief Date",
        "Estimated Completion Date",
        "Days From Due Date",
        "Timing",
    ],
)
fig.add_hrect(y0=y_min, y1=0, fillcolor="#DCEBD8", opacity=0.48, line_width=0, layer="below")
fig.add_hrect(y0=0, y1=y_max, fillcolor="#F4D7D2", opacity=0.48, line_width=0, layer="below")
fig.add_hline(
    y=0,
    line_color="#2F2F2F",
    line_width=2,
    annotation_text="Due date / on time",
    annotation_position="top left",
)
fig.update_traces(marker=dict(size=11, line=dict(width=1, color="#FFFFFF")))
fig.update_layout(showlegend=False)
fig.update_xaxes(title=None, tickangle=-25)
fig.update_yaxes(title="Days from due date", zeroline=False, range=[y_min, y_max])
st.plotly_chart(style_fig(fig, 390), use_container_width=True)

panel("How do teams compare on project ratings?")
rating_chart, rating_summary = st.columns([3, 1])
average_rating = f_projects["Project Rating"].mean()
with rating_chart:
    rating_points = f_projects.dropna(subset=["Project Rating"]).copy()
    fig = px.box(
        rating_points,
        x="Business Unit",
        y="Project Rating",
        color="Business Unit",
        color_discrete_map=goal_color_map,
        points="all",
        category_orders={"Business Unit": goal_overview["Business Unit"].tolist()},
        hover_data=[
            "Project Name",
            "Project Number",
            "Project Lead",
            "Stage",
            "Debrief Date",
            "Quarter",
            "Project Rating",
        ],
    )
    fig.add_hline(
        y=average_rating,
        line_color="#C94C4C",
        line_width=3,
        annotation_text=f"Average {average_rating:.2f}",
        annotation_position="top left",
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title=None, tickangle=-25)
    fig.update_yaxes(title="Project rating", range=[0, 5.2])
    st.plotly_chart(style_fig(fig, 360), use_container_width=True)

with rating_summary:
    st.markdown(
        f"""
        <div class="goal-card" style="height:100%;">
          <span>Overall average project rating</span>
          <strong>{average_rating:.2f} / 5</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

section("Get More Info")
panel("Want to explore past project insights?")
st.markdown(
        """
        <div class="goal-card" style="margin-bottom:12px;">
            <span>Debrief insights bot</span>
            <strong>Interested in extracting insights from past projects or asking questions about prior debriefs? Chat with our bot.</strong>
        </div>
        """,
        unsafe_allow_html=True,
)

# ---------------------------------------------------------------- project table
panel("Project details for people who want the specifics")
table_bu = st.multiselect(
    "Filter project sheet by team",
    sorted(f_projects["Business Unit"].unique()),
    default=sorted(f_projects["Business Unit"].unique()),
)
project_sheet = f_projects[f_projects["Business Unit"].isin(table_bu)].copy() if table_bu else f_projects.copy()
project_sheet["Survey Participation"] = project_sheet["Survey Response Rate"] * 100
takeaway_columns = ["Category 1", "Key Takeaway 1", "Category 2", "Key Takeaway 2", "Category 3", "Key Takeaway 3"]
takeaway_source = raw_table[["Row"] + [column for column in takeaway_columns if column in raw_table.columns]].copy()
project_sheet = project_sheet.merge(takeaway_source, on="Row", how="left")
for column in takeaway_columns:
    if column not in project_sheet.columns:
        project_sheet[column] = ""
project_sheet = project_sheet[
    [
        "Business Unit",
        "Project Number",
        "Project Name",
        "Project Lead",
        "Stage",
        "Debrief Date",
        "Estimated Completion Date",
        "Survey Participation",
        "Project Rating",
        "Category 1",
        "Key Takeaway 1",
        "Category 2",
        "Key Takeaway 2",
        "Category 3",
        "Key Takeaway 3",
        "Suggested Path Forward",
    ]
].sort_values(["Business Unit", "Debrief Date"])
st.dataframe(
    project_sheet,
    use_container_width=True,
    hide_index=True,
    height=520,
    column_config={
        "Debrief Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "Estimated Completion Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "Survey Participation": st.column_config.NumberColumn(format="%.0f%%"),
        "Project Rating": st.column_config.NumberColumn(format="%.2f"),
    },
)
st.download_button(
    "Download filtered project sheet (CSV)",
    project_sheet.to_csv(index=False).encode("utf-8"),
    file_name="debrief_project_sheet_filtered.csv",
    mime="text/csv",
)
