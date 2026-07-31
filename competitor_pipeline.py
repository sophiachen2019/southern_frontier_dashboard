import os
import json
import requests
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")

class PositioningScore(BaseModel):
    positioning_score: int = Field(description="Score 1-10 on Modern Authenticity Positioning")


def infer_weight_grams(text):
    if not text:
        return None

    matches = re.findall(r"(\d+(?:\.\d+)?)\s?(kg|kilogram|kilograms|g|gram|grams)", text.lower())
    candidates = []
    for value, unit in matches:
        grams = float(value) * 1000 if unit.startswith("kg") or unit.startswith("kilogram") else float(value)
        if 1 <= grams <= 5000:
            candidates.append(grams)
    return min(candidates) if candidates else None

def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS competitor_products (
            id SERIAL PRIMARY KEY,
            vendor VARCHAR(100),
            title VARCHAR(255),
            product_type VARCHAR(100),
            price_usd FLOAT,
            description TEXT,
            positioning_score INT,
            timestamp TIMESTAMP,
            product_url TEXT,
            inferred_weight_g FLOAT,
            price_per_100g FLOAT
        )
    """)
    cur.execute("ALTER TABLE competitor_products ADD COLUMN IF NOT EXISTS product_url TEXT;")
    cur.execute("ALTER TABLE competitor_products ADD COLUMN IF NOT EXISTS inferred_weight_g FLOAT;")
    cur.execute("ALTER TABLE competitor_products ADD COLUMN IF NOT EXISTS price_per_100g FLOAT;")
    conn.commit()
    return conn, cur

def fetch_shopify_products(vendor_name, base_url):
    products_data = []
    url = f"{base_url}/products.json?limit=15"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            products = data.get('products', [])
            for p in products:
                title = p.get('title', '')
                product_type = p.get('product_type', 'Unknown')
                if not product_type:
                    product_type = 'Unknown'
                body_html = p.get('body_html', '')
                if not body_html:
                    body_html = ''
                
                soup = BeautifulSoup(body_html, 'html.parser')
                description = soup.get_text(separator=' ', strip=True)
                
                price = 0.0
                variants = p.get('variants', [])
                if variants:
                    try:
                        price = float(variants[0].get('price', 0))
                    except ValueError:
                        price = 0.0
                        
                handle = p.get('handle', '')
                
                if description and price > 0:
                    inferred_weight_g = infer_weight_grams(f"{title} {description}")
                    price_per_100g = (price / inferred_weight_g) * 100 if inferred_weight_g else None
                    products_data.append({
                        "vendor": vendor_name,
                        "title": title[:250],
                        "product_type": product_type,
                        "price_usd": price,
                        "description": description[:1000],
                        "product_url": f"{base_url}/products/{handle}" if handle else "",
                        "inferred_weight_g": inferred_weight_g,
                        "price_per_100g": price_per_100g
                    })
        else:
            print(f"Failed to fetch {url}: {response.status_code}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return products_data

def analyze_positioning(client, title, description):
    prompt = """
You are a brand strategist analyzing competitor product descriptions in the specialty tea space.
Score this product's copy on a scale of 1-10 for "Modern Authenticity Positioning".
- A score of 10 means the brand successfully bridges ancient heritage with modern, transparent, premium design. It feels rooted in tradition (ancient trees, resilience) but is highly accessible, clean, and modern.
- A score of 1 means the brand is either too sterile and soulless, OR overly esoteric, confusing, and dusty.
Return only the JSON output.
"""
    try:
        text = f"Title: {title}\nDescription: {description}"
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[prompt, text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PositioningScore,
                temperature=0.1,
            ),
        )
        time.sleep(4.5)  # Rate limiting
        return json.loads(response.text).get('positioning_score', 5)
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Error scoring '{title[:50]}': {e}")
        return None  # Return None instead of 5 to avoid biasing averages

def main():
    print("Starting Competitor Pipeline...")
    
    vendors = [
        {"name": "Kuura", "url": "https://kuura.co"},
        {"name": "White2Tea", "url": "https://white2tea.com"},
        {"name": "Yunnan Sourcing", "url": "https://yunnansourcing.com"},
        {"name": "Crimson Lotus Tea", "url": "https://crimsonlotustea.com"},
        {"name": "Ippodo Tea", "url": "https://ippodotea.com"},
        {"name": "Teas We Like", "url": "https://teaswelike.com"},
        {"name": "Farmerleaf", "url": "https://www.farmer-leaf.com"},
        {"name": "Bitterleaf Teas", "url": "https://www.bitterleafteas.com"}
    ]
    
    all_products = []
    for vendor in vendors:
        print(f"Fetching {vendor['name']} products...")
        prods = fetch_shopify_products(vendor['name'], vendor['url'])
        all_products.extend(prods)
        
    if not all_products:
        print("No products fetched.")
        return
        
    print(f"Analyzing positioning for {len(all_products)} products with Gemini...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    records = []
    for p in all_products:
        score = analyze_positioning(client, p["title"], p["description"])
        records.append((
            p["vendor"],
            p["title"],
            p["product_type"],
            p["price_usd"],
            p["description"],
            score,
            datetime.now(),
            p["product_url"],
            p["inferred_weight_g"],
            p["price_per_100g"]
        ))
        
    print("Saving to database...")
    conn, cur = setup_database()
    
    
    insert_query = """
        INSERT INTO competitor_products 
        (vendor, title, product_type, price_usd, description, positioning_score, timestamp, product_url, inferred_weight_g, price_per_100g)
        VALUES %s
    """
    execute_values(cur, insert_query, records)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Successfully inserted {len(records)} competitor products.")

if __name__ == "__main__":
    main()
