#!/usr/bin/env python3
import json, time, re, sqlite3, os, requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'instance', 'carsinstock.db')
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
USER_AGENT = 'CarsInStock-Neighbor-Letters/1.0 (admin@carsinstock.com)'
RADIUS_METERS = 500

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _check_cache(query_address):
    try:
        conn = _get_db()
        row = conn.execute('SELECT * FROM geocode_cache WHERE query_address = ?', (query_address.lower().strip(),)).fetchone()
        conn.close()
        if row and row['neighbor_addresses_json']:
            cached = json.loads(row['neighbor_addresses_json'])
            if len(cached) > 0:
                return cached
    except Exception:
        pass
    return None

def _save_cache(query_address, lat, lon, formatted, neighbors):
    try:
        conn = _get_db()
        conn.execute('''INSERT OR REPLACE INTO geocode_cache
            (query_address, latitude, longitude, formatted_address, neighbor_addresses_json, cached_at)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (query_address.lower().strip(), lat, lon, formatted, json.dumps(neighbors), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass

def _geocode_address(address):
    time.sleep(1)
    headers = {'User-Agent': USER_AGENT}
    params = {'q': address, 'format': 'json', 'limit': 1, 'countrycodes': 'us'}
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    results = r.json()
    if not results:
        raise ValueError(f"Could not geocode address: {address}")
    result = results[0]
    return float(result['lat']), float(result['lon']), result.get('display_name', address)

def _get_overpass_addresses(lat, lon, radius=RADIUS_METERS):
    time.sleep(1)
    query = f"""[out:json][timeout:25];
(
  node["addr:housenumber"]["addr:street"](around:{radius},{lat},{lon});
  way["addr:housenumber"]["addr:street"](around:{radius},{lat},{lon});
);
out center 30;"""
    headers = {'User-Agent': USER_AGENT}
    try:
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
            if city: parts.append(city)
            if state: parts.append(state)
            if zipcode: parts.append(zipcode)
            addr_str = ', '.join(parts)
            if addr_str.lower() not in seen:
                seen.add(addr_str.lower())
                addresses.append(addr_str)
            if len(addresses) >= 15:
                break
        return addresses
    except Exception:
        return []

def _generate_street_addresses(input_address, count=15):
    match = re.match(r'^(\d+)\s+(.+?)(?:,\s*(.+))?$', input_address.strip())
    if not match:
        return []
    base_number = int(match.group(1))
    street_name = match.group(2).strip()
    street_only = street_name.split(',')[0].strip()
    addr_parts = input_address.split(',')
    location_suffix = ', '.join(addr_parts[1:]).strip() if len(addr_parts) >= 2 else ''
    addresses = []
    seen = set()
    step = 2
    offsets = []
    for i in range(1, 20):
        offsets.append(i * step)
        offsets.append(-i * step)
    offsets.sort(key=abs)
    for offset in offsets:
        num = base_number + offset
        if num <= 0:
            continue
        addr = f"{num} {street_only}, {location_suffix}" if location_suffix else f"{num} {street_only}"
        key = addr.lower()
        if key not in seen:
            seen.add(key)
            addresses.append(addr)
        if len(addresses) >= count:
            break
    return addresses

def get_neighbor_addresses(query_address):
    cached = _check_cache(query_address)
    if cached:
        return cached
    try:
        lat, lon, formatted = _geocode_address(query_address)
    except ValueError as e:
        raise ValueError(str(e))
    neighbors = _get_overpass_addresses(lat, lon)
    if len(neighbors) < 5:
        street_addresses = _generate_street_addresses(query_address)
        seen = set(a.lower() for a in neighbors)
        for addr in street_addresses:
            if addr.lower() not in seen:
                neighbors.append(addr)
                seen.add(addr.lower())
            if len(neighbors) >= 15:
                break
    _save_cache(query_address, lat, lon, formatted, neighbors)
    return neighbors
