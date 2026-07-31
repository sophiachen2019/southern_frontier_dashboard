import json
import os
import time
from datetime import datetime

import psycopg2
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from psycopg2.extras import execute_values
from pydantic import BaseModel, Field

load_dotenv()

NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


CAFE_COMPETITORS = [
    ("Blue Bottle", "Specialty coffee", "https://bluebottlecoffee.com", "Premium daily coffee ritual and minimalist cafe design"),
    ("% Arabica", "Design-led coffee", "https://arabica.coffee", "Global cafe-as-brand-world model with strong visual consistency"),
    ("Asha Tea House", "Modern tea cafe", "https://ashateahouse.com", "Tea-forward cafe format with approachable premium drinks"),
    ("Boba Guys", "Premium milk tea", "https://www.bobaguys.com", "Mainstreamed premium Asian tea drinks in the US"),
    ("Chicha San Chen", "Premium brewed tea drinks", "https://www.chichasanchen.com", "Visible brewing craft and modern tea drink retail"),
    ("HeyTea", "Modern Chinese tea drinks", "https://www.heytea.com", "Tea-as-lifestyle beverage model with strong signature SKUs"),
    ("Matcha Cafe Maiko", "Matcha cafe", "https://www.matchacafe-maiko.com", "Matcha ritual, desserts, and accessible premium Japanese tea cues"),
]


SIGNAL_QUERIES = {
    "Menu / drink pricing": "{name} menu prices signature drinks",
    "Review language": "{name} reviews atmosphere service drinks",
    "Visual / store cues": "{name} cafe interior design photos brand experience",
    "Cafe-to-product bridge": "{name} packaged products subscription gift set retail",
}


class CafePositioningScore(BaseModel):
    visual_positioning_score: int = Field(description="1-10 for modern premium visual/brand positioning")
    ritual_theater_score: int = Field(description="1-10 for visible ritual, craft, brewing, or experience theater")
    speed_ritual_duality_score: int = Field(description="1-10 for serving both fast to-go and slower ritual occasions")
    cafe_to_product_bridge_score: int = Field(description="1-10 for ability to convert cafe trial into packaged/home products")
    overall_positioning_score: int = Field(description="1-10 overall relevance as a Southern Frontier cafe/retail benchmark")
    signature_drinks: str = Field(description="Short summary of visible signature drinks or menu angle")
    experience_notes: str = Field(description="Short summary of store/cafe experience positioning")
    review_language: str = Field(description="Short summary of customer/review/search language")


def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cafe_competitors (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            category TEXT,
            website TEXT,
            rationale TEXT,
            collected_at TIMESTAMP,
            menu_url TEXT,
            avg_drink_price_usd FLOAT,
            signature_drinks TEXT,
            experience_notes TEXT,
            review_language TEXT,
            visual_positioning_score FLOAT,
            ritual_theater_score FLOAT,
            speed_ritual_duality_score FLOAT,
            cafe_to_product_bridge_score FLOAT,
            overall_positioning_score FLOAT,
            search_evidence TEXT,
            source_urls TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cafe_retail_signals (
            id SERIAL PRIMARY KEY,
            competitor_name TEXT,
            category TEXT,
            signal_type TEXT,
            query TEXT,
            title TEXT,
            snippet TEXT,
            url TEXT,
            collected_at TIMESTAMP,
            UNIQUE(competitor_name, signal_type, url)
        )
    """)
    for column, column_type in [
        ("speed_ritual_duality_score", "FLOAT"),
        ("overall_positioning_score", "FLOAT"),
        ("search_evidence", "TEXT"),
        ("source_urls", "TEXT"),
    ]:
        cur.execute(f"ALTER TABLE cafe_competitors ADD COLUMN IF NOT EXISTS {column} {column_type};")
    conn.commit()
    return conn, cur


def search_serper(query, num=5):
    if not SERPER_API_KEY:
        raise RuntimeError("Set SERPER_API_KEY in .env first.")

    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        data=json.dumps({"q": query, "num": num}),
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("organic", [])


def collect_competitor_evidence(name, category):
    snippets = []
    urls = []
    signal_rows = []
    for signal_type, query_template in SIGNAL_QUERIES.items():
        query = query_template.format(name=name)
        for result in search_serper(query, num=5):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            link = result.get("link", "")
            if title or snippet:
                snippets.append(f"Query: {query}\nTitle: {title}\nSnippet: {snippet}\nURL: {link}")
            if link:
                urls.append(link)
            signal_rows.append((name, category, signal_type, query, title, snippet, link, datetime.now()))
    return "\n\n".join(snippets[:16]), "\n".join(dict.fromkeys(urls[:12])), signal_rows


def score_competitor(client, name, category, rationale, evidence):
    prompt = """
You are a brand strategist scoring cafe, coffee, tea shop, and beverage competitors for Southern Frontier, a premium Pu'er tea brand.

Southern Frontier's US GTM will likely run ecommerce and one flagship/popup experience in parallel. The store is not mainly a distribution scale strategy. It is a learning lab, content engine, trust proof point, and conversion bridge into ecommerce, gifting, subscriptions, wholesale, and partnerships.

Score the competitor from 1-10 on:
- visual_positioning_score: modern premium visual/brand positioning.
- ritual_theater_score: visible craft, brewing, tea/coffee ritual, tasting, or hospitality theater.
- speed_ritual_duality_score: ability to serve both fast to-go lifestyle and slower ritual/experiential occasions.
- cafe_to_product_bridge_score: ability to convert cafe trial into home products, packaged goods, subscription, or gifting.
- overall_positioning_score: usefulness as a benchmark for Southern Frontier.

Also summarize signature_drinks, experience_notes, and review_language. Use only the provided evidence and make uncertainty visible.
"""
    text = f"Name: {name}\nCategory: {category}\nRationale: {rationale}\nEvidence:\n{evidence}"
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=[prompt, text],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CafePositioningScore,
            temperature=0.2,
        ),
    )
    return json.loads(response.text)


def main():
    print("Starting cafe/retail competitor pipeline...")
    conn, cur = setup_database()
    client = genai.Client(api_key=GEMINI_API_KEY)

    records = []
    signal_records = []
    for name, category, website, rationale in CAFE_COMPETITORS:
        print(f"Collecting evidence for {name}...")
        evidence, source_urls, competitor_signal_records = collect_competitor_evidence(name, category)
        signal_records.extend(competitor_signal_records)
        print(f"Scoring {name}...")
        score = score_competitor(client, name, category, rationale, evidence)
        records.append((
            name,
            category,
            website,
            rationale,
            datetime.now(),
            score.get("signature_drinks", ""),
            score.get("experience_notes", ""),
            score.get("review_language", ""),
            score.get("visual_positioning_score"),
            score.get("ritual_theater_score"),
            score.get("speed_ritual_duality_score"),
            score.get("cafe_to_product_bridge_score"),
            score.get("overall_positioning_score"),
            evidence[:8000],
            source_urls,
        ))
        time.sleep(4.5)

    execute_values(
        cur,
        """
        INSERT INTO cafe_competitors
        (name, category, website, rationale, collected_at, signature_drinks,
         experience_notes, review_language, visual_positioning_score, ritual_theater_score,
         speed_ritual_duality_score, cafe_to_product_bridge_score, overall_positioning_score,
         search_evidence, source_urls)
        VALUES %s
        ON CONFLICT (name) DO UPDATE SET
            category = EXCLUDED.category,
            website = EXCLUDED.website,
            rationale = EXCLUDED.rationale,
            collected_at = EXCLUDED.collected_at,
            signature_drinks = EXCLUDED.signature_drinks,
            experience_notes = EXCLUDED.experience_notes,
            review_language = EXCLUDED.review_language,
            visual_positioning_score = EXCLUDED.visual_positioning_score,
            ritual_theater_score = EXCLUDED.ritual_theater_score,
            speed_ritual_duality_score = EXCLUDED.speed_ritual_duality_score,
            cafe_to_product_bridge_score = EXCLUDED.cafe_to_product_bridge_score,
            overall_positioning_score = EXCLUDED.overall_positioning_score,
            search_evidence = EXCLUDED.search_evidence,
            source_urls = EXCLUDED.source_urls
        """,
        records,
    )
    execute_values(
        cur,
        """
        INSERT INTO cafe_retail_signals
        (competitor_name, category, signal_type, query, title, snippet, url, collected_at)
        VALUES %s
        ON CONFLICT (competitor_name, signal_type, url) DO UPDATE SET
            category = EXCLUDED.category,
            query = EXCLUDED.query,
            title = EXCLUDED.title,
            snippet = EXCLUDED.snippet,
            collected_at = EXCLUDED.collected_at
        """,
        signal_records,
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Saved {len(records)} scored cafe/retail competitors and {len(signal_records)} raw signal rows.")


if __name__ == "__main__":
    main()
