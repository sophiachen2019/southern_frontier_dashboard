import os
import json
import requests
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")

def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovered_vendors (
            domain TEXT PRIMARY KEY,
            name TEXT,
            status VARCHAR(20) DEFAULT 'pending'
        )
    """)
    conn.commit()
    return conn, cur

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

def is_shopify_store(base_url):
    try:
        response = requests.get(f"{base_url}/products.json?limit=1", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'products' in data:
                return True
    except Exception:
        pass
    return False

def fetch_serper(query, num=100):
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = json.dumps({"q": query, "num": num})
    try:
        response = requests.request("POST", url, headers=headers, data=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get('organic', [])
    except Exception as e:
        print(f"Error fetching serper for {query}: {e}")
    return []

def main():
    conn, cur = setup_database()
    
    # Check existing domains to avoid checking Shopify again
    cur.execute("SELECT domain FROM discovered_vendors")
    existing_domains = set([row[0] for row in cur.fetchall()])
    
    # Hardcoded guarantees
    guarantees = [
        ("https://www.rishi-tea.com", "Rishi Tea"),
        ("https://www.firebellytea.com", "Firebelly Tea"),
        ("https://www.smithtea.com", "Smith Teamaker"),
        ("https://kuura.co", "Kuura"),
        ("https://white2tea.com", "White2Tea"),
        ("https://yunnansourcing.com", "Yunnan Sourcing"),
        ("https://crimsonlotustea.com", "Crimson Lotus Tea"),
        ("https://ippodotea.com", "Ippodo Tea"),
        ("https://teaswelike.com", "Teas We Like"),
        ("https://www.farmer-leaf.com", "Farmerleaf"),
        ("https://www.bitterleafteas.com", "Bitterleaf Teas")
    ]
    
    for domain, name in guarantees:
        if domain not in existing_domains:
            print(f"Adding guaranteed vendor: {name}")
            cur.execute("INSERT INTO discovered_vendors (domain, name, status) VALUES (%s, %s, 'pending') ON CONFLICT (domain) DO NOTHING", (domain, name))
            existing_domains.add(domain)
    conn.commit()

    queries = [
        "buy premium black tea online",
        "dark tea vendors",
        "puerh tea shop",
        "buy loose leaf artisanal tea",
        "buy oolong tea online shopify",
        "buy white tea online vendor",
        "buy raw puerh tea",
        "buy ripe puerh tea",
        "specialty loose leaf tea vendor",
        "premium loose leaf tea shopify",
        "buy high end puerh tea",
        "best artisanal tea online store",
        "buy aged puerh tea online",
        "buy premium matcha online",
        "best tea vendors 2024",
        "best pu'er tea brands"
    ]
    
    ignore_domains = ['amazon.com', 'reddit.com', 'wikipedia.org', 'youtube.com', 'ebay.com', 'etsy.com', 'walmart.com', 'teadb.org', 'steepster.com']
    
    found_count = 0
    for q in queries:
        print(f"Searching: {q}")
        results = fetch_serper(q)
        for r in results:
            url = r.get('link')
            if not url:
                continue
            base_url = get_base_url(url)
            
            # Basic filtering
            if any(ign in base_url for ign in ignore_domains):
                continue
            if base_url in existing_domains:
                continue
            
            # Test Shopify
            if is_shopify_store(base_url):
                print(f"Discovered Shopify Tea Store: {base_url}")
                title = r.get('title', 'Unknown Tea Vendor').split('-')[0].split('|')[0].strip()
                cur.execute("INSERT INTO discovered_vendors (domain, name, status) VALUES (%s, %s, 'pending') ON CONFLICT (domain) DO NOTHING", (base_url, title))
                existing_domains.add(base_url)
                found_count += 1
                conn.commit()
                
    print(f"Discovery complete. Found {found_count} new Shopify vendors.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
