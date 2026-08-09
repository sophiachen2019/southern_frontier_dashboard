import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
from youtube_transcript_api import YouTubeTranscriptApi
import subprocess
import time
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEON_DB_CONNECTION_STRING = os.getenv("NEON_DB_CONNECTION_STRING")

class SentimentScores(BaseModel):
    transparency_desire: int = Field(description="Score 1-10 for Transparency & Purity Desire")
    brewing_theater: int = Field(description="Score 1-10 for Brewing Theater")
    grounded_energy_desire: int = Field(description="Score 1-10 for Grounded Energy & Resilience")
    summary: str = Field(description="1-sentence summary of the core aesthetic friction or desire")
    segment: str = Field(description="One of: Coffee switchers, Matcha ritualists, Wellness purists, Tea explorers, Premium ritual gifters, Curious premium drinkers")

def fetch_serper_data(queries):
    import urllib.parse
    all_questions = []
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    for q in queries:
        payload = json.dumps({"q": q})
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            data = response.json()
            paa = data.get('peopleAlsoAsk', [])
            for item in paa:
                text = f"Q: {item.get('question')} A: {item.get('snippet')}"
                link = f"https://www.google.com/search?q={urllib.parse.quote(q)}"
                all_questions.append((text, link))
        else:
            print(f"Failed to fetch Serper data for '{q}': {response.status_code}")
    return all_questions
def search_youtube_videos(queries, limit=5):
    videos_by_id = {}
    for q in queries:
        try:
            cmd = ["yt-dlp", f"ytsearch{limit}:{q}", "--dump-json", "--ignore-errors", "--no-warnings"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            for line in result.stdout.splitlines():
                try:
                    video = json.loads(line)
                except json.JSONDecodeError:
                    continue
                video_id = video.get("id")
                if not video_id:
                    continue
                videos_by_id[video_id] = {
                    "video_id": video_id,
                    "url": video.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                    "title": video.get("title"),
                    "channel": video.get("channel") or video.get("uploader"),
                    "view_count": video.get("view_count"),
                    "like_count": video.get("like_count"),
                    "comment_count": video.get("comment_count"),
                    "duration": video.get("duration"),
                    "upload_date": video.get("upload_date"),
                    "search_query": q,
                }
        except Exception as e:
            print(f"Failed to search YouTube using yt-dlp for '{q}': {e}")
    return list(videos_by_id.values())


def fetch_youtube_transcripts(video_records):
    transcripts = []
    for video in video_records:
        vid = video["video_id"]
        try:
            # Correct API usage for youtube_transcript_api 1.x
            transcript_list = YouTubeTranscriptApi().list(vid)
            transcript = transcript_list.find_transcript(['en']).fetch()
            # transcript is a list of snippet objects
            text = " ".join([getattr(t, 'text', str(t)) for t in transcript[:20]])
            video["text"] = text
            transcripts.append(video)
        except Exception as e:
            print(f"Failed to fetch transcript for {vid}: {e}")
            continue
    return transcripts

def analyze_text(client, text):
    prompt = """
You are an expert consumer behavior analyst. Analyze the provided text (search queries or video transcripts) and score it 1-10 for the following three aesthetic vectors:
- Transparency & Purity Desire: Desire for clean sourcing, lab testing, zero pesticides, and transparent quality.
- Brewing Theater: Appreciation for the physical environment, precise brewing rituals (e.g., scales, timers, no-mess), and spatial design.
- Grounded Energy & Resilience: Looking for the resilience, quiet strength, and grounded feeling of tea (vs the jittery rush of coffee).

Also classify the text into exactly one of these consumer segments:
- Coffee switchers: People looking for coffee alternatives, mentions of jitters, caffeine crashes, energy management.
- Matcha ritualists: People drawn to ceremonial prep, aesthetic routines, whisking, latte art, daily rituals.
- Wellness purists: People focused on clean ingredients, pesticide-free, organic, heavy metal testing, transparent sourcing.
- Tea explorers: People interested in pu'er, sheng, shu, aged tea, fermented tea, loose leaf discovery.
- Premium ritual gifters: People interested in premium gifts, luxury tea, beautiful packaging, sharing, collections.
- Curious premium drinkers: General premium beverage interest that doesn't clearly fit one of the above segments.

Output a short 1-sentence summary of the core aesthetic friction or desire. Return the output as strict JSON.
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[prompt, text],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SentimentScores,
                temperature=0.2,
            ),
        )
        time.sleep(4.5)  # Rate limiting for free tier (15 requests/minute)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None

def setup_database():
    conn = psycopg2.connect(NEON_DB_CONNECTION_STRING)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friction_data (
            id SERIAL PRIMARY KEY,
            source_text TEXT,
            source_type VARCHAR(50),
            timestamp TIMESTAMP,
            transparency_desire INT,
            brewing_theater INT,
            grounded_energy_desire INT,
            summary TEXT,
            premium_accessibility_score FLOAT,
            source_url TEXT,
            segment VARCHAR(80),
            youtube_video_id VARCHAR(40),
            youtube_title TEXT,
            youtube_channel TEXT,
            youtube_view_count BIGINT,
            youtube_like_count BIGINT,
            youtube_comment_count BIGINT,
            youtube_duration_seconds INT,
            youtube_upload_date DATE,
            youtube_search_query TEXT
        )
    """)
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS segment VARCHAR(80);")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_video_id VARCHAR(40);")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_title TEXT;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_channel TEXT;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_view_count BIGINT;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_like_count BIGINT;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_comment_count BIGINT;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_duration_seconds INT;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_upload_date DATE;")
    cur.execute("ALTER TABLE friction_data ADD COLUMN IF NOT EXISTS youtube_search_query TEXT;")
    conn.commit()
    return conn, cur

def main():
    print("Starting Data Pipeline...")
    
    queries = ["ceremonial matcha prep", "pour over coffee setup"]
    print("Fetching Serper.dev PAA questions...")
    serper_texts = fetch_serper_data(queries)
    
    youtube_keywords = ["pour over coffee aesthetic", "ceremonial matcha prep", "puerh tea routine"]
    print("Searching YouTube for dynamic videos...")
    video_records = search_youtube_videos(youtube_keywords, limit=5)
    
    print(f"Fetching transcripts for {len(video_records)} YouTube videos...")
    youtube_texts = fetch_youtube_transcripts(video_records)
    
    dataset = []
    for text, url in serper_texts:
        dataset.append({"text": text, "source_type": "Google PAA", "url": url})
    for video in youtube_texts:
        dataset.append({
            "text": video["text"],
            "source_type": "YouTube Video",
            "url": video["url"],
            "youtube_video_id": video.get("video_id"),
            "youtube_title": video.get("title"),
            "youtube_channel": video.get("channel"),
            "youtube_view_count": video.get("view_count"),
            "youtube_like_count": video.get("like_count"),
            "youtube_comment_count": video.get("comment_count"),
            "youtube_duration_seconds": video.get("duration"),
            "youtube_upload_date": video.get("upload_date"),
            "youtube_search_query": video.get("search_query"),
        })
        
    if not dataset:
        print("No data fetched. Check API keys.")
        return

    print("Processing text with Gemini API...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    processed_records = []
    for item in dataset:
        text = item["text"]
        url = item["url"]
        scores = analyze_text(client, text)
        if scores:
            trans_desire = scores.get("transparency_desire", 5)
            brew_thea = scores.get("brewing_theater", 5)
            ground_energy = scores.get("grounded_energy_desire", 5)
            summary = scores.get("summary", "")
            segment = scores.get("segment", "Curious premium drinkers")
            prem_acc_score = (trans_desire + brew_thea + ground_energy) / 3.0
            upload_date = item.get("youtube_upload_date")
            if upload_date and len(str(upload_date)) == 8:
                upload_date = datetime.strptime(str(upload_date), "%Y%m%d").date()
            else:
                upload_date = None
            
            processed_records.append((
                text, item["source_type"], datetime.now(),
                trans_desire, brew_thea, ground_energy, summary, prem_acc_score, url, segment,
                item.get("youtube_video_id"), item.get("youtube_title"), item.get("youtube_channel"),
                item.get("youtube_view_count"), item.get("youtube_like_count"), item.get("youtube_comment_count"),
                item.get("youtube_duration_seconds"), upload_date, item.get("youtube_search_query")
            ))
            
    print("Saving to Neon Postgres...")
    conn, cur = setup_database()
    insert_query = """
        INSERT INTO friction_data 
        (source_text, source_type, timestamp, transparency_desire, brewing_theater, grounded_energy_desire,
         summary, premium_accessibility_score, source_url, segment, youtube_video_id, youtube_title,
         youtube_channel, youtube_view_count, youtube_like_count, youtube_comment_count,
         youtube_duration_seconds, youtube_upload_date, youtube_search_query)
        VALUES %s
    """
    execute_values(cur, insert_query, processed_records)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Successfully inserted {len(processed_records)} records.")

if __name__ == "__main__":
    main()
