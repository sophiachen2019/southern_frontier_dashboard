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
    pu_er["interest"] = pd.to_numeric(pu_er["interest"], errors="coerce")
    pu_er = pu_er.dropna(subset=["date", "interest"])
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


def build_value_prop_evidence_packet(
    top_records,
    trend_summary,
    signal_summary,
    comp_summary,
    comp_df,
    cafe_comp_df,
    launch_market_df,
    opportunity_df,
):
    sections = []

    sections.append({
        "id": "B1",
        "title": "Brand Context",
        "body": (
            "Southern Frontier is a Pu'er tea brand built around ancient-tree Pu'er, modern daily rituals, "
            "and the values Pure, Power, Pleasure. The brand should make Pu'er transparent, accessible, "
            "sensory, and joyful without losing cultural credibility."
        ),
    })
    sections.append({
        "id": "G1",
        "title": "GTM Context",
        "body": (
            "Current staged strategy: use the website as an education, trust, and lead-capture hub; "
            "use one physical proof lab such as a pop-up, tasting, or cafe partnership for sensory trust; "
            "treat ecommerce as a later scale path once value proposition signals are stronger."
        ),
    })

    if trend_summary is not None and not trend_summary.empty:
        top_trends = trend_summary.head(5)
        trend_lines = [
            f"{row['keyword']}: latest={row['latest_interest']:.0f}, avg={row['average_interest']:.1f}, change={row['delta']:.0f}"
            for _, row in top_trends.iterrows()
        ]
        sections.append({
            "id": "M1",
            "title": "Macro Search Signals",
            "body": (
                "Google Trends suggests Pu'er should be interpreted alongside adjacent behaviors and spelling friction. "
                "Top directional trend rows: " + "; ".join(trend_lines)
            ),
        })

    if signal_summary:
        score_lines = [
            f"{label.replace('_', ' ')}={score:.1f}/10"
            for label, score in signal_summary["scores"].items()
        ]
        sections.append({
            "id": "M2",
            "title": "Consumer Language Signals",
            "body": (
                f"The strongest scored consumer-language vector is {signal_summary['top_signal']} "
                f"({signal_summary['top_score']:.1f}/10). Scorecard: " + "; ".join(score_lines)
            ),
        })

    if top_records is not None and not top_records.empty:
        snippets = []
        for idx, (_, row) in enumerate(top_records.head(8).iterrows(), start=1):
            snippets.append(
                f"S{idx} [{row.get('source_type', 'Source')}]: {row.get('summary', '')}"
            )
        sections.append({
            "id": "M3",
            "title": "High-Alignment Consumer Snippets",
            "body": " | ".join(snippets),
        })

    if comp_summary:
        sections.append({
            "id": "C1",
            "title": "Ecommerce Competitor Summary",
            "body": (
                f"Observed ecommerce set: {comp_summary['products']} products across "
                f"{comp_summary['vendors']} vendors; median observed price {comp_summary['median_price_label']}; "
                f"average Modern Authenticity {comp_summary['avg_positioning_label']}; "
                f"{comp_summary['weak_count']} low-scoring whitespace candidates."
            ),
        })

    if comp_df is not None and not comp_df.empty and {"vendor", "positioning_score", "price_usd"}.issubset(comp_df.columns):
        comp_clean = comp_df.copy()
        comp_clean["positioning_score"] = pd.to_numeric(comp_clean["positioning_score"], errors="coerce")
        comp_clean["price_usd"] = pd.to_numeric(comp_clean["price_usd"], errors="coerce")
        vendor_summary = comp_clean.dropna(subset=["vendor", "positioning_score", "price_usd"]).groupby("vendor").agg(
            avg_price=("price_usd", "mean"),
            avg_authenticity=("positioning_score", "mean"),
            products=("vendor", "size"),
        ).reset_index()
        if not vendor_summary.empty:
            weak_vendors = vendor_summary.sort_values("avg_authenticity").head(5)
            vendor_lines = [
                f"{row['vendor']}: authenticity={row['avg_authenticity']:.1f}/10, avg_price=${row['avg_price']:.0f}, products={int(row['products'])}"
                for _, row in weak_vendors.iterrows()
            ]
            sections.append({
                "id": "C2",
                "title": "Ecommerce Positioning Gaps",
                "body": (
                    "Lowest average Modern Authenticity vendors indicate possible whitespace around clearer education, "
                    "modern craft, and cultural credibility: " + "; ".join(vendor_lines)
                ),
            })

    if cafe_comp_df is not None and not cafe_comp_df.empty and "overall_positioning_score" in cafe_comp_df.columns:
        cafe_top = cafe_comp_df.sort_values("overall_positioning_score", ascending=False).head(5)
        cafe_lines = [
            f"{row.get('name', 'Competitor')}: overall={row.get('overall_positioning_score', 0):.1f}, "
            f"ritual={row.get('ritual_theater_score', 0):.1f}, bridge={row.get('cafe_to_product_bridge_score', 0):.1f}"
            for _, row in cafe_top.iterrows()
        ]
        sections.append({
            "id": "C3",
            "title": "Cafe/Retail Experience Benchmarks",
            "body": (
                "Cafe and retail benchmarks inform menu, design, ritual theater, to-go/ritual duality, "
                "and cafe-to-product bridge. Top benchmarks: " + "; ".join(cafe_lines)
            ),
        })

    if launch_market_df is not None and not launch_market_df.empty:
        top_markets = launch_market_df.head(5)
        market_lines = [
            f"{row['geography']}: score={row['launch_score']:.1f}, income=${row['median_household_income']:,.0f}, pop={row['population']:,.0f}"
            for _, row in top_markets.iterrows()
        ]
        sections.append({
            "id": "G2",
            "title": "GTM Market Prioritization",
            "body": (
                "Census ranking informs where to test paid media, creator outreach, tastings, pop-ups, or partnerships. "
                "Top markets: " + "; ".join(market_lines)
            ),
        })

    if opportunity_df is not None and not opportunity_df.empty:
        opportunity_lines = [
            f"{row['Segment']}: {row['Opportunity']} / test: {row['Recommended test']}"
            for _, row in opportunity_df.head(5).iterrows()
        ]
        sections.append({
            "id": "P1",
            "title": "Prioritized Audience Opportunities",
            "body": "Top audience/message opportunities: " + "; ".join(opportunity_lines),
        })

    return sections


def format_evidence_packet(sections):
    return "\n\n".join(
        f"Source ID: {section['id']}\nTitle: {section['title']}\nEvidence: {section['body']}"
        for section in sections
    )


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


def render_question_framework():
    questions = pd.DataFrame([
        {
            "Market Question": "What does the broader market already understand or search for?",
            "Useful Signal": "Google Trends, Pu'er spelling variants, adjacent beverage terms",
            "Dashboard Tab": "Macro Signals",
            "Decision": "Decide whether to lead with Pu'er directly or enter through adjacent narratives like matcha, coffee alternatives, gut health, and ritual beverages.",
        },
        {
            "Market Question": "What language, curiosity, or friction should shape the brand story?",
            "Useful Signal": "People Also Ask, YouTube transcripts, LLM-coded themes",
            "Dashboard Tab": "Macro Signals",
            "Decision": "Identify the education, reassurance, and first-use guidance Southern Frontier must provide before asking for purchase intent.",
        },
        {
            "Market Question": "How do ecommerce tea vendors price, package, and explain premium tea?",
            "Useful Signal": "Shopify product feeds, price bands, Modern Authenticity scoring",
            "Dashboard Tab": "Competitor Intelligence",
            "Decision": "Inform future product architecture, pricing permission, proof language, merchandising, and ecommerce positioning.",
        },
        {
            "Market Question": "How do cafe and retail competitors make premium beverage rituals approachable?",
            "Useful Signal": "Cafe/retail search signals, menu cues, ritual theater, design and cafe-to-product bridge scores",
            "Dashboard Tab": "Competitor Intelligence",
            "Decision": "Inform menu, signature drinks, design cues, service flow, and the role of a physical proof lab.",
        },
        {
            "Market Question": "What brand position should Southern Frontier test first?",
            "Useful Signal": "Macro signals, competitor gaps, audience/message opportunity scores, broad evidence-packet value props",
            "Dashboard Tab": "Brand Positioning",
            "Decision": "Choose testable positioning directions rather than treating one brand concept as final.",
        },
        {
            "Market Question": "Where should physical or market tests happen?",
            "Useful Signal": "Census ACS income, population density, education proxy, Asian diaspora share",
            "Dashboard Tab": "GTM Strategy",
            "Decision": "Prioritize metros for paid tests, creator outreach, tastings, pop-ups, cafe partnerships, or eventual physical entry.",
        },
        {
            "Market Question": "What should we test before committing more capital?",
            "Useful Signal": "Experiment backlog, value-prop tests, decision log",
            "Dashboard Tab": "Learning Loop",
            "Decision": "Turn insights into small tests before committing to ecommerce, partnerships, or physical build-out.",
        },
    ])
    show_table(
        questions,
        "Analyst-defined market-entry question framework.",
        "This is the dashboard spine: question -> decision-domain signal -> decision.",
        full_text=True,
    )


def render_signal_map():
    signals = pd.DataFrame([
        {
            "Decision Area": "Macro market signals",
            "Signal": "Search interest, spelling fragmentation, adjacent beverage demand",
            "Source": "Google Trends via pytrends",
            "Why It Matters": "Shows whether Pu'er has existing category vocabulary or needs an adjacent-entry narrative.",
        },
        {
            "Decision Area": "Macro consumer language",
            "Signal": "Questions, anxieties, benefits, and ritual language",
            "Source": "Google PAA, YouTube transcripts, Gemini scoring",
            "Why It Matters": "Reveals what the brand, website, creators, and tastings need to explain first.",
        },
        {
            "Decision Area": "Ecommerce competitors",
            "Signal": "Observed products, prices, descriptions, product types, positioning scores",
            "Source": "Shopify feeds and LLM scoring",
            "Why It Matters": "Informs pricing, product architecture, merchandising, and the gap between expertise without accessibility and polish without depth.",
        },
        {
            "Decision Area": "Cafe and retail competitors",
            "Signal": "Menu cues, ritual theater, visual positioning, speed/ritual duality, cafe-to-product bridge",
            "Source": "Serper search signals and Gemini scoring",
            "Why It Matters": "Informs menu design, physical experience, signature drinks, service flow, and sensory trust-building.",
        },
        {
            "Decision Area": "Brand positioning",
            "Signal": "Synthesized macro, competitor, brand, GTM, and audience opportunity evidence",
            "Source": "Dashboard evidence packet and LLM-generated value-prop tests",
            "Why It Matters": "Turns evidence into testable positioning directions instead of a static brand claim.",
        },
        {
            "Decision Area": "GTM market prioritization",
            "Signal": "Income, population, education proxy, Asian population percentage",
            "Source": "US Census ACS",
            "Why It Matters": "Ranks where early paid media, tasting, pop-up, partner, creator, or future physical tests may learn fastest.",
        },
        {
            "Decision Area": "GTM learning",
            "Signal": "Hypothesis, audience, channel, metric, result, decision",
            "Source": "Dashboard experiment and decision tables",
            "Why It Matters": "Keeps strategy iterative instead of treating research as a static conclusion.",
        },
    ])
    show_table(
        signals,
        "Current public-data and dashboard-generated signal map.",
        "Use this to explain how each evidence domain supports a specific brand, competitor, GTM, or learning decision.",
        full_text=True,
    )


def render_dashboard_journey():
    journey = pd.DataFrame([
        {
            "Tab": "1. Market Questions",
            "Purpose": "Define what the market-entry decision system needs to answer.",
            "Main Output": "Question framework and signal map.",
        },
        {
            "Tab": "2. Macro Signals",
            "Purpose": "Read category awareness and consumer language.",
            "Main Output": "Google Trends, Pu'er spelling friction, YouTube/PAA language, and desire vectors.",
        },
        {
            "Tab": "3. Competitor Intelligence",
            "Purpose": "Compare ecommerce vendors and cafe/retail benchmarks.",
            "Main Output": "Pricing, product copy, modern authenticity, menu cues, design cues, and retail experience benchmarks.",
        },
        {
            "Tab": "4. Brand Positioning",
            "Purpose": "Synthesize macro and competitor evidence into positioning hypotheses.",
            "Main Output": "Article-ready insight chains, audience priorities, message tests, and value-prop drafts.",
        },
        {
            "Tab": "5. GTM Strategy",
            "Purpose": "Translate positioning into staged launch choices.",
            "Main Output": "Website hub, physical proof lab, ecommerce path, Census market prioritization, and data gaps.",
        },
        {
            "Tab": "6. Learning Loop",
            "Purpose": "Track experiments, results, and decisions.",
            "Main Output": "Experiment backlog and decision log.",
        },
    ])
    show_table(
        journey,
        "Dashboard information architecture.",
        "This is the intended reading path: orient -> inspect evidence -> synthesize -> choose strategy -> test -> learn.",
        full_text=True,
    )


def render_insight_chain(label, signal, interpretation, takeaway, test):
    st.markdown(
        f"""
        <div class="story-card">
            <div class="story-label">{escape(label)}</div>
            <div class="story-title">{escape(takeaway)}</div>
            <div class="story-body"><strong>Signal:</strong> {escape(signal)}</div>
            <div class="story-body"><strong>Interpretation:</strong> {escape(interpretation)}</div>
            <div class="story-rationale"><strong>Recommended test:</strong> {escape(test)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_strategic_insight_overview(signal_summary, comp_summary, launch_market_df):
    consumer_signal = "PAA and YouTube snippets are scored for transparency, ritual, and grounded-energy desire."
    consumer_interpretation = "Pu'er needs translation: the strongest message should lower the education burden while keeping the product premium."
    consumer_takeaway = "Make ancient tea feel approachable, useful, and modern."
    consumer_test = "Test education-first vs product-first landing sections using signup rate, scroll depth, and tasting interest."
    if signal_summary:
        consumer_signal = f"The leading scored consumer vector is {signal_summary['top_signal']} at {signal_summary['top_score']:.1f}/10."
        consumer_takeaway = f"Lead with {signal_summary['top_signal']} as the first message hypothesis."
        consumer_test = f"Test a {signal_summary['top_signal']} hero against a heritage-led hero and compare qualified signup rate."

    competitor_signal = "Competitor feeds and Modern Authenticity scoring show mixed ability to balance depth with accessibility."
    competitor_takeaway = "Position Southern Frontier in the gap between connoisseur tea and generic wellness."
    competitor_interpretation = "The opportunity is not only better tea; it is clearer translation, visual trust, and a more usable first purchase."
    if comp_summary:
        competitor_signal = f"The current set has {comp_summary['products']} products across {comp_summary['vendors']} vendors, with average Modern Authenticity of {comp_summary['avg_positioning_label']}."
        competitor_takeaway = "Own modern craft with authentic roots."

    market_signal = "Census scoring ranks metros by premium launch potential."
    market_interpretation = "The highest-scoring markets are learning environments, not automatic store locations."
    market_takeaway = "Use early markets for tests before physical expansion decisions."
    market_test = "Run geo-targeted signup or tasting-RSVP campaigns in the top 3-5 metros."
    if not launch_market_df.empty:
        top_market = launch_market_df.iloc[0]["geography"].replace(" Metro Area", "").replace(" Micro Area", "")
        market_signal = f"The current launch-market model ranks {top_market} first."
        market_test = f"Use {top_market} as one paid-media or partnership test cell, then compare against other high-scoring metros."

    render_insight_chain(
        "Category Awareness",
        "Pu'er demand is fragmented across spellings and much smaller than adjacent beverage behaviors.",
        "Most US consumers do not have stable category vocabulary yet.",
        "Capture adjacent intent before expecting direct Pu'er search demand.",
        "Compare coffee alternative, matcha alternative, gut-health tea, and daily-ritual landing-page angles.",
    )
    render_insight_chain(
        "Consumer Perception",
        consumer_signal,
        consumer_interpretation,
        consumer_takeaway,
        consumer_test,
    )
    render_insight_chain(
        "Competitor Gap",
        competitor_signal,
        competitor_interpretation,
        competitor_takeaway,
        "Compare modern-accessible copy against heritage-heavy copy and measure comprehension, signup, and partner inquiry.",
    )
    render_insight_chain(
        "Early Markets",
        market_signal,
        market_interpretation,
        market_takeaway,
        market_test,
    )


def render_staged_gtm_strategy():
    strategy = pd.DataFrame([
        {
            "Stage": "1. Website as education and trust hub",
            "Role": "Explain Pu'er, build credibility, capture early intent.",
            "Primary Assets": "Brand story, Discover Pu'er content, message tests, newsletter, tasting interest, partnership inquiry.",
            "What To Measure": "Signup rate, scroll depth, quiz starts, inquiry rate, feedback quality.",
        },
        {
            "Stage": "2. Physical experience as proof lab",
            "Role": "Let people taste, smell, understand, photograph, and trust the product.",
            "Primary Assets": "Pop-up, tasting, cafe partnership, Pu'er latte, tea flight, QR capture.",
            "What To Measure": "Drink-to-email conversion, tasting RSVP, repeat drink behavior, UGC, partner leads.",
        },
        {
            "Stage": "3. Ecommerce as scale path",
            "Role": "Scale what has already shown intent instead of launching on assumptions.",
            "Primary Assets": "Discovery sampler, gift bundle, Pu'er latte kit, cold brew, subscription or replenishment.",
            "What To Measure": "Add-to-cart, conversion, repeat purchase, bundle preference, subscription intent.",
        },
    ])
    show_table(
        strategy,
        "Synthesized GTM model from brand context, consumer signals, competitor landscape, and cafe bridge analysis.",
        "This keeps ecommerce as a later scale path until the value proposition has stronger prelaunch signal.",
        full_text=True,
    )


def render_ranked_bar_chart(df, x_col, y_col, tooltip_cols, title=None, color="#A0442D", height=340):
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        return
    chart_df = df.dropna(subset=[x_col, y_col]).copy()
    if chart_df.empty:
        return
    chart_df[x_col] = pd.to_numeric(chart_df[x_col], errors="coerce")
    chart_df = chart_df.dropna(subset=[x_col])
    if chart_df.empty:
        return
    tooltip = [alt.Tooltip(f"{col}:Q" if pd.api.types.is_numeric_dtype(chart_df[col]) else f"{col}:N") for col in tooltip_cols if col in chart_df.columns]
    chart = alt.Chart(chart_df).mark_bar(color=color, opacity=0.86).encode(
        x=alt.X(f"{x_col}:Q", title=title or x_col),
        y=alt.Y(f"{y_col}:N", sort="-x", title=None),
        tooltip=tooltip,
    ).properties(height=height)
    st.altair_chart(chart, width="stretch")


def render_consumer_desire_chart(signal_summary):
    if not signal_summary:
        return
    scores = signal_summary["scores"].reset_index()
    scores.columns = ["Desire Vector", "Score"]
    scores = scores.dropna(subset=["Score"])
    if scores.empty:
        return
    scores["Desire Vector"] = scores["Desire Vector"].str.replace("_", " ").str.title()
    chart = alt.Chart(scores).mark_bar(color="#2B4533", opacity=0.86).encode(
        x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 10]), title="Average Score"),
        y=alt.Y("Desire Vector:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("Desire Vector:N"), alt.Tooltip("Score:Q", format=".1f")],
    ).properties(height=190)
    st.altair_chart(chart, width="stretch")


def render_launch_market_chart(launch_market_df):
    if launch_market_df.empty:
        return
    chart_cols = ["geography", "launch_score", "median_household_income", "population"]
    if "asian_population_pct" in launch_market_df.columns:
        chart_cols.append("asian_population_pct")
    chart_df = launch_market_df.head(12)[chart_cols].copy()
    chart_df["Market"] = chart_df["geography"].str.replace(" Metro Area", "", regex=False).str.replace(" Micro Area", "", regex=False)
    chart_df = chart_df.rename(columns={
        "launch_score": "Launch Score",
        "median_household_income": "Median Income",
        "population": "Population",
        "asian_population_pct": "Asian Pop %",
    })
    render_ranked_bar_chart(
        chart_df,
        "Launch Score",
        "Market",
        ["Market", "Launch Score", "Median Income", "Population", "Asian Pop %"],
        title="Launch Score",
        color="#2B4533",
        height=360,
    )


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


def generate_value_props(evidence_sections):
    client = genai.Client(api_key=GEMINI_API_KEY)
    text_data = format_evidence_packet(evidence_sections)
    prompt = """
You are a lead growth marketer for 'Southern Frontier', a Pu'er tea brand. 
Southern Frontier combines modern, transparent design philosophy with the resilient, authentic spirit of ancient mountain Pu'er (values: Pure, Power, Pleasure).

Review the provided cross-dashboard evidence packet. It may include:
- Brand and GTM context
- Google Trends / macro category signals
- YouTube and Google PAA consumer-language signals
- Ecommerce competitor pricing and positioning gaps
- Cafe/retail benchmark cues
- Launch-market prioritization
- Audience/message opportunity scores

Generate 3 distinct value proposition directions for upcoming A/B tests.
Each direction should be grounded in the evidence packet, not only consumer snippets.
Avoid generic wellness claims. Preserve cultural credibility while making Pu'er approachable to US consumers.

For each, provide: 
- The Angle (e.g., 'Website Hero', 'Paid Social Hook', 'Pop-up Tasting Invite', 'Cafe Menu Message')
- H1 Headline (Max 6 words)
- H2 Sub-headline (Max 12 words)
- The Data Rationale (1 sentence explaining why this is worth testing, citing the provided evidence).
- evidence_refs: 2-4 Source IDs such as ["M1", "M3", "C2", "G1"] that support the rationale.

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
    "This dashboard connects market-entry questions to macro signals, competitor intelligence, brand positioning, GTM choices, and experiments. Read left to right to move from uncertainty to testable strategy."
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


tab_questions, tab_macro, tab_competitors, tab_positioning, tab_gtm, tab_learning_loop = st.tabs([
    "Market Questions",
    "Macro Signals",
    "Competitor Intelligence",
    "Brand Positioning",
    "GTM Strategy",
    "Learning Loop",
])

with tab_questions:
    st.header("Market-Entry Question Framework")
    render_story_card(
        "How to read this dashboard",
        "Start with the business questions, then follow the evidence domains that inform the US launch strategy.",
        "The dashboard separates market signals, competitor intelligence, brand-positioning synthesis, GTM planning, and experiments so each tab has one job.",
        "Read left to right: orient -> read macro signals -> study competitors -> synthesize positioning -> plan GTM -> run experiments."
    )
    render_question_framework()

    st.header("Signal Map")
    render_story_card(
        "From data source to decision",
        "Each signal exists because it informs a specific market-entry decision.",
        "Google Trends and YouTube/PAA language are macro market signals for brand positioning. Competitor data informs pricing, menu, design, and experience choices. Census data belongs with GTM because it informs where physical tests may happen.",
        "This keeps evidence and decisions connected without repeating the same insight across multiple tabs."
    )
    render_signal_map()

    st.header("Dashboard Journey")
    journey = pd.DataFrame([
        {"Tab": "1. Market Questions", "Purpose": "Frame what the dashboard must answer.", "Decisions Supported": "What evidence do we need before entering the US market?"},
        {"Tab": "2. Macro Signals", "Purpose": "Read category awareness and consumer language.", "Decisions Supported": "Which market narratives and consumer frictions should inform brand positioning?"},
        {"Tab": "3. Competitor Intelligence", "Purpose": "Compare ecommerce vendors and cafe/retail benchmarks.", "Decisions Supported": "How should Southern Frontier think about pricing, assortment, menu, design, and experience cues?"},
        {"Tab": "4. Brand Positioning", "Purpose": "Synthesize macro and competitor evidence into positioning options.", "Decisions Supported": "What promise, audience, and message angles should be tested first?"},
        {"Tab": "5. GTM Strategy", "Purpose": "Translate positioning into staged launch choices.", "Decisions Supported": "Website, physical proof lab, ecommerce roadmap, and metro prioritization."},
        {"Tab": "6. Learning Loop", "Purpose": "Turn strategy into experiments and decisions.", "Decisions Supported": "What did we test, what happened, and what changed?"},
    ])
    show_table(
        journey,
        "Dashboard information architecture.",
        "Each tab owns one decision domain to avoid duplicate evidence and conclusions.",
        full_text=True,
    )

with tab_macro:
    st.header("Macro Signals")
    render_story_card(
        "Market and consumer context",
        "Google search trends and YouTube/PAA language are macro signals, not tactical GTM outputs by themselves.",
        "Together, they show whether Pu'er has category awareness, which adjacent beverage behaviors matter, and what language or friction should shape brand positioning.",
        "Use this tab to understand the market narrative before evaluating competitors or GTM channels."
    )

    st.subheader("Google Trends: Category Awareness and Adjacent Demand")
    render_story_card(
        "How to read this",
        "Google Trends scales are normalized within each query payload, so cross-chart 80s are not equal.",
        "Adjacent beverage terms and Pu'er spelling variants answer different questions. Adjacent terms show familiar demand pools; Pu'er variants show awareness and spelling fragmentation.",
        "For brand positioning, the practical question is whether Southern Frontier should lead with Pu'er directly or enter through adjacent behaviors such as matcha, coffee alternatives, gut health, and daily ritual."
    )
    if not trends_df.empty:
        trend_keywords = sorted(trends_df["keyword"].dropna().unique())
        render_source_note(
            "Google Trends via pytrends, stored in google_trends_data.",
            f"Current pipeline/data are US-only. Stored keywords: {', '.join(trend_keywords)}."
        )

        trends_for_chart = trends_df.copy()
        trends_for_chart["interest"] = pd.to_numeric(trends_for_chart["interest"], errors="coerce")
        trends_for_chart = trends_for_chart.dropna(subset=["date", "interest", "keyword"])
        trends_for_chart["family"] = trends_for_chart["keyword"].apply(trend_family)
        benchmark_df = trends_for_chart[trends_for_chart["family"] == "Adjacent benchmark"]
        puer_df = trends_for_chart[trends_for_chart["family"] == "Pu'er variants"]

        if not puer_df.empty:
            strongest_spelling = puer_df.groupby('keyword')['interest'].mean().idxmax()
            st.markdown(f"**Pu'er Spelling Variants** (Strongest: `{strongest_spelling}`)")
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
            st.altair_chart((puer_chart + labels_puer).properties(height=320), width="stretch")

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
            st.altair_chart((bench_chart + labels).properties(height=320), width="stretch")

        clean_indexed_trends_df = indexed_trends_df.dropna(subset=["date", "indexed_interest", "keyword"]) if not indexed_trends_df.empty else pd.DataFrame()
        if not clean_indexed_trends_df.empty:
            st.markdown("**Indexed Growth View, First Non-Zero Week = 100**")
            render_source_note(
                "Derived from google_trends_data.",
                "This view compares growth direction rather than absolute volume. It is safer for comparing terms collected in different Google Trends payloads."
            )
            max_date_idx = clean_indexed_trends_df['date'].max()
            label_df_idx = clean_indexed_trends_df[clean_indexed_trends_df['date'] == max_date_idx]
            idx_chart = alt.Chart(clean_indexed_trends_df).mark_line(strokeWidth=2).encode(
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
            st.altair_chart((idx_chart + labels_idx).properties(height=320), width="stretch")
    else:
        st.info("No Google Trends data available yet.")

    st.header("YouTube and Search-Language Insights")
    render_story_card(
        "Consumer language as macro signal",
        "YouTube transcripts and People Also Ask snippets reveal how consumers talk about adjacent rituals, energy, purity, brewing, and intimidation.",
        "These are not final customer segments; they are market-language signals that help decide what Southern Frontier should explain, emphasize, or avoid in brand positioning.",
        "Use these charts to translate messy qualitative language into positioning hypotheses."
    )
    if signal_summary:
        score_text = " ".join([
            f"<span class='evidence-pill'>{escape(label.replace('_', ' ').title())}: {score:.1f}/10</span>"
            for label, score in signal_summary["scores"].items()
        ])
        st.markdown(score_text, unsafe_allow_html=True)
        st.subheader("Consumer Desire Scorecard")
        render_consumer_desire_chart(signal_summary)
        render_story_card(
            "What the language is saying",
            f"The leading macro language vector is {signal_summary['top_signal']}.",
            "The brand should choose one primary promise for the first launch campaign, then use the other vectors as supporting proof.",
            "A focused brand wedge is easier to test than a broad claim that tries to be heritage, wellness, luxury, taste, ritual, and energy all at once."
        )

    st.subheader("Brand Alignment Over Time")
    if 'source_url' not in df.columns:
        df['source_url'] = None
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date
    chart_data = df.groupby('timestamp')['premium_accessibility_score'].mean().reset_index()
    chart_data.columns = ["Date", "Avg Brand Alignment"]
    chart_data = chart_data.dropna(subset=["Date", "Avg Brand Alignment"])
    if not chart_data.empty:
        render_source_note(
            "friction_data table.",
            "premium_accessibility_score = average of transparency_desire, brewing_theater, and grounded_energy_desire from Gemini-scored PAA/transcript snippets."
        )
        alignment_chart = alt.Chart(chart_data).mark_line(strokeWidth=2.5, color="#2B4533").encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Avg Brand Alignment:Q", title="Avg Brand Alignment Score", scale=alt.Scale(domain=[0, 10])),
            tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Avg Brand Alignment:Q", format=".1f")],
        ).properties(height=300)
        st.altair_chart(alignment_chart, width="stretch")
    else:
        st.info("No time-series alignment data available yet.")

    st.subheader("High-Signal Language Evidence")
    render_story_card(
        "Why these excerpts matter",
        "These are the snippets most likely to contain usable customer language.",
        "When writing ads, packaging, creator briefs, or landing pages, this table should be mined for phrases that make the customer feel recognized.",
        "The current filter shows records with strong grounded-energy or transparency scores."
    )
    high_theater_df = df[(df['transparency_desire'] >= 8) | (df['grounded_energy_desire'] >= 8)].copy()
    if not high_theater_df.empty:
        engagement_cols = [
            col for col in [
                'youtube_title', 'youtube_channel', 'youtube_view_count',
                'youtube_like_count', 'youtube_comment_count', 'youtube_search_query'
            ]
            if col in high_theater_df.columns
        ]
        cols_to_show = [
            'source_type', *engagement_cols, 'transparency_desire',
            'grounded_energy_desire', 'summary', 'source_text', 'source_url'
        ]
        show_table(
            high_theater_df[cols_to_show],
            "friction_data table from Google PAA and YouTube transcripts, scored by Gemini.",
            "Rows shown have transparency_desire >= 8 or grounded_energy_desire >= 8.",
            full_text=True,
            column_config={
                "source_url": st.column_config.LinkColumn("Source Link"),
                "source_type": st.column_config.TextColumn("Source", width="small"),
                "youtube_view_count": st.column_config.NumberColumn("YouTube Views", format="%d"),
                "youtube_like_count": st.column_config.NumberColumn("YouTube Likes", format="%d"),
                "youtube_comment_count": st.column_config.NumberColumn("YouTube Comments", format="%d"),
            }
        )
    else:
        st.info("No highly aligned consumer records found yet.")

with tab_competitors:
    st.header("Competitor Intelligence")
    render_story_card(
        "Two competitor lenses",
        "Competitor intelligence deserves its own tab because it informs concrete execution choices.",
        "Ecommerce vendors inform product architecture, pricing, proof language, merchandising, and future online conversion. Cafe and retail competitors inform menu, drink format, ritual theater, service design, visual language, and cafe-to-product bridge.",
        "Use this tab to decide what Southern Frontier should borrow, avoid, price against, and visually differentiate from."
    )

    st.header("Ecommerce Vendor Intelligence")
    render_story_card(
        "What this informs",
        "Ecommerce vendor data helps benchmark pricing, product formats, and how well vendors balance cultural credibility with modern accessibility.",
        "This matters even before Southern Frontier launches ecommerce because the website still needs education, proof, and future product architecture.",
        "The goal is to find pricing permission and positioning whitespace, not to copy existing tea shops."
    )
    if not comp_df.empty:
        if {"price_usd", "positioning_score", "vendor"}.issubset(comp_df.columns):
            st.subheader("Modern Authenticity by Vendor")
            render_story_card(
                "Whitespace lens",
                "This bubble chart compares vendors by average observed product price and average Modern Authenticity score.",
                "For brand positioning, the vendor-level view is more useful than one dot per product because customers experience the vendor as one brand world.",
                "Look for brands that are high-priced but low-accessibility, or modern-looking but weak on cultural credibility. Those gaps inform Southern Frontier's positioning."
            )
            bubble_source_df = comp_df.copy()
            bubble_source_df["price_usd"] = pd.to_numeric(bubble_source_df["price_usd"], errors="coerce")
            bubble_source_df["positioning_score"] = pd.to_numeric(bubble_source_df["positioning_score"], errors="coerce")
            bubble_source_df = bubble_source_df.dropna(subset=["vendor", "price_usd", "positioning_score"])
            if not bubble_source_df.empty:
                plot_df = bubble_source_df.groupby("vendor").agg(
                    avg_price_usd=("price_usd", "mean"),
                    avg_positioning_score=("positioning_score", "mean"),
                    products=("vendor", "size"),
                ).reset_index().rename(columns={
                    "vendor": "Vendor",
                    "avg_price_usd": "Avg Price USD",
                    "avg_positioning_score": "Avg Modern Authenticity",
                    "products": "Observed Products",
                })
                base_chart = alt.Chart(plot_df).encode(
                    x=alt.X("Avg Price USD:Q", title="Average Observed Product Price, USD"),
                    y=alt.Y("Avg Modern Authenticity:Q", title="Average Modern Authenticity Score", scale=alt.Scale(domain=[0, 10])),
                    tooltip=[
                        alt.Tooltip("Vendor:N"),
                        alt.Tooltip("Avg Price USD:Q", format="$.2f"),
                        alt.Tooltip("Avg Modern Authenticity:Q", format=".1f"),
                        alt.Tooltip("Observed Products:Q"),
                    ],
                )
                points = base_chart.mark_circle(color="#A0442D", opacity=0.78).encode(
                    size=alt.Size("Observed Products:Q", title="Observed Products", scale=alt.Scale(range=[80, 700])),
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

                st.subheader("Pu'er Landscape by Vendor (Pu'er Products Only)")
                render_story_card(
                    "Pu'er Benchmarking",
                    "This chart filters the dataset to only include Pu'er tea products, showing the average price and authenticity for Pu'er items across all vendors.",
                    "Comparing these vendors shows the competitive landscape Southern Frontier is entering.",
                    "Notice if any vendors occupy the high-authenticity + high-accessibility quadrant."
                )
                
                puer_mask = bubble_source_df["title"].str.lower().str.contains("puer|pu'er|pu-erh|pu erh|puerh", na=False) | \
                            bubble_source_df["product_type"].str.lower().str.contains("puer|pu'er|pu-erh|pu erh|puerh", na=False) | \
                            bubble_source_df["description"].str.lower().str.contains("puer|pu'er|pu-erh|pu erh|puerh", na=False) | \
                            bubble_source_df["vendor"].str.lower().str.contains("puer|pu'er|pu-erh|pu erh|puerh", na=False)
                
                puer_bubble_source = bubble_source_df[puer_mask]
                
                if not puer_bubble_source.empty:
                    puer_plot_df = puer_bubble_source.groupby("vendor").agg(
                        avg_price_usd=("price_usd", "mean"),
                        avg_positioning_score=("positioning_score", "mean"),
                        products=("vendor", "size"),
                    ).reset_index().rename(columns={
                        "vendor": "Vendor",
                        "avg_price_usd": "Avg Price USD",
                        "avg_positioning_score": "Avg Modern Authenticity",
                        "products": "Observed Products",
                    })
                    
                    base_chart_puer = alt.Chart(puer_plot_df).encode(
                        x=alt.X("Avg Price USD:Q", title="Average Observed Product Price, USD"),
                        y=alt.Y("Avg Modern Authenticity:Q", title="Average Modern Authenticity Score", scale=alt.Scale(domain=[0, 10])),
                        tooltip=[
                            alt.Tooltip("Vendor:N"),
                            alt.Tooltip("Avg Price USD:Q", format="$.2f"),
                            alt.Tooltip("Avg Modern Authenticity:Q", format=".1f"),
                            alt.Tooltip("Observed Products:Q"),
                        ],
                    )
                    points_puer = base_chart_puer.mark_circle(color="#2B4533", opacity=0.85).encode(
                        size=alt.Size("Observed Products:Q", title="Observed Products", scale=alt.Scale(range=[100, 800])),
                    )
                    labels_puer = base_chart_puer.mark_text(
                        align="left",
                        baseline="middle",
                        dx=10,
                        fontSize=12,
                        fontWeight="bold",
                        color="#1A1A1A",
                    ).encode(text="Vendor:N")
                    st.altair_chart((points_puer + labels_puer).properties(height=380), width="stretch")
                    show_table(
                        puer_plot_df.sort_values("Avg Modern Authenticity", ascending=False),
                        "competitor_products table, filtered to pure-play Pu'er vendors.",
                    )
                else:
                    st.info("No Pu'er specialist vendors found in the current dataset.")
            else:
                st.info("No valid vendor price and positioning rows are available for this chart.")

        if {"vendor", "product_type", "price_usd"}.issubset(comp_df.columns):
            st.subheader("Average Price by Vendor")
            price_source_df = comp_df.copy()
            price_source_df["price_usd"] = pd.to_numeric(price_source_df["price_usd"], errors="coerce")
            price_source_df = price_source_df.dropna(subset=["vendor", "price_usd"])
            price_df = price_source_df.groupby(['vendor', 'product_type'])['price_usd'].mean().reset_index()
            vendor_price_df = price_source_df.groupby("vendor").agg(
                avg_price_usd=("price_usd", "mean"),
                products=("vendor", "size"),
            ).reset_index().sort_values("avg_price_usd", ascending=False).head(20).rename(columns={
                "vendor": "Vendor",
                "avg_price_usd": "Average Price USD",
                "products": "Observed Products",
            })
            render_ranked_bar_chart(
                vendor_price_df,
                "Average Price USD",
                "Vendor",
                ["Vendor", "Average Price USD", "Observed Products"],
                title="Average Price, USD",
                color="#A0442D",
                height=460,
            )
            show_table(
                price_df.rename(columns={
                    "vendor": "Vendor",
                    "product_type": "Product Type",
                    "price_usd": "Average Price USD",
                }),
                "Shopify /products.json endpoints stored in competitor_products.",
                "Grouped by vendor and product_type; mean price of observed products.",
            )

        st.subheader("Positioning Whitespace Candidates")
        render_story_card(
            "Why these rows matter",
            "Low-scoring products are not necessarily bad products. They are examples where copy may leave a modern US customer confused, underwhelmed, or unsure why the product matters.",
            "These are useful references for what Southern Frontier can improve: clearer benefits, cleaner packaging language, better origin proof, and a more accessible ritual.",
            "The current rule flags products with a modern-authenticity score at or below 4."
        )
        if 'product_url' not in comp_df.columns:
            comp_df['product_url'] = None
        if "positioning_score" in comp_df.columns:
            weak_df = comp_df[comp_df['positioning_score'] <= 4].copy()
            if not weak_df.empty:
                cols_to_show = ['vendor', 'title', 'product_type', 'price_usd', 'positioning_score', 'product_url']
                cols_to_show = [col for col in cols_to_show if col in weak_df.columns]
                show_table(
                    weak_df[cols_to_show],
                    "competitor_products table from Shopify product feeds, scored by Gemini using the Modern Authenticity rubric.",
                    "Rows shown have positioning_score <= 4 and are treated as copy/positioning whitespace candidates.",
                    column_config={"product_url": st.column_config.LinkColumn("Product Link")}
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
            st.info("Positioning scores are not available in the current competitor table.")
    else:
        st.info("No ecommerce competitor data available yet.")

    st.header("Cafe and Retail Competitor Intelligence")
    render_story_card(
        "What this informs",
        "Cafe and retail benchmarks are the right lens for menu, drink architecture, ritual theater, design language, and the bridge from first sip to future product purchase.",
        "This is not about copying their store footprint. It is about learning which experience cues make an unfamiliar tea desirable enough to join a list, attend a tasting, start a partnership conversation, or later buy online.",
        "The strongest competitor lessons should feed the GTM physical proof lab and future menu design."
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

    st.subheader("Collected Cafe / Retail Signals")
    if not cafe_signal_df.empty:
        signal_display = cafe_signal_df[["competitor_name", "signal_type", "title", "snippet", "url"]].rename(columns={
            "competitor_name": "Competitor",
            "signal_type": "Signal Type",
            "title": "Title",
            "snippet": "Snippet",
            "url": "Source Link",
        })
        show_table(
            signal_display,
            "cafe_retail_signals table populated by cafe_competitor_pipeline.py via Serper search.",
            "Collected public signals: menu/drink pricing snippets, review language, visual/store cues, and cafe-to-product bridge evidence.",
            full_text=True,
            column_config={"Source Link": st.column_config.LinkColumn("Source Link")},
        )
    else:
        st.info("No cafe retail signal rows found yet. Run cafe_competitor_pipeline.py to collect public search evidence.")

with tab_positioning:
    st.header("Brand Positioning")
    render_story_card(
        "Synthesis from macro and competitors",
        "This tab distills macro market signals and competitor intelligence into brand-positioning hypotheses.",
        "Google Trends and YouTube/PAA language inform what the market understands and fears. Competitor intelligence shows the gaps in pricing, education, menu, design, and experience. The output here is not final strategy; it is what to test next.",
        "Keep this tab synthesis-only so it does not duplicate the evidence tabs."
    )
    render_strategic_insight_overview(signal_summary, comp_summary, launch_market_df)

    st.header("Audience and Message Prioritization")
    render_story_card(
        "From language to launch audiences",
        "The dashboard turns raw consumer language into actionable audience and message hypotheses.",
        "This segment model is intentionally simple and explainable for a case study. It should guide product format, channel, offer, and message tests, not replace real customer research.",
        "Use the scores as a prioritization queue for experiments."
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
        st.subheader("Segment Opportunity Ranking")
        render_ranked_bar_chart(
            display_segments,
            "Opportunity Score",
            "Segment",
            ["Segment", "Opportunity Score", "Mentions", "Alignment", "Transparency", "Ritual", "Energy"],
            title="Opportunity Score",
            color="#2B4533",
            height=260,
        )
        show_table(
            display_segments,
            "friction_data table populated by Google People Also Ask and YouTube transcript collection, scored by Gemini.",
            "Segments are classified by Gemini. Opportunity Score (0-100) = alignment (40%) + volume rank (30%).",
        )

        st.subheader("Recommended Test Queue")
        show_table(
            opportunity_df[["Opportunity", "Segment", "Score", "Recommended test"]] if not opportunity_df.empty else pd.DataFrame(),
            "Derived from macro language signals, directional trend context, and competitor whitespace assumptions.",
            "Each row should become an experiment before it is treated as a GTM decision.",
        )
    else:
        st.info("No segment table is available yet.")

    st.header("Message Tests")
    render_story_card(
        "From insight to copy hypotheses",
        "Generated value propositions are test assets, not final brand copy.",
        "The generator now uses a broader evidence packet: macro signals, consumer language, ecommerce competitor gaps, cafe/retail benchmarks, brand context, GTM context, and market prioritization.",
        "Every generated rationale should cite cross-dashboard evidence IDs, not just a few YouTube snippets."
    )
    top_records = df.nlargest(20, 'premium_accessibility_score')
    evidence_sections = build_value_prop_evidence_packet(
        top_records=top_records,
        trend_summary=trend_summary,
        signal_summary=signal_summary,
        comp_summary=comp_summary,
        comp_df=comp_df,
        cafe_comp_df=cafe_comp_df,
        launch_market_df=launch_market_df,
        opportunity_df=opportunity_df,
    )
    with st.expander("Broad evidence packet used for generated copy", expanded=False):
        for section in evidence_sections:
            st.markdown(f"**{section['id']} - {section['title']}**\n\n{section['body']}")
    if st.button("Re-generate Value Props from Full Evidence Packet", type="primary"):
        with st.spinner("Synthesizing macro, competitor, brand, GTM, and consumer evidence..."):
            value_props = generate_value_props(evidence_sections)
            if value_props:
                save_value_props(value_props)
                st.success("Value Propositions Generated and Saved!")
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
        st.info("No value props generated yet. Click 'Re-generate Value Props from Full Evidence Packet' to create your first set.")

with tab_gtm:
    st.header("GTM Strategy")
    render_story_card(
        "From positioning to market entry",
        "The recommended strategy is staged: website first, one physical proof lab second, ecommerce later.",
        "Macro signals inform the brand story. Competitor intelligence informs pricing, menu, design, and experience. Census data belongs here because it helps prioritize where physical tests, pop-ups, partnerships, or a future storefront could happen.",
        "This tab converts positioning into channel and market-entry decisions."
    )
    render_staged_gtm_strategy()

    st.header("Physical Proof Lab and Cafe Bridge")
    render_story_card(
        "Role of the physical experience",
        "Southern Frontier is not only a tea product brand; it is a hospitality and ritual brand.",
        "The US strategy does not need a costly multi-store rollout. One flagship, pop-up, or partner experience can become a learning lab, content engine, sensory proof point, and lead-capture bridge while ecommerce remains a future roadmap layer.",
        "Use competitor intelligence to shape the menu and experience; use Census and partner signals to decide where to test."
    )
    cols = st.columns(4)
    cols[0].metric("Experience Wedge", "To-go + ritual")
    cols[1].metric("Bridge Drink", "Pu'er latte")
    cols[2].metric("Trust Cue", "Visible proof")
    cols[3].metric("Home Bridge", "Sampler / bundle")

    st.subheader("One Flagship to Lead-Capture and Future Commerce Bridge")
    render_website_links(["Flagship Store", "Products"])
    show_table(
        build_cafe_bridge_table(),
        "Derived from Southern Frontier website product and store positioning.",
        "Maps high-touch flagship moments to near-term lead capture, content, partnership, and future commerce paths.",
        full_text=True,
    )

    st.header("Launch-Market Prioritization")
    render_story_card(
        "Census-powered GTM lens",
        "The dashboard ranks US metro areas for early testing potential.",
        "This uses Census ACS population, household income, higher-education proxy, and Asian diaspora share where available. It should guide where to test partnerships, creator seeding, cafe collaborations, events, and paid geo-targeting first.",
        "This is a GTM prioritization input, not an automatic lease-location recommendation."
    )
    if not launch_market_df.empty:
        top_market = launch_market_df.iloc[0]
        cols = st.columns(4)
        cols[0].metric("Top Launch Market", top_market["geography"].replace(" Metro Area", "").replace(" Micro Area", ""))
        cols[1].metric("Launch Score", f"{top_market['launch_score']:.1f}")
        cols[2].metric("Median Income", f"${top_market['median_household_income']:,.0f}")
        cols[3].metric("Population", f"{top_market['population']:,.0f}")
        st.subheader("Top Launch Markets by Score")
        render_launch_market_chart(launch_market_df)
        has_asian = "asian_population_pct" in launch_market_df.columns
        display_cols = ["geography", "launch_score", "Strategic read", "population", "median_household_income", "education_proxy"]
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
        market_display = launch_market_df.head(25)[[c for c in display_cols if c in launch_market_df.columns]].rename(columns=rename_map)
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

    st.subheader("What Still Needs Manual or Specialized Collection")
    next_collection = pd.DataFrame([
        {"Data": "Verified menu prices", "Why": "Search snippets expose menu hints, but exact drink prices need menu pages, photos, or manual capture.", "Possible Source": "Official menus, Google Business photos, manual capture"},
        {"Data": "Flagship-market fit", "Why": "Choose one store or pop-up city based on learning value, content potential, partner access, and brand-signal quality.", "Possible Source": "Census launch-market table, cafe competitor density, creator/community presence"},
        {"Data": "Cafe-to-lead conversion", "Why": "Measure whether a limited physical experience can drive newsletter signups, tasting RSVPs, partner conversations, and future commerce intent.", "Possible Source": "Future Southern Frontier tests: QR codes, email capture, landing pages, partner inquiry forms"},
    ])
    show_table(
        next_collection,
        "Proposed GTM data collection plan.",
        "These collection gaps connect physical-market selection to measurable learning.",
        full_text=True,
    )

with tab_learning_loop:
    st.header("Learning Loop")
    render_story_card(
        "Why this completes the loop",
        "The dashboard should not end at insight. Each finding needs a lightweight market test so you can learn before committing brand, product, or channel budget.",
        "This tracker turns the analysis into a repeatable operating system: hypothesis, audience, channel, creative angle, success metric, result, decision.",
        "For the AI/DS case study, this is where analytics becomes an experiment backlog."
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

    st.markdown("---")
    st.subheader("Decisions Log")
    render_story_card(
        "From experiments to decisions",
        "Experiments produce results, but results need decisions.",
        "Track what was decided, what evidence it was based on, who owns it, and whether it has been executed.",
        "This closes the loop from data -> experiment -> decision -> action."
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
