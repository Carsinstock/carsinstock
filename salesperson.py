@salesperson_bp.route('/api/generate_social_ad', methods=['POST'])
def generate_social_ad():
    team_member_id = session.get('team_member_id')
    if not team_member_id:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    now = datetime.utcnow()

    include_referral = request.json.get('include_referral', True) if request.json else True

    # Pull team member
    member = db.execute(
        'SELECT id, name, title, phone, slug, profile_photo, salesperson_id FROM dealership_team WHERE id = ?',
        (team_member_id,)
    ).fetchone()

    if not member:
        return jsonify({'error': 'Team member not found'}), 404

    # Pull dealership info from users table
    user = db.execute(
        'SELECT dealership, city FROM users WHERE id = ?',
        (member['salesperson_id'],)
    ).fetchone()

    dealership = user['dealership'] if user and user['dealership'] else ''
    city = user['city'] if user and user['city'] else ''

    # Try Top Pick first
    vehicle = db.execute(
        '''SELECT id, year, make, model, price, mileage, created_at, expires_at
           FROM vehicles
           WHERE pick_user_id = ?
             AND status = 'active'
             AND expires_at > ?
             AND is_team_pick = 1
           ORDER BY expires_at DESC
           LIMIT 1''',
        (team_member_id, now)
    ).fetchone()

    # Fallback: most recent active vehicle by salesperson_id
    if not vehicle:
        vehicle = db.execute(
            '''SELECT id, year, make, model, price, mileage, created_at, expires_at
               FROM vehicles
               WHERE salesperson_id = ?
                 AND status = 'active'
                 AND expires_at > ?
               ORDER BY created_at DESC
               LIMIT 1''',
            (member['salesperson_id'], now)
        ).fetchone()

    if not vehicle:
        return jsonify({'no_inventory': True})

    # Vehicle photo
    photo_row = db.execute(
        'SELECT photo_url FROM vehicle_photos WHERE vehicle_id = ? ORDER BY id ASC LIMIT 1',
        (vehicle['id'],)
    ).fetchone()
    vehicle_photo = photo_row['photo_url'] if photo_row else ''

    # Stats
    stats = db.execute(
        '''SELECT COUNT(*) as count,
                  MIN(price) as lowest_price,
                  MIN(created_at) as oldest_listing
           FROM vehicles
           WHERE salesperson_id = ?
             AND status = 'active'
             AND expires_at > ?''',
        (member['salesperson_id'], now)
    ).fetchone()

    active_count = stats['count'] if stats else 0
    lowest_price_raw = stats['lowest_price'] if stats else None
    oldest_listing = stats['oldest_listing'] if stats else None

    # days_fresh — days since oldest active listing
    if oldest_listing:
        oldest_dt = datetime.strptime(oldest_listing, '%Y-%m-%d %H:%M:%S')
        days_fresh = (now - oldest_dt).days
    else:
        days_fresh = 0

    # days_left — days until vehicle expires_at
    expires_dt = datetime.strptime(str(vehicle['expires_at']), '%Y-%m-%d %H:%M:%S')
    days_left = max((expires_dt - now).days, 0)

    # Format price as "$28,995"
    price_formatted = f"${vehicle['price']:,}"

    # Format starting_at as "$22k"
    if lowest_price_raw is not None:
        lowest_k = round(lowest_price_raw / 1000)
        starting_at = f"${lowest_k}k"
    else:
        starting_at = ''

    # vehicle_name
    vehicle_name = f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"

    # Claude Haiku — 12-word max quote in salesperson's voice
    quote = ''
    try:
        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            f"You are {member['name']}, a car salesperson. "
            f"Write a single punchy quote, 12 words max, in first person, "
            f"promoting this vehicle: {vehicle_name} priced at {price_formatted}. "
            f"No hashtags. No quotes around it. Just the line."
        )
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
        'title': member['title'],
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
