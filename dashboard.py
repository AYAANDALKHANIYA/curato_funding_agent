"""
dashboard.py
------------
Curato — Funding & Grant Intelligence Dashboard
A Streamlit app to visualize and explore daily funding leads from leads_output.csv.

Run with:
    streamlit run dashboard.py
"""

import os
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Curato — Funding Intelligence",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Header */
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1e1e2e;
        margin-bottom: 0.25rem;
    }
    .sub-header {
        color: #6b7280;
        font-size: 1rem;
        margin-bottom: 1.5rem;
    }

    /* Metric cards */
    .metric-card {
        background: #f8fafc;
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid #e2e8f0;
    }

    /* Score badges */
    .score-high {
        background-color: #dcfce7;
        color: #166534;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
    }
    .score-mid-high {
        background-color: #fed7aa;
        color: #9a3412;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
    }
    .score-mid {
        background-color: #fef3c7;
        color: #92400e;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
    }
    .score-low {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 2px 8px;
        border-radius: 12px;
        font-weight: 600;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #f8fafc;
    }
    [data-testid="stSidebar"] .stMarkdown h2 {
        color: #374151;
        font-size: 1rem;
        font-weight: 600;
        margin-top: 1rem;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab"] {
        font-size: 1rem;
        font-weight: 500;
    }

    /* Top lead cards */
    .lead-card-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e1e2e;
    }
    .lead-detail-label {
        font-size: 0.85rem;
        color: #6b7280;
        font-weight: 500;
    }
    .lead-detail-value {
        font-size: 0.95rem;
        color: #1e1e2e;
    }

    /* Download button */
    .stDownloadButton button {
        background-color: #6366f1;
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: 500;
    }
    .stDownloadButton button:hover {
        background-color: #4f46e5;
        color: white;
    }

    /* General polish */
    div[data-testid="metric-container"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.25rem;
    }
    div[data-testid="metric-container"] label {
        color: #6b7280;
        font-size: 0.85rem;
        font-weight: 500;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #1e1e2e;
        font-size: 1.6rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Resolve CSV path relative to the project root (parent of this script)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(_SCRIPT_DIR, "data", "leads_output.csv")

EXPECTED_COLUMNS = [
    "Company Name", "Website", "LinkedIn", "Location", "Industry",
    "Company Stage", "Announcement Type", "Funding/Grant Amount",
    "Announcement Date", "Source URL", "Lead Score", "Why This Lead?",
    "Source Name", "Collected At",
]

ALL_STAGES = ["Idea", "MVP", "Early Revenue", "Growth", "Scale", "Enterprise"]

PLOTLY_PALETTE = ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981",
                  "#3b82f6", "#ef4444", "#14b8a6", "#f97316", "#a855f7"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)  # 5-minute cache
def load_data() -> pd.DataFrame:
    """Load and clean the leads from Google Sheets. Returns empty DataFrame if not found."""
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    
    if not sheet_id or not json_path:
        st.warning("Google Sheets credentials not found in .env")
        return pd.DataFrame()

    if not os.path.isabs(json_path):
        json_path = os.path.join(_SCRIPT_DIR, json_path)

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
        client = gspread.authorize(creds)
        doc = client.open_by_key(sheet_id)
        
        all_records = []
        for ws in doc.worksheets():
            all_records.extend(ws.get_all_records())
            
        df = pd.DataFrame(all_records)
    except Exception as exc:
        st.error(f"Error loading Google Sheets: {exc}")
        return pd.DataFrame()

    if df.empty:
        return df

    # Ensure all expected columns exist, fill missing with ""
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")

    # Parse date columns
    for date_col in ["Announcement Date", "Collected At"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    # Lead Score → numeric
    df["Lead Score"] = pd.to_numeric(df["Lead Score"], errors="coerce").fillna(0).astype(int)

    return df


def _score_badge(score: int) -> str:
    """Return HTML badge string for a given score."""
    if score >= 9:
        css = "score-high"
        label = f"🟢 {score}/10"
    elif score >= 7:
        css = "score-mid-high"
        label = f"🟠 {score}/10"
    elif score >= 5:
        css = "score-mid"
        label = f"🟡 {score}/10"
    else:
        css = "score-low"
        label = f"🔴 {score}/10"
    return f'<span class="{css}">{label}</span>'


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
header_left, header_right = st.columns([3, 1])
with header_left:
    st.markdown('<div class="main-header">💰 Funding &amp; Grant Intelligence</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Daily lead feed for Curato — companies that just raised money '
        'and need branding, marketing, and web services.</div>',
        unsafe_allow_html=True,
    )
with header_right:
    st.markdown(f"<div style='text-align:right; color:#6b7280; padding-top:0.5rem;'>"
                f"📅 {date.today().strftime('%B %d, %Y')}</div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df_all = load_data()

if df_all.empty:
    if not os.path.exists(CSV_PATH):
        st.warning(
            "**No leads found yet.**\n\n"
            "Run the pipeline first:\n"
            "```\npython -m src.pipeline\n```\n\n"
            f"Expected CSV path: `{CSV_PATH}`"
        )
    else:
        st.warning("The leads CSV exists but contains no data yet. Run the pipeline to populate it.")
    st.stop()

# ---------------------------------------------------------------------------
# Summary Metrics
# ---------------------------------------------------------------------------
today = pd.Timestamp(date.today())

leads_today = df_all[
    df_all["Announcement Date"].dt.date == date.today()
] if "Announcement Date" in df_all.columns else pd.DataFrame()

total_today = len(leads_today)
total_all = len(df_all)
avg_score = round(df_all["Lead Score"].mean(), 1) if not df_all.empty else 0.0
top_source = (
    df_all["Source Name"].value_counts().idxmax()
    if not df_all["Source Name"].eq("").all()
    else "N/A"
)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("📅 Leads Today", total_today)
with m2:
    st.metric("📊 Total Leads (All Time)", total_all)
with m3:
    st.metric("⭐ Avg Lead Score", f"{avg_score}/10")
with m4:
    st.metric("🏆 Top Source", top_source)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar Filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🎯 Filters")

    # --- Date Range ---
    st.markdown("**📅 Date Range**")
    default_start = date.today() - timedelta(days=7)
    default_end = date.today()
    start_date = st.date_input("Start Date", value=default_start, key="start_date")
    end_date = st.date_input("End Date", value=default_end, key="end_date")

    # --- Lead Score ---
    st.markdown("**⭐ Lead Score**")
    score_range = st.slider(
        "Minimum Lead Score",
        min_value=1, max_value=10,
        value=(7, 10),
        key="score_range",
    )

    # --- Announcement Type ---
    st.markdown("**💼 Announcement Type**")
    all_types = sorted([x for x in df_all["Announcement Type"].unique() if x])
    selected_types = st.multiselect(
        "Announcement Type",
        options=all_types,
        default=all_types,
        label_visibility="collapsed",
        key="sel_types",
    )

    # --- Industry ---
    st.markdown("**🏭 Industry**")
    all_industries = sorted([x for x in df_all["Industry"].unique() if x])
    selected_industries = st.multiselect(
        "Industry",
        options=all_industries,
        default=all_industries,
        label_visibility="collapsed",
        key="sel_industries",
    )

    # --- Company Stage ---
    st.markdown("**🚀 Company Stage**")
    available_stages = [s for s in ALL_STAGES if s in df_all["Company Stage"].unique()]
    # Include any stages in data not in our predefined list
    extra_stages = [s for s in df_all["Company Stage"].unique() if s and s not in ALL_STAGES]
    stage_options = available_stages + sorted(extra_stages)
    selected_stages = st.multiselect(
        "Company Stage",
        options=stage_options if stage_options else ALL_STAGES,
        default=stage_options if stage_options else ALL_STAGES,
        label_visibility="collapsed",
        key="sel_stages",
    )

    # --- Source ---
    st.markdown("**📰 Source**")
    all_sources = sorted([x for x in df_all["Source Name"].unique() if x])
    selected_sources = st.multiselect(
        "Source",
        options=all_sources,
        default=all_sources,
        label_visibility="collapsed",
        key="sel_sources",
    )

    # --- Search ---
    st.markdown("**🔍 Search**")
    search_query = st.text_input(
        "Search by company name or keyword",
        placeholder="e.g. FinTech, Mumbai, Razorpay...",
        label_visibility="collapsed",
        key="search",
    )

    st.divider()

# ---------------------------------------------------------------------------
# Apply Filters
# ---------------------------------------------------------------------------
df = df_all.copy()

# Date filter (handle NaT gracefully)
if "Announcement Date" in df.columns:
    mask_date = (
        df["Announcement Date"].dt.date.between(start_date, end_date)
        | df["Announcement Date"].isna()
    )
    df = df[mask_date & ~df["Announcement Date"].isna()]

# Score filter
df = df[df["Lead Score"].between(score_range[0], score_range[1])]

# Announcement Type filter
if selected_types:
    df = df[df["Announcement Type"].isin(selected_types)]

# Industry filter
if selected_industries:
    df = df[df["Industry"].isin(selected_industries)]

# Company Stage filter
if selected_stages:
    df = df[df["Company Stage"].isin(selected_stages)]

# Source filter
if selected_sources:
    df = df[df["Source Name"].isin(selected_sources)]

# Search filter
if search_query.strip():
    q = search_query.strip().lower()
    df = df[
        df["Company Name"].str.lower().str.contains(q, na=False)
        | df["Why This Lead?"].str.lower().str.contains(q, na=False)
        | df["Industry"].str.lower().str.contains(q, na=False)
        | df["Location"].str.lower().str.contains(q, na=False)
    ]

# Show filter count in sidebar
with st.sidebar:
    match_color = "#166534" if len(df) > 0 else "#991b1b"
    st.markdown(
        f'<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; '
        f'padding:0.75rem; text-align:center; color:{match_color}; font-weight:600;">'
        f"✅ {len(df)} lead{'s' if len(df) != 1 else ''} match your filters"
        f"</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# No results state
# ---------------------------------------------------------------------------
if df.empty:
    st.info("🔍 No leads match your current filters. Try adjusting the sidebar filters.")
    st.stop()

# ---------------------------------------------------------------------------
# Main Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📋 Lead Table", "📊 Analytics", "🏆 Top Leads"])

# ============================================================
# TAB 1 — Lead Table
# ============================================================
with tab1:
    st.markdown(f"### Showing {len(df)} leads")

    # Build display dataframe
    display_cols = [
        "Lead Score", "Company Name", "Website", "Announcement Type",
        "Funding/Grant Amount", "Industry", "Location", "Company Stage",
        "Announcement Date", "Why This Lead?", "Source Name", "Source URL", "LinkedIn",
    ]

    df_display = df[[c for c in display_cols if c in df.columns]].copy()

    # Format date column for display
    if "Announcement Date" in df_display.columns:
        df_display["Announcement Date"] = df_display["Announcement Date"].dt.strftime("%Y-%m-%d")

    # Sort by score descending
    df_display = df_display.sort_values("Lead Score", ascending=False)

    # Build column config
    col_config = {
        "Lead Score": st.column_config.NumberColumn(
            "Score",
            help="Lead priority score (1–10)",
            format="%d",
            width="small",
        ),
        "Company Name": st.column_config.TextColumn("Company", width="medium"),
        "Website": st.column_config.LinkColumn("Website", width="small"),
        "Source URL": st.column_config.LinkColumn("Article", width="small"),
        "LinkedIn": st.column_config.LinkColumn("LinkedIn", width="small"),
        "Announcement Type": st.column_config.TextColumn("Type", width="medium"),
        "Funding/Grant Amount": st.column_config.TextColumn("Amount", width="small"),
        "Industry": st.column_config.TextColumn("Industry", width="medium"),
        "Location": st.column_config.TextColumn("Location", width="medium"),
        "Company Stage": st.column_config.TextColumn("Stage", width="small"),
        "Announcement Date": st.column_config.TextColumn("Date", width="small"),
        "Why This Lead?": st.column_config.TextColumn("Why This Lead?", width="large"),
        "Source Name": st.column_config.TextColumn("Source", width="medium"),
    }

    st.dataframe(
        df_display,
        column_config=col_config,
        use_container_width=True,
        hide_index=True,
        height=520,
    )

    # Score legend
    st.markdown(
        '<div style="margin-top:0.5rem; font-size:0.85rem; color:#6b7280;">'
        'Score guide: &nbsp;'
        '<span class="score-high">🟢 9–10 Hot</span>&nbsp;&nbsp;'
        '<span class="score-mid-high">🟠 7–8 Warm</span>&nbsp;&nbsp;'
        '<span class="score-mid">🟡 5–6 Moderate</span>&nbsp;&nbsp;'
        '<span class="score-low">🔴 1–4 Low Priority</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Download button
    csv_export = df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download Filtered Leads as CSV",
        data=csv_export,
        file_name=f"curato_leads_{date.today().isoformat()}.csv",
        mime="text/csv",
        use_container_width=False,
    )


# ============================================================
# TAB 2 — Analytics
# ============================================================
with tab2:
    st.markdown("### 📊 Lead Analytics")

    if len(df) < 2:
        st.info("Not enough data to render analytics. Adjust your filters to include more leads.")
    else:
        col_a, col_b = st.columns(2)

        # --- Chart 1: Leads by Announcement Type ---
        with col_a:
            type_counts = (
                df.groupby("Announcement Type")
                .agg(Count=("Company Name", "count"), Avg_Score=("Lead Score", "mean"))
                .reset_index()
                .sort_values("Count", ascending=False)
            )
            fig1 = px.bar(
                type_counts,
                x="Announcement Type",
                y="Count",
                color="Avg_Score",
                color_continuous_scale=["#fef3c7", "#f59e0b", "#10b981"],
                title="Leads by Funding Type",
                labels={"Avg_Score": "Avg Score", "Count": "# Leads"},
                text="Count",
            )
            fig1.update_traces(textposition="outside")
            fig1.update_layout(
                coloraxis_colorbar_title="Avg Score",
                plot_bgcolor="white",
                paper_bgcolor="white",
                font_family="Inter, sans-serif",
                title_font_size=16,
                xaxis_tickangle=-30,
                margin=dict(t=50, b=80),
            )
            st.plotly_chart(fig1, use_container_width=True)

        # --- Chart 2: Lead Score Distribution ---
        with col_b:
            fig2 = px.histogram(
                df,
                x="Lead Score",
                nbins=10,
                title="Lead Score Distribution",
                labels={"Lead Score": "Lead Score (1–10)", "count": "# Leads"},
                color_discrete_sequence=["#6366f1"],
                range_x=[0.5, 10.5],
            )
            fig2.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                font_family="Inter, sans-serif",
                title_font_size=16,
                bargap=0.1,
                margin=dict(t=50, b=40),
            )
            fig2.update_traces(marker_line_color="white", marker_line_width=1)
            st.plotly_chart(fig2, use_container_width=True)

        col_c, col_d = st.columns(2)

        # --- Chart 3: Top Industries (horizontal bar) ---
        with col_c:
            industry_counts = (
                df[df["Industry"] != ""]
                .groupby("Industry")
                .size()
                .reset_index(name="Count")
                .sort_values("Count", ascending=True)
                .tail(10)
            )
            if not industry_counts.empty:
                fig3 = px.bar(
                    industry_counts,
                    x="Count",
                    y="Industry",
                    orientation="h",
                    title="Top Industries",
                    labels={"Count": "# Leads"},
                    color="Count",
                    color_continuous_scale=["#e0e7ff", "#6366f1"],
                    text="Count",
                )
                fig3.update_traces(textposition="outside")
                fig3.update_layout(
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    font_family="Inter, sans-serif",
                    title_font_size=16,
                    showlegend=False,
                    coloraxis_showscale=False,
                    margin=dict(t=50, l=10, b=40),
                    yaxis_title="",
                )
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("No industry data available.")

        # --- Chart 4: Lead Volume Over Time ---
        with col_d:
            df_time = df.copy()
            df_time = df_time[df_time["Announcement Date"].notna()]
            if not df_time.empty:
                df_time["Date"] = df_time["Announcement Date"].dt.date
                daily_counts = (
                    df_time.groupby("Date")
                    .size()
                    .reset_index(name="Leads")
                    .sort_values("Date")
                )
                fig4 = px.line(
                    daily_counts,
                    x="Date",
                    y="Leads",
                    title="Lead Volume Over Time",
                    labels={"Date": "Announcement Date", "Leads": "# Leads"},
                    markers=True,
                    line_shape="spline",
                    color_discrete_sequence=["#6366f1"],
                )
                fig4.update_traces(
                    fill="tozeroy",
                    fillcolor="rgba(99,102,241,0.1)",
                    marker_size=8,
                    line_width=2.5,
                )
                fig4.update_layout(
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    font_family="Inter, sans-serif",
                    title_font_size=16,
                    margin=dict(t=50, b=40),
                    xaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                    yaxis=dict(showgrid=True, gridcolor="#f1f5f9"),
                )
                st.plotly_chart(fig4, use_container_width=True)
            else:
                st.info("No date data available for timeline chart.")

        # --- Bonus: Source breakdown pie ---
        st.markdown("---")
        st.markdown("#### 📰 Leads by Source")
        source_counts = (
            df[df["Source Name"] != ""]
            .groupby("Source Name")
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
        )
        if not source_counts.empty:
            fig5 = px.pie(
                source_counts,
                names="Source Name",
                values="Count",
                title="Lead Distribution by Source",
                color_discrete_sequence=PLOTLY_PALETTE,
                hole=0.4,
            )
            fig5.update_traces(textposition="inside", textinfo="percent+label")
            fig5.update_layout(
                font_family="Inter, sans-serif",
                title_font_size=16,
                legend_orientation="h",
                legend_y=-0.2,
                margin=dict(t=60, b=80),
            )
            col_pie, col_spacer = st.columns([1, 1])
            with col_pie:
                st.plotly_chart(fig5, use_container_width=True)


# ============================================================
# TAB 3 — Top Leads
# ============================================================
with tab3:
    st.markdown("### 🏆 Top 10 Leads by Score")
    st.caption("Expand each card to see full details and the Curato pitch for why to reach out.")

    top_leads = df.sort_values("Lead Score", ascending=False).head(10)

    if top_leads.empty:
        st.info("No leads to display. Adjust your filters.")
    else:
        for rank, (_, lead) in enumerate(top_leads.iterrows(), start=1):
            score = int(lead.get("Lead Score", 0))
            company = lead.get("Company Name", "Unknown Company") or "Unknown Company"
            ann_type = lead.get("Announcement Type", "") or ""
            amount = lead.get("Funding/Grant Amount", "") or ""

            # Score emoji
            if score >= 9:
                score_emoji = "🟢"
            elif score >= 7:
                score_emoji = "🟠"
            elif score >= 5:
                score_emoji = "🟡"
            else:
                score_emoji = "🔴"

            header_label = f"#{rank} 🏆 {company} — Score: {score}/10 {score_emoji}"
            if ann_type:
                header_label += f"  |  {ann_type}"
            if amount:
                header_label += f"  |  {amount}"

            with st.expander(header_label, expanded=(rank == 1)):
                why = lead.get("Why This Lead?", "") or ""
                if why:
                    st.info(f"**💡 Why Contact Them?**\n\n{why}")

                st.markdown("---")
                detail_left, detail_right = st.columns(2)

                with detail_left:
                    st.markdown("**Company Details**")
                    details_l = {
                        "🏭 Industry": lead.get("Industry", ""),
                        "📍 Location": lead.get("Location", ""),
                        "🚀 Company Stage": lead.get("Company Stage", ""),
                        "💼 Announcement Type": lead.get("Announcement Type", ""),
                        "💰 Funding Amount": lead.get("Funding/Grant Amount", ""),
                    }
                    for label, value in details_l.items():
                        if value:
                            st.markdown(
                                f'<div style="margin-bottom:0.4rem;">'
                                f'<span style="color:#6b7280;font-size:0.85rem;">{label}</span><br>'
                                f'<span style="color:#1e1e2e;font-weight:500;">{value}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                with detail_right:
                    st.markdown("**Source & Links**")
                    ann_date = lead.get("Announcement Date", "")
                    if hasattr(ann_date, "strftime"):
                        ann_date = ann_date.strftime("%B %d, %Y")

                    details_r = {
                        "📅 Announcement Date": str(ann_date) if ann_date else "",
                        "📰 Source": lead.get("Source Name", ""),
                    }
                    for label, value in details_r.items():
                        if value:
                            st.markdown(
                                f'<div style="margin-bottom:0.4rem;">'
                                f'<span style="color:#6b7280;font-size:0.85rem;">{label}</span><br>'
                                f'<span style="color:#1e1e2e;font-weight:500;">{value}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                    # Links
                    st.markdown("**🔗 Links**")
                    links_html = ""
                    website = lead.get("Website", "") or ""
                    linkedin = lead.get("LinkedIn", "") or ""
                    source_url = lead.get("Source URL", "") or ""

                    if website:
                        links_html += f'<a href="{website}" target="_blank" style="margin-right:12px; color:#6366f1; font-weight:500;">🌐 Website</a>'
                    if linkedin:
                        links_html += f'<a href="{linkedin}" target="_blank" style="margin-right:12px; color:#0077b5; font-weight:500;">💼 LinkedIn</a>'
                    if source_url:
                        links_html += f'<a href="{source_url}" target="_blank" style="color:#374151; font-weight:500;">📰 View Article</a>'

                    if links_html:
                        st.markdown(links_html, unsafe_allow_html=True)
                    else:
                        st.caption("No links available for this lead.")

# ---------------------------------------------------------------------------
# How to Use — collapsible at the bottom
# ---------------------------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("ℹ️ How to use this dashboard"):
    st.markdown(f"""
**How filters work**
- All sidebar filters apply together with AND logic — a lead must match every active filter
- Use the **Search** box to find leads by company name, industry, location, or keyword
- Adjust the **Date Range** to see leads from any time window
- The **Lead Score** slider defaults to 7–10 (high-quality leads only)

**How to refresh data**
- Data is cached for **5 minutes** — the page will auto-update
- Click **🔄 Refresh Data** in the top right to force an immediate reload

**How to run the pipeline manually**
```bash
cd funding-agent
python -m src.pipeline
```
This fetches fresh articles, extracts leads with Gemini AI, deduplicates, scores, and appends to the CSV.

**File being read**
```
{CSV_PATH}
```

**Lead Score guide**
| Score | Meaning | Color |
|-------|---------|-------|
| 9–10 | 🟢 Hot lead — contact immediately | Green |
| 7–8 | 🟠 Warm lead — strong prospect | Orange |
| 5–6 | 🟡 Moderate — worth monitoring | Yellow |
| 1–4 | 🔴 Low priority | Red |

**How to start the dashboard**
```bash
pip install streamlit pandas plotly
streamlit run dashboard.py
```
Then open: **http://localhost:8501**
""")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center; color:#9ca3af; font-size:0.8rem; padding:1rem 0;">'
    "Built for <strong>Curato</strong> — Funding &amp; Grant Intelligence Agent &nbsp;|&nbsp; "
    f"Data: <code>data/leads_output.csv</code> &nbsp;|&nbsp; "
    f"Last checked: {datetime.now().strftime('%H:%M:%S')}"
    "</div>",
    unsafe_allow_html=True,
)
