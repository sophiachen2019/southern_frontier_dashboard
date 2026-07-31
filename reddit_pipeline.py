import os
from datetime import datetime

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()

NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "southern-frontier-market-research/0.1")


def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_market_documents (
            id SERIAL PRIMARY KEY,
            source VARCHAR(80),
            source_type VARCHAR(80),
            source_id TEXT UNIQUE,
            title TEXT,
            body TEXT,
            url TEXT,
            collected_at TIMESTAMP,
            query TEXT
        )
    """)
    conn.commit()
    return conn, cur


def get_access_token():
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise RuntimeError("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env first.")

    response = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def search_subreddit(token, subreddit, query, limit=50):
    response = requests.get(
        f"https://oauth.reddit.com/r/{subreddit}/search",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": REDDIT_USER_AGENT,
        },
        params={
            "q": query,
            "restrict_sr": "true",
            "sort": "relevance",
            "t": "year",
            "limit": limit,
        },
        timeout=20,
    )
    response.raise_for_status()
    posts = []
    for child in response.json().get("data", {}).get("children", []):
        data = child.get("data", {})
        posts.append({
            "source": "reddit",
            "source_type": f"r/{subreddit}",
            "source_id": data.get("id"),
            "title": data.get("title", ""),
            "body": data.get("selftext", ""),
            "url": f"https://www.reddit.com{data.get('permalink', '')}",
            "collected_at": datetime.now(),
            "query": query,
        })
    return posts


def main():
    queries = [
        ("tea", "puerh beginner"),
        ("tea", "puerh daily drink"),
        ("puer", "beginner puer"),
        ("Coffee", "coffee alternative tea"),
        ("matcha", "tea ritual"),
        ("biohackers", "caffeine jitters alternative"),
    ]

    token = get_access_token()
    records = []
    for subreddit, query in queries:
        print(f"Searching r/{subreddit}: {query}")
        records.extend(search_subreddit(token, subreddit, query))

    if not records:
        print("No Reddit records found.")
        return

    conn, cur = setup_database()
    insert_query = """
        INSERT INTO raw_market_documents
        (source, source_type, source_id, title, body, url, collected_at, query)
        VALUES %s
        ON CONFLICT (source_id) DO NOTHING
    """
    execute_values(
        cur,
        insert_query,
        [
            (
                r["source"], r["source_type"], r["source_id"], r["title"], r["body"],
                r["url"], r["collected_at"], r["query"]
            )
            for r in records
        ],
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Saved up to {len(records)} Reddit records.")


if __name__ == "__main__":
    main()
