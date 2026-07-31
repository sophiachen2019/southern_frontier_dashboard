import os
from datetime import datetime

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()

NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")


ACS_VARIABLES = {
    "B01001_001E": "population",
    "B19013_001E": "median_household_income",
    "B15003_022E": "bachelors_degree",
    "B15003_023E": "masters_degree",
    "B15003_024E": "professional_degree",
    "B15003_025E": "doctorate_degree",
    "B02001_005E": "asian_population",
}


def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metro_demographics (
            id SERIAL PRIMARY KEY,
            collected_at TIMESTAMP,
            geography TEXT,
            population FLOAT,
            median_household_income FLOAT,
            bachelors_degree FLOAT,
            masters_degree FLOAT,
            professional_degree FLOAT,
            doctorate_degree FLOAT,
            education_proxy FLOAT,
            asian_population FLOAT,
            asian_population_pct FLOAT
        )
    """)
    # Migration for existing tables
    cur.execute("ALTER TABLE metro_demographics ADD COLUMN IF NOT EXISTS asian_population FLOAT;")
    cur.execute("ALTER TABLE metro_demographics ADD COLUMN IF NOT EXISTS asian_population_pct FLOAT;")
    conn.commit()
    return conn, cur


def fetch_acs_profile():
    if not CENSUS_API_KEY:
        raise RuntimeError("Set CENSUS_API_KEY in .env first.")

    fields = ["NAME"] + list(ACS_VARIABLES.keys())
    response = requests.get(
        "https://api.census.gov/data/2024/acs/acs1",
        params={
            "get": ",".join(fields),
            "for": "metropolitan statistical area/micropolitan statistical area:*",
            "key": CENSUS_API_KEY,
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    header, values = rows[0], rows[1:]

    records = []
    for row in values:
        item = dict(zip(header, row))
        parsed = {"geography": item["NAME"], "collected_at": datetime.now()}
        for census_field, clean_name in ACS_VARIABLES.items():
            try:
                parsed[clean_name] = float(item.get(census_field))
            except (TypeError, ValueError):
                parsed[clean_name] = None
        parsed["education_proxy"] = sum([
            parsed.get("bachelors_degree") or 0,
            parsed.get("masters_degree") or 0,
            parsed.get("professional_degree") or 0,
            parsed.get("doctorate_degree") or 0,
        ])
        # Asian diaspora percentage
        pop = parsed.get("population")
        asian = parsed.get("asian_population")
        if pop and pop > 0 and asian is not None:
            parsed["asian_population_pct"] = round((asian / pop) * 100, 2)
        else:
            parsed["asian_population_pct"] = None
        records.append(parsed)
    return records


def main():
    records = fetch_acs_profile()
    conn, cur = setup_database()
    cur.execute("DELETE FROM metro_demographics")
    insert_query = """
        INSERT INTO metro_demographics
        (collected_at, geography, population, median_household_income,
         bachelors_degree, masters_degree, professional_degree, doctorate_degree,
         education_proxy, asian_population, asian_population_pct)
        VALUES %s
    """
    execute_values(
        cur,
        insert_query,
        [
            (
                r["collected_at"], r["geography"], r["population"], r["median_household_income"],
                r["bachelors_degree"], r["masters_degree"], r["professional_degree"],
                r["doctorate_degree"], r["education_proxy"],
                r.get("asian_population"), r.get("asian_population_pct")
            )
            for r in records
        ],
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Saved {len(records)} metro demographic records (including Asian population data).")


if __name__ == "__main__":
    main()
