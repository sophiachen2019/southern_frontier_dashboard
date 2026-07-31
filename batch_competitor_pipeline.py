import os
import json
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv
import time
import re
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
            positioning_score INT,
            product_url TEXT,
            inferred_weight_g FLOAT,
            price_per_100g FLOAT
        )
    """)
    cur.execute("ALTER TABLE competitor_products ADD COLUMN IF NOT EXISTS inferred_weight_g FLOAT;")
    cur.execute("ALTER TABLE competitor_products ADD COLUMN IF NOT EXISTS price_per_100g FLOAT;")
    conn.commit()
    return conn, cur

def fetch_shopify_products(vendor_name, base_url, limit=5):
    all_products = []
    # Ensure URL ends correctly for products.json
    url = f"{base_url.rstrip('/')}/products.json?limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for prod in data.get('products', []):
                price = 0.0
                if prod.get('variants'):
                    try:
                        price = float(prod['variants'][0].get('price', 0))
                    except ValueError:
                        pass
                
                handle = prod.get('handle', '')
                product_url = f"{base_url.rstrip('/')}/products/{handle}" if handle else ""
                
                # strip html tags for cleaner description
                import re
                desc = re.sub('<[^<]+>', '', prod.get('body_html', ''))[:1000] 
                inferred_weight_g = infer_weight_grams(f"{prod.get('title', '')} {desc}")
                price_per_100g = (price / inferred_weight_g) * 100 if inferred_weight_g else None
                
                all_products.append({
                    "vendor": vendor_name,
                    "title": prod.get('title', ''),
                    "product_type": prod.get('product_type', 'Tea'),
                    "price": price,
                    "description": desc,
                    "product_url": product_url,
                    "inferred_weight_g": inferred_weight_g,
                    "price_per_100g": price_per_100g
                })
        else:
            print(f"Failed to fetch products for {vendor_name}: {response.status_code}")
    except Exception as e:
        print(f"Error fetching products for {vendor_name}: {e}")
    return all_products

def analyze_positioning(client, title, description):
    prompt = """
You are a brand strategist analyzing competitor product descriptions in the specialty tea space.
Score this product's copy on a scale of 1-10 for "Modern Authenticity Positioning".
- A score of 10 means the brand successfully bridges ancient heritage with modern, transparent, premium design. It feels rooted in tradition (ancient trees, resilience) but is highly accessible, clean, and modern.
- A score of 1 means the brand is either too sterile and soulless, OR overly esoteric, confusing, and dusty.
Return only the JSON output.
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[prompt, f"Title: {title}\nDescription: {description}"],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PositioningScore,
                temperature=0.2,
            ),
        )
        time.sleep(4.5)  # Rate limiting for free tier
        data = json.loads(response.text)
        return data.get('positioning_score', 5)
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        if "429" in str(e) or "ResourceExhausted" in str(e):
            raise Exception("Daily API Quota Exceeded")
        return 5

def main():
    print("Starting Daily Competitor Pipeline...")
    conn, cur = setup_database()
    
    # Grab next 250 pending vendors (up to 1250 requests, keeping under 1500 daily limit)
    cur.execute("SELECT domain, name FROM discovered_vendors WHERE status = 'pending' LIMIT 250")
    batch = cur.fetchall()
    
    if not batch:
        print("No pending vendors found. Batch pipeline resting.")
        cur.close()
        conn.close()
        return

    print(f"Processing batch of {len(batch)} vendors...")
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    for domain, name in batch:
        print(f"Fetching products for {name} ({domain})...")
        prods = fetch_shopify_products(name, domain, limit=5)
        
        if not prods:
            print(f"No products found for {name}. Marking as failed.")
            cur.execute("UPDATE discovered_vendors SET status = 'failed' WHERE domain = %s", (domain,))
            conn.commit()
            continue
            
        print(f"Analyzing positioning for {len(prods)} products from {name}...")
        records = []
        quota_exceeded = False
        for p in prods:
            try:
                score = analyze_positioning(client, p['title'], p['description'])
                records.append((
                    p['vendor'], p['title'], p['product_type'], 
                    p['price'], score, p['product_url'], p['inferred_weight_g'], p['price_per_100g']
                ))
            except Exception as e:
                if str(e) == "Daily API Quota Exceeded":
                    print("Hit daily API limit. Aborting batch.")
                    quota_exceeded = True
                    break
        
        if records:
            insert_query = """
                INSERT INTO competitor_products 
                (vendor, title, product_type, price_usd, positioning_score, product_url, inferred_weight_g, price_per_100g)
                VALUES %s
            """
            execute_values(cur, insert_query, records)
        
        if quota_exceeded:
            break
            
        cur.execute("UPDATE discovered_vendors SET status = 'completed' WHERE domain = %s", (domain,))
        conn.commit()
        
    print("Batch processing complete.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
