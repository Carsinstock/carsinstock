#!/usr/bin/env python3
"""
app/utils/nominatim.py
Wraps OpenStreetMap Nominatim + Overpass APIs for neighbor address lookup.
Free, no API key required.
Rate limit: 1 request/second — enforced via sleep.
"""

import json
import math
import time
import sqlite3
import os
import requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'carsinstock.db')

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
USER_AGENT = 'CarsInStock-Neighbor-Letters/1.0 (admin@carsinstock.com)'
RADIUS_METERS = 320  # ~0.2 miles


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _check_cache(query_address):
    """Return cached result if exists, else None."""
    try:
        conn = _get_db()
        row = conn.execute(
            'SELECT * FROM geocode_cache WHERE query_address = ?',
            (query_address.lower().strip(),)
        ).fetchone()
        conn.close()
        if row and row['neighbor_addresses_json']:
            return json.loads(row['neighbor_addresses_json'])
    except Exception:
        pass
    return None


def _save_cache(query_address, lat, lon, formatted, neighbors):
    """Save geocode result to cache."""
    try:
        conn = _get_db()
        conn.execute('''
            INSERT OR REPLACE INTO geocode_cache
            (query_address, latitude, longitude, formatted_address, neighbor_addresses_json, cached_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            query_address.lower().strip(),
            lat, lon, formatted,
            json.dumps(neighbors),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _geocode_address(address):
    """
    Geocode address using Nominatim.
    Returns (lat, lon, formatted_address) or raises ValueError.
    """
    time.sleep(1)  # Rate limit
    headers = {'User-Agent': USER_AGENT}
    params = {
        'q': address,
        'format': 'json',
        'limit': 1,
        'countrycodes': 'us',
    }
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    results = r.json()
    if not results:
        raise ValueError(f"Could not geocode address: {address}")
    result = results[0]
    return float(result['lat']), float(result['lon']), result.get('display_name', address)


def _get_nearby_addresses(lat, lon, radius=RADIUS_METERS):
    """
    Query Overpass API for residential addresses near lat/lon.
    Returns list of address strings.
    """
    time.sleep(1)  # Rate limit
    # Overpass QL query for address nodes within radius
    query = f"""
    [out:json][timeout:25];
    (
      node["addr:housenumber"]["addr:street"](around:{radius},{lat},{lon});
      way["addr:housenumber"]["addr:street"](around:{radius},{lat},{lon});
    );
    out center 30;
    """
    headers = {'User-Agent': USER_AGENT}
    r = requests.post(OVERPASS_URL, data={'data': query}, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    addresses = []
    seen = set()

    for element in data.get('elements', []):
        tags = element.get('tags', {})
        house = tags.get('addr:housenumber', '').strip()
        street = tags.get('addr:street', '').strip()
        city = tags.get('addr:city', '').strip()
        state = tags.get('addr:state', '').strip()
        zipcode = tags.get('addr:postcode', '').strip()

        if not house or not street:
            continue

        parts = [f"{house} {street}"]
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if zipcode:
            parts.append(zipcode)

        addr_str = ', '.join(parts)

        if addr_str.lower() not in seen:
            seen.add(addr_str.lower())
            addresses.append(addr_str)

        if len(addresses) >= 15:
            break

    return addresses


def get_neighbor_addresses(query_address):
    """
    Main entry point. Takes a street address string.
    Returns list of up to 15 nearby address strings.
    Uses cache to avoid repeat API calls.
    Raises ValueError if geocoding fails.
    """
    # Check cache first
    cached = _check_cache(query_address)
    if cached:
        return cached

    # Geocode
    lat, lon, formatted = _geocode_address(query_address)

    # Get nearby addresses
    neighbors = _get_nearby_addresses(lat, lon)

    # Save to cache
    _save_cache(query_address, lat, lon, formatted, neighbors)

    return neighbors
