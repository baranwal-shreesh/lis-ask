"""
LIS Ask — Client UI
app_client.py  v8 — Light / Dark theme toggle
  ✅ Full light mode (white bg, blue + orange accents)
  ✅ Full dark mode  (dark navy bg, same blue + orange accents)
  ✅ Toggle in sidebar — persists across reruns via session_state
  ✅ All 4 previous UI fixes retained
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import logging
import traceback
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ── Initialise step-by-step pipeline logging ───────────────────────────────
try:
    from logging_config import setup_logging
    setup_logging()          # console (INFO) + file (DEBUG) to lis_ask_debug.log
except ImportError:
    logging.basicConfig(
        stream=__import__('sys').stdout,
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(message)s',
        datefmt='%H:%M:%S',
    )

try:
    from enhanced_sql_agent import EnhancedSQLAgent
    import config
except ImportError as e:
    st.error(f"❌ Import error: {str(e)}")
    st.stop()

# =============================================================================
# PAGE CONFIG
# =============================================================================
st.set_page_config(
    page_title="LIS Ask",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CONSTANTS
# =============================================================================
STARTER_DAILY_LIMIT = 50

THINKING_PHRASES = [
    ("🧠", "Thinking really hard...",       "Neurons firing at maximum capacity!"),
    ("🔮", "Consulting the data oracle...", "The crystal ball is warming up..."),
    ("📊", "Crunching the numbers...",      "Math mode activated!"),
    ("🎯", "Aiming for the answer...",      "Bull's eye in sight!"),
    ("🔍", "Digging through the data...",   "Detective mode engaged!"),
    ("💡", "Having a lightbulb moment...",  "Eureka! Almost there..."),
    ("⚡", "Firing up the query engine...", "Power level: 9000!"),
    ("☕", "Brewing your answer...",        "Fresh data coming up!"),
]

# =============================================================================
# THEME PALETTE
# =============================================================================
THEMES = {
    "light": {
        # Backgrounds
        "app_bg"          : "#ffffff",
        "sidebar_bg"      : "#f4f6fb",
        "card_bg"         : "#f8f9fa",
        "blue_tint"       : "#E3F2FD",
        "orange_tint"     : "#FFF3E0",
        "input_bg"        : "#ffffff",
        # Text
        "text_primary"    : "#1a1a2e",
        "text_secondary"  : "#555577",
        "text_muted"      : "#888899",
        # Brand colours
        "blue"            : "#1565C0",
        "blue_mid"        : "#1976D2",
        "blue_border"     : "#90CAF9",
        "orange"          : "#FF6B2B",
        "dark_btn"        : "#1a1a2e",
        "white"           : "#ffffff",
        "border"          : "#e0e5ef",
        # Composite
        "answer_gradient" : "linear-gradient(135deg, #E3F2FD 0%, #ffffff 100%)",
        "progress_track"  : "#e0e5ef",
        "badge_bg"        : "#1565C0",
        "tag_bg"          : "#e8f0fe",
        "tag_text"        : "#1565C0",
    },
    "dark": {
        # Backgrounds
        "app_bg"          : "#0e1117",
        "sidebar_bg"      : "#161b27",
        "card_bg"         : "#1a1f2e",
        "blue_tint"       : "#162044",
        "orange_tint"     : "#2d1a0a",
        "input_bg"        : "#1a1f2e",
        # Text
        "text_primary"    : "#e8eaf6",
        "text_secondary"  : "#9fa8c0",
        "text_muted"      : "#6b728a",
        # Brand colours (slightly lighter blue on dark)
        "blue"            : "#5C9EE8",
        "blue_mid"        : "#4A90D9",
        "blue_border"     : "#2a4a7f",
        "orange"          : "#FF6B2B",
        "dark_btn"        : "#252a3d",
        "white"           : "#e8eaf6",
        "border"          : "#252a3d",
        # Composite
        "answer_gradient" : "linear-gradient(135deg, #162044 0%, #1a1f2e 100%)",
        "progress_track"  : "#252a3d",
        "badge_bg"        : "#1976D2",
        "tag_bg"          : "#162044",
        "tag_text"        : "#5C9EE8",
    },
}

# =============================================================================
# QUICK QUESTIONS
# =============================================================================
CATEGORY_ICONS = {
    "👥 Headcount"      : "👥",
    "📅 Attendance"     : "📅",
    "🏪 Store Coverage" : "🏪",
    "👁️ Paid Visibility": "👁️",
    "📦 MSL / OSA"      : "📦",
    "💰 Sales"          : "💰",
    "📊 Share of Shelf" : "📊",
    "🏷️ Shelf Talker"   : "🏷️",
    "⭐ Visitor Rating" : "⭐",
}

QUICK_QUESTIONS = {
    "👥 Headcount": [
        {"id": "HC-01", "label": "Budgeted vs actual headcount",        "template": "What is my budgeted headcount vs actual headcount for [this month] in [Region: All]?", "schema": "production"},
        {"id": "HC-02", "label": "How many positions are vacant?",       "template": "How many positions are currently vacant in the program in [Region: All]?",            "schema": "production"},
        {"id": "HC-03", "label": "How long have positions been vacant?", "template": "For how long have the vacant positions been unfilled in [Region: All]?",              "schema": "production"},
        {"id": "HC-04", "label": "Actual headcount by region today",     "template": "What is the actual headcount by region today?",                                       "schema": "mvp"},
    ],
    "📅 Attendance": [
        {"id": "ATT-01", "label": "How many were present today?",         "template": "How many merchandisers/promoters were present on [today] in [Region: All]?",                       "schema": "mvp"},
        {"id": "ATT-02", "label": "Who was absent today?",                "template": "Who was absent on [today] in [Region: All]?",                                                     "schema": "mvp"},
        {"id": "ATT-03", "label": "Attendance rate this week",            "template": "What is the attendance rate for [this week] in [Region: All]?",                                   "schema": "mvp"},
        {"id": "ATT-04", "label": "Attendance trend — last 30 days",      "template": "Show me attendance trend for the last [30] days in [Region: All]",                                "schema": "mvp"},
        {"id": "ATT-05", "label": "This month vs last month",             "template": "How many merchandisers were present in [this month] vs [last month] in [Region: All]?",           "schema": "mvp"},
        {"id": "ATT-06", "label": "Absent 3+ consecutive days",           "template": "Which team members have been absent for more than [3] consecutive days in [Region: All]?",        "schema": "mvp"},
        {"id": "ATT-07", "label": "Year-on-year attendance change",       "template": "What is year-on-year change in attendance for [this month] in [Region: All]?",                   "schema": "mvp"},
    ],
    "🏪 Store Coverage": [
        {"id": "COV-01", "label": "How many stores visited today?",       "template": "How many stores were visited on [today] in [Region: All]?",                                       "schema": "mvp"},
        {"id": "COV-02", "label": "Which stores NOT visited? Why?",       "template": "Which stores were not visited on [today] in [Region: All]? What are the reasons?",               "schema": "mvp"},
        {"id": "COV-04", "label": "Store coverage rate this week",        "template": "What is the store coverage rate for [this week] in [Region: All]?",                              "schema": "mvp"},
        {"id": "COV-05", "label": "Coverage trend this month",            "template": "Show store coverage trend for [this month] in [Region: All]",                                    "schema": "mvp"},
        {"id": "COV-07", "label": "Year-on-year coverage change",         "template": "What is year-on-year change in store coverage for [this month] in [Region: All]?",               "schema": "mvp"},
        {"id": "COV-08", "label": "Coverage by store chain / format",     "template": "How many stores were covered by [store chain / store format] on [today]?",                       "schema": "mvp"},
    ],
    "👁️ Paid Visibility": [
        {"id": "PV-01", "label": "Stores with paid visibility today",        "template": "In how many stores is paid visibility available on [today] in [Region: All]?",                 "schema": "production"},
        {"id": "PV-02", "label": "Stores with specific paid asset",          "template": "In how many stores is [Asset Name] available on [today] in [Region: All]?",                   "schema": "production"},
        {"id": "PV-03", "label": "Paid visibility NOT available + reasons",  "template": "In how many stores was paid visibility not available on [today] in [Region: All]? What are the reasons?", "schema": "production"},
        {"id": "PV-04", "label": "Paid visibility purity rate this week",    "template": "What is the paid visibility purity rate for [this week] in [Region: All]?",                   "schema": "production"},
        {"id": "PV-05", "label": "Paid visibility by store chain",           "template": "Show paid visibility availability by [store chain / region] for [this month]",                "schema": "production"},
        {"id": "PV-06", "label": "Free / ad-hoc visibility today",           "template": "How many stores have free / ad-hoc visibility available on [today] in [Region: All]?",        "schema": "production"},
    ],
    "📦 MSL / OSA": [
        {"id": "MSL-01", "label": "Products out of stock today",             "template": "How many products are out of stock on [today] in [Region: All]?",                             "schema": "mvp"},
        {"id": "MSL-02", "label": "Which products are out of stock?",        "template": "Which specific products are out of stock on [today] in [Store: All] in [Region: All]?",       "schema": "mvp"},
        {"id": "MSL-03", "label": "SKUs at low stock (set threshold)",       "template": "How many SKUs have stock less than [X units] on [today] in [Region: All]?",                  "schema": "mvp"},
        {"id": "MSL-04", "label": "MSL / OSA compliance rate",               "template": "What is the MSL/OSA compliance rate for [this week] in [Region: All]?",                      "schema": "mvp"},
        {"id": "MSL-05", "label": "Out-of-stock trend — last 30 days",       "template": "Show out-of-stock trend for the last [30 days] by [product category] in [Region: All]",      "schema": "mvp"},
        {"id": "MSL-06", "label": "Year-on-year OOS change",                 "template": "What is year-on-year change in out-of-stock products for [this month] in [Region: All]?",    "schema": "mvp"},
    ],
    "💰 Sales": [
        {"id": "SAL-01", "label": "Total sales today",                       "template": "What is total sales on [today] in [Region: All]?",                                            "schema": "mvp"},
        {"id": "SAL-02", "label": "Top 5 products sold this week",           "template": "What are the top [5] products sold in [this week] in [Region: All]?",                        "schema": "mvp"},
        {"id": "SAL-03", "label": "Sales by region this month",              "template": "What is total sales by region for [this month]?",                                            "schema": "mvp"},
        {"id": "SAL-04", "label": "Sales trend — last 30 days",              "template": "Show me sales trend for the last [30] days in [Region: All] by [product category / all products]", "schema": "mvp"},
        {"id": "SAL-05", "label": "Year-on-year sales growth / fall",        "template": "What is year-on-year growth/fall in sales for [this month] in [Region: All] for [product category / all]?", "schema": "mvp"},
        {"id": "SAL-06", "label": "Selling price adherence",                 "template": "What is the selling price adherence for [all products / specific product] in [this week] in [Region: All]?", "schema": "production"},
        {"id": "SAL-07", "label": "Compare sales across store chains",       "template": "Compare sales across [store chains / regions] for [this quarter / this month]",              "schema": "mvp"},
        {"id": "SAL-08", "label": "Sales by product category",               "template": "What is total sales by product category for [this month] in [Region: All]?",                "schema": "mvp"},
    ],
    "📊 Share of Shelf": [
        {"id": "SOS-01", "label": "Share of shelf this week",                "template": "What is our share of shelf for [this week] in [Region: All]?",                               "schema": "production"},
        {"id": "SOS-02", "label": "Share of shelf by store chain",           "template": "How does our share of shelf compare across [store chains] for [this month]?",               "schema": "production"},
        {"id": "SOS-03", "label": "Year-on-year share of shelf change",      "template": "What is year-on-year change in share of shelf for [this month] in [Region: All]?",          "schema": "production"},
    ],
    "🏷️ Shelf Talker": [
        {"id": "ST-01", "label": "Stores with shelf talkers today",          "template": "In how many stores are shelf talkers present on [today] in [Region: All]?",                  "schema": "production"},
        {"id": "ST-02", "label": "Shelf talker compliance rate",             "template": "What is shelf talker compliance rate for [this week] in [Region: All]?",                     "schema": "production"},
    ],
    "⭐ Visitor Rating": [
        {"id": "VR-01", "label": "Average visitor rating this week",         "template": "What is the average visitor rating for [this week] in [Region: All]?",                       "schema": "production"},
        {"id": "VR-02", "label": "Stores with lowest visitor ratings",       "template": "Which stores have the lowest visitor ratings in [this month] in [Region: All]?",            "schema": "production"},
    ],
}

# =============================================================================
# CSS — theme-aware (generated from THEMES dict)
# =============================================================================
def inject_css(t: dict):
    """Inject full CSS using the active theme palette dict `t`."""
    st.markdown(f"""
    <style>

    /* ── FORCE APP BACKGROUND ────────────────────────────────────────── */
    .stApp,
    [data-testid="stApp"],
    [data-testid="stMain"],
    section.main {{
        background-color: {t["app_bg"]} !important;
        color: {t["text_primary"]} !important;
    }}

    /* ── SIDEBAR ─────────────────────────────────────────────────────── */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div {{
        background-color: {t["sidebar_bg"]} !important;
        border-right: 1px solid {t["border"]} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {t["text_primary"]} !important;
    }}

    /* ── INPUTS ──────────────────────────────────────────────────────── */
    .stTextArea textarea,
    .stTextInput input {{
        background-color: {t["input_bg"]} !important;
        color: {t["text_primary"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 8px !important;
    }}
    .stTextArea textarea:focus,
    .stTextInput input:focus {{
        border-color: {t["blue"]} !important;
        box-shadow: 0 0 0 2px {t["blue_tint"]} !important;
    }}

    /* ── DATAFRAME ───────────────────────────────────────────────────── */
    [data-testid="stDataFrame"],
    .stDataFrame {{
        background-color: {t["card_bg"]} !important;
        border: 1px solid {t["border"]} !important;
        border-radius: 8px;
    }}
    [data-testid="stDataFrame"] th {{
        background-color: {t["blue_tint"]} !important;
        color: {t["blue"]} !important;
        font-weight: 700;
    }}
    [data-testid="stDataFrame"] td {{
        color: {t["text_primary"]} !important;
    }}

    /* ── TABS: base ──────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
        background-color: transparent;
        border-bottom: 2px solid {t["blue"]};
    }}
    .stTabs [data-baseweb="tab"] {{
        background-color: {t["blue_tint"]};
        color: {t["blue"]};
        border-radius: 8px 8px 0 0;
        padding: 8px 14px;
        font-size: 18px;
        border: 1px solid {t["blue_border"]};
        border-bottom: none;
        transition: background-color 0.15s ease, color 0.15s ease;
        cursor: pointer;
    }}

    /* ── TABS: hover → orange + white ───────────────────────────────── */
    .stTabs [data-baseweb="tab"]:hover {{
        background-color: {t["orange"]} !important;
        color: #ffffff !important;
        border-color: {t["orange"]} !important;
    }}

    /* ── TABS: selected → orange + white ────────────────────────────── */
    .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        background-color: {t["orange"]} !important;
        color: #ffffff !important;
        border-color: {t["orange"]} !important;
        font-weight: 600;
    }}
    .stTabs [data-baseweb="tab-panel"] {{
        padding-top: 14px;
        background-color: {t["app_bg"]} !important;
    }}

    /* ── EXPANDERS: always visible ───────────────────────────────────── */
    [data-testid="stExpander"] > details > summary {{
        background-color: {t["blue_tint"]} !important;
        color: {t["blue"]} !important;
        border-radius: 8px;
        padding: 10px 14px;
        font-weight: 600;
        font-size: 14px;
        border: 1px solid {t["blue_border"]} !important;
        cursor: pointer;
        transition: background-color 0.15s ease;
    }}
    [data-testid="stExpander"] > details > summary:hover {{
        background-color: {t["orange_tint"]} !important;
        color: {t["orange"]} !important;
        border-color: {t["orange"]} !important;
    }}
    [data-testid="stExpander"] > details[open] > summary {{
        background-color: {t["orange_tint"]} !important;
        color: {t["orange"]} !important;
        border-color: {t["orange"]} !important;
        border-radius: 8px 8px 0 0;
    }}
    [data-testid="stExpander"] > details > summary::marker,
    [data-testid="stExpander"] > details > summary::-webkit-details-marker {{
        color: {t["blue"]} !important;
    }}
    [data-testid="stExpander"] > details {{
        border: 1px solid {t["blue_border"]} !important;
        border-radius: 8px;
        overflow: hidden;
        background-color: {t["card_bg"]} !important;
    }}

    /* ── QUICK QUESTION BUTTONS ──────────────────────────────────────── */
    div[data-testid="stHorizontalBlock"] .stButton > button {{
        background-color: {t["dark_btn"]};
        color: #ffffff;
        border: none;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 13px;
        text-align: left;
        transition: background-color 0.15s ease, transform 0.1s ease;
        width: 100%;
    }}
    div[data-testid="stHorizontalBlock"] .stButton > button:hover {{
        background-color: {t["orange"]} !important;
        color: #ffffff !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255,107,43,0.3);
    }}

    /* ── ANSWER BLOCK ────────────────────────────────────────────────── */
    .answer-block {{
        background: {t["answer_gradient"]};
        border-left: 4px solid {t["orange"]};
        border-radius: 0 8px 8px 0;
        padding: 18px 22px;
        margin: 10px 0;
        font-size: 15px;
        line-height: 1.75;
        color: {t["text_primary"]};
    }}

    /* ── METADATA BADGES ─────────────────────────────────────────────── */
    .meta-row {{ margin: 8px 0 14px 0; }}
    .meta-badge {{
        display: inline-block;
        background-color: {t["badge_bg"]};
        color: #ffffff;
        border-radius: 20px;
        padding: 3px 12px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 6px;
    }}
    .meta-badge.green {{ background-color: #2e7d32; }}

    /* ── CATEGORY LABEL ──────────────────────────────────────────────── */
    .qq-cat-label {{
        font-size: 12px;
        font-weight: 700;
        color: {t["blue"]};
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 10px;
        border-bottom: 2px solid {t["blue_tint"]};
        padding-bottom: 6px;
    }}

    /* ── SIDEBAR SECTION TITLE ───────────────────────────────────────── */
    .sidebar-section-title {{
        font-size: 10px;
        font-weight: 700;
        color: {t["blue"]};
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin: 16px 0 6px 0;
    }}

    /* ── CODE BLOCK ──────────────────────────────────────────────────── */
    [data-testid="stCode"] {{
        border-radius: 8px;
        border: 1px solid {t["border"]};
    }}

    /* ── DIVIDERS ────────────────────────────────────────────────────── */
    hr {{
        border-color: {t["border"]} !important;
    }}

    /* ── GENERAL TEXT ────────────────────────────────────────────────── */
    p, li, span, label {{
        color: {t["text_primary"]};
    }}

    </style>
    """, unsafe_allow_html=True)


# =============================================================================
# SESSION STATE
# =============================================================================
def init_session_state():
    defaults = {
        "daily_prompt_count": 0,
        "prompt_date"       : datetime.now().date(),
        "last_result"       : None,
        "query_history"     : [],
        "username"          : "",
        "user_prompt_input" : "",
        "theme"             : "light",   # ← default to light for presentation
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_daily_count_if_new_day():
    today = datetime.now().date()
    if st.session_state.prompt_date != today:
        st.session_state.daily_prompt_count = 0
        st.session_state.prompt_date = today


def get_theme() -> dict:
    return THEMES[st.session_state.get("theme", "light")]


# =============================================================================
# AGENT  (cached — initialised once per session)
# =============================================================================
@st.cache_resource
def get_agent():
    try:
        agent = EnhancedSQLAgent(
            db_path            = config.DB_PATH,
            schema_config_path = config.SCHEMA_CONFIG_PATH,
        )
        # ── Monkey-patch with full pipeline logging ──────────────────────────
        try:
            import types
            from enhanced_sql_agent_patch import _patched_process_query, _patched_init
            agent.process_query = types.MethodType(_patched_process_query, agent)
            logger.info("✅ Pipeline logging patch applied to EnhancedSQLAgent")
        except ImportError:
            logger.warning("enhanced_sql_agent_patch.py not found — using original process_query")
        return agent, None
    except Exception as e:
        return None, str(e)


# =============================================================================
# CALLBACKS
# =============================================================================
def select_quick_question(template: str):
    st.session_state["user_prompt_input"] = template


# =============================================================================
# THINKING ANIMATION
# =============================================================================
def show_thinking_animation():
    t = get_theme()
    emoji, phrase, subtitle = random.choice(THINKING_PHRASES)
    ph = st.empty()
    pb = st.progress(0)
    for i in range(100):
        pb.progress(i + 1)
        time.sleep(0.008)
    ph.markdown(
        f"""<div style="background:{t['answer_gradient']};
            border-left:4px solid {t['orange']};
            border-radius:0 8px 8px 0;padding:16px 20px;
            font-size:15px;color:{t['text_primary']};">
            {emoji} <strong>{phrase}</strong><br>
            <span style="font-size:13px;color:{t['text_muted']};">{subtitle}</span>
        </div>""",
        unsafe_allow_html=True,
    )
    pb.empty()
    return ph


# =============================================================================
# SIDEBAR
# =============================================================================
def render_sidebar():
    t = get_theme()
    with st.sidebar:

        # ── Brand ──────────────────────────────────────────────────────────
        st.markdown(
            f"""<div style="text-align:center;padding:10px 0 20px 0;">
               <span style="font-size:32px;">💬</span><br>
               <span style="font-size:20px;font-weight:700;color:{t['blue']};">LIS Ask</span><br>
               <span style="font-size:11px;color:{t['text_muted']};">Powered by AI</span>
            </div>""",
            unsafe_allow_html=True,
        )

        # ── Theme toggle ───────────────────────────────────────────────────
        is_dark = st.session_state.theme == "dark"
        toggle_label = "🌙  Dark mode" if not is_dark else "☀️  Light mode"
        if st.button(toggle_label, use_container_width=True, key="theme_toggle"):
            st.session_state.theme = "dark" if not is_dark else "light"
            st.rerun()

        st.divider()

        # ── Username ───────────────────────────────────────────────────────
        st.markdown('<p class="sidebar-section-title">YOUR NAME</p>', unsafe_allow_html=True)
        username = st.text_input(
            "un",
            label_visibility="collapsed",
            placeholder="Enter your name...",
            key="username_input",
        )
        if username:
            st.session_state.username = username

        st.divider()

        # ── Daily query bar ────────────────────────────────────────────────
        st.markdown('<p class="sidebar-section-title">DAILY QUERIES</p>', unsafe_allow_html=True)
        used  = st.session_state.daily_prompt_count
        limit = STARTER_DAILY_LIMIT
        pct   = min(int(used / limit * 100), 100)
        bar_color = t["blue"] if pct < 80 else "#c62828"
        st.markdown(
            f"""<div style="margin-bottom:8px;">
                <div style="background:{t['progress_track']};border-radius:10px;height:8px;">
                  <div style="background:{bar_color};width:{pct}%;height:8px;
                              border-radius:10px;transition:width 0.3s;"></div>
                </div>
                <p style="font-size:12px;color:{t['text_muted']};margin-top:4px;">
                  {used} / {limit} queries used today
                </p>
            </div>""",
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Query history ──────────────────────────────────────────────────
        st.markdown('<p class="sidebar-section-title">QUERY HISTORY</p>', unsafe_allow_html=True)
        if not st.session_state.query_history:
            st.markdown(
                f'<p style="font-size:12px;color:{t["text_muted"]};font-style:italic;">No queries yet</p>',
                unsafe_allow_html=True,
            )
        else:
            for i, item in enumerate(reversed(st.session_state.query_history[-8:])):
                q_short = item["query"][:42] + "…" if len(item["query"]) > 42 else item["query"]
                ts      = item.get("timestamp", "")
                if st.button(q_short, key=f"hist_{i}", help=f"Re-run: {item['query']}"):
                    st.session_state["user_prompt_input"] = item["query"]
                    st.rerun()
                st.markdown(
                    f'<p style="font-size:10px;color:{t["text_muted"]};margin:-8px 0 6px 4px;">{ts}</p>',
                    unsafe_allow_html=True,
                )


# =============================================================================
# QUICK QUESTIONS  ── collapsible section (Fix #1)
# =============================================================================
def render_quick_questions():
    t = get_theme()
    with st.expander("💡 Most Asked Questions", expanded=True):
        st.caption("Select a question to pre-fill the prompt — edit any **[placeholder]** before submitting.")

        category_names = list(QUICK_QUESTIONS.keys())
        tab_labels     = [CATEGORY_ICONS.get(n, "❓") for n in category_names]
        tabs           = st.tabs(tab_labels)

        for tab, cat_name in zip(tabs, category_names):
            with tab:
                questions = QUICK_QUESTIONS[cat_name]
                live_qs   = [q for q in questions if q.get("schema") == "mvp"]
                locked_qs = [q for q in questions if q.get("schema") == "production"]

                st.markdown(
                    f'<p class="qq-cat-label">{cat_name}</p>',
                    unsafe_allow_html=True,
                )

                if live_qs:
                    cols = st.columns(2)
                    for idx, q in enumerate(live_qs):
                        with cols[idx % 2]:
                            if st.button(
                                f"→ {q['label']}",
                                key=f"qq_{q['id']}",
                                help=q["template"],
                                use_container_width=True,
                            ):
                                select_quick_question(q["template"])
                                st.rerun()
                else:
                    st.markdown(
                        f'<p style="color:{t["text_muted"]};font-size:13px;font-style:italic;">'
                        "All questions in this category require the production data module.</p>",
                        unsafe_allow_html=True,
                    )

                if locked_qs:
                    n = len(locked_qs)
                    with st.expander(
                        f"🔒 Coming in Production — {n} question{'s' if n > 1 else ''} available",
                        expanded=False,
                    ):
                        st.markdown(
                            f'<p style="color:{t["text_muted"]};font-size:12px;font-style:italic;">'
                            "These will activate once the corresponding data module is live.</p>",
                            unsafe_allow_html=True,
                        )
                        lcols = st.columns(2)
                        for idx, q in enumerate(locked_qs):
                            with lcols[idx % 2]:
                                st.markdown(
                                    f"""<div style="background:{t['card_bg']};color:{t['text_muted']};
                                        border:1px solid {t['border']};border-radius:8px;
                                        padding:10px 14px;font-size:12px;margin-bottom:6px;
                                        cursor:not-allowed;opacity:0.6;">
                                        🔒 {q["label"]}
                                    </div>""",
                                    unsafe_allow_html=True,
                                )


# =============================================================================
# RESULT RENDERER
# =============================================================================
def render_result(result: Dict[str, Any]):
    if not result:
        return
    t = get_theme()

    # ── Answer ────────────────────────────────────────────────────────────────
    nl_response = result.get("response", {}) or {}   # agent returns key "response"
    main_answer = nl_response.get("main_answer", "Query executed successfully.")
    st.markdown(
        f'<div class="answer-block">{main_answer}</div>',
        unsafe_allow_html=True,
    )

    for ins in (nl_response.get("insights", []) or []):
        st.markdown(
            f'<p style="color:{t["blue"]};font-size:13px;margin:4px 0;">💡 {ins}</p>',
            unsafe_allow_html=True,
        )

    # ── Metadata badges (native Streamlit — avoids stray </div> rendering) ─────
    metadata  = result.get("metadata", {}) or {}
    exec_secs = float(metadata.get("execution_time", 0) or 0)
    exec_ms   = exec_secs * 1000 if exec_secs < 1000 else exec_secs
    cached    = bool(metadata.get("cached", False))
    data_obj  = result.get("data", {}) or {}
    row_count = int(data_obj.get("row_count", 0)) if isinstance(data_obj, dict) else 0

    _badge_style = (
        f"display:inline-block;background:{t['badge_bg']};color:#fff;"
        "border-radius:20px;padding:3px 12px;font-size:12px;font-weight:600;"
        "margin-right:6px;"
    )
    _badge_html = (
        f'<span style="{_badge_style}">{exec_ms:.0f} ms</span>'
        f'<span style="{_badge_style}">{row_count} rows</span>'
    )
    if cached:
        _badge_html += (
            '<span style="display:inline-block;background:#2e7d32;color:#fff;' 
            'border-radius:20px;padding:3px 12px;font-size:12px;font-weight:600;">'
            '⚡ Cached</span>'
        )
    st.markdown(_badge_html, unsafe_allow_html=True)

    # ── SQL (Fix #2 — st.code, no stray </div>) ───────────────────────────────
    sql_query = result.get("sql_query", "")
    if sql_query:
        with st.expander("🔍 View generated SQL", expanded=False):
            st.code(sql_query, language="sql")

    # ── Recommendations ───────────────────────────────────────────────────────
    recs = nl_response.get("recommendations", []) or []
    if recs:
        with st.expander("💡 Recommendations", expanded=False):
            for rec in recs:
                st.markdown(f"• {rec}")

    # ── Chart ─────────────────────────────────────────────────────────────────
    chart = result.get("chart")
    if chart:
        try:
            st.plotly_chart(chart, use_container_width=True)
        except Exception:
            pass

    # ── Data table ────────────────────────────────────────────────────────────
    if isinstance(data_obj, dict):
        rows    = data_obj.get("data", [])
        columns = data_obj.get("columns", [])
        if rows and columns:
            df = pd.DataFrame(rows, columns=columns)
            st.dataframe(df, use_container_width=True, hide_index=True)


# =============================================================================
# MAIN
# =============================================================================
def main():
    init_session_state()
    reset_daily_count_if_new_day()

    t = get_theme()
    inject_css(t)         # must be after init so theme state exists

    render_sidebar()

    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        f"""<div style="padding:10px 0 20px 0;">
           <h1 style="font-size:28px;font-weight:700;color:{t['blue']};margin:0;">
               💬 LIS Ask
           </h1>
           <p style="color:{t['text_muted']};font-size:14px;margin:4px 0 0 0;">
               Ask anything about your field operations in plain English.
           </p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Most Asked Questions ─────────────────────────────────────────────────
    render_quick_questions()

    st.markdown("---")

    # ── Prompt input ──────────────────────────────────────────────────────────
    st.markdown(f"#### ✏️ Your Question")
    col_input, col_btn = st.columns([5, 1])

    with col_input:
        user_query = st.text_area(
            "query_input",
            label_visibility="collapsed",
            placeholder="e.g. How many promoters were present today in the North region?",
            height=90,
            key="user_prompt_input",
        )

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        ask_clicked = st.button(
            "Ask →",
            type="primary",
            use_container_width=True,
            disabled=(st.session_state.daily_prompt_count >= STARTER_DAILY_LIMIT),
        )

    if st.session_state.daily_prompt_count >= STARTER_DAILY_LIMIT:
        st.warning(f"⚠️ Daily limit of {STARTER_DAILY_LIMIT} queries reached. Resets at midnight.")

    # ── Process ───────────────────────────────────────────────────────────────
    if ask_clicked and user_query.strip():
        agent, agent_err = get_agent()
        if agent_err:
            st.error(f"❌ Agent initialisation failed: {agent_err}")
            return

        anim_ph = show_thinking_animation()
        try:
            result  = agent.process_query(user_query.strip())
            anim_ph.empty()

            st.session_state.last_result          = result
            st.session_state.daily_prompt_count  += 1
            st.session_state.query_history.append({
                "query"    : user_query.strip(),
                "timestamp": datetime.now().strftime("%d %b, %H:%M"),
            })
        except Exception as e:
            anim_ph.empty()
            logger.error(f"Query failed: {e}\n{traceback.format_exc()}")
            st.error(f"❌ Something went wrong: {str(e)}")
            return

    # ── Show result ───────────────────────────────────────────────────────────
    if st.session_state.last_result:
        st.markdown("---")
        st.markdown(f"#### 📋 Answer")
        render_result(st.session_state.last_result)


if __name__ == "__main__":
    main()
