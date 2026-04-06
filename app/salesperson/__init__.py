from flask import Blueprint
salesperson_bp = Blueprint('salesperson', __name__)

from flask import request, session, jsonify
from datetime import datetime

@salesperson_bp.route('/api/generate_social_ad', methods=['POST'])
def generate_social_ad():
    team_member_id = session.get('team_member_id')
    if not team_member_id:
        return jsonify({'error': 'Unauthorized'}), 401

    import sqlite3
    db = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    db.row_factory = sqlite3.Row
    now = datetime.utcnow()

    include_referral = request.json.get('include_referral', True) if request.json else True

    member = db.execute(
        'SELECT id, name, phone, slug, profile_photo, dealership_id FROM dealership_team WHERE id=? AND is_active=1',
        (team_member_id,)
    ).fetchone()
    if not member:
        return jsonify({'error': 'Team member not found'}), 404

    dealership_row = db.execute(
        'SELECT name, city FROM dealerships WHERE id=?',
        (member['dealership_id'],)
    ).fetchone()
    dealership = dealership_row['name'] if dealership_row and dealership_row['name'] else 'Pine Belt'
    city = dealership_row['city'] if dealership_row and dealership_row['city'] else ''

    vehicle = db.execute(
        'SELECT id, year, make, model, price, mileage, image_url, created_at, expires_at FROM vehicles WHERE pick_user_id=? AND status="available" AND expires_at > ? AND is_team_pick=1 ORDER BY expires_at DESC LIMIT 1',
        (team_member_id, now)
    ).fetchone()

    if not vehicle:
        vehicle = db.execute(
            'SELECT id, year, make, model, price, mileage, image_url, created_at, expires_at FROM vehicles WHERE salesperson_id=? AND status="available" AND expires_at > ? ORDER BY created_at DESC LIMIT 1',
            (member['dealership_id'], now)
        ).fetchone()

    if not vehicle:
        return jsonify({'no_inventory': True})

    vehicle_photo = vehicle['image_url'] if vehicle['image_url'] else ''

    stats = db.execute(
        'SELECT COUNT(*) as count, MIN(price) as lowest_price, MIN(created_at) as oldest_listing FROM vehicles WHERE pick_user_id=? AND status="available" AND expires_at > ?',
        (team_member_id, now)
    ).fetchone()

    active_count = stats['count'] if stats else 0
    lowest_price_raw = stats['lowest_price'] if stats else None
    oldest_listing = stats['oldest_listing'] if stats else None

    if oldest_listing:
        oldest_dt = datetime.strptime(oldest_listing.split('.')[0], '%Y-%m-%d %H:%M:%S')
        days_fresh = (now - oldest_dt).days
    else:
        days_fresh = 0

    expires_str = str(vehicle['expires_at']).split('.')[0]
    expires_dt = datetime.strptime(expires_str, '%Y-%m-%d %H:%M:%S')
    days_left = max((expires_dt - now).days, 0)

    price_formatted = '${:,.0f}'.format(vehicle['price'])

    if lowest_price_raw is not None:
        lowest_k = round(lowest_price_raw / 1000)
        starting_at = '${:}k'.format(lowest_k)
    else:
        starting_at = ''

    vehicle_name = '{} {} {}'.format(vehicle['year'], vehicle['make'], vehicle['model'])

    quote = ''
    try:
        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            'You are {}, a car salesperson. '
            'Write a single punchy quote, 12 words max, in first person, '
            'promoting this vehicle: {} priced at {}. '
            'No hashtags. No quotes around it. Just the line.'
        ).format(member['name'], vehicle_name, price_formatted)
        haiku_response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=60,
            messages=[{'role': 'user', 'content': prompt}]
        )
        quote = haiku_response.content[0].text.strip()
    except Exception:
        quote = 'Come see me today — I have the right car for you.'

    return jsonify({
        'name': member['name'],
        'dealership': dealership,
        'city': city,
        'phone': member['phone'],
        'profile_photo': member['profile_photo'],
        'slug': member['slug'],
        'vehicle_name': vehicle_name,
        'vehicle_photo': vehicle_photo,
        'price': price_formatted,
        'days_left': days_left,
        'cars_live': active_count,
        'starting_at': starting_at,
        'days_fresh': days_fresh,
        'quote': quote,
        'include_referral': include_referral,
        'no_inventory': False,
    })


@salesperson_bp.route('/api/proxy-image')
def proxy_image():
    import requests as _req
    from flask import request as _request, Response
    url = _request.args.get('url', '')
    if not url or not url.startswith('https://res.cloudinary.com'):
        return ('', 400)
    r = _req.get(url, timeout=10)
    resp = Response(r.content, content_type=r.headers.get('content-type', 'image/jpeg'))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cache-Control'] = 'no-store'
    return resp
