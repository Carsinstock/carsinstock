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
    params = {'q': address, 'format': 'json', 'limit': 1, 'countrycodes': 'us', 'addressdetails': 1}
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    results = r.json()
    if not results:
        raise ValueError(f"Could not geocode address: {address}")
    result = results[0]
    ad = result.get('address', {})
    default_zip = (ad.get('postcode') or '').strip()
    default_state = (ad.get('state') or '').strip()
    STATE_ABBR = {'New Jersey':'NJ','New York':'NY','Pennsylvania':'PA','Connecticut':'CT','Massachusetts':'MA','Delaware':'DE','Maryland':'MD','California':'CA','Texas':'TX','Florida':'FL','Illinois':'IL','Ohio':'OH','Georgia':'GA','North Carolina':'NC','Virginia':'VA','Washington':'WA','Arizona':'AZ','Michigan':'MI','Indiana':'IN','Tennessee':'TN','Missouri':'MO','Wisconsin':'WI','Colorado':'CO','Minnesota':'MN','South Carolina':'SC','Alabama':'AL','Louisiana':'LA','Kentucky':'KY','Oregon':'OR','Oklahoma':'OK','Arkansas':'AR','Mississippi':'MS','Kansas':'KS','Nevada':'NV','Utah':'UT','Iowa':'IA','Nebraska':'NE','West Virginia':'WV','Idaho':'ID','Hawaii':'HI','Maine':'ME','New Hampshire':'NH','Rhode Island':'RI','Montana':'MT','South Dakota':'SD','North Dakota':'ND','Alaska':'AK','Vermont':'VT','Wyoming':'WY','New Mexico':'NM','District of Columbia':'DC'}
    default_state = STATE_ABBR.get(default_state, default_state)
    default_city = ''
    for _ck in ('city', 'town', 'village', 'hamlet', 'suburb'):
        _cv = (ad.get(_ck) or '').strip()
        if _cv:
            default_city = _cv
            break
    return float(result['lat']), float(result['lon']), result.get('display_name', address), default_zip, default_state, default_city

def _get_overpass_addresses(lat, lon, radius=RADIUS_METERS, default_zip='', default_state='', default_city=''):
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
            city = tags.get('addr:city', '').strip() or default_city
            state = tags.get('addr:state', '').strip() or default_state
            zipcode = tags.get('addr:postcode', '').strip() or default_zip
            if not house or not street:
                continue
            csz = []
            if city: csz.append(city)
            if state and zipcode:
                csz.append(f"{state} {zipcode}")
            elif state: csz.append(state)
            elif zipcode: csz.append(zipcode)
            addr_str = f"{house} {street}" + (("\n" + ", ".join(csz)) if csz else "")
            if addr_str.lower() not in seen:
                seen.add(addr_str.lower())
                addresses.append(addr_str)
            if len(addresses) >= 15:
                break
        return addresses
    except Exception:
        return []

def _generate_street_addresses(input_address, count=15, default_zip='', default_state='', default_city=''):
    match = re.match(r'^(\d+)\s+(.+?)(?:,\s*(.+))?$', input_address.strip())
    if not match:
        return []
    base_number = int(match.group(1))
    street_name = match.group(2).strip()
    street_only = street_name.split(',')[0].strip()
    # Prefer geocoder city; strip trailing city/state/zip tokens that bled into the parsed street
    if default_city:
        city = default_city
        for _tok in (default_zip, default_state, default_city):
            if _tok:
                street_only = re.sub(r'[\s,]+' + re.escape(_tok) + r'$', '', street_only, flags=re.IGNORECASE).strip()
    else:
        addr_parts = [p.strip() for p in input_address.split(',') if p.strip()]
        city = addr_parts[1] if len(addr_parts) > 1 else ''
    if city and (default_state or default_zip):
        line2 = f"{city}, {default_state} {default_zip}".strip().rstrip(',').strip()
    elif city:
        line2 = city
    elif default_state or default_zip:
        line2 = f"{default_state} {default_zip}".strip()
    else:
        line2 = ''
    addresses = []
    seen = set()
    step = 1  # cover both sides of street (was 2 = same-parity only)
    offsets = []
    for i in range(1, 20):
        offsets.append(i * step)
        offsets.append(-i * step)
    offsets.sort(key=abs)
    for offset in offsets:
        num = base_number + offset
        if num <= 0:
            continue
        line1 = f"{num} {street_only}"
        addr = f"{line1}\n{line2}" if line2 else line1
        key = addr.lower()
        if key not in seen:
            seen.add(key)
            addresses.append(addr)
        if len(addresses) >= count:
            break
    return addresses

def _is_likely_commercial(addr_str):
    """Heuristic filter: skip highway/commercial addresses unsuitable for residential neighbor mailings."""
    lower = addr_str.lower()
    patterns = [
        r'\bstate route\b',
        r'\bus[-\s]?\d{1,3}\b',
        r'\bus highway\b',
        r'\broute\s+\d{1,3}\b',
        r'\b(rt|rte)\.?\s+\d',
        r'\bturnpike\b',
        r'\bparkway\b',
        r'\bnj[-\s]\d{1,3}\b',
    ]
    return any(re.search(p, lower) for p in patterns)

def get_neighbor_addresses(query_address):
    cached = _check_cache(query_address)
    if cached:
        return cached
    try:
        lat, lon, formatted, default_zip, default_state, default_city = _geocode_address(query_address)
    except ValueError as e:
        raise ValueError(str(e))
    # Synthetic first: same-street neighbors are most relevant for residential mailings
    neighbors = _generate_street_addresses(query_address, default_zip=default_zip, default_state=default_state, default_city=default_city)
    seen = set(a.lower() for a in neighbors)
    # Augment with Overpass, filtered to skip highway/commercial noise
    if len(neighbors) < 15:
        overpass_addrs = _get_overpass_addresses(lat, lon, default_zip=default_zip, default_state=default_state, default_city=default_city)
        for addr in overpass_addrs:
            if addr.lower() not in seen and not _is_likely_commercial(addr):
                neighbors.append(addr)
                seen.add(addr.lower())
            if len(neighbors) >= 15:
                break
    # Final safety net: if both methods returned nothing, fall back to raw Overpass
    if not neighbors:
        neighbors = _get_overpass_addresses(lat, lon, default_zip=default_zip, default_state=default_state)
    _save_cache(query_address, lat, lon, formatted, neighbors)
    return neighbors
