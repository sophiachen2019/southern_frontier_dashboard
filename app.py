import os
import json
import re
from datetime import datetime, timedelta
from html import escape
import altair as alt
import base64
import pandas as pd
import streamlit as st
import psycopg2
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")
BRAND_LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "logo.png")
SOUTHERN_FRONTIER_WEBSITE_URL = os.getenv("SOUTHERN_FRONTIER_WEBSITE_URL", "https://southernfrontiertea.com")
WEBSITE_LINKS = {
    "Brand Story": f"{SOUTHERN_FRONTIER_WEBSITE_URL}#brand",
    "Discover Pu'er": f"{SOUTHERN_FRONTIER_WEBSITE_URL}#culture",
    "Products": f"{SOUTHERN_FRONTIER_WEBSITE_URL}#products",
    "Flagship Store": f"{SOUTHERN_FRONTIER_WEBSITE_URL}#store",
    "Partnership": f"{SOUTHERN_FRONTIER_WEBSITE_URL}#partner",
}
ADJACENT_TREND_KEYWORDS = {"matcha", "specialty coffee", "puer (benchmark)", "boba tea", "kombucha"}
PUER_TREND_KEYWORDS = {"puer", "puerh", "pu'er", "pu-erh", "pu erh"}

CAFE_EXPERIENCE_COMPETITORS = [
    {
        "Competitor": "Blue Bottle",
        "Category": "Specialty coffee",
        "Why It Matters": "Premium daily ritual, minimalist design, strong quality cues.",
        "What To Track": "Menu architecture, store design, price ladder, subscription bridge.",
        "Southern Frontier Question": "Can Pu'er occupy a calm, slower alternative to premium coffee?",
    },
    {
        "Competitor": "% Arabica",
        "Category": "Design-led coffee",
        "Why It Matters": "Global cafe-as-brand-world model with visual consistency.",
        "What To Track": "Store footprint, signature drink simplicity, social-media visual codes.",
        "Southern Frontier Question": "What is the visual system for modern Asian premium beverage ritual?",
    },
    {
        "Competitor": "Asha Tea House",
        "Category": "Modern tea cafe",
        "Why It Matters": "Tea-forward cafe format with approachable premium drinks.",
        "What To Track": "Pure tea vs milk tea mix, education burden, cafe-to-home conversion.",
        "Southern Frontier Question": "How much education can a US tea cafe carry without slowing conversion?",
    },
    {
        "Competitor": "Boba Guys",
        "Category": "Premium milk tea",
        "Why It Matters": "Made Asian tea drinks accessible to mainstream US consumers.",
        "What To Track": "Drink naming, flavor ladder, brand tone, ingredient proof.",
        "Southern Frontier Question": "Can Pu'er be introduced through a delicious signature drink first?",
    },
    {
        "Competitor": "Chicha San Chen",
        "Category": "Premium brewed tea drinks",
        "Why It Matters": "Strong tea craft theater with modern retail execution.",
        "What To Track": "Brewing visibility, freshness claims, origin language, queue flow.",
        "Southern Frontier Question": "Should brewing theater be visible in the US flagship experience?",
    },
    {
        "Competitor": "HeyTea",
        "Category": "Modern Chinese tea drinks",
        "Why It Matters": "Turns tea into a lifestyle beverage and social object.",
        "What To Track": "Signature SKUs, seasonal drops, visual merchandising, creator buzz.",
        "Southern Frontier Question": "Where is the line between modern accessibility and losing Pu'er seriousness?",
    },
    {
        "Competitor": "Matcha cafes",
        "Category": "Ritual wellness cafe",
        "Why It Matters": "Closest behavior bridge for ceremonial prep, aesthetics, and daily ritual.",
        "What To Track": "Ritual cues, latte formats, wellness language, entry-level education.",
        "Southern Frontier Question": "Can Pu'er become the next premium ritual drink after matcha?",
    },
]

st.set_page_config(page_title="Southern Frontier Dashboard", layout="wide", page_icon="🍵")

st.markdown("""
<style>
    .stApp { background-color: #FAF8F4; color: #1A1A1A; font-size: 16.5px; }
    .reportview-container { background-color: #FAF8F4; color: #1A1A1A; font-family: 'Inter', sans-serif; font-size: 16.5px; }
    
    /* Streamlit Global Typography Overrides */
    .stMarkdown p, .stMarkdown li { font-size: 1.1rem !important; line-height: 1.68; color: #2C302C; }
    .stMarkdown h1 { font-size: 2.2rem !important; font-weight: 750; color: #1A1A1A; }
    .stMarkdown h2 { font-size: 1.7rem !important; font-weight: 720; color: #1A1A1A; }
    .stMarkdown h3 { font-size: 1.35rem !important; font-weight: 680; color: #1A1A1A; }
    .stMarkdown h4 { font-size: 1.18rem !important; font-weight: 650; color: #1A1A1A; }
    
    /* Tabs & Controls */
    button[data-baseweb="tab"] p, button[data-baseweb="tab"] div { font-size: 1.08rem !important; font-weight: 600; }
    [data-testid="stCaptionContainer"], .stCaption { font-size: 0.96rem !important; line-height: 1.55; color: #6E6258 !important; }
    [data-testid="stMetricValue"] { font-size: 2.1rem !important; }
    [data-testid="stMetricLabel"] { font-size: 1.05rem !important; }
    [data-testid="stExpander"] { font-size: 1.05rem !important; }

    /* Custom Component Cards & Metrics */
    .metric-card { background: white; padding: 26px 28px; border-radius: 8px; box-shadow: 0 4px 20px rgba(160,68,45,0.08); border-left: 4px solid #A0442D; margin-bottom: 18px; }
    .metric-angle { font-size: 0.98rem; text-transform: uppercase; letter-spacing: 1.5px; color: #666; margin-bottom: 8px; font-weight: 600; }
    .metric-h1 { font-size: 2.1rem; font-weight: 700; color: #1A1A1A; margin-bottom: 6px; line-height: 1.25; }
    .metric-h2 { font-size: 1.35rem; font-weight: 400; color: #4A4A4A; margin-bottom: 16px; line-height: 1.4; }
    .metric-rationale { font-size: 1.05rem; color: #4A4A4A; font-style: italic; padding-top: 14px; border-top: 1px solid #EEE; line-height: 1.6; }
    .title-text { font-family: 'Playfair Display', serif; color: #1A1A1A; }
    
    /* Narrative Story Cards */
    .story-card { background: #FFFFFF; border: 1px solid #E7E3DA; border-radius: 8px; padding: 24px 26px; margin: 16px 0 20px; }
    .story-label { color: #A0442D; font-size: 0.86rem; font-weight: 750; text-transform: uppercase; letter-spacing: 1.3px; margin-bottom: 8px; }
    .story-title { color: #1A1A1A; font-size: 1.32rem; font-weight: 750; margin-bottom: 10px; line-height: 1.35; }
    
    /* SF Wrap Table for Adjustable Wrapping Tables */
    .sf-wrap-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
        background-color: white;
        border-radius: 4px;
        overflow: hidden;
    }
    .sf-wrap-table th, .sf-wrap-table td {
        text-align: left;
        padding: 10px 14px;
        border-bottom: 1px solid rgba(0,0,0,0.08);
        word-wrap: break-word;
        white-space: normal;
    }
    .sf-wrap-table th {
        background-color: rgba(0,0,0,0.03);
        font-weight: 600;
        color: #444;
        resize: horizontal;
        overflow: auto;
        min-width: 80px;
    }
    .story-body { color: #323632; font-size: 1.12rem; line-height: 1.68; margin-bottom: 14px; }
    .story-rationale { color: #555B56; font-size: 1.02rem; line-height: 1.6; border-top: 1px solid #EEE9DF; padding-top: 12px; }
    
    /* Callouts, Pills & Badges */
    .callout { background: #F2F1EF; border-left: 4px solid #A0442D; border-radius: 6px; padding: 16px 20px; color: #2F332F; line-height: 1.62; font-size: 1.08rem; margin: 12px 0 18px; }
    .evidence-pill { display: inline-block; background: #FFFDF7; color: #A0442D; border: 1px solid #E8D4A4; border-radius: 999px; padding: 5px 12px; margin: 3px 5px 3px 0; font-size: 0.92rem; font-weight: 500; }
    
    /* Brand Philosophy Banner */
    .brand-panel { background: #1A1A1A; color: #FAF8F4; border-radius: 8px; padding: 30px 32px; margin: 20px 0 24px; border-top: 4px solid #A0442D; }
    .brand-kicker { color: #D9BD7E; font-size: 0.86rem; font-weight: 750; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 10px; }
    .brand-title { font-size: 1.65rem; font-weight: 760; line-height: 1.3; margin-bottom: 12px; }
    .brand-body { color: #EEE9DF; font-size: 1.12rem; line-height: 1.68; max-width: 960px; }
    .brand-values { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }
    .brand-value { border: 1px solid rgba(217,189,126,0.55); border-radius: 999px; padding: 7px 14px; color: #FFF9EC; font-size: 0.95rem; }
    .brand-philosophy { color: #D9BD7E; font-size: 1.22rem; font-weight: 760; margin-top: 20px; }
    
    /* Executive Briefing Grid */
    .brief-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 16px 0 20px; }
    .brief-cell { background: #FFFFFF; border: 1px solid #E7E3DA; border-radius: 8px; padding: 15px 16px; min-height: 136px; }
    .brief-label { color: #A0442D; font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 8px; }
    .brief-text { color: #2D322E; font-size: 1.02rem; line-height: 1.5; }
    
    /* Header & Meta Notes */
    .sf-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 8px 0 14px; border-bottom: 1px solid #E9E1D2; margin-bottom: 20px; }
    .sf-logo-wrap { background: #FFFFFF; border: 1px solid #E9E1D2; border-radius: 8px; padding: 10px 14px; width: fit-content; }
    .sf-eyebrow { color: #A0442D; text-transform: uppercase; letter-spacing: 0.22em; font-size: 0.82rem; font-weight: 800; margin-bottom: 4px; }
    .small-muted { color: #60574F; font-size: 0.98rem; line-height: 1.55; }
    .source-note { color: #60574F; font-size: 0.94rem; line-height: 1.55; margin: 4px 0 14px; }
    
    @media (max-width: 1100px) { .brief-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 680px) { .brief-grid { grid-template-columns: 1fr; } }
</style>
""", unsafe_allow_html=True)

class ValueProp(BaseModel):
    angle: str = Field(description="The Angle")
    headline: str = Field(description="H1 Headline")
    sub_headline: str = Field(description="H2 Sub-headline")
    rationale: str = Field(description="The Data Rationale")
    evidence_refs: list[str] = Field(default_factory=list, description="Source IDs that support this copy")

class ValuePropResponse(BaseModel):
    value_props: list[ValueProp]

def get_db_connection():
    return psycopg2.connect(NEON_DB_CONNECTION_STRING)


def get_data_freshness():
    """Query MAX(timestamp) from each key table to show data freshness."""
    tables = {
        "Consumer Signals": ("friction_data", "timestamp"),
        "Google Trends": ("google_trends_data", "date"),
        "Ecommerce Competitors": ("competitor_products", "timestamp"),
        "Metro Demographics": ("metro_demographics", "collected_at"),
        "Cafe Competitors": ("cafe_competitors", "collected_at"),
        "Cafe Signals": ("cafe_retail_signals", "collected_at"),
        "Experiments": ("gtm_experiments", "created_at"),
    }
    freshness = {}
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for label, (table, col) in tables.items():
            try:
                cur.execute(f"SELECT MAX({col}) FROM {table}")
                result = cur.fetchone()
                freshness[label] = result[0] if result and result[0] else None
            except Exception:
                conn.rollback()
                freshness[label] = None
        cur.close()
    finally:
        conn.close()
    return freshness


@st.cache_data(ttl=300)
def load_data():
    conn = get_db_connection()
    try:
        query = "SELECT * FROM friction_data ORDER BY timestamp ASC"
        df = pd.read_sql(query, conn)
    finally:
        conn.close()
    return df

@st.cache_data(ttl=300)
def load_trends_data():
    conn = get_db_connection()
    try:
        df = pd.read_sql("SELECT * FROM google_trends_data ORDER BY date ASC", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data(ttl=300)
def load_competitor_data():
    conn = get_db_connection()
    try:
        try:
            df = pd.read_sql("SELECT * FROM competitor_products ORDER BY timestamp ASC", conn)
        except Exception:
            df = pd.read_sql("SELECT * FROM competitor_products", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


@st.cache_data(ttl=300)
def load_demographics_data():
    conn = get_db_connection()
    try:
        df = pd.read_sql("SELECT * FROM metro_demographics", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


@st.cache_data(ttl=300)
def load_cafe_competitor_data():
    conn = get_db_connection()
    try:
        df = pd.read_sql("SELECT * FROM cafe_competitors ORDER BY overall_positioning_score DESC NULLS LAST", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


@st.cache_data(ttl=300)
def load_cafe_signal_data():
    conn = get_db_connection()
    try:
        df = pd.read_sql("SELECT * FROM cafe_retail_signals ORDER BY collected_at DESC", conn)
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()
    return df


def setup_experiment_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gtm_experiments (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            hypothesis TEXT,
            segment TEXT,
            channel TEXT,
            creative_angle TEXT,
            success_metric TEXT,
            status VARCHAR(40) DEFAULT 'planned',
            result_notes TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def load_experiments():
    try:
        setup_experiment_table()
        conn = get_db_connection()
        try:
            return pd.read_sql("SELECT * FROM gtm_experiments ORDER BY created_at DESC", conn)
        finally:
            conn.close()
    except Exception:
        return pd.DataFrame()


def save_experiment(hypothesis, segment, channel, creative_angle, success_metric, status, result_notes):
    setup_experiment_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO gtm_experiments
        (hypothesis, segment, channel, creative_angle, success_metric, status, result_notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (hypothesis, segment, channel, creative_angle, success_metric, status, result_notes),
    )
    conn.commit()
    cur.close()
    conn.close()


def update_experiment(exp_id, status, result_notes):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE gtm_experiments SET status = %s, result_notes = %s WHERE id = %s",
        (status, result_notes, int(exp_id)),
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_experiment(exp_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM gtm_experiments WHERE id = %s", (int(exp_id),))
    conn.commit()
    cur.close()
    conn.close()


def setup_value_props_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS generated_value_props (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            value_props_json TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def save_value_props(value_props):
    setup_value_props_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO generated_value_props (value_props_json) VALUES (%s)",
        (json.dumps(value_props),),
    )
    conn.commit()
    cur.close()
    conn.close()


def load_latest_value_props():
    try:
        setup_value_props_table()
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT value_props_json, created_at FROM generated_value_props ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            cur.close()
            if row:
                return json.loads(row[0]), row[1]
        finally:
            conn.close()
    except Exception:
        pass
    return None, None


def setup_decisions_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gtm_decisions (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decision TEXT,
            based_on TEXT,
            owner TEXT,
            status VARCHAR(40) DEFAULT 'proposed'
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def save_decision(decision, based_on, owner, status):
    setup_decisions_table()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO gtm_decisions (decision, based_on, owner, status) VALUES (%s, %s, %s, %s)",
        (decision, based_on, owner, status),
    )
    conn.commit()
    cur.close()
    conn.close()


def load_decisions():
    try:
        setup_decisions_table()
        conn = get_db_connection()
        try:
            return pd.read_sql("SELECT * FROM gtm_decisions ORDER BY created_at DESC", conn)
        finally:
            conn.close()
    except Exception:
        return pd.DataFrame()


def row_text(row):
    parts = [str(row.get("summary", "")), str(row.get("source_text", "")), str(row.get("source_type", ""))]
    return " ".join(parts).lower()


def classify_segment(row):
    text = row_text(row)
    score_map = {
        "Coffee switchers": ["coffee", "jitter", "caffeine", "energy", "focus", "crash"],
        "Matcha ritualists": ["matcha", "ceremonial", "whisk", "aesthetic", "ritual", "latte"],
        "Wellness purists": ["pure", "pesticide", "clean", "organic", "testing", "heavy metal", "transparent", "source"],
        "Tea explorers": ["puer", "pu'er", "sheng", "shu", "aged", "fermented", "loose leaf", "tea"],
        "Premium ritual gifters": ["gift", "premium", "luxury", "beautiful", "design", "sharing", "collection"],
    }
    counts = {segment: sum(1 for kw in keywords if kw in text) for segment, keywords in score_map.items()}
    best_segment = max(counts, key=counts.get)
    if counts[best_segment] == 0:
        if row.get("grounded_energy_desire", 0) >= 7:
            return "Coffee switchers"
        if row.get("brewing_theater", 0) >= 7:
            return "Matcha ritualists"
        if row.get("transparency_desire", 0) >= 7:
            return "Wellness purists"
        return "Curious premium drinkers"
    return best_segment


def segment_recommendation(segment):
    recommendations = {
        "Coffee switchers": {
            "Primary promise": "Calm stamina without the coffee crash",
            "Hero product": "Cold brew Pu'er or smooth Shu starter",
            "Best channels": "TikTok, Meta, coffee-alternative SEO",
            "Message test": "Steady energy vs ancient tea ritual",
        },
        "Matcha ritualists": {
            "Primary promise": "A beautiful daily ritual with deeper flavor",
            "Hero product": "Pu'er latte kit or tasting flight",
            "Best channels": "Instagram, creators, cafe partnerships",
            "Message test": "Modern ritual vs Yunnan origin story",
        },
        "Wellness purists": {
            "Primary promise": "Clean ancient-tree Pu'er with transparent proof",
            "Hero product": "Tested ancient-tree pure tea",
            "Best channels": "Search, newsletter, wellness communities",
            "Message test": "Lab-tested purity vs zero-pesticide sourcing",
        },
        "Tea explorers": {
            "Primary promise": "Demystified Sheng and Shu for modern collectors",
            "Hero product": "Shu/Sheng education bundle",
            "Best channels": "SEO, Reddit, long-form guides",
            "Message test": "Start with Shu vs choose your Pu'er path",
        },
        "Premium ritual gifters": {
            "Primary promise": "A giftable tea ritual with story and substance",
            "Hero product": "Compressed tea gift set",
            "Best channels": "Holiday gifting, partnerships, corporate gifting",
            "Message test": "Rare mountain tea vs meaningful modern gift",
        },
        "Curious premium drinkers": {
            "Primary promise": "Premium tea made easy to discover",
            "Hero product": "Discovery sampler",
            "Best channels": "Landing page quiz, email capture",
            "Message test": "Discovery sampler vs daily ritual starter",
        },
    }
    return recommendations.get(segment, recommendations["Curious premium drinkers"])


def build_segment_table(df):
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    scored = df.copy()
    # Prefer Gemini-classified segment from pipeline; fall back to keyword heuristic for legacy rows
    if "segment" in scored.columns and scored["segment"].notna().any():
        missing_mask = scored["segment"].isna() | (scored["segment"] == "")
        scored.loc[missing_mask, "segment"] = scored.loc[missing_mask].apply(classify_segment, axis=1)
    else:
        scored["segment"] = scored.apply(classify_segment, axis=1)
    grouped = scored.groupby("segment").agg(
        mentions=("segment", "size"),
        avg_transparency=("transparency_desire", "mean"),
        avg_ritual=("brewing_theater", "mean"),
        avg_energy=("grounded_energy_desire", "mean"),
        avg_alignment=("premium_accessibility_score", "mean"),
    ).reset_index()

    recs = grouped["segment"].apply(segment_recommendation).apply(pd.Series)
    grouped = pd.concat([grouped, recs], axis=1)

    # Normalized opportunity score (0-100) with component breakdown
    alignment_component = (grouped["avg_alignment"].fillna(0) / 10) * 40  # 0-40 points
    volume_component = grouped["mentions"].rank(pct=True).fillna(0) * 30  # 0-30 points
    grouped["alignment_pts"] = alignment_component.round(1)
    grouped["volume_pts"] = volume_component.round(1)
    grouped["opportunity_score"] = (alignment_component + volume_component).round(1)
    grouped = grouped.sort_values("opportunity_score", ascending=False)
    return grouped, scored


def build_opportunity_table(segment_df, trend_summary, comp_summary):
    rows = []
    # Trend contribution: up to 15 points based on largest positive delta
    trend_boost = 0
    if not trend_summary.empty:
        raw_delta = max(float(trend_summary["delta"].max()), 0)
        trend_boost = min(raw_delta / 10 * 3, 15)  # cap at 15
    # Competitor gap contribution: up to 15 points based on weak-count
    comp_gap = (comp_summary or {}).get("weak_count", 0)
    comp_boost = min(comp_gap / 10 * 3, 15)  # cap at 15

    for _, row in segment_df.iterrows():
        base = float(row["opportunity_score"])  # 0-70
        total = round(base + trend_boost + comp_boost, 1)  # 0-100
        rows.append({
            "Opportunity": row["Primary promise"],
            "Segment": row["segment"],
            "Score": total,
            "Alignment": float(row["alignment_pts"]),
            "Volume": float(row["volume_pts"]),
            "Trend Boost": round(trend_boost, 1),
            "Comp Gap Boost": round(comp_boost, 1),
            "Why it matters": f"{int(row['mentions'])} mentions, {row['avg_alignment']:.1f}/10 average brand alignment, and a concrete product bridge: {row['Hero product']}.",
            "Recommended test": row["Message test"],
        })
    return pd.DataFrame(rows).sort_values("Score", ascending=False)


def build_launch_market_table(demo_df):
    if demo_df.empty:
        return pd.DataFrame()

    required = {"geography", "population", "median_household_income", "education_proxy"}
    if not required.issubset(demo_df.columns):
        return pd.DataFrame()

    launch_df = demo_df.copy()
    numeric_cols = ["population", "median_household_income", "education_proxy"]
    has_asian_data = "asian_population_pct" in launch_df.columns
    if has_asian_data:
        numeric_cols.append("asian_population_pct")
    for col in numeric_cols:
        launch_df[col] = pd.to_numeric(launch_df[col], errors="coerce")

    launch_df = launch_df.dropna(subset=["population", "median_household_income", "education_proxy"])
    if launch_df.empty:
        return pd.DataFrame()

    launch_df["income_percentile"] = launch_df["median_household_income"].rank(pct=True)
    launch_df["education_percentile"] = launch_df["education_proxy"].rank(pct=True)
    launch_df["population_percentile"] = launch_df["population"].rank(pct=True)

    if has_asian_data and launch_df["asian_population_pct"].notna().any():
        launch_df["asian_pct_percentile"] = launch_df["asian_population_pct"].rank(pct=True)
        # Weighted formula: income 30%, education 30%, population 25%, Asian diaspora 15%
        launch_df["launch_score"] = (
            launch_df["income_percentile"] * 30
            + launch_df["education_percentile"] * 30
            + launch_df["population_percentile"] * 25
            + launch_df["asian_pct_percentile"] * 15
        ).round(1)
    else:
        # Fallback without Asian data: income 35%, education 35%, population 30%
        launch_df["launch_score"] = (
            launch_df["income_percentile"] * 35
            + launch_df["education_percentile"] * 35
            + launch_df["population_percentile"] * 30
        ).round(1)

    launch_df["Strategic read"] = launch_df.apply(
        lambda row: (
            "Strong cultural bridge market"
            if has_asian_data and row.get("asian_pct_percentile", 0) >= 0.85 and row["income_percentile"] >= 0.7
            else "Premium early-adopter market"
            if row["income_percentile"] >= 0.85 and row["education_percentile"] >= 0.75
            else "Strong scale market"
            if row["population_percentile"] >= 0.9
            else "Niche affluent test market"
        ),
        axis=1,
    )
    return launch_df.sort_values("launch_score", ascending=False)


def build_cafe_bridge_table():
    return pd.DataFrame([
        {
            "Flagship Role": "First-sip trial lab",
            "Experience Offer": "Pu'er latte or cold brew Pu'er",
            "Customer Job": "Try something delicious without learning the category first",
            "Scale Path": "Waitlist, tasting RSVP, discovery sampler roadmap",
            "Metric": "Drink-to-email signup rate",
        },
        {
            "Flagship Role": "Education lab",
            "Experience Offer": "Pure tea tasting flight: Shu vs Sheng",
            "Customer Job": "Understand Pu'er through taste, not jargon",
            "Scale Path": "Shu/Sheng starter bundle, landing-page quiz, creator scripts",
            "Metric": "Tasting-to-bundle conversion",
        },
        {
            "Flagship Role": "Trust proof lab",
            "Experience Offer": "Visible sourcing/testing proof near the menu",
            "Customer Job": "Feel safe paying premium for unfamiliar tea",
            "Scale Path": "Website proof modules, partner deck, future product pages",
            "Metric": "Proof-section engagement and partner inquiry rate",
        },
        {
            "Flagship Role": "Content engine",
            "Experience Offer": "Quiet flagship setting and signature serveware",
            "Customer Job": "Share a beautiful, culturally rooted experience",
            "Scale Path": "UGC, founder content, gift set campaigns, partner decks",
            "Metric": "UGC mentions and gift-set inquiry rate",
        },
        {
            "Flagship Role": "Retention lab",
            "Experience Offer": "Daily calm-energy beverage routine",
            "Customer Job": "Replace or complement coffee/matcha",
            "Scale Path": "Email lifecycle, event invites, wholesale/cafe partners, future subscription",
            "Metric": "Repeat drink purchase and waitlist retention",
        },
    ])


def trend_family(keyword):
    kw = str(keyword).lower()
    if kw in ADJACENT_TREND_KEYWORDS:
        return "Adjacent benchmark"
    if kw in PUER_TREND_KEYWORDS:
        return "Pu'er variants"
    return "Other"


def filter_adjacent_trends(trends_df):
    if trends_df.empty or "keyword" not in trends_df.columns:
        return pd.DataFrame()
    return trends_df[trends_df["keyword"].str.lower().isin(ADJACENT_TREND_KEYWORDS)].copy()


def build_indexed_trends(trends_df):
    if trends_df.empty:
        return pd.DataFrame()

    rows = []
    for keyword, group in trends_df.sort_values("date").groupby("keyword"):
        clean = group.dropna(subset=["interest"])
        non_zero = clean[clean["interest"] > 0]
        if non_zero.empty:
            continue
        baseline = float(non_zero.iloc[0]["interest"])
        for _, row in clean.iterrows():
            rows.append({
                "date": row["date"],
                "keyword": keyword,
                "indexed_interest": round((float(row["interest"]) / baseline) * 100, 1) if baseline else None,
            })
    return pd.DataFrame(rows)


def build_puer_composite(trends_df):
    if trends_df.empty:
        return pd.DataFrame()

    pu_er = trends_df[trends_df["keyword"].str.lower().isin(PUER_TREND_KEYWORDS)].copy()
    if pu_er.empty:
        return pd.DataFrame()

    composite = pu_er.groupby("date")["interest"].agg(["mean", "max"]).reset_index()
    composite = composite.rename(columns={"mean": "Pu'er variant average", "max": "Pu'er strongest spelling"})
    return composite


def add_competitor_weight_fields(comp_df):
    if comp_df.empty:
        return comp_df

    enriched = comp_df.copy()
    title = enriched["title"].fillna("") if "title" in enriched.columns else ""
    desc = enriched["description"].fillna("") if "description" in enriched.columns else ""
    if isinstance(title, str):
        title = pd.Series([""] * len(enriched))
    if isinstance(desc, str):
        desc = pd.Series([""] * len(enriched))

    def _infer_weight(text):
        if not text:
            return None
        clean = str(text).lower()
        matches = re.findall(r"(\d+(?:\.\d+)?)\s?(kg|kilogram|kilograms|g|gram|grams)", clean)
        candidates = []
        for value, unit in matches:
            grams = float(value) * 1000 if unit.startswith("kg") or unit.startswith("kilogram") else float(value)
            if 1 <= grams <= 5000:
                candidates.append(grams)
        return min(candidates) if candidates else None

    enriched["inferred_weight_g"] = (title + " " + desc).apply(_infer_weight)
    if "price_usd" in enriched.columns:
        enriched["price_per_100g"] = enriched.apply(
            lambda row: (row["price_usd"] / row["inferred_weight_g"]) * 100
            if pd.notna(row.get("price_usd")) and pd.notna(row.get("inferred_weight_g")) and row.get("inferred_weight_g") > 0
            else None,
            axis=1,
        )
    return enriched


def extract_evidence(top_records, max_items=5):
    evidence = []
    for idx, (_, row) in enumerate(top_records.head(max_items).iterrows(), start=1):
        summary = str(row.get("summary", "")).strip()
        source_type = str(row.get("source_type", "Source")).strip()
        source_url = str(row.get("source_url", "")).strip()
        evidence.append({
            "id": f"S{idx}",
            "source_type": source_type,
            "summary": summary,
            "source_url": source_url if source_url and source_url != "None" else "",
        })
    return evidence


def render_source_note(source, method=None):
    method_html = f"<br><strong>Method:</strong> {escape(method)}" if method else ""
    st.markdown(
        f"<div class='source-note'><strong>Data source:</strong> {escape(source)}{method_html}</div>",
        unsafe_allow_html=True,
    )


def render_website_links(labels):
    links = [
        f"<a href='{escape(WEBSITE_LINKS[label])}' target='_blank'>{escape(label)}</a>"
        for label in labels
        if label in WEBSITE_LINKS
    ]
    if links:
        st.markdown(
            f"<div class='source-note'><strong>Website context:</strong> {' | '.join(links)}</div>",
            unsafe_allow_html=True,
        )


def show_table(df, source, method=None, height="content", column_config=None, hide_index=True, full_text=False):
    render_source_note(source, method)
    display_df = df.copy()
    
    if column_config:
        for col, config in column_config.items():
            if col in display_df.columns:
                if isinstance(config, dict):
                    if config.get("type_config", {}).get("type") == "link":
                        display_df[col] = display_df[col].apply(
                            lambda x: f'<a href="{x}" target="_blank">Link</a>' if pd.notnull(x) and x != "" else ""
                        )
                    if "label" in config and config["label"] is not None:
                        display_df = display_df.rename(columns={col: config["label"]})
                elif isinstance(config, str):
                    display_df = display_df.rename(columns={col: config})

    html = display_df.to_html(escape=False, index=not hide_index)
    html_content = f"""
<div style="overflow-x: auto; border: 1px solid rgba(0,0,0,0.08); border-radius: 4px;">
    {html.replace('<table border="1" class="dataframe">', '<table class="sf-wrap-table">')}
</div>
"""
    st.markdown(html_content, unsafe_allow_html=True)


def render_story_card(label, title, body, rationale=None):
    rationale_html = ""
    if rationale:
        rationale_html = f"<div class='story-rationale'><strong>Why this matters:</strong> {escape(rationale)}</div>"
    st.markdown(
        f"""
        <div class="story-card">
            <div class="story-label">{escape(label)}</div>
            <div class="story-title">{escape(title)}</div>
            <div class="story-body">{escape(body)}</div>
            {rationale_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_callout(text):
    st.markdown(f"<div class='callout'>{escape(text)}</div>", unsafe_allow_html=True)


def render_portfolio_brief():
    items = [
        (
            "Problem",
            "Southern Frontier needs a US market-entry view for a heritage Pu'er brand before committing to expensive retail or commerce infrastructure.",
        ),
        (
            "Data",
            "Google Trends, People Also Ask, YouTube transcripts, Shopify feeds, Census ACS, cafe search signals, and future Reddit listening.",
        ),
        (
            "Method",
            "Collect public signals, normalize them into tables, use LLM scoring for unstructured text, then expose sources beside each claim.",
        ),
        (
            "Output",
            "A market-entry dashboard for audience whitespace, competitor positioning, cafe DNA, GTM hypotheses, and experiment tracking.",
        ),
        (
            "Recommendation",
            "Use the site for brand trust, education, and lead capture now; use one physical experience as a proof lab; keep ecommerce as a later roadmap layer.",
        ),
    ]
    first_row = st.columns(3)
    second_row = st.columns(2)
    for col, (label, text) in zip(first_row + second_row, items):
        with col:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(text)


def render_page_header():
    if os.path.exists(BRAND_LOGO_PATH):
        with open(BRAND_LOGO_PATH, "rb") as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode()
        img_html = f'<img src="data:image/png;base64,{img_base64}" width="220" style="margin-right: 20px; flex-shrink: 0;" />'
    else:
        img_html = ""

    st.markdown(
        f"""
        <div style="display: flex; align-items: center; margin-bottom: 1rem;">
            {img_html}
            <div>
                <div class="sf-eyebrow">Southern Frontier Strategy Intelligence</div>
                <h1 class="title-text" style="margin:0;">Market Entry Dashboard</h1>
                <div class="small-muted">
                    Branding, audience, competitor, and GTM signals for bringing ancient-tree Pu'er
                    into the US market through modern ritual, transparent sourcing, and grounded energy.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_brand_intro():
    st.markdown(
        """
        <div class="brand-panel">
            <div class="brand-kicker">Brand Context</div>
            <div class="brand-title">A Journey of Resilience: The Pu'er Spirit</div>
            <div class="brand-body">
                Southern Frontier is a Pu'er tea brand built around the Pu'er Spirit:
                patient, resilient, and always evolving. The brand's mission is to demystify
                ancient-tree Pu'er and make it transparent, accessible, and joyful for modern life.
                The tea comes from the mountains, but the spirit belongs anywhere people are
                learning to adapt, endure, and begin again.
            </div>
            <div class="brand-values">
                <span class="brand-value">Pure: transparently sourced and tested</span>
                <span class="brand-value">Power: quiet strength from tea trees and time</span>
                <span class="brand-value">Pleasure: beautiful taste and modern rituals</span>
            </div>
            <div class="brand-philosophy">Savor Life. Share Life. Salute Life.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def classify_score(score):
    if pd.isna(score):
        return "Not enough data"
    if score >= 7.5:
        return "strong signal"
    if score >= 6:
        return "promising signal"
    if score >= 4.5:
        return "mixed signal"
    return "weak signal"


def summarize_consumer_signal(df):
    score_cols = ["transparency_desire", "brewing_theater", "grounded_energy_desire"]
    available_cols = [col for col in score_cols if col in df.columns]
    if not available_cols or df.empty:
        return None

    means = df[available_cols].mean(numeric_only=True).sort_values(ascending=False)
    top_signal = means.index[0]
    signal_names = {
        "transparency_desire": "transparency and purity",
        "brewing_theater": "ritual and brewing theater",
        "grounded_energy_desire": "grounded energy",
    }
    return {
        "top_signal": signal_names.get(top_signal, top_signal),
        "top_score": means.iloc[0],
        "scores": means,
        "aligned_count": len(df[(df.get("transparency_desire", 0) >= 8) | (df.get("grounded_energy_desire", 0) >= 8)]),
    }


def summarize_trends(trends_df):
    if trends_df.empty or not {"keyword", "interest"}.issubset(trends_df.columns):
        return pd.DataFrame()

    records = []
    for keyword, group in trends_df.sort_values("date").groupby("keyword"):
        clean_group = group.dropna(subset=["interest"])
        if clean_group.empty:
            continue
        first = float(clean_group.iloc[0]["interest"])
        latest = float(clean_group.iloc[-1]["interest"])
        delta = latest - first
        records.append({
            "keyword": keyword,
            "first_interest": first,
            "latest_interest": latest,
            "delta": delta,
            "average_interest": float(clean_group["interest"].mean()),
        })
    return pd.DataFrame(records).sort_values(["delta", "average_interest"], ascending=False)


def summarize_competitors(comp_df):
    if comp_df.empty:
        return None

    median_price = comp_df["price_usd"].median() if "price_usd" in comp_df.columns else None
    avg_positioning = comp_df["positioning_score"].mean() if "positioning_score" in comp_df.columns else None
    summary = {
        "vendors": comp_df["vendor"].nunique() if "vendor" in comp_df.columns else 0,
        "products": len(comp_df),
        "median_price": median_price,
        "median_price_label": f"${median_price:.2f}" if pd.notna(median_price) else "Not available",
        "avg_positioning": avg_positioning,
        "avg_positioning_label": f"{avg_positioning:.1f}/10" if pd.notna(avg_positioning) else "Not available",
        "weak_count": len(comp_df[comp_df.get("positioning_score", 10) <= 4]) if "positioning_score" in comp_df.columns else 0,
    }
    return summary


def build_launch_hypotheses(signal_summary, comp_summary):
    hypotheses = []
    if signal_summary:
        top_signal = signal_summary["top_signal"]
        hypotheses.append({
            "Hypothesis": f"Lead with {top_signal}",
            "Rationale": f"The strongest consumer vector in the current sample is {top_signal}, with an average score of {signal_summary['top_score']:.1f}/10.",
            "Suggested test": "Run two landing page hero variants: one product-led and one benefit-led, then compare email signup intent.",
        })
    if comp_summary and comp_summary["weak_count"] > 0:
        hypotheses.append({
            "Hypothesis": "Modern accessibility is a positioning gap",
            "Rationale": f"{comp_summary['weak_count']} competitor products score at or below 4 on modern authenticity, suggesting room for clearer, less esoteric education.",
            "Suggested test": "Compare a clean 'daily ritual' brand section against a heritage-heavy version for comprehension, partner inquiry, and signup intent.",
        })
    hypotheses.append({
        "Hypothesis": "Pu'er needs a bridge audience, not only tea experts",
        "Rationale": "The strongest GTM path is likely through matcha and specialty coffee behaviors: ritual, energy management, and premium taste.",
        "Suggested test": "Target coffee alternative and matcha ritual keywords separately, then measure which segment gives cheaper qualified signups.",
    })
    hypotheses.append({
        "Hypothesis": "Health & heritage may convert when paired with proof",
        "Rationale": "Southern Frontier has credible website proof points around microbially fermented Shu, polyphenol-rich Sheng, low caffeine, zero-pesticide positioning, and third-party testing.",
        "Suggested test": "Run a proof-led landing section against an emotion-led Pu'er Spirit section; measure scroll depth, quiz starts, and email signup rate.",
    })
    return pd.DataFrame(hypotheses)


def generate_value_props(top_records):
    client = genai.Client(api_key=GEMINI_API_KEY)
    evidence_blocks = []
    for idx, (_, row) in enumerate(top_records.iterrows(), start=1):
        evidence_blocks.append(
            f"Source ID: S{idx}\nSource: {row['source_type']}\nSummary: {row['summary']}\nText: {row['source_text']}"
        )
    text_data = "\n\n".join(evidence_blocks)
    prompt = """
You are a lead growth marketer for 'Southern Frontier', a Pu'er tea brand. 
Southern Frontier combines modern, transparent design philosophy (like Blue Bottle) with the resilient, authentic spirit of ancient mountain Pu'er (values: Pure, Power, Pleasure).
Review the provided consumer friction and intent data from specialty coffee and matcha drinkers. 
Based strictly on the pain points and aesthetic desires mentioned, generate 3 distinct pieces of marketing copy for upcoming A/B tests. 

For each, provide: 
- The Angle (e.g., 'Hero Headline', 'Instagram Ad Hook', 'Product Description')
- H1 Headline (Max 6 words)
- H2 Sub-headline (Max 12 words)
- The Data Rationale (1 sentence explaining why this will convert, citing the provided data).
- evidence_refs: 1-3 Source IDs such as ["S1", "S4"] that support the rationale.

Return clean JSON that conforms to the schema.
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[prompt, text_data],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ValuePropResponse,
                temperature=0.7,
            ),
        )
        return json.loads(response.text).get('value_props', [])
    except Exception as e:
        st.error(f"Error calling Gemini API: {e}")
        return []

render_page_header()
render_brand_intro()
render_website_links(["Brand Story", "Discover Pu'er", "Products", "Flagship Store", "Partnership"])
render_callout(
    "This dashboard reads early demand, competitor, consumer-language, and cafe-experience signals to guide Southern Frontier's US branding and GTM choices. The website should serve as a brand trust, education, and lead-capture hub now; a limited physical experience can create trust, content, and learning; ecommerce can remain a later roadmap layer once prelaunch signals are clearer."
)

try:
    df = load_data()
    if df.empty:
        st.warning("No data found in the database. Please run the data pipeline script first.")
        st.stop()
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

trends_df = load_trends_data()
comp_df = load_competitor_data()
comp_df = add_competitor_weight_fields(comp_df)
demo_df = load_demographics_data()
cafe_comp_df = load_cafe_competitor_data()
cafe_signal_df = load_cafe_signal_data()
signal_summary = summarize_consumer_signal(df)
trend_summary = summarize_trends(trends_df)
adjacent_trends_df = filter_adjacent_trends(trends_df)
adjacent_trend_summary = summarize_trends(adjacent_trends_df)
comp_summary = summarize_competitors(comp_df)
segment_df, scored_mentions = build_segment_table(df)
opportunity_df = build_opportunity_table(segment_df, adjacent_trend_summary, comp_summary) if not segment_df.empty else pd.DataFrame()
launch_market_df = build_launch_market_table(demo_df)
indexed_trends_df = build_indexed_trends(trends_df)
puer_composite_df = build_puer_composite(trends_df)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Market Story",
    "Audience & Whitespace",
    "Cafe & Retail DNA",
    "Evidence Explorer",
    "Strategy Engine",
    "Experiment Tracker",
])

with tab1:
    st.header("Executive Readout")
    render_story_card(
        "How to read this dashboard",
        "This is a market-entry intelligence tool, not a demand forecast or sales model.",
        "Use it to decide what to test, where to test, what to collect next, and how Southern Frontier's brand DNA should translate for US audiences before committing major capital.",
        "The strongest evidence should lead to lightweight experiments: waitlist pages, partner outreach, tasting RSVPs, creator briefs, cafe collaborations, and eventually commerce tests."
    )
    st.subheader("One-Page Case Study Summary")
    render_portfolio_brief()
    if signal_summary:
        cols = st.columns(4)
        cols[0].metric("Top Consumer Vector", signal_summary["top_signal"].title())
        cols[1].metric("Top Vector Score", f"{signal_summary['top_score']:.1f}/10", classify_score(signal_summary["top_score"]))
        cols[2].metric("High-Alignment Mentions", signal_summary["aligned_count"])
        if comp_summary:
            cols[3].metric("Competitor Products", comp_summary["products"])
        else:
            cols[3].metric("Competitor Products", "No data")

        render_story_card(
            "Strategic interpretation",
            f"The strongest early wedge is {signal_summary['top_signal']}.",
            "The current evidence suggests Southern Frontier should not introduce pu'er as a niche connoisseur category first. The stronger move is to translate the brand's Pure, Power, Pleasure story into an existing consumer behavior: premium ritual, cleaner energy, transparent sourcing, or modern beverage discovery.",
            "A US launch has to lower the education burden. The dashboard should therefore measure not only whether people like tea, but which part of the brand story gives new customers a reason to care now."
        )
    else:
        st.info("No scored consumer data is available yet.")

    if not adjacent_trend_summary.empty:
        leader = adjacent_trend_summary.iloc[0]
        render_story_card(
            "Adjacent demand context",
            f"'{leader['keyword']}' is the strongest trend mover in the shared benchmark set.",
            "Use this table to compare adjacent beverage and ritual behaviors collected in the same Google Trends payload. Pu'er variants are intentionally excluded here because they use a separate scale and answer a different question: spelling awareness and education burden.",
            f"The latest shared-payload pull shows '{leader['keyword']}' with the highest positive change among comparable benchmark terms."
        )
        show_table(
            adjacent_trend_summary.rename(columns={
                "keyword": "Keyword",
                "first_interest": "First Interest",
                "latest_interest": "Latest Interest",
                "delta": "Change",
                "average_interest": "Average Interest",
            }),
            "Google Trends via pytrends, stored in google_trends_data.",
            "First-tab table is restricted to comparable adjacent keywords collected in one benchmark payload: matcha, specialty coffee, puer (benchmark), boba tea, and kombucha. Pu'er variants are shown only in Evidence Explorer.",
        )
    else:
        render_story_card(
            "Adjacent demand context",
            "Comparable benchmark trend data has not been collected yet.",
            "Once the quantitative pipeline runs, this section should compare familiar adjacent behaviors such as matcha, specialty coffee, puer (benchmark), boba tea, and kombucha.",
            "Pu'er trend variants belong in the Evidence Explorer because they use a separate Google Trends scale and are best read as awareness and spelling-friction signals."
        )

    if comp_summary:
        position_label = classify_score(comp_summary["avg_positioning"])
        render_story_card(
            "Competitive landscape",
            f"The current competitor set averages {comp_summary['avg_positioning_label']} on modern authenticity.",
            "This is where brand whitespace can become concrete. If competitors are either highly traditional or too plain, Southern Frontier can own the middle: culturally rooted, visually clean, and easy to understand.",
            f"The database currently includes {comp_summary['products']} products across {comp_summary['vendors']} vendors, with a median listed price of {comp_summary['median_price_label']}."
        )
        cols = st.columns(3)
        cols[0].metric("Median Competitor Price", comp_summary["median_price_label"])
        cols[1].metric("Avg Positioning Score", comp_summary["avg_positioning_label"], position_label)
        cols[2].metric("Whitespace Candidates", comp_summary["weak_count"])
    else:
        render_story_card(
            "Competitive landscape",
            "Competitor data has not been collected yet.",
            "This section should eventually answer where Southern Frontier can be meaningfully different: format, price, education, visual identity, sourcing proof, or daily-use convenience.",
            "Competitor analysis becomes most valuable when it is translated into a positioning map and concrete launch hypotheses."
        )

    st.header("Launch Hypotheses")
    render_callout(
        "Use these as the bridge from analytics to action. Each hypothesis should become a scrappy test: a landing page, ad angle, creator brief, waitlist survey, or product bundle."
    )
    show_table(
        build_launch_hypotheses(signal_summary, comp_summary),
        "Derived from scored consumer snippets, Shopify competitor data, and Southern Frontier website brand proof points.",
        "Hypotheses are analyst heuristics for experiment planning, not validated causal findings yet.",
    )

with tab2:
    st.header("Audience Segments and Opportunity Whitespace")
    render_story_card(
        "MVP segment model",
        "The dashboard now turns raw snippets into actionable launch audiences.",
        "The segmentation is intentionally simple and explainable for the case study: it uses consumer language and score patterns to classify each mention into a likely GTM segment.",
        "This gives you a bridge from qualitative mining to decisions about product format, channel, offer, and message tests."
    )

    if not segment_df.empty:
        top_segment = segment_df.iloc[0]
        cols = st.columns(4)
        cols[0].metric("Top Segment", top_segment["segment"])
        cols[1].metric("Segment Mentions", int(top_segment["mentions"]))
        cols[2].metric("Avg Alignment", f"{top_segment['avg_alignment']:.1f}/10")
        cols[3].metric("Opportunity Score", f"{top_segment['opportunity_score']:.1f}")

        display_segments = segment_df.rename(columns={
            "segment": "Segment",
            "mentions": "Mentions",
            "avg_transparency": "Transparency",
            "avg_ritual": "Ritual",
            "avg_energy": "Energy",
            "avg_alignment": "Alignment",
            "opportunity_score": "Opportunity Score",
        })
        show_table(
            display_segments,
            "friction_data table populated by Google People Also Ask and YouTube transcript collection, scored by Gemini.",
            "Segments are classified by Gemini. Opportunity Score (0-100) = alignment (40%) + volume rank (30%).",
        )
        st.download_button(
            "Download Segments CSV",
            display_segments.to_csv(index=False).encode("utf-8"),
            "sf_segments.csv",
            "text/csv",
        )

        st.subheader("Opportunity Map")
        render_story_card(
            "How to use this",
            "Prioritize opportunities that are easy to explain, strongly aligned with the brand, and testable with a low-cost launch asset.",
            "The score combines segment strength, current evidence volume, trend context, and competitor whitespace. It is a prioritization heuristic, not a truth machine.",
            "Good case-study dashboards make assumptions visible. This one shows the recommended test next to each opportunity so strategy can be validated."
        )
        render_callout(
            "Score formula (0-100): Alignment contribution (0-40) + Volume contribution (0-30) + Trend boost (0-15) + Competitor gap boost (0-15). Each component is shown in the table for transparency."
        )
        show_table(
            opportunity_df,
            "Derived from segment table, Google Trends directional change, and competitor whitespace count.",
            "Score = alignment (40%) + volume rank (30%) + trend boost (15%) + competitor gap (15%). Use as prioritization, then validate with experiments.",
        )
        st.download_button(
            "Download Opportunities CSV",
            opportunity_df.to_csv(index=False).encode("utf-8"),
            "sf_opportunities.csv",
            "text/csv",
        )
    else:
        st.info("No segment table is available yet.")

    if not comp_df.empty and {"price_usd", "positioning_score", "vendor"}.issubset(comp_df.columns):
        st.subheader("Vendor-Level Competitor Positioning")
        render_story_card(
            "Whitespace lens",
            "For brand positioning, the vendor-level view is more useful than one dot per product.",
            "The map aggregates each vendor's average product price and average Modern Authenticity score. This better approximates brand-level positioning while still using product-copy evidence.",
        )
        plot_df = comp_df.groupby("vendor").agg(
            avg_price_usd=("price_usd", "mean"),
            avg_positioning_score=("positioning_score", "mean"),
            products=("vendor", "size"),
        ).reset_index().rename(columns={
            "vendor": "Vendor",
            "avg_price_usd": "Avg Price USD",
            "avg_positioning_score": "Avg Modern Authenticity",
            "products": "Products",
        })
        render_source_note(
            "Shopify /products.json endpoints and Gemini scoring stored in competitor_products.",
            "Each point is a vendor aggregate: average observed price and average product-copy positioning score."
        )
        base_chart = alt.Chart(plot_df).encode(
            x=alt.X("Avg Price USD:Q", title="Average Observed Product Price, USD"),
            y=alt.Y("Avg Modern Authenticity:Q", title="Average Modern Authenticity Score", scale=alt.Scale(domain=[0, 10])),
            tooltip=[
                alt.Tooltip("Vendor:N"),
                alt.Tooltip("Avg Price USD:Q", format="$.2f"),
                alt.Tooltip("Avg Modern Authenticity:Q", format=".1f"),
                alt.Tooltip("Products:Q"),
            ],
        )
        points = base_chart.mark_circle(color="#A0442D", opacity=0.78).encode(
            size=alt.Size("Products:Q", title="Observed Products", scale=alt.Scale(range=[80, 700])),
        )
        labels = base_chart.mark_text(
            align="left",
            baseline="middle",
            dx=8,
            fontSize=11,
            color="#1A1A1A",
        ).encode(text="Vendor:N")
        st.altair_chart((points + labels).properties(height=420), width="stretch")
        show_table(
            plot_df.sort_values("Avg Modern Authenticity", ascending=False),
            "competitor_products table from Shopify feeds, scored by Gemini.",
            "Vendor positioning score = average positioning_score across observed products for that vendor. This is a proxy until brand-level visual/site analysis is added.",
        )
        st.download_button(
            "Download Vendor Positioning CSV",
            plot_df.to_csv(index=False).encode("utf-8"),
            "sf_vendor_positioning.csv",
            "text/csv",
        )

    st.subheader("US Launch-Market Prioritization")
    render_story_card(
        "Census-powered GTM lens",
        "The dashboard now ranks US metro areas for premium launch potential.",
        "This uses Census ACS population, household income, and higher-education proxy signals. It should guide where to test partnerships, creator seeding, cafe collaborations, events, and paid geo-targeting first.",
        "For Southern Frontier, the ideal early market likely has premium beverage behavior, high disposable income, educated consumers, and enough density to learn quickly."
    )
    if not launch_market_df.empty:
        top_market = launch_market_df.iloc[0]
        cols = st.columns(4)
        cols[0].metric("Top Launch Market", top_market["geography"].replace(" Metro Area", "").replace(" Micro Area", ""))
        cols[1].metric("Launch Score", f"{top_market['launch_score']:.1f}")
        cols[2].metric("Median Income", f"${top_market['median_household_income']:,.0f}")
        cols[3].metric("Population", f"{top_market['population']:,.0f}")

        has_asian = "asian_population_pct" in launch_market_df.columns
        display_cols = [
            "geography",
            "launch_score",
            "Strategic read",
            "population",
            "median_household_income",
            "education_proxy",
        ]
        rename_map = {
            "geography": "Market",
            "launch_score": "Launch Score",
            "population": "Population",
            "median_household_income": "Median Household Income",
            "education_proxy": "Education Proxy",
        }
        if has_asian:
            display_cols.insert(3, "asian_population_pct")
            rename_map["asian_population_pct"] = "Asian Pop %"
        market_display = launch_market_df.head(25)[
            [c for c in display_cols if c in launch_market_df.columns]
        ].rename(columns=rename_map)

        formula_text = (
            "Launch Score = income (30%) + education (30%) + population (25%) + Asian pop % (15%)."
            if has_asian
            else "Launch Score = income (35%) + education (35%) + population (30%). Run census_pipeline.py to add Asian diaspora data."
        )
        show_table(
            market_display,
            "US Census ACS 2024 acs1 API, stored in metro_demographics.",
            formula_text,
        )
        st.download_button(
            "Download Launch Markets CSV",
            market_display.to_csv(index=False).encode("utf-8"),
            "sf_launch_markets.csv",
            "text/csv",
        )
    else:
        st.info("No Census metro demographics found yet. Run census_pipeline.py after adding CENSUS_API_KEY.")

with tab3:
    st.header("Cafe & Retail Experience Intelligence")
    render_story_card(
        "Brand DNA",
        "Southern Frontier is not only a tea product brand; it is a hospitality and ritual brand.",
        "The Hangzhou flagship sits in a tourist area, so slowing down is part of the atmosphere. But the brand should also support fast-paced modern life through to-go Pu'er lattes and convenient drinks, just as coffee shops serve both quick to-go orders and slower pour-over rituals.",
        "This does not mean a costly multi-store rollout. It means one flagship, pop-up, or partner experience can become a learning lab, content engine, and lead-capture bridge while ecommerce remains a future roadmap layer."
    )
    render_website_links(["Flagship Store", "Products", "Brand Story"])
    render_source_note(
        "Southern_Frontier_Website StoreSection and store photo/video assets.",
        "Flagship cues used here: Grand Canal location, Pu'er latte, pure tea, tasting, quiet-by-design space, conversation-led hospitality, and to-go drinks for fast-paced use cases."
    )

    cols = st.columns(4)
    cols[0].metric("Experience Wedge", "To-go + ritual")
    cols[1].metric("Bridge Drink", "Pu'er latte")
    cols[2].metric("Trust Cue", "Visible proof")
    cols[3].metric("Home Bridge", "Sampler / bundle")

    st.subheader("Cafe / Retail Competitor Positioning")
    render_story_card(
        "How to use this",
        "Track these competitors for menu strategy, ritual theater, visual language, beverage pricing, and cafe-to-home conversion.",
        "The cafe score mirrors the tea-vendor positioning concept, but it focuses on retail experience: visual positioning, ritual theater, fast-to-go plus slow-ritual duality, and cafe-to-product bridge.",
        "This is not about copying their store footprint. It is about learning which experience cues make an unfamiliar tea desirable enough to join a list, attend a tasting, start a partnership conversation, or later buy online."
    )
    if not cafe_comp_df.empty and "overall_positioning_score" in cafe_comp_df.columns:
        cafe_display = cafe_comp_df[[
            "name", "category", "website", "overall_positioning_score",
            "visual_positioning_score", "ritual_theater_score",
            "speed_ritual_duality_score", "cafe_to_product_bridge_score",
            "signature_drinks", "experience_notes", "review_language"
        ]].rename(columns={
            "name": "Competitor",
            "category": "Category",
            "website": "Website",
            "overall_positioning_score": "Overall Cafe Benchmark",
            "visual_positioning_score": "Visual Positioning",
            "ritual_theater_score": "Ritual Theater",
            "speed_ritual_duality_score": "To-Go + Ritual Duality",
            "cafe_to_product_bridge_score": "Cafe-to-Product Bridge",
            "signature_drinks": "Signature Drinks",
            "experience_notes": "Experience Notes",
            "review_language": "Review/Search Language",
        })
        source_col = alt.Chart(cafe_display).mark_bar(color="#A0442D").encode(
            x=alt.X("Overall Cafe Benchmark:Q", scale=alt.Scale(domain=[0, 10])),
            y=alt.Y("Competitor:N", sort="-x"),
            tooltip=["Competitor:N", "Category:N", "Overall Cafe Benchmark:Q", "To-Go + Ritual Duality:Q", "Cafe-to-Product Bridge:Q"],
        ).properties(height=320)
        st.altair_chart(source_col, width="stretch")
        show_table(
            cafe_display,
            "cafe_competitors table populated by cafe_competitor_pipeline.py using Serper search snippets and Gemini scoring.",
            "Scores are directional. Overall Cafe Benchmark combines visual brand positioning, ritual theater, to-go/ritual duality, and cafe-to-product bridge evidence.",
            full_text=True,
            column_config={"Website": st.column_config.LinkColumn("Website")},
        )
    else:
        show_table(
            pd.DataFrame(CAFE_EXPERIENCE_COMPETITORS),
            "Analyst-defined seed set based on Southern Frontier's cafe/store brand DNA and adjacent US beverage behaviors.",
            "Run cafe_competitor_pipeline.py to collect search evidence and score these competitors.",
            full_text=True,
        )

    st.subheader("One Flagship to Lead-Capture and Future Commerce Bridge")
    render_website_links(["Flagship Store", "Products"])
    show_table(
        build_cafe_bridge_table(),
        "Derived from Southern Frontier website product and store positioning.",
        "Maps high-touch flagship moments to near-term lead capture, content, partnership, and future commerce paths.",
        full_text=True,
    )

    st.subheader("Collected Cafe / Retail Signals")
    if not cafe_signal_df.empty:
        signal_display = cafe_signal_df[[
            "competitor_name", "signal_type", "title", "snippet", "url"
        ]].rename(columns={
            "competitor_name": "Competitor",
            "signal_type": "Signal Type",
            "title": "Title",
            "snippet": "Snippet",
            "url": "Source Link",
        })
        show_table(
            signal_display,
            "cafe_retail_signals table populated by cafe_competitor_pipeline.py via Serper search.",
            "Collected easy public signals: menu/drink pricing snippets, review language, visual/store cues, and cafe-to-product bridge evidence. These are snippets, not verified full menu/review datasets.",
            full_text=True,
            column_config={"Source Link": st.column_config.LinkColumn("Source Link")},
        )
    else:
        st.info("No cafe retail signal rows found yet. Run cafe_competitor_pipeline.py to collect public search evidence.")

    st.subheader("What Still Needs Manual or Specialized Collection")
    next_collection = pd.DataFrame([
        {
            "Data": "Verified menu prices",
            "Why": "Search snippets expose some menu hints, but exact drink prices need menu pages, photos, or manual capture.",
            "Possible Source": "Official menus, Google Business photos, manual capture",
        },
        {
            "Data": "Flagship-market fit",
            "Why": "Choose one store or pop-up city based on high learning value, content potential, partner access, and brand-signal quality.",
            "Possible Source": "Census launch-market table, cafe competitor density, creator/community presence",
        },
        {
            "Data": "Cafe-to-lead conversion",
            "Why": "Measure whether a limited physical experience can drive newsletter signups, tasting RSVPs, partner conversations, and future commerce intent.",
            "Possible Source": "Future Southern Frontier tests: QR codes, email capture, landing pages, partner inquiry forms",
        },
    ])
    show_table(
        next_collection,
        "Proposed data collection plan.",
        "This section is intentionally framed as a roadmap because cafe intelligence requires different sources than Shopify product scraping.",
        full_text=True,
    )

with tab4:
    st.header("Quantitative Insights")
    st.subheader("Google Trends: Macro Search Volume Trajectory")
    render_story_card(
        "How to read this",
        "Google Trends scales are normalized within each query payload, so cross-chart 80s are not equal.",
        "The pipeline currently queries matcha/specialty coffee together, and pu'er spellings together. That means a value of 80 in the benchmark chart and a value of 80 in the pu'er chart do not represent the same absolute search volume.",
        "Best practice: visualize adjacent benchmarks separately from pu'er variants, then compare indexed growth or rerun collection with a shared anchor term if absolute cross-category comparison is required."
    )
    if not trends_df.empty:
        trend_keywords = sorted(trends_df["keyword"].dropna().unique())
        render_source_note(
            "Google Trends via pytrends, stored in google_trends_data.",
            f"Current stored keywords: {', '.join(trend_keywords)}. Requested pu'er variants were puerh, puer, pu'er, Pu-erh, and pu erh; pytrends returned/stored three distinct pu'er columns in this run."
        )

        trends_for_chart = trends_df.copy()
        trends_for_chart["family"] = trends_for_chart["keyword"].apply(trend_family)
        benchmark_df = trends_for_chart[trends_for_chart["family"] == "Adjacent benchmark"]
        puer_df = trends_for_chart[trends_for_chart["family"] == "Pu'er variants"]

        if not benchmark_df.empty:
            st.markdown("**Adjacent Benchmark Terms**")
            max_date = benchmark_df['date'].max()
            label_df = benchmark_df[benchmark_df['date'] == max_date]
            
            bench_chart = alt.Chart(benchmark_df).mark_line(strokeWidth=2).encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("interest:Q", title="Search Interest"),
                color=alt.Color("keyword:N", title="Keyword", scale=alt.Scale(range=["#A0442D", "#D9BD7E", "#2B4533", "#6E6258", "#8B5E3C"])),
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("keyword:N"), alt.Tooltip("interest:Q")],
            )
            labels = alt.Chart(label_df).mark_text(align='left', dx=5, fontSize=11, fontWeight='bold').encode(
                x=alt.X("date:T"),
                y=alt.Y("interest:Q"),
                text="keyword:N",
                color=alt.Color("keyword:N", scale=alt.Scale(range=["#A0442D", "#D9BD7E", "#2B4533", "#6E6258", "#8B5E3C"]))
            )
            st.altair_chart((bench_chart + labels).properties(height=320), use_container_width=True)

        if not puer_df.empty:
            strongest_spelling = puer_df.groupby('keyword')['interest'].mean().idxmax()
            st.markdown(f"**Pu'er Spelling Variants** (Strongest: `{strongest_spelling}`) ")
            max_date_puer = puer_df['date'].max()
            label_df_puer = puer_df[puer_df['date'] == max_date_puer]
            
            puer_chart = alt.Chart(puer_df).mark_line(strokeWidth=2).encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("interest:Q", title="Search Interest"),
                color=alt.Color("keyword:N", title="Spelling", scale=alt.Scale(range=["#2B4533", "#A0442D", "#D9BD7E", "#6E6258", "#8B5E3C"])),
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("keyword:N"), alt.Tooltip("interest:Q")],
            )
            labels_puer = alt.Chart(label_df_puer).mark_text(align='left', dx=5, fontSize=11, fontWeight='bold').encode(
                x=alt.X("date:T"),
                y=alt.Y("interest:Q"),
                text="keyword:N",
                color=alt.Color("keyword:N", scale=alt.Scale(range=["#2B4533", "#A0442D", "#D9BD7E", "#6E6258", "#8B5E3C"]))
            )
            st.altair_chart((puer_chart + labels_puer).properties(height=320), use_container_width=True)

        if not puer_composite_df.empty:
            st.markdown("**Pu'er Composite Demand Signal**")
            comp_melt = puer_composite_df.melt(id_vars=["date"], var_name="metric", value_name="interest")
            max_date_comp = comp_melt['date'].max()
            label_df_comp = comp_melt[comp_melt['date'] == max_date_comp]

            comp_chart = alt.Chart(comp_melt).mark_line(strokeWidth=2).encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("interest:Q", title="Interest"),
                color=alt.Color("metric:N", title="Metric", scale=alt.Scale(range=["#A0442D", "#2B4533"])),
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("metric:N"), alt.Tooltip("interest:Q")],
            )
            labels_comp = alt.Chart(label_df_comp).mark_text(align='left', dx=5, fontSize=11, fontWeight='bold').encode(
                x=alt.X("date:T"),
                y=alt.Y("interest:Q"),
                text="metric:N",
                color=alt.Color("metric:N", scale=alt.Scale(range=["#A0442D", "#2B4533"]))
            )
            st.altair_chart((comp_chart + labels_comp).properties(height=320), use_container_width=True)

        if not indexed_trends_df.empty:
            st.markdown("**Indexed Growth View, First Non-Zero Week = 100**")
            render_source_note(
                "Derived from google_trends_data.",
                "This view compares growth direction rather than absolute volume. It is safer for comparing terms collected in different TrendReq payloads."
            )
            max_date_idx = indexed_trends_df['date'].max()
            label_df_idx = indexed_trends_df[indexed_trends_df['date'] == max_date_idx]

            idx_chart = alt.Chart(indexed_trends_df).mark_line(strokeWidth=2).encode(
                x=alt.X("date:T", title="Date"),
                y=alt.Y("indexed_interest:Q", title="Indexed Interest (baseline = 100)"),
                color=alt.Color("keyword:N", title="Keyword", scale=alt.Scale(range=["#A0442D", "#D9BD7E", "#2B4533", "#6E6258", "#8B5E3C"])),
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("keyword:N"), alt.Tooltip("indexed_interest:Q", format=".1f")],
            )
            labels_idx = alt.Chart(label_df_idx).mark_text(align='left', dx=5, fontSize=11, fontWeight='bold').encode(
                x=alt.X("date:T"),
                y=alt.Y("indexed_interest:Q"),
                text="keyword:N",
                color=alt.Color("keyword:N", scale=alt.Scale(range=["#A0442D", "#D9BD7E", "#2B4533", "#6E6258", "#8B5E3C"]))
            )
            st.altair_chart((idx_chart + labels_idx).properties(height=320), use_container_width=True)
    else:
        st.info("No Google Trends data available yet.")
        
    st.header("Competitor Intelligence")
    render_story_card(
        "How to read this",
        "Pricing tells you where the market already gives permission.",
        "A premium tea launch does not need to be the cheapest option. It needs an entry product that feels low-risk and a hero product that makes the brand world desirable.",
        "Look for the price band where modern brands can explain value without forcing customers into expert-level tea knowledge."
    )
    render_story_card(
        "How positioning score is computed",
        "Modern Authenticity is an LLM rubric applied to product title and description.",
        "A score of 10 means the copy bridges ancient heritage with modern, transparent, premium design. A score of 1 means it feels either sterile/soulless or overly esoteric/confusing. The scoring prompt lives in competitor_pipeline.py and batch_competitor_pipeline.py.",
        "This is a directional content-quality score, not a consumer survey. It should be audited with examples and eventually calibrated against human labels."
    )
    if not comp_df.empty:
        if "positioning_score" in comp_df.columns and "vendor" in comp_df.columns:
            st.subheader("Modern Authenticity by Vendor")
            render_story_card(
                "Authenticity spread",
                "This view shows the distribution of Modern Authenticity scores for individual products across vendors.",
                "The red lines indicate the vendor's average score.",
            )
            stripplot = alt.Chart(comp_df).mark_circle(size=50, opacity=0.5, color="#6E6258").encode(
                x=alt.X("vendor:N", title="Vendor", axis=alt.Axis(labelAngle=-45)),
                xOffset="jitter:Q",
                y=alt.Y("positioning_score:Q", title="Modern Authenticity Score", scale=alt.Scale(domain=[0, 10])),
                tooltip=["vendor:N", "title:N", "positioning_score:Q"]
            ).transform_calculate(jitter="random()")
            
            avg_plot = alt.Chart(comp_df).mark_tick(
                color="#A0442D",
                thickness=3,
                size=40
            ).encode(
                x=alt.X("vendor:N"),
                y=alt.Y("mean(positioning_score):Q", title="Modern Authenticity Score"),
                tooltip=[alt.Tooltip("vendor:N"), alt.Tooltip("mean(positioning_score):Q", format=".1f", title="Average Score")]
            )
            
            st.altair_chart((stripplot + avg_plot).properties(height=400), use_container_width=True)
            
            render_source_note(
                "Individual products (dots) and vendor average (red line).",
                "Stored in competitor_products, scored by Gemini."
            )

        st.subheader("Average Price by Vendor and Product Type")
        if {"vendor", "product_type", "price_usd"}.issubset(comp_df.columns):
            price_df = comp_df.groupby(['vendor', 'product_type'])['price_usd'].mean().reset_index()
            price_pivot = price_df.pivot(index="vendor", columns="product_type", values="price_usd").fillna(0)
            render_source_note(
                "Shopify /products.json endpoints stored in competitor_products.",
                "Price is the first listed variant price in USD where available. Product type is the merchant-provided Shopify product_type."
            )
            price_chart = alt.Chart(price_df).mark_bar(color="#A0442D", opacity=0.85).encode(
                x=alt.X("price_usd:Q", title="Average Price (USD)"),
                y=alt.Y("vendor:N", title="Vendor", sort="-x"),
                color=alt.Color("product_type:N", title="Product Type", scale=alt.Scale(range=["#A0442D", "#D9BD7E", "#2B4533", "#6E6258", "#8B5E3C"])),
                tooltip=[alt.Tooltip("vendor:N"), alt.Tooltip("product_type:N"), alt.Tooltip("price_usd:Q", format="$.2f")],
            ).properties(height=400)
            st.altair_chart(price_chart, use_container_width=True)
            show_table(
                price_df.rename(columns={
                    "vendor": "Vendor",
                    "product_type": "Product Type",
                    "price_usd": "Average Price USD",
                }),
                "Shopify /products.json endpoints stored in competitor_products.",
                "Grouped by vendor and product_type; mean price of observed products.",
            )

            render_source_note(
                "Weight data note.",
                "Shopify public product feeds in this project do not provide reliable structured tea weight. The earlier regex-based weight inference was removed from the dashboard because it produced noisy estimates."
            )
        else:
            st.info("Price data is not available in the current competitor table.")
        
        st.subheader("Positioning Whitespace Candidates")
        render_story_card(
            "Why these rows matter",
            "Low-scoring products are not necessarily bad products. They are examples where the copy may leave a modern US customer confused, underwhelmed, or unsure why the product matters.",
            "These are useful references for what Southern Frontier can improve: clearer benefits, cleaner packaging language, better origin proof, and a more accessible ritual.",
            "The current rule flags products with a modern-authenticity score at or below 4."
        )
        if 'product_url' not in comp_df.columns:
            comp_df['product_url'] = None
            
        if "positioning_score" not in comp_df.columns:
            st.info("Positioning scores are not available in the current competitor table.")
        else:
            weak_df = comp_df[comp_df['positioning_score'] <= 4].copy()
        if "positioning_score" in comp_df.columns and not weak_df.empty:
            cols_to_show = ['vendor', 'title', 'product_type', 'price_usd', 'positioning_score', 'product_url']
            cols_to_show = [col for col in cols_to_show if col in weak_df.columns]
            show_table(
                weak_df[cols_to_show],
                "competitor_products table from Shopify product feeds, scored by Gemini using the Modern Authenticity rubric.",
                "Rows shown have positioning_score <= 4 and are treated as copy/positioning whitespace candidates.",
                column_config={
                    "product_url": st.column_config.LinkColumn("Product Link")
                }
            )
            st.download_button(
                "Download Whitespace Candidates CSV",
                weak_df[cols_to_show].to_csv(index=False).encode("utf-8"),
                "sf_competitor_whitespace.csv",
                "text/csv",
            )
        else:
            st.info("No Modern Authenticity targets found.")
    else:
        st.info("No competitor data available yet.")
        

    st.header("Consumer Desires and Friction")
    if signal_summary:
        score_text = " ".join([
            f"<span class='evidence-pill'>{escape(label.replace('_', ' ').title())}: {score:.1f}/10</span>"
            for label, score in signal_summary["scores"].items()
        ])
        st.markdown(score_text, unsafe_allow_html=True)
        render_story_card(
            "What the language is saying",
            f"The leading desire is {signal_summary['top_signal']}.",
            "The practical implication is that Southern Frontier should choose one primary promise for the first launch campaign, then use the other vectors as supporting proof.",
            "A focused brand wedge is easier to test than a broad claim that tries to be heritage, wellness, luxury, taste, ritual, and energy all at once."
        )
    
    st.subheader("Brand Alignment Over Time")
    if 'source_url' not in df.columns:
        df['source_url'] = None
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
    chart_data = df.groupby('timestamp')['premium_accessibility_score'].mean().reset_index()
    chart_data.columns = ["Date", "Avg Brand Alignment"]
    render_source_note(
        "friction_data table.",
        "premium_accessibility_score = average of transparency_desire, brewing_theater, and grounded_energy_desire from Gemini-scored PAA/transcript snippets."
    )
    alignment_chart = alt.Chart(chart_data).mark_line(strokeWidth=2.5, color="#2B4533").encode(
        x=alt.X("Date:T", title="Date"),
        y=alt.Y("Avg Brand Alignment:Q", title="Avg Brand Alignment Score", scale=alt.Scale(domain=[0, 10])),
        tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Avg Brand Alignment:Q", format=".1f")],
    ).properties(height=300)
    st.altair_chart(alignment_chart, use_container_width=True)
    
    st.markdown("---")
    st.subheader("High-Signal Consumer Evidence")
    render_story_card(
        "Why these excerpts matter",
        "These are the snippets most likely to contain usable customer language.",
        "When you write ads, packaging, creator briefs, or a landing page, this table should be mined for phrases that make the customer feel recognized.",
        "The current filter shows records with strong grounded-energy or transparency scores."
    )
    high_theater_df = df[(df['transparency_desire'] >= 8) | (df['grounded_energy_desire'] >= 8)].copy()
    if not high_theater_df.empty:
        cols_to_show = ['source_type', 'transparency_desire', 'grounded_energy_desire', 'summary', 'source_text', 'source_url']
        show_table(
            high_theater_df[cols_to_show], 
            "friction_data table from Google PAA and YouTube transcripts, scored by Gemini.",
            "Rows shown have transparency_desire >= 8 or grounded_energy_desire >= 8. Full text is wrapped with taller rows.",
            full_text=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Source Link"),
                "source_type": st.column_config.TextColumn("Source", width="small")
            }
        )
    else:
        st.info("No highly aligned consumer records found yet.")

    if not scored_mentions.empty:
        st.subheader("Scored Mentions With Segment Labels")
        cols_to_show = [
            "segment", "source_type", "transparency_desire", "brewing_theater",
            "grounded_energy_desire", "premium_accessibility_score", "summary", "source_url"
        ]
        cols_to_show = [col for col in cols_to_show if col in scored_mentions.columns]
        show_table(
            scored_mentions[cols_to_show],
            "friction_data table with rule-based segment labels added in the dashboard.",
            "Segment labels are explainable keyword/score heuristics used for GTM planning.",
            full_text=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Source Link") if "source_url" in cols_to_show else None,
                "segment": st.column_config.TextColumn("Segment", width="small"),
                "source_type": st.column_config.TextColumn("Source", width="small")
            },
        )

with tab5:
    st.subheader("Synthesize Strategy from Data")
    render_story_card(
        "From insight to GTM",
        "This engine turns high-scoring evidence into copy directions for structured tests.",
        "Use the generated outputs as hypotheses, not final brand copy. The best next step is to test them against a brand landing page, waitlist, partner inquiry flow, creator script, tasting RSVP, or paid-social audience.",
        "Every generated rationale should trace back to the highest-alignment records, so the case study can show a clear path from raw text to strategy."
    )

    if not opportunity_df.empty:
        st.subheader("Recommended Test Queue")
        show_table(
            opportunity_df[["Opportunity", "Segment", "Score", "Recommended test"]],
            "Derived from audience segments, Google Trends direction, competitor whitespace, and brand strategy assumptions.",
            "Each row should become an experiment before it is treated as a GTM decision.",
        )

    top_records = df.nlargest(20, 'premium_accessibility_score')
    evidence = extract_evidence(top_records, max_items=5)
    with st.expander("Evidence packet used for generated copy", expanded=False):
        for item in evidence:
            link_text = f" | {item['source_url']}" if item["source_url"] else ""
            st.markdown(f"**{item['id']} - {item['source_type']}**{link_text}\n\n{item['summary']}")
    
    if st.button("Re-generate Value Props", type="primary"):
        with st.spinner("Analyzing top sentiment data and generating value props..."):
            value_props = generate_value_props(top_records)

            if value_props:
                save_value_props(value_props)
                st.success("Value Propositions Generated and Saved!")

    # Always show the latest persisted value props
    saved_vps, saved_at = load_latest_value_props()
    if saved_vps:
        if saved_at:
            st.caption(f"Last generated: {saved_at.strftime('%Y-%m-%d %H:%M')}")
        cols = st.columns(3)
        for i, vp in enumerate(saved_vps):
            with cols[i % 3]:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-angle">{vp.get('angle', 'Unknown Angle')}</div>
                    <div class="metric-h1">{vp.get('headline', 'Headline')}</div>
                    <div class="metric-h2">{vp.get('sub_headline', 'Sub-headline')}</div>
                    <div class="metric-rationale"><strong>Data Rationale:</strong> {vp.get('rationale', '')}</div>
                    <div class="metric-rationale"><strong>Evidence:</strong> {', '.join(vp.get('evidence_refs', [])) or 'Top scored records'}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No value props generated yet. Click 'Re-generate Value Props' to create your first set.")

with tab6:
    st.header("GTM Experiment Tracker")
    render_story_card(
        "Why this completes the loop",
        "The dashboard should not end at insight. Each finding needs a lightweight market test so you can learn before committing brand, product, or channel budget.",
        "This tracker turns the analysis into a repeatable operating system: hypothesis, audience, channel, creative angle, success metric, result, decision.",
        "For the AI/DS case study, this is where you show how analytics becomes an experiment backlog."
    )

    with st.form("new_experiment"):
        st.subheader("Add Experiment")
        hypothesis = st.text_area("Hypothesis", value="Coffee switchers will respond better to grounded energy than to traditional Pu'er heritage.")
        c1, c2 = st.columns(2)
        segment = c1.selectbox(
            "Segment",
            ["Coffee switchers", "Matcha ritualists", "Wellness purists", "Tea explorers", "Premium ritual gifters", "Curious premium drinkers"],
        )
        channel = c2.selectbox("Channel", ["Landing page", "Meta ads", "TikTok", "Instagram creators", "SEO content", "Cafe partnership", "Email/waitlist"])
        creative_angle = st.text_input("Creative angle", value="Steady energy for modern rituals")
        c3, c4 = st.columns(2)
        success_metric = c3.text_input("Success metric", value="Qualified signup rate")
        status = c4.selectbox("Status", ["planned", "running", "complete", "paused"])
        result_notes = st.text_area("Result notes", value="")
        submitted = st.form_submit_button("Save Experiment", type="primary")
        if submitted:
            try:
                save_experiment(hypothesis, segment, channel, creative_angle, success_metric, status, result_notes)
                st.success("Experiment saved.")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Could not save experiment: {e}")

    experiments_df = load_experiments()
    st.subheader("Experiment Backlog")
    if not experiments_df.empty:
        edit_cols = ["id", "hypothesis", "segment", "channel", "creative_angle", "success_metric", "status", "result_notes"]
        edit_cols = [c for c in edit_cols if c in experiments_df.columns]
        edited_df = st.data_editor(
            experiments_df[edit_cols],
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "status": st.column_config.SelectboxColumn("Status", options=["planned", "running", "complete", "paused"]),
            },
            hide_index=True,
            num_rows="fixed",
            key="experiment_editor",
        )
        render_source_note(
            "gtm_experiments table in Neon, populated by the dashboard form.",
            "Edit status or result notes inline, then click 'Save Changes'. This is user-entered experiment planning and results data.",
        )
        save_col, delete_col, export_col = st.columns(3)
        with save_col:
            if st.button("Save Changes", type="primary"):
                try:
                    for _, row in edited_df.iterrows():
                        update_experiment(row["id"], row["status"], row.get("result_notes", ""))
                    st.success("Experiments updated.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Could not update experiments: {e}")
        with delete_col:
            del_id = st.number_input("Delete experiment ID", min_value=0, step=1, value=0)
            if st.button("Delete") and del_id > 0:
                try:
                    delete_experiment(del_id)
                    st.success(f"Experiment {del_id} deleted.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Could not delete experiment: {e}")
        with export_col:
            st.download_button(
                "Download Experiments CSV",
                experiments_df.to_csv(index=False).encode("utf-8"),
                "sf_experiments.csv",
                "text/csv",
            )
    else:
        st.info("No saved experiments yet.")

    # ── Decisions Log ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Decisions Log")
    render_story_card(
        "From experiments to decisions",
        "Experiments produce results, but results need decisions.",
        "Track what was decided, what evidence it was based on, who owns it, and whether it's been executed.",
        "This closes the loop from data → experiment → decision → action."
    )
    with st.form("new_decision"):
        dec_text = st.text_area("Decision", value="")
        dc1, dc2 = st.columns(2)
        dec_based_on = dc1.text_input("Based on (experiment or evidence)", value="")
        dec_owner = dc2.text_input("Owner", value="")
        dec_status = st.selectbox("Decision status", ["proposed", "approved", "executing", "completed", "rejected"])
        dec_submitted = st.form_submit_button("Save Decision")
        if dec_submitted and dec_text.strip():
            try:
                save_decision(dec_text, dec_based_on, dec_owner, dec_status)
                st.success("Decision logged.")
            except Exception as e:
                st.error(f"Could not save decision: {e}")
    decisions_df = load_decisions()
    if not decisions_df.empty:
        show_table(
            decisions_df,
            "gtm_decisions table in Neon, populated by the dashboard form.",
            "This is user-entered decision tracking data.",
        )
    else:
        st.info("No decisions logged yet.")
