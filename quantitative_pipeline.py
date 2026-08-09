import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pytrends.request import TrendReq
import requests
import re
from dotenv import load_dotenv

load_dotenv()
NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")

def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS google_trends_data (
            id SERIAL PRIMARY KEY,
            date TIMESTAMP,
            keyword VARCHAR(100),
            interest INT
        )
    """)
    conn.commit()
    return conn, cur

def fetch_google_trends(kw_list):
    try:
        pytrends = TrendReq(
            hl='en-US', 
            tz=360, 
            timeout=(10,25),
            requests_args={
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
        )
        pytrends.build_payload(kw_list, cat=0, timeframe='today 12-m', geo='', gprop='')
        df = pytrends.interest_over_time()
        if not df.empty:
            if 'isPartial' in df.columns:
                # Drop the incomplete current week to prevent artificial spikes
                df = df[df['isPartial'] != 'True']
                df = df[df['isPartial'] != True]
                df = df.drop(columns=['isPartial'])
            else:
                # Fallback: if isPartial is missing, drop the last row as it is usually the incomplete week
                df = df.iloc[:-1]
            
        return df
    except Exception as e:
        print(f"Error fetching Google Trends for {kw_list}: {e}")
        return pd.DataFrame()


def main():
    conn, cur = setup_database()
    
    print("Fetching Google Trends data...")
    records = []
    
    # Keep this benchmark group to five terms so Google Trends returns one shared 0-100 scale.
    group1 = ["matcha", "specialty coffee", "puer", "boba tea", "kombucha"]
    df1 = fetch_google_trends(group1)
    if not df1.empty:
        for index, row in df1.iterrows():
            for kw in group1:
                saved_kw = "puer (benchmark)" if kw == "puer" else kw
                records.append((index, saved_kw, int(row[kw])))
                
    group2 = ["puerh", "puer", "pu'er", "Pu-erh", "pu erh"]
    df2 = fetch_google_trends(group2)
    if not df2.empty:
        for index, row in df2.iterrows():
            for kw in group2:
                records.append((index, kw, int(row[kw])))
                
    if records:
        cur.execute("DELETE FROM google_trends_data")
        insert_query = "INSERT INTO google_trends_data (date, keyword, interest) VALUES %s"
        execute_values(cur, insert_query, records)
        print(f"Inserted {len(records)} trends records.")
    

    conn.commit()
    cur.close()
    conn.close()
    print("Quantitative pipeline completed.")

if __name__ == "__main__":
    main()
