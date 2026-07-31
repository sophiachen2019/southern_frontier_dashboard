import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

def fetch_serper(query, num=100):
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = json.dumps({"q": query, "num": num})
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code == 200:
        return response.json().get('organic', [])
    return []

results = fetch_serper('inurl:myshopify.com "tea"')
print(f"Found {len(results)} results")
for r in results[:5]:
    print(r.get('link'))
