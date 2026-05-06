#!/usr/bin/env python3
"""
cron_google_reviews.py
Runs daily at 6AM UTC — fetches Google rating + review count for all
dealerships with a google_place_id and caches in the DB.
"""
import sqlite3, requests, logging, os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

DB = '/home/eddie/carsinstock/instance/carsinstock.db'
API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY', '')

if not API_KEY:
    log.error("GOOGLE_PLACES_API_KEY not set — aborting")
    exit(1)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
dealerships = conn.execute(
    "SELECT id, name, google_place_id FROM dealerships WHERE google_place_id IS NOT NULL"
).fetchall()

for d in dealerships:
    try:
        url = f"https://places.googleapis.com/v1/places/{d['google_place_id']}"
        resp = requests.get(url, headers={
            'X-Goog-Api-Key': API_KEY,
            'X-Goog-FieldMask': 'rating,userRatingCount'
        }, timeout=10)
        data = resp.json()
        rating = data.get('rating')
        count = data.get('userRatingCount')
        if rating and count:
            conn.execute(
                "UPDATE dealerships SET google_rating=?, google_review_count=?, google_last_synced=? WHERE id=?",
                (rating, count, datetime.utcnow().isoformat(), d['id'])
            )
            conn.commit()
            log.info(f"{d['name']}: {rating} stars / {count} reviews — updated")
        else:
            log.warning(f"{d['name']}: unexpected response {data}")
    except Exception as e:
        log.error(f"{d['name']}: error — {e}")

conn.close()
log.info("Done.")
