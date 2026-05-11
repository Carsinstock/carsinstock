from flask import Blueprint
salesperson_bp = Blueprint('salesperson', __name__)

from flask import request, session, jsonify
from datetime import datetime


@salesperson_bp.route('/api/birddog/my-network', methods=['GET'])
def birddog_my_network():
    import sqlite3
    from flask import session, jsonify
    if 'team_member_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row
    birddogs = conn.execute('SELECT * FROM birddogs WHERE team_member_id=? ORDER BY created_at DESC', (session['team_member_id'],)).fetchall()
    result = []
    for b in birddogs:
        referrals = conn.execute('SELECT * FROM birddog_referrals WHERE birddog_id=?', (b['id'],)).fetchall()
        pending = [dict(r) for r in referrals if r['status'] in ('pending','submitted')]
        sold = [dict(r) for r in referrals if r['status'] == 'sold']
        result.append({
            'id': b['id'], 'name': b['name'], 'email': b['email'],
            'phone': b['phone'], 'token': b['token'],
            'total': len(referrals), 'pending': len(pending), 'sold': len(sold),
            'referrals': [dict(r) for r in referrals]
        })
    conn.close()
    return jsonify({'birddogs': result})


@salesperson_bp.route('/api/birddog/mark-sold/<int:referral_id>', methods=['POST'])
def sp_birddog_mark_sold(referral_id):
    import sqlite3
    from flask import session, jsonify
    from datetime import datetime
    if 'team_member_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row
    referral = conn.execute('SELECT * FROM birddog_referrals WHERE id=? AND team_member_id=?',
                            (referral_id, session['team_member_id'])).fetchone()
    if not referral:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    conn.execute('UPDATE birddog_referrals SET status=?, closed_at=? WHERE id=?',
                 ('sold', datetime.utcnow().isoformat(), referral_id))
    conn.commit()
    birddog = conn.execute('SELECT * FROM birddogs WHERE id=?', (referral['birddog_id'],)).fetchone()
    rep = conn.execute('SELECT name FROM dealership_team WHERE id=?', (session['team_member_id'],)).fetchone()
    conn.close()
    if birddog and birddog['email']:
        try:
            import requests as _req2
            from app.utils.email import send_email as _se
            tracking_url = 'https://carsinstock.com/track/' + birddog['token']
            rep_name = rep['name'] if rep else 'your rep'
            buyer_name = referral['buyer_name'] if referral['buyer_name'] else 'your referral'
            _se(
                to_email=birddog['email'],
                subject='Your referral closed!',
                html_content='<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"><div style="background:#1E293B;padding:20px;text-align:center;border-radius:12px 12px 0 0;"><h1 style="color:#00C851;margin:0;">Cars IN STOCK</h1></div><div style="background:#f0fdf4;padding:30px;border-radius:0 0 12px 12px;"><h2 style="color:#166534;">Your referral closed!</h2><p style="color:#555;font-size:16px;line-height:1.6;"><strong>' + buyer_name + '</strong> just bought a car through ' + rep_name + '. Your Thank You gift is being processed.</p><div style="text-align:center;margin:30px 0;"><a href="' + tracking_url + '" style="background:#00C851;color:#1E293B;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;">View Your Referrals</a></div></div></div>'
            )
        except Exception as e:
            print(f"Birddog sold notify error: {e}")
    return jsonify({'success': True})

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
        'SELECT name, city, address, state, zip, google_rating, google_review_count FROM dealerships WHERE id=?',
        (member['dealership_id'],)
    ).fetchone()
    dealership = dealership_row['name'] if dealership_row and dealership_row['name'] else 'Pine Belt'
    city = dealership_row['city'] if dealership_row and dealership_row['city'] else ''

    vehicle = db.execute(
        'SELECT id, year, make, model, price, mileage, exterior_color, transmission, image_url, created_at, expires_at FROM vehicles WHERE pick_user_id=? AND status="available" AND expires_at > ? AND is_team_pick=1 ORDER BY expires_at DESC LIMIT 1',
        (team_member_id, now)
    ).fetchone()

    if not vehicle:
        vehicle = db.execute(
            'SELECT id, year, make, model, price, mileage, exterior_color, transmission, image_url, created_at, expires_at FROM vehicles WHERE salesperson_id=? AND status="available" AND expires_at > ? ORDER BY created_at DESC LIMIT 1',
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
        'full_address': ((dealership_row['address'] + ', ') if dealership_row and dealership_row['address'] else '') + city + ', ' + ((dealership_row['state']) if dealership_row and dealership_row['state'] else 'NJ') + ' ' + ((dealership_row['zip']) if dealership_row and dealership_row['zip'] else ''),
        'google_rating': dealership_row['google_rating'] if dealership_row and dealership_row['google_rating'] else None,
        'google_review_count': dealership_row['google_review_count'] if dealership_row and dealership_row['google_review_count'] else None,
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
        'mileage': vehicle['mileage'] if vehicle['mileage'] else '',
        'exterior_color': vehicle['exterior_color'] if vehicle['exterior_color'] else '',
        'transmission': vehicle['transmission'] if vehicle['transmission'] else '',
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


@salesperson_bp.route('/api/generate_social_ad_image', methods=['POST'])
def generate_social_ad_image():
    import io, requests as _req
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    from flask import request as _request, Response, session

    team_member_id = session.get('team_member_id')
    if not team_member_id:
        return ('', 401)

    # Get JSON data from request
    data = _request.get_json() or {}

    # Required fields
    profile_photo = data.get('profile_photo', '')
    vehicle_photo = data.get('vehicle_photo', '')
    name = data.get('name', '')
    dealership = data.get('dealership', '')
    city = data.get('city', '')
    full_address = data.get('full_address', city + ', NJ')
    vehicle_name = data.get('vehicle_name', '')
    price = data.get('price', '')
    days_left = int(data.get('days_left', 0))
    cars_live = str(data.get('cars_live', '0'))
    starting_at = data.get('starting_at', '')
    slug = data.get('slug', '')
    include_referral = data.get('include_referral', False)

    W, H = 1080, 1080
    NAVY = (30, 41, 59)
    GREEN = (0, 200, 81)
    WHITE = (255, 255, 255)
    GRAY = (100, 116, 139)
    LIGHT = (248, 250, 252)

    img = Image.new('RGB', (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    def fetch_img(url):
        try:
            r = _req.get(url, timeout=10)
            return Image.open(io.BytesIO(r.content)).convert('RGBA')
        except:
            return None

    # Load fonts - use default if custom not available
    try:
        font_bold_lg = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 52)
        font_bold_md = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 40)
        font_bold_sm = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 28)
        font_reg = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 28)
        font_sm = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 22)
        font_price = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 60)
        font_car = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 44)
    except:
        font_bold_lg = font_bold_md = font_bold_sm = font_reg = font_sm = font_price = font_car = ImageFont.load_default()

    # Profile fetched here, drawn after gradient
    cx, cy, cr = 110, 110, 70
    profile_img = fetch_img(profile_photo)

    # SECTION 2: Vehicle photo (220-660px)
    car_y, car_h = 220, 440
    car_img = fetch_img(vehicle_photo)
    if car_img:
        car_img = car_img.convert('RGB')
        scale = max(W / car_img.width, car_h / car_img.height)
        nw, nh = int(car_img.width * scale), int(car_img.height * scale)
        car_img = car_img.resize((nw, nh))
        dx = (W - nw) // 2
        dy = car_y + (car_h - nh) // 2
        # Clip paste to car section only
        from PIL import Image as _Img
        car_region = Image.new('RGB', (W, car_h), (226, 232, 240))
        paste_y = dy - car_y
        car_region.paste(car_img, (dx, paste_y))
        img.paste(car_region, (0, car_y))
    else:
        draw.rectangle([0, car_y, W, car_y+car_h], fill=(226, 232, 240))

    # Gradient overlay using RGBA composite
    gradient = Image.new('RGBA', (W, car_h), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for i in range(car_h):
        alpha = int(200 * (i / car_h) ** 2)
        grad_draw.line([0, i, W, i], fill=(0, 0, 0, alpha))
    img_rgba = img.convert('RGBA')
    img_rgba.paste(gradient, (0, car_y), gradient)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # SECTION 1: Profile (drawn after gradient to avoid RGBA conversion loss)
    draw.rectangle([0, 0, W, 220], fill=WHITE)
    if profile_img:
        profile_img = profile_img.resize((cr*2, cr*2))
        mask = Image.new('L', (cr*2, cr*2), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, cr*2-1, cr*2-1], fill=255)
        profile_img = profile_img.convert('RGB')
        img.paste(profile_img, (cx-cr, cy-cr), mask)
    draw.ellipse([cx-cr-6, cy-cr-6, cx+cr+6, cy+cr+6], outline=GREEN, width=5)
    tx = cx + cr + 30
    draw.text((tx, 65), name, font=font_bold_lg, fill=NAVY)
    draw.text((tx, 130), 'Sales Professional', font=font_sm, fill=GRAY)
    draw.rounded_rectangle([W-270, 25, W-15, 80], radius=25, fill=GREEN)
    draw.text((W-143, 52), 'Fresh Inventory', font=font_bold_sm, fill=WHITE, anchor='mm')
    draw.line([40, 205, W-40, 205], fill=(226, 232, 240), width=2)

    # Days left badge
    if days_left > 0:
        badge_color = (220, 38, 38) if days_left <= 2 else (249, 115, 22) if days_left <= 4 else GREEN
        draw.rounded_rectangle([24, car_y+20, 250, car_y+76], radius=28, fill=badge_color)
        draw.text((137, car_y+48), str(days_left) + ' Days Left', font=font_bold_sm, fill=WHITE, anchor='mm')

    # Car name and price overlay
    draw.text((30, car_y+car_h-70), vehicle_name, font=font_car, fill=WHITE)
    bbox = draw.textbbox((0,0), price, font=font_price)
    # SECTION 3: Stats bar
    stats_y = 660
    draw.text((W-30, stats_y), price, font=font_price, fill=GREEN, anchor='rb')
    draw.rectangle([0, stats_y, W, stats_y+100], fill=NAVY)
    stats = [(cars_live, 'Cars Live'), (starting_at, 'Starting At')]
    positions = [W//4, W*3//4]
    for i, (val, label) in enumerate(stats):
        sx = positions[i]
        draw.text((sx, stats_y+40), val, font=font_bold_md, fill=GREEN, anchor='mm')
        draw.text((sx, stats_y+78), label, font=font_sm, fill=(200, 210, 220), anchor='mm')
    draw.line([(W//2), stats_y+18, (W//2), stats_y+88], fill=(60, 80, 100), width=1)

    # SECTION 4: Referral
    next_y = stats_y + 100
    if include_referral:
        draw.rectangle([0, next_y, W, next_y+80], fill=(240, 253, 244))
        draw.rectangle([0, next_y, W, next_y+80], outline=(187, 247, 208), width=2)
        draw.text((W//2, next_y+40), 'Know someone? Refer them -- they buy -- you receive a Thank You gift', font=font_bold_sm, fill=(6, 95, 70), anchor='mm')
        next_y += 80

    # SECTION 5: Dealership proud bottom
    draw.rectangle([0, next_y, W, H], fill=WHITE)
    try:
        font_dealership = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 54)
        font_dealership_addr = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 26)
    except:
        font_dealership = font_bold_md
        font_dealership_addr = font_sm
    draw.line([80, next_y+20, W-80, next_y+20], fill=(226, 232, 240), width=2)
    draw.text((W//2, next_y+70), dealership, font=font_dealership, fill=NAVY, anchor='mm')
    draw.text((W//2, next_y+110), full_address, font=font_dealership_addr, fill=GRAY, anchor='mm')
    # Google reviews badge
    google_rating = data.get('google_rating')
    google_review_count = data.get('google_review_count')
    if google_rating and google_review_count:
        badge_y = next_y + 138
        badge_text = f'★ {google_rating}  ·  {google_review_count} Google reviews'
        try:
            font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 22)
        except:
            font_badge = font_sm
        # Draw pill background
        bbox = draw.textbbox((0,0), badge_text, font=font_badge)
        bw = bbox[2] - bbox[0] + 32
        bh = bbox[3] - bbox[1] + 14
        bx = W//2 - bw//2
        by = badge_y
        draw.rounded_rectangle([bx, by, bx+bw, by+bh], radius=12, fill=(255,255,255), outline=(226,232,240), width=1)
        # Draw G in blue
        try:
            font_g = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 22)
        except:
            font_g = font_badge
        draw.text((bx+10, by+bh//2), 'G', font=font_g, fill=(66,133,244), anchor='lm')
        # Draw stars in gold
        draw.text((bx+26, by+bh//2), f'★ {google_rating}', font=font_badge, fill=(245,158,11), anchor='lm')
        # Draw review count
        rating_bbox = draw.textbbox((0,0), f'★ {google_rating}', font=font_badge)
        rw = rating_bbox[2] - rating_bbox[0]
        draw.text((bx+30+rw, by+bh//2), f'  ·  {google_review_count} Google reviews', font=font_badge, fill=(107,114,128), anchor='lm')
        draw.text((W-30, badge_y+bh+8), 'Powered by CarsInStock', font=font_dealership_addr, fill=(203, 213, 225), anchor='rm')
    else:
        draw.text((W-30, next_y+148), 'Powered by CarsInStock', font=font_dealership_addr, fill=(203, 213, 225), anchor='rm')

    template = data.get('template', 'classic')

    if template == 'just_listed':
        # JUST LISTED TEMPLATE — Full bleed car photo, elegant overlay
        jl_img = Image.new('RGB', (W, H), (0, 0, 0))

        # Full bleed car photo
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(W / car_copy.width, H / car_copy.height)
            nw, nh = int(car_copy.width * scale), int(car_copy.height * scale)
            car_copy = car_copy.resize((nw, nh))
            dx = (W - nw) // 2
            dy = (H - nh) // 2
            jl_img.paste(car_copy, (dx, dy))

        # Dark gradient overlay
        gradient = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(gradient)
        for i in range(H):
            alpha = int(210 * (i / H) ** 1.4)
            grad_draw.line([0, i, W, i], fill=(0, 0, 0, alpha))
        jl_rgba = jl_img.convert('RGBA')
        jl_rgba.paste(gradient, (0, 0), gradient)
        jl_img = jl_rgba.convert('RGB')
        jl_draw = ImageDraw.Draw(jl_img)

        # Top left profile photo
        if profile_img:
            pr = profile_img.resize((90, 90))
            mask = Image.new('L', (90, 90), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 89, 89], fill=255)
            pr = pr.convert('RGB')
            jl_img.paste(pr, (30, 30), mask)
        jl_draw.ellipse([24, 24, 126, 126], outline=GREEN, width=4)

        # Top right Fresh Inventory badge
        jl_draw.rounded_rectangle([W-280, 30, W-20, 84], radius=27, fill=GREEN)
        jl_draw.text((W-150, 57), 'Fresh Inventory', font=font_bold_sm, fill=WHITE, anchor='mm')


        # Center Just Listed text
        try:
            font_script = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf', 100)
        except:
            font_script = font_bold_lg
        jl_draw.text((W//2, 360), 'Just Listed', font=font_script, fill=WHITE, anchor='mm')

        # Divider line
        jl_draw.line([120, 420, W-120, 420], fill=(255, 255, 255), width=1)

        # Vehicle name
        jl_draw.text((W//2, 490), vehicle_name, font=font_bold_lg, fill=WHITE, anchor='mm')

        # Price in green
        jl_draw.text((W//2, 575), price, font=font_price, fill=GREEN, anchor='mm')

        # Days left badge
        if days_left > 0:
            badge_color = (220, 38, 38) if days_left <= 2 else (249, 115, 22) if days_left <= 4 else GREEN
            jl_draw.rounded_rectangle([W//2-110, 625, W//2+110, 681], radius=28, fill=badge_color)
            jl_draw.text((W//2, 653), f'{days_left} Days Left', font=font_bold_sm, fill=WHITE, anchor='mm')

        # Bottom navy strip
        jl_draw.rectangle([0, 800, W, 920], fill=NAVY)
        jl_draw.text((40, 860), name, font=font_bold_md, fill=WHITE, anchor='lm')
        jl_draw.text((W-40, 860), 'cardeals.autos/' + slug, font=font_bold_sm, fill=GREEN, anchor='rm')

        # Dealership strip
        jl_draw.rectangle([0, 920, W, 1010], fill=(20, 30, 48))
        jl_draw.text((W//2, 948), dealership, font=font_bold_sm, fill=WHITE, anchor='mm')
        jl_draw.text((W//2, 976), full_address, font=font_sm, fill=(180, 190, 200), anchor='mm')
        try:
            font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
        except:
            font_tiny = font_sm
        jl_draw.text((W-30, 1000), 'Powered by CarsInStock', font=font_tiny, fill=(160, 170, 185), anchor='rm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = jl_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 992
            jl_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            jl_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            jl_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = jl_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-jl_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            jl_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf = io.BytesIO()
        jl_img.save(buf, format='PNG')
        buf.seek(0)
        return Response(buf.read(), content_type='image/png')

    if template == 'urgency':
        urg_img = Image.new('RGB', (W, H), (0, 0, 0))

        # Full bleed car photo
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(W / car_copy.width, H / car_copy.height)
            nw, nh = int(car_copy.width * scale), int(car_copy.height * scale)
            car_copy = car_copy.resize((nw, nh))
            dx = (W - nw) // 2
            dy = (H - nh) // 2
            urg_img.paste(car_copy, (dx, dy))

        # Heavy dark overlay — more dramatic than Just Listed
        gradient = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(gradient)
        for i in range(H):
            alpha = int(230 * (i / H) ** 1.2)
            grad_draw.line([0, i, W, i], fill=(0, 0, 0, alpha))
        urg_rgba = urg_img.convert('RGBA')
        urg_rgba.paste(gradient, (0, 0), gradient)
        urg_img = urg_rgba.convert('RGB')
        urg_draw = ImageDraw.Draw(urg_img)

        # Top left profile photo - bigger, no name
        if profile_img:
            pr = profile_img.resize((110, 110))
            mask = Image.new('L', (110, 110), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 109, 109], fill=255)
            pr = pr.convert('RGB')
            urg_img.paste(pr, (25, 25), mask)
        urg_draw.ellipse([19, 19, 141, 141], outline=GREEN, width=5)

        # Days left — BIG urgent badge top center
        if days_left > 0:
            badge_color = (220, 38, 38) if days_left <= 2 else (249, 115, 22) if days_left <= 4 else (200, 30, 30)
            urg_draw.rounded_rectangle([W//2-180, 25, W//2+180, 105], radius=50, fill=badge_color)
            try:
                font_urgent = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
            except:
                font_urgent = font_bold_md
            urg_draw.text((W//2, 65), f'⚠ {days_left} DAYS LEFT', font=font_urgent, fill=WHITE, anchor='mm')

        # THIS WON'T LAST text - elegant serif italic
        try:
            font_wont = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf', 52)
        except:
            font_wont = font_bold_md
        urg_draw.text((W//2, 165), "This Won't Last", font=font_wont, fill=(255, 210, 60), anchor='mm')

        # Vehicle name
        urg_draw.text((W//2, 480), vehicle_name, font=font_bold_lg, fill=WHITE, anchor='mm')

        # Price
        urg_draw.text((W//2, 570), price, font=font_price, fill=GREEN, anchor='mm')

        # Bottom navy strip
        urg_draw.rectangle([0, 800, W, 920], fill=NAVY)
        urg_draw.text((40, 860), name, font=font_bold_md, fill=WHITE, anchor='lm')
        urg_draw.text((W-40, 860), 'cardeals.autos/' + slug, font=font_bold_sm, fill=GREEN, anchor='rm')

        # Dealership strip
        urg_draw.rectangle([0, 920, W, 1010], fill=(20, 30, 48))
        urg_draw.text((W//2, 948), dealership, font=font_bold_sm, fill=WHITE, anchor='mm')
        urg_draw.text((W//2, 976), full_address, font=font_sm, fill=(180, 190, 200), anchor='mm')
        try:
            font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
        except:
            font_tiny = font_sm
        urg_draw.text((W-30, 1000), 'Powered by CarsInStock', font=font_tiny, fill=(160, 170, 185), anchor='rm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = urg_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 992
            urg_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            urg_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            urg_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = urg_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-urg_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            urg_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf = io.BytesIO()
        urg_img.save(buf, format='PNG')
        buf.seek(0)
        return Response(buf.read(), content_type='image/png')

    if template == 'personal':
        pb_img = Image.new('RGB', (W, H), NAVY)
        pb_draw = ImageDraw.Draw(pb_img)

        # Left half — rep photo large, face centered
        if profile_img:
            pr = profile_img.convert('RGB')
            # Crop to square from top center to show face
            pw, ph = pr.size
            side = min(pw, ph)
            left = (pw - side) // 2
            top = 0
            pr = pr.crop((left, top, left + side, top + side))
            pr = pr.resize((480, 480))
            mask = Image.new('L', (480, 480), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 479, 479], fill=255)
            pb_img.paste(pr, (60, 140), mask)
            pb_draw.ellipse([54, 134, 546, 626], outline=GREEN, width=6)

        # Right half — car photo
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(480 / car_copy.width, 360 / car_copy.height)
            nw, nh = int(car_copy.width * scale), int(car_copy.height * scale)
            car_copy = car_copy.resize((nw, nh))
            car_region = Image.new('RGB', (480, 360), NAVY)
            dx = (480 - nw) // 2
            dy = (360 - nh) // 2
            car_region.paste(car_copy, (dx, dy))
            pb_img.paste(car_region, (580, 160))

        # Green accent line top
        pb_draw.rectangle([0, 0, W, 8], fill=GREEN)

        # Rep name — large and bold left side bottom
        try:
            font_name_lg = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 52)
        except:
            font_name_lg = font_bold_lg
        pb_draw.text((60, 650), name, font=font_name_lg, fill=WHITE, anchor='lm')
        pb_draw.text((60, 706), 'Sales Professional', font=font_sm, fill=GREEN, anchor='lm')

        # Vehicle info right side
        pb_draw.text((580, 540), vehicle_name, font=font_bold_md, fill=WHITE, anchor='lm')
        pb_draw.text((580, 590), price, font=font_bold_lg, fill=GREEN, anchor='lm')

        # Days left badge
        if days_left > 0:
            badge_color = (220, 38, 38) if days_left <= 2 else (249, 115, 22) if days_left <= 4 else GREEN
            pb_draw.rounded_rectangle([580, 630, 580+200, 630+46], radius=23, fill=badge_color)
            pb_draw.text((680, 653), f'{days_left} Days Left', font=font_bold_sm, fill=WHITE, anchor='mm')

        # Bottom strip
        pb_draw.rectangle([0, 800, W, 920], fill=(20, 30, 48))
        pb_draw.text((40, 860), 'cardeals.autos/' + slug, font=font_bold_sm, fill=GREEN, anchor='lm')
        pb_draw.text((W-40, 845), dealership, font=font_bold_sm, fill=WHITE, anchor='rm')
        pb_draw.text((W-40, 878), full_address, font=font_sm, fill=(180, 190, 200), anchor='rm')

        # Dealership address
        pb_draw.rectangle([0, 920, W, 1010], fill=(15, 23, 42))
        try:
            font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
        except:
            font_tiny = font_sm
        pb_draw.text((40, 965), 'Powered by CarsInStock', font=font_tiny, fill=(160, 170, 185), anchor='lm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = pb_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 982
            pb_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            pb_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            pb_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = pb_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-pb_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            pb_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')

        buf = io.BytesIO()
        pb_img.save(buf, format='PNG')
        buf.seek(0)
        return Response(buf.read(), content_type='image/png')

    if template == 'dealsheet':
        from PIL import ImageOps
        ds_img = Image.new('RGB', (W, 900), (255, 255, 255))
        ds_draw = ImageDraw.Draw(ds_img)

        # ZONE 1: Top green accent line
        ds_draw.rectangle([0, 0, W, 8], fill=GREEN)

        # ZONE 2: Rep info bar (y=8 to y=155)
        if profile_img:
            pr = profile_img.convert('RGB')
            pw, ph = pr.size
            side = min(pw, ph)
            pr = pr.crop(((pw-side)//2, 0, (pw-side)//2+side, side))
        pr = pr.resize((80, 80))
        mask = Image.new('L', (80, 80), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 79, 79], fill=255)
        ds_img.paste(pr, (20, 15), mask)
        ds_draw.ellipse([14, 9, 106, 101], outline=GREEN, width=3)
        ds_draw.text((115, 42), name, font=font_bold_sm, fill=NAVY, anchor='lm')
        ds_draw.text((115, 70), dealership, font=font_sm, fill=(100, 116, 139), anchor='lm')
        ds_draw.rounded_rectangle([W-220, 30, W-15, 72], radius=20, fill=GREEN)
        ds_draw.text((W-118, 51), "THIS WEEK'S PICK", font=font_sm, fill=WHITE, anchor='mm')
        ds_draw.line([20, 118, W-20, 118], fill=(220, 228, 240), width=1)

        # ZONE 3: Car photo fixed crop (y=150 to y=530)
        car_zone_top = 120
        car_zone_height = 460
        car_region = Image.new('RGB', (W, car_zone_height), (230, 235, 240))
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(W / car_copy.width, car_zone_height / car_copy.height)
            nw = int(car_copy.width * scale)
            nh = int(car_copy.height * scale)
            car_copy = car_copy.resize((nw, nh))
            dx = (W - nw) // 2
            dy = (car_zone_height - nh) // 2
            car_region.paste(car_copy, (dx, dy))
        ds_img.paste(car_region, (0, car_zone_top))

        # Days left badge on car
        if days_left > 0:
            badge_color = (220, 38, 38) if days_left <= 2 else (249, 115, 22) if days_left <= 4 else GREEN
            ds_draw.rounded_rectangle([18, car_zone_top+14, 210, car_zone_top+60], radius=24, fill=badge_color)
            ds_draw.text((114, car_zone_top+37), f'{days_left} Days Left', font=font_bold_sm, fill=WHITE, anchor='mm')

        # ZONE 4: Navy data section (y=530 to y=720)
        ds_draw.rectangle([0, 580, W, 720], fill=NAVY)
        ds_draw.text((W//2, 612), vehicle_name, font=font_bold_lg, fill=WHITE, anchor='mm')
        ds_draw.text((W//2, 648), price, font=font_bold_md, fill=GREEN, anchor='mm')

        # Three data points
        mileage_str = f"{int(data.get('mileage', 0)):,} mi" if data.get('mileage') else 'N/A'
        color_str = str(data.get('exterior_color', '') or 'N/A')
        trans_str = str(data.get('transmission', '') or 'N/A')
        if len(trans_str) > 12:
            trans_str = trans_str[:12]
        if len(color_str) > 12:
            color_str = color_str[:12]

        ds_draw.line([W//3, 670, W//3, 712], fill=(80, 100, 130), width=1)
        ds_draw.line([W*2//3, 670, W*2//3, 712], fill=(80, 100, 130), width=1)
        for idx, (val, label) in enumerate([(mileage_str, 'Mileage'), (color_str, 'Color'), (trans_str, 'Trans')]):
            sx = W//6 + (W//3)*idx
            ds_draw.text((sx, 686), val, font=font_bold_sm, fill=WHITE, anchor='mm')
            ds_draw.text((sx, 708), label, font=font_sm, fill=(148, 163, 184), anchor='mm')

        # ZONE 5: Link section (y=720 to y=860)
        ds_draw.rectangle([0, 720, W, 790], fill=(248, 250, 252))
        ds_draw.line([20, 722, W-20, 722], fill=(220, 228, 240), width=1)
        if include_referral:
            ds_draw.rectangle([0, 720, W, 758], fill=(240, 253, 244))
            ds_draw.text((W//2, 739), 'Refer a friend — they buy — you receive a Thank You gift', font=font_sm, fill=(6, 95, 70), anchor='mm')
        ds_draw.text((W//2, 762), 'cardeals.autos/' + slug, font=font_bold_md, fill=GREEN, anchor='mm')

        # ZONE 6: Footer (y=860 to y=1000)
        ds_draw.rectangle([0, 790, W, 880], fill=(241, 245, 249))
        ds_draw.line([20, 792, W-20, 792], fill=(220, 228, 240), width=1)
        ds_draw.text((W//2, 822), dealership, font=font_bold_sm, fill=NAVY, anchor='mm')
        ds_draw.text((W//2, 850), full_address, font=font_sm, fill=(100, 116, 139), anchor='mm')
        try:
            font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
        except:
            font_tiny = font_sm
        ds_draw.text((W-20, 872), 'Powered by CarsInStock', font=font_tiny, fill=(160, 170, 185), anchor='rm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = ds_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 888
            ds_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=(240,242,245))
            ds_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ds_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = ds_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-ds_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            ds_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')

        buf = io.BytesIO()
        ds_img.save(buf, format='PNG')
        buf.seek(0)
        return Response(buf.read(), content_type='image/png')

    if template == 'lowmiles':
        lm_img = Image.new('RGB', (W, H), (0, 0, 0))
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(W / car_copy.width, H / car_copy.height)
            nw, nh = int(car_copy.width * scale), int(car_copy.height * scale)
            car_copy = car_copy.resize((nw, nh))
            lm_img.paste(car_copy, ((W-nw)//2, (H-nh)//2))
        gradient = Image.new('RGBA', (W, H), (0,0,0,0))
        gd = ImageDraw.Draw(gradient)
        for i in range(H):
            gd.line([0,i,W,i], fill=(0,0,0,int(200*(i/H)**1.3)))
        lm_rgba = lm_img.convert('RGBA')
        lm_rgba.paste(gradient, (0,0), gradient)
        lm_img = lm_rgba.convert('RGB')
        lm_draw = ImageDraw.Draw(lm_img)
        # Top badge
        lm_draw.rounded_rectangle([W//2-220, 30, W//2+220, 100], radius=35, fill=(59,130,246))
        lm_draw.text((W//2, 65), '🔢  LOW MILES', font=font_bold_md, fill=WHITE, anchor='mm')
        # Rep photo
        if profile_img:
            pr = profile_img.convert('RGB')
            pw,ph = pr.size; side=min(pw,ph)
            pr = pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((90,90))
            mask = Image.new('L',(90,90),0); ImageDraw.Draw(mask).ellipse([0,0,89,89],fill=255)
            lm_img.paste(pr,(30,30),mask)
            lm_draw.ellipse([24,24,126,126],outline=GREEN,width=4)
        lm_draw.text((W//2, 370), vehicle_name, font=font_bold_lg, fill=WHITE, anchor='mm')
        mileage_str = f"{int(data.get('mileage',0)):,} Miles" if data.get('mileage') else 'Low Miles'
        lm_draw.text((W//2, 460), mileage_str, font=font_price, fill=(59,130,246), anchor='mm')
        lm_draw.text((W//2, 560), price, font=font_bold_lg, fill=GREEN, anchor='mm')
        if days_left > 0:
            bc = (220,38,38) if days_left<=2 else (249,115,22) if days_left<=4 else GREEN
            lm_draw.rounded_rectangle([W//2-120,610,W//2+120,662],radius=30,fill=bc)
            lm_draw.text((W//2,636),f'{days_left} Days Left',font=font_bold_sm,fill=WHITE,anchor='mm')
        lm_draw.rectangle([0,800,W,920],fill=NAVY)
        lm_draw.text((40,860),name,font=font_bold_md,fill=WHITE,anchor='lm')
        lm_draw.text((W-40,860),'cardeals.autos/'+slug,font=font_bold_sm,fill=GREEN,anchor='rm')
        lm_draw.rectangle([0,920,W,1010],fill=(20,30,48))
        lm_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        lm_draw.text((W//2,976),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = lm_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 992
            lm_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            lm_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            lm_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = lm_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-lm_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            lm_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); lm_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    if template == 'warranty':
        wt_img = Image.new('RGB', (W, H), (0, 0, 0))
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(W / car_copy.width, H / car_copy.height)
            nw, nh = int(car_copy.width * scale), int(car_copy.height * scale)
            car_copy = car_copy.resize((nw, nh))
            wt_img.paste(car_copy, ((W-nw)//2, (H-nh)//2))
        gradient = Image.new('RGBA', (W, H), (0,0,0,0))
        gd = ImageDraw.Draw(gradient)
        for i in range(H):
            gd.line([0,i,W,i], fill=(0,0,0,int(210*(i/H)**1.3)))
        wt_rgba = wt_img.convert('RGBA')
        wt_rgba.paste(gradient,(0,0),gradient)
        wt_img = wt_rgba.convert('RGB')
        wt_draw = ImageDraw.Draw(wt_img)
        # Top yellow badge full width
        wt_draw.rectangle([0, 0, W, 90], fill=(234,179,8))
        wt_draw.text((W//2, 45), 'FACTORY WARRANTY', font=font_bold_lg, fill=NAVY, anchor='mm')
        # Rep photo top left
        if profile_img:
            pr = profile_img.convert('RGB')
            pw,ph = pr.size; side=min(pw,ph)
            pr = pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((90,90))
            mask = Image.new('L',(90,90),0); ImageDraw.Draw(mask).ellipse([0,0,89,89],fill=255)
            wt_img.paste(pr,(30,110),mask)
            wt_draw.ellipse([24,104,126,206],outline=(234,179,8),width=4)
        # Vehicle info
        wt_draw.text((W//2, 480), vehicle_name, font=font_bold_lg, fill=WHITE, anchor='mm')
        wt_draw.text((W//2, 570), price, font=font_price, fill=GREEN, anchor='mm')
        wt_draw.text((W//2, 650), 'Still Under Factory Warranty', font=font_bold_sm, fill=(234,179,8), anchor='mm')
        if days_left > 0:
            bc = (220,38,38) if days_left<=2 else (249,115,22) if days_left<=4 else GREEN
            wt_draw.rounded_rectangle([W//2-120,700,W//2+120,752],radius=30,fill=bc)
            wt_draw.text((W//2,726),f'{days_left} Days Left',font=font_bold_sm,fill=WHITE,anchor='mm')
        wt_draw.rectangle([0,800,W,920],fill=NAVY)
        wt_draw.text((40,860),name,font=font_bold_md,fill=WHITE,anchor='lm')
        wt_draw.text((W-40,860),'cardeals.autos/'+slug,font=font_bold_sm,fill=GREEN,anchor='rm')
        wt_draw.rectangle([0,920,W,1010],fill=(20,30,48))
        wt_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        wt_draw.text((W//2,976),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = wt_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 992
            wt_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            wt_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            wt_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = wt_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-wt_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            wt_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); wt_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    if template == 'cleancarfax':
        cc_img = Image.new('RGB', (W, H), (0,0,0))
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,H/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            cc_img.paste(car_copy,((W-nw)//2,(H-nh)//2))
        gradient=Image.new('RGBA',(W,H),(0,0,0,0))
        gd=ImageDraw.Draw(gradient)
        for i in range(H): gd.line([0,i,W,i],fill=(0,0,0,int(210*(i/H)**1.3)))
        cc_rgba=cc_img.convert('RGBA'); cc_rgba.paste(gradient,(0,0),gradient)
        cc_img=cc_rgba.convert('RGB'); cc_draw=ImageDraw.Draw(cc_img)
        cc_draw.rounded_rectangle([W//2-230,30,W//2+230,100],radius=35,fill=GREEN)
        cc_draw.text((W//2,65),'✅  CLEAN CARFAX',font=font_bold_md,fill=WHITE,anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB'); pw,ph=pr.size; side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((90,90))
            mask=Image.new('L',(90,90),0); ImageDraw.Draw(mask).ellipse([0,0,89,89],fill=255)
            cc_img.paste(pr,(30,30),mask)
            cc_draw.ellipse([24,24,126,126],outline=GREEN,width=4)
        cc_draw.text((W//2,370),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        cc_draw.text((W//2,460),price,font=font_price,fill=GREEN,anchor='mm')
        cc_draw.text((W//2,550),'No Accidents · Clean Title · Ready to Go',font=font_bold_sm,fill=(200,255,200),anchor='mm')
        if days_left>0:
            bc=(220,38,38) if days_left<=2 else (249,115,22) if days_left<=4 else GREEN
            cc_draw.rounded_rectangle([W//2-120,610,W//2+120,662],radius=30,fill=bc)
            cc_draw.text((W//2,636),f'{days_left} Days Left',font=font_bold_sm,fill=WHITE,anchor='mm')
        cc_draw.rectangle([0,800,W,920],fill=NAVY)
        cc_draw.text((40,860),name,font=font_bold_md,fill=WHITE,anchor='lm')
        cc_draw.text((W-40,860),'cardeals.autos/'+slug,font=font_bold_sm,fill=GREEN,anchor='rm')
        cc_draw.rectangle([0,920,W,1010],fill=(20,30,48))
        cc_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        cc_draw.text((W//2,976),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = cc_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 992
            cc_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            cc_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            cc_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = cc_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-cc_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            cc_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); cc_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    if template == 'oneowner':
        oo_img = Image.new('RGB', (W, H), (0,0,0))
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,H/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            oo_img.paste(car_copy,((W-nw)//2,(H-nh)//2))
        gradient=Image.new('RGBA',(W,H),(0,0,0,0))
        gd=ImageDraw.Draw(gradient)
        for i in range(H): gd.line([0,i,W,i],fill=(0,0,0,int(210*(i/H)**1.3)))
        oo_rgba=oo_img.convert('RGBA'); oo_rgba.paste(gradient,(0,0),gradient)
        oo_img=oo_rgba.convert('RGB'); oo_draw=ImageDraw.Draw(oo_img)
        oo_draw.rounded_rectangle([W//2-230,30,W//2+230,100],radius=35,fill=(168,85,247))
        oo_draw.text((W//2,65),'👤  ONE OWNER',font=font_bold_md,fill=WHITE,anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB'); pw,ph=pr.size; side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((90,90))
            mask=Image.new('L',(90,90),0); ImageDraw.Draw(mask).ellipse([0,0,89,89],fill=255)
            oo_img.paste(pr,(30,30),mask)
            oo_draw.ellipse([24,24,126,126],outline=GREEN,width=4)
        oo_draw.text((W//2,370),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        oo_draw.text((W//2,460),price,font=font_price,fill=GREEN,anchor='mm')
        oo_draw.text((W//2,550),'Loved by One · Ready for You',font=font_bold_sm,fill=(220,200,255),anchor='mm')
        if days_left>0:
            bc=(220,38,38) if days_left<=2 else (249,115,22) if days_left<=4 else GREEN
            oo_draw.rounded_rectangle([W//2-120,610,W//2+120,662],radius=30,fill=bc)
            oo_draw.text((W//2,636),f'{days_left} Days Left',font=font_bold_sm,fill=WHITE,anchor='mm')
        oo_draw.rectangle([0,800,W,920],fill=NAVY)
        oo_draw.text((40,860),name,font=font_bold_md,fill=WHITE,anchor='lm')
        oo_draw.text((W-40,860),'cardeals.autos/'+slug,font=font_bold_sm,fill=GREEN,anchor='rm')
        oo_draw.rectangle([0,920,W,1010],fill=(20,30,48))
        oo_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        oo_draw.text((W//2,976),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            bbox = oo_draw.textbbox((0,0), f'G ★ {google_rating} · {google_review_count} Google reviews', font=font_badge)
            bw = bbox[2]-bbox[0]+28; bh = bbox[3]-bbox[1]+12
            bx = W//2-bw//2; by = 992
            oo_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            oo_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            oo_draw.text((bx+26,by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw = oo_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[2]-oo_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)[0]
            oo_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); oo_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    if template == 'referral':
        rf_img = Image.new('RGB', (W, H), NAVY)
        rf_draw = ImageDraw.Draw(rf_img)
        # Top green accent
        rf_draw.rectangle([0,0,W,8],fill=GREEN)
        # Large rep photo center top
        if profile_img:
            pr=profile_img.convert('RGB'); pw,ph=pr.size; side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((280,280))
            mask=Image.new('L',(280,280),0); ImageDraw.Draw(mask).ellipse([0,0,279,279],fill=255)
            rf_img.paste(pr,(W//2-140,60),mask)
            rf_draw.ellipse([W//2-146,54,W//2+146,346],outline=GREEN,width=6)
        # Rep name and title
        rf_draw.text((W//2,390),name,font=font_bold_lg,fill=WHITE,anchor='mm')
        rf_draw.text((W//2,440),'Sales Professional · '+dealership,font=font_sm,fill=(148,163,184),anchor='mm')
        rf_draw.line([80,475,W-80,475],fill=(51,65,85),width=1)
        # Message
        rf_draw.text((W//2,540),'Know someone buying a car?',font=font_bold_md,fill=WHITE,anchor='mm')
        try:
            font_script=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf',64)
        except:
            font_script=font_bold_lg
        rf_draw.text((W//2,620),'Send them my way.',font=font_script,fill=GREEN,anchor='mm')
        # $100 badge — full width with padding
        rf_draw.rounded_rectangle([60,670,W-60,740],radius=35,fill=GREEN)
        rf_draw.text((W//2,705),'They buy — You receive a Thank You gift',font=font_bold_md,fill=NAVY,anchor='mm')
        # Referral link
        rf_draw.text((W//2,800),'cardeals.autos/'+slug,font=font_bold_md,fill=GREEN,anchor='mm')
        # Footer
        rf_draw.rectangle([0,870,W,1010],fill=(20,30,48))
        rf_draw.text((W//2,903),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        rf_draw.text((W//2,935),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        # Google badge
        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 20)
            except:
                font_badge = font_sm
            g_text = f'G  ★ {google_rating}  ·  {google_review_count} Google reviews'
            bbox = rf_draw.textbbox((0,0), g_text, font=font_badge)
            bw = bbox[2] - bbox[0] + 28
            bh = bbox[3] - bbox[1] + 12
            bx = W//2 - bw//2
            by = 952
            rf_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            rf_draw.text((bx+10, by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            rf_draw.text((bx+26, by+bh//2),f'★ {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            star_bbox = rf_draw.textbbox((0,0),f'★ {google_rating}',font=font_badge)
            sw = star_bbox[2]-star_bbox[0]
            rf_draw.text((bx+30+sw, by+bh//2),f'  ·  {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); rf_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')



    # ── TEMPLATE: magazine ──────────────────────────────────────────────────
    if template == 'magazine':
        mg_img = Image.new('RGB', (W, H), (10, 10, 20))
        mg_draw = ImageDraw.Draw(mg_img)
        # Full bleed car photo top 65%
        if car_img:
            car_copy = car_img.convert('RGB')
            scale = max(W / car_copy.width, (H*0.65) / car_copy.height)
            nw, nh = int(car_copy.width*scale), int(car_copy.height*scale)
            car_copy = car_copy.resize((nw, nh))
            mg_img.paste(car_copy, ((W-nw)//2, 0))
        # Heavy gradient bottom half
        grad = Image.new('RGBA', (W, H), (0,0,0,0))
        gd = ImageDraw.Draw(grad)
        for i in range(H):
            a = int(255 * max(0, (i - H*0.25) / (H*0.75))**1.5)
            gd.line([0,i,W,i], fill=(10,10,20,min(a,255)))
        mg_rgba = mg_img.convert('RGBA')
        mg_rgba.paste(grad,(0,0),grad)
        mg_img = mg_rgba.convert('RGB')
        mg_draw = ImageDraw.Draw(mg_img)
        # Top bar
        mg_draw.rectangle([0,0,W,6], fill=GREEN)
        mg_draw.text((40,28),'CARS IN STOCK',font=font_bold_sm,fill=GREEN,anchor='lm')
        mg_draw.text((W-40,28),'EXCLUSIVE',font=font_sm,fill=(100,100,120),anchor='rm')
        # Large rep circle bottom left
        if profile_img:
            pr = profile_img.convert('RGB'); pw,ph=pr.size; side=min(pw,ph)
            pr = pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((140,140))
            mask = Image.new('L',(140,140),0); ImageDraw.Draw(mask).ellipse([0,0,139,139],fill=255)
            mg_img.paste(pr,(50,H-330),mask)
            mg_draw.ellipse([44,H-336,194,H-184],outline=GREEN,width=5)
        # Headline
        try:
            font_xl = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',72)
        except:
            font_xl = font_bold_lg
        parts = vehicle_name.split(' ',2)
        line1 = ' '.join(parts[:2]) if len(parts)>=2 else vehicle_name
        line2 = parts[2] if len(parts)>2 else ''
        mg_draw.text((220,H-290),line1,font=font_bold_lg,fill=WHITE,anchor='lm')
        if line2:
            mg_draw.text((220,H-230),line2,font=font_xl,fill=GREEN,anchor='lm')
        mg_draw.text((220,H-160),price,font=font_bold_lg,fill=WHITE,anchor='lm')
        mg_draw.text((220,H-110),name,font=font_sm,fill=(180,190,200),anchor='lm')
        mg_draw.text((220,H-78),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        # Footer
        mg_draw.rectangle([0,H-50,W,H],fill=(10,10,20))
        mg_draw.text((W//2,H-25),dealership+' · '+full_address,font=font_sm,fill=(80,90,110),anchor='mm')
        # Google badge — positioned bottom right, clear of rep circle
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=mg_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W-bw-20;by=H-58-bh
            mg_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            mg_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            mg_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=mg_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-mg_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            mg_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); mg_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: pricedrop ─────────────────────────────────────────────────
    if template == 'pricedrop':
        pd_img = Image.new('RGB', (W, H), NAVY)
        pd_draw = ImageDraw.Draw(pd_img)
        # Red price drop banner top
        pd_draw.rectangle([0,0,W,90],fill=(185,28,28))
        pd_draw.text((W//2,45),'PRICE DROP',font=font_bold_lg,fill=WHITE,anchor='mm')
        # Car photo middle
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,440/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,440),(30,41,59))
            region.paste(car_copy,((W-nw)//2,(440-nh)//2))
            pd_img.paste(region,(0,100))
        # Gradient over car bottom
        grad=Image.new('RGBA',(W,440),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(440):
            a=int(220*(i/440)**1.8)
            gd.line([0,i,W,i],fill=(30,41,59,min(a,255)))
        pd_rgba=pd_img.convert('RGBA')
        pd_rgba.paste(grad,(0,100),grad)
        pd_img=pd_rgba.convert('RGB')
        pd_draw=ImageDraw.Draw(pd_img)
        # Vehicle name
        pd_draw.text((W//2,560),vehicle_name,font=font_bold_md,fill=WHITE,anchor='mm')
        # Slashed old price + new price
        try:
            font_old=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',44)
        except:
            font_old=font_reg
        # Draw old price with strikethrough
        old_price_text = price  # we show same price with visual slash — dealer sets context
        pd_draw.text((W//2,640),f'WAS {old_price_text}',font=font_old,fill=(150,60,60),anchor='mm')
        bbox=pd_draw.textbbox((W//2,640),f'WAS {old_price_text}',font=font_old,anchor='mm')
        pd_draw.line([bbox[0],bbox[1]+(bbox[3]-bbox[1])//2,bbox[2],bbox[1]+(bbox[3]-bbox[1])//2],fill=(220,50,50),width=4)
        pd_draw.text((W//2,730),'NEW PRICE',font=font_bold_sm,fill=GREEN,anchor='mm')
        pd_draw.text((W//2,820),price,font=font_price,fill=GREEN,anchor='mm')
        # Rep + link
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            pd_img.paste(pr,(40,880),mask)
            pd_draw.ellipse([34,874,126,946],outline=GREEN,width=3)
        pd_draw.text((140,900),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        pd_draw.text((140,936),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        # Footer
        pd_draw.rectangle([0,H-60,W,H],fill=(15,25,40))
        pd_draw.text((W//2,H-30),dealership+' · '+full_address,font=font_sm,fill=(80,90,110),anchor='mm')
        # Google badge
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox2=pd_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox2[2]-bbox2[0]+28;bh=bbox2[3]-bbox2[1]+12;bx=W//2-bw//2;by=H-60-bh-8
            pd_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            pd_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            pd_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=pd_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-pd_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            pd_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); pd_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: freshtraded ───────────────────────────────────────────────
    if template == 'freshtraded':
        ft_img = Image.new('RGB', (W, H), (8,20,45))
        ft_draw = ImageDraw.Draw(ft_img)
        # Subtle diagonal stripe texture
        for i in range(0,W+H,40):
            ft_draw.line([i,0,i-H,H],fill=(15,30,60),width=1)
        # Car full bleed top 60%
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,(H*0.6)/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            ft_img.paste(car_copy,((W-nw)//2,0))
        # Gradient over bottom of car
        grad=Image.new('RGBA',(W,H),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(H):
            a=int(255*max(0,(i-H*0.3)/(H*0.7))**1.3)
            gd.line([0,i,W,i],fill=(8,20,45,min(a,255)))
        ft_rgba=ft_img.convert('RGBA')
        ft_rgba.paste(grad,(0,0),grad)
        ft_img=ft_rgba.convert('RGB')
        ft_draw=ImageDraw.Draw(ft_img)
        # FRESH TRADE badge
        ft_draw.rounded_rectangle([40,30,400,90],radius=30,fill=GREEN)
        ft_draw.ellipse([48,42,68,68],fill=WHITE)
        ft_draw.text((230,60),'FRESH TRADE — JUST ARRIVED',font=font_bold_sm,fill=NAVY,anchor='mm')
        # Vehicle + price
        ft_draw.text((W//2,620),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ft_draw.text((W//2,700),price,font=font_price,fill=GREEN,anchor='mm')
        ft_draw.text((W//2,780),'DM me before it\'s gone',font=font_sm,fill=(148,163,184),anchor='mm')
        # Rep row
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((90,90))
            mask=Image.new('L',(90,90),0);ImageDraw.Draw(mask).ellipse([0,0,89,89],fill=255)
            ft_img.paste(pr,(40,850),mask)
            ft_draw.ellipse([34,844,136,946],outline=GREEN,width=4)
        ft_draw.text((148,880),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ft_draw.text((148,918),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        # Footer
        ft_draw.rectangle([0,H-60,W,H],fill=(5,12,28))
        ft_draw.text((W//2,H-30),dealership+' · '+full_address,font=font_sm,fill=(60,80,110),anchor='mm')
        # Google badge
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ft_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-60-bh-8
            ft_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ft_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ft_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ft_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ft_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ft_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); ft_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: boldstreet ────────────────────────────────────────────────
    if template == 'boldstreet':
        ORANGE=(220,90,0)
        bs_img=Image.new('RGB',(W,H),ORANGE)
        bs_draw=ImageDraw.Draw(bs_img)
        # Oversized price watermark background
        try:
            font_wm=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',220)
        except:
            font_wm=font_bold_lg
        bs_draw.text((W//2,-20),price,font=font_wm,fill=(200,80,0),anchor='mm')
        # Car photo center
        if car_img:
            car_copy=car_img.convert('RGBA')
            scale=max((W*0.9)/car_copy.width,(H*0.5)/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            bs_img.paste(car_copy.convert('RGB'),((W-nw)//2,160))
        # Bottom dark section
        bs_draw.rectangle([0,700,W,H],fill=(20,10,0))
        bs_draw.text((40,750),'JUST DROPPED',font=font_bold_sm,fill=ORANGE,anchor='lm')
        bs_draw.text((40,800),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='lm')
        bs_draw.text((40,860),price,font=font_bold_lg,fill=GREEN,anchor='lm')
        # Rep
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((70,70))
            mask=Image.new('L',(70,70),0);ImageDraw.Draw(mask).ellipse([0,0,69,69],fill=255)
            bs_img.paste(pr,(40,910),mask)
            bs_draw.ellipse([34,904,116,976],outline=ORANGE,width=3)
        bs_draw.text((128,930),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        bs_draw.text((128,964),'cardeals.autos/'+slug,font=font_sm,fill=ORANGE,anchor='lm')
        # Footer
        bs_draw.rectangle([0,H-40,W,H],fill=(10,5,0))
        bs_draw.text((W//2,H-20),dealership+' · '+full_address,font=font_sm,fill=(80,60,40),anchor='mm')
        # Google badge
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=bs_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-40-bh-8
            bs_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            bs_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            bs_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=bs_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-bs_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            bs_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO(); bs_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: cleanstudio ───────────────────────────────────────────────
    if template == 'cleanstudio':
        cs_img=Image.new('RGB',(W,H),(248,248,248))
        cs_draw=ImageDraw.Draw(cs_img)
        # Top nav bar
        cs_draw.rectangle([0,0,W,70],fill=NAVY)
        cs_draw.text((40,35),'Cars IN STOCK',font=font_bold_sm,fill=GREEN,anchor='lm')
        cs_draw.text((W-40,35),'cardeals.autos/'+slug,font=font_sm,fill=WHITE,anchor='rm')
        # Car centered on white
        if car_img:
            car_copy=car_img.convert('RGB')
            # Try Cloudinary bg removal URL
            if vehicle_photo and 'cloudinary.com' in vehicle_photo:
                try:
                    parts=vehicle_photo.split('/upload/')
                    bg_url=parts[0]+'/upload/e_background_removal/'+parts[1]
                    r=_req.get(bg_url,timeout=15)
                    if r.status_code==200:
                        car_copy=Image.open(io.BytesIO(r.content)).convert('RGBA')
                        scale=min((W-80)/car_copy.width,460/car_copy.height)
                        nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
                        car_copy=car_copy.resize((nw,nh))
                        cs_img.paste(car_copy,((W-nw)//2,120),car_copy)
                    else:
                        raise Exception('bg removal failed')
                except:
                    scale=min((W-80)/car_copy.width,460/car_copy.height)
                    nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
                    car_copy=car_copy.resize((nw,nh))
                    cs_img.paste(car_copy,((W-nw)//2,120))
            else:
                scale=min((W-80)/car_copy.width,460/car_copy.height)
                nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
                car_copy=car_copy.resize((nw,nh))
                cs_img.paste(car_copy,((W-nw)//2,120))
        # Shadow under car
        cs_draw.ellipse([W//2-200,575,W//2+200,605],fill=(210,210,210))
        # Divider
        cs_draw.line([60,620,W-60,620],fill=(200,200,200),width=1)
        # Vehicle name + price
        cs_draw.text((W//2,660),vehicle_name,font=font_bold_md,fill=NAVY,anchor='mm')
        cs_draw.text((W//2,730),price,font=font_price,fill=GREEN,anchor='mm')
        # Rep pill
        pill_y=800
        cs_draw.rounded_rectangle([W//2-200,pill_y,W//2+200,pill_y+60],radius=30,fill=NAVY)
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((50,50))
            mask=Image.new('L',(50,50),0);ImageDraw.Draw(mask).ellipse([0,0,49,49],fill=255)
            cs_img.paste(pr,(W//2-190,pill_y+5),mask)
        cs_draw.text((W//2+10,pill_y+30),name,font=font_bold_sm,fill=WHITE,anchor='mm')
        # Google badge
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',22)
            except: font_badge=font_sm
            bbox=cs_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=880
            cs_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=12,fill=WHITE,outline=(220,220,220),width=1)
            cs_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            cs_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=cs_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-cs_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            cs_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        # Footer
        cs_draw.rectangle([0,H-70,W,H],fill=NAVY)
        cs_draw.text((W//2,H-44),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        cs_draw.text((W//2,H-18),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        buf=io.BytesIO(); cs_img.save(buf,format='PNG'); buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: certified ─────────────────────────────────────────────────
    if template == 'certified':
        GOLD = (201, 169, 97)
        DARK_NAVY = (15, 23, 42)
        MUTED = (148, 163, 184)

        ct_img = Image.new('RGB', (W, H), NAVY)
        ct_draw = ImageDraw.Draw(ct_img)

        try:
            font_cert_xl = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 56)
        except:
            font_cert_xl = font_bold_lg
        try:
            font_cert_seal = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
        except:
            font_cert_seal = font_bold_sm
        try:
            font_cert_strip = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 22)
        except:
            font_cert_strip = font_bold_sm
        try:
            font_cert_sub = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 18)
        except:
            font_cert_sub = font_bold_sm

        # TOP GOLD BAND
        ct_draw.rectangle([0, 0, W, 140], fill=GOLD)
        ct_draw.text((W//2, 60), 'DEALER CERTIFIED', font=font_cert_xl, fill=NAVY, anchor='mm')
        ct_draw.text((W//2, 110), 'INSPECTED  ·  APPROVED  ·  WARRANTY READY', font=font_cert_sub, fill=NAVY, anchor='mm')

        # HERO VEHICLE AREA
        ct_draw.rounded_rectangle([60, 180, W-60, 680], radius=14, fill=DARK_NAVY)
        ct_draw.rounded_rectangle([76, 196, W-76, 664], radius=8, outline=GOLD, width=1)

        if car_img:
            car_copy = car_img.convert('RGB')
            target_w, target_h = 860, 440
            scale = min(target_w/car_copy.width, target_h/car_copy.height)
            nw, nh = int(car_copy.width*scale), int(car_copy.height*scale)
            car_copy = car_copy.resize((nw, nh))
            cx = (W - nw) // 2
            cy = 210 + (460 - nh) // 2
            ct_img.paste(car_copy, (cx, cy))

        # CERTIFIED SEAL
        seal_cx, seal_cy, seal_r = 900, 295, 90
        ct_draw.ellipse([seal_cx-seal_r, seal_cy-seal_r, seal_cx+seal_r, seal_cy+seal_r], fill=GOLD)
        ct_draw.ellipse([seal_cx-78, seal_cy-78, seal_cx+78, seal_cy+78], outline=NAVY, width=2)
        ct_draw.ellipse([seal_cx-70, seal_cy-70, seal_cx+70, seal_cy+70], outline=NAVY, width=1)
        ct_draw.text((seal_cx, seal_cy-44), 'DEALER', font=font_cert_seal, fill=NAVY, anchor='mm')
        ct_draw.line([(seal_cx-22, seal_cy-2), (seal_cx-6, seal_cy+14)], fill=NAVY, width=6)
        ct_draw.line([(seal_cx-6, seal_cy+14), (seal_cx+22, seal_cy-18)], fill=NAVY, width=6)
        ct_draw.text((seal_cx, seal_cy+38), 'CERTIFIED', font=font_cert_seal, fill=NAVY, anchor='mm')
        ct_draw.text((seal_cx, seal_cy+58), 'INSPECTED', font=font_sm, fill=NAVY, anchor='mm')

        # TRUST STRIP
        ct_draw.rectangle([0, 700, W, 780], fill=DARK_NAVY)
        ct_draw.rectangle([0, 700, W, 702], fill=GOLD)
        ct_draw.rectangle([0, 778, W, 780], fill=GOLD)
        for cx_pos, label_txt in [(215, 'MULTI-POINT INSPECTION'), (W//2, 'WARRANTY ELIGIBLE'), (W-215, 'VERIFIED HISTORY')]:
            full_str = '✓  ' + label_txt
            fbbox = ct_draw.textbbox((0, 0), full_str, font=font_cert_strip)
            full_w = fbbox[2] - fbbox[0]
            sx = cx_pos - full_w // 2
            cbbox = ct_draw.textbbox((0, 0), '✓  ', font=font_cert_strip)
            chk_w = cbbox[2] - cbbox[0]
            ct_draw.text((sx, 740), '✓', font=font_cert_strip, fill=GOLD, anchor='lm')
            ct_draw.text((sx + chk_w, 740), label_txt, font=font_cert_strip, fill=WHITE, anchor='lm')

        # VEHICLE INFO
        ct_draw.text((W//2, 830), vehicle_name.upper(), font=font_bold_lg, fill=WHITE, anchor='mm')
        mileage_str = '{:,}'.format(vehicle['mileage'] or 0)
        ct_draw.text((W//2, 895), '{}  ·  {} MI'.format(price, mileage_str), font=font_bold_lg, fill=GOLD, anchor='mm')

        # FOOTER
        ct_draw.rectangle([0, 940, W, H], fill=DARK_NAVY)
        ct_draw.rectangle([0, 940, W, 942], fill=GOLD)

        ct_draw.text((W//2, 980), dealership.upper(), font=font_bold_md, fill=WHITE, anchor='mm')
        ct_draw.text((W//2, 1010), full_address, font=font_sm, fill=MUTED, anchor='mm')
        ct_draw.text((W//2, 1050), 'cardeals.autos/'+slug, font=font_bold_sm, fill=GREEN, anchor='mm')

        if profile_img:
            pr = profile_img.convert('RGB'); pw, ph = pr.size; side = min(pw, ph)
            pr = pr.crop(((pw-side)//2, 0, (pw-side)//2+side, side)).resize((78, 78))
            mask = Image.new('L', (78, 78), 0); ImageDraw.Draw(mask).ellipse([0, 0, 77, 77], fill=255)
            ct_img.paste(pr, (W-130, 968), mask)
            ct_draw.ellipse([W-133, 965, W-49, 1049], outline=GOLD, width=3)
        ct_draw.text((W-91, 1063), name.upper()[:16], font=font_sm, fill=WHITE, anchor='mm')

        if google_rating and google_review_count:
            try:
                font_badge = ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 18)
            except:
                font_badge = font_sm
            bx, by = 60, 980
            ct_draw.ellipse([bx, by, bx+44, by+44], fill=WHITE)
            ct_draw.text((bx+22, by+22), 'G', font=font_badge, fill=(66,133,244), anchor='mm')
            ct_draw.text((bx+58, by+10), '★ {}'.format(google_rating), font=font_badge, fill=(245,158,11), anchor='lm')
            ct_draw.text((bx+58, by+34), '{} reviews'.format(google_review_count), font=font_badge, fill=MUTED, anchor='lm')

        buf = io.BytesIO(); ct_img.save(buf, format='PNG'); buf.seek(0)
        return Response(buf.read(), content_type='image/png')





    # ── TEMPLATE: certified ─────────────────────────────────────────────────
    if template == 'certified':
        ct_img = Image.new('RGB', (W, H), (15, 25, 50))
        ct_draw = ImageDraw.Draw(ct_img)
        # Gold top bar
        ct_draw.rectangle([0,0,W,8], fill=(212,175,55))
        ct_draw.text((W//2,50),'CERTIFIED PRE-OWNED',font=font_bold_md,fill=(212,175,55),anchor='mm')
        ct_draw.line([80,80,W-80,80],fill=(212,175,55),width=1)
        # Car photo center
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,420/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,420),(15,25,50))
            region.paste(car_copy,((W-nw)//2,(420-nh)//2))
            ct_img.paste(region,(0,100))
        # Gradient
        grad=Image.new('RGBA',(W,420),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(420):
            a=int(200*(i/420)**1.5)
            gd.line([0,i,W,i],fill=(15,25,50,min(a,255)))
        ct_rgba=ct_img.convert('RGBA')
        ct_rgba.paste(grad,(0,100),grad)
        ct_img=ct_rgba.convert('RGB')
        ct_draw=ImageDraw.Draw(ct_img)
        # Gold badge
        ct_draw.ellipse([W//2-60,480,W//2+60,600],fill=(212,175,55))
        ct_draw.text((W//2,540),'✓',font=font_bold_lg,fill=(15,25,50),anchor='mm')
        # Vehicle info
        ct_draw.text((W//2,650),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ct_draw.text((W//2,720),price,font=font_price,fill=(212,175,55),anchor='mm')
        ct_draw.text((W//2,790),'Inspected · Verified · Ready to Drive',font=font_sm,fill=(148,163,184),anchor='mm')
        # Rep row
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            ct_img.paste(pr,(40,860),mask)
            ct_draw.ellipse([34,854,126,946],outline=(212,175,55),width=3)
        ct_draw.text((140,890),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ct_draw.text((140,926),'cardeals.autos/'+slug,font=font_sm,fill=(212,175,55),anchor='lm')
        ct_draw.rectangle([0,H-60,W,H],fill=(10,18,35))
        ct_draw.text((W//2,H-30),dealership+' · '+full_address,font=font_sm,fill=(80,90,110),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ct_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-60-bh-8
            ct_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ct_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ct_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ct_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ct_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ct_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ct_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: familyready ───────────────────────────────────────────────
    if template == 'familyready':
        fr_img = Image.new('RGB', (W, H), (20, 40, 80))
        fr_draw = ImageDraw.Draw(fr_img)
        fr_draw.rectangle([0,0,W,8],fill=GREEN)
        fr_draw.text((W//2,50),'👨‍👩‍👧 PERFECT FOR YOUR FAMILY',font=font_bold_sm,fill=GREEN,anchor='mm')
        fr_draw.line([80,80,W-80,80],fill=(40,80,140),width=1)
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,440/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,440),(20,40,80))
            region.paste(car_copy,((W-nw)//2,(440-nh)//2))
            fr_img.paste(region,(0,100))
        grad=Image.new('RGBA',(W,440),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(440):
            a=int(220*(i/440)**1.6)
            gd.line([0,i,W,i],fill=(20,40,80,min(a,255)))
        fr_rgba=fr_img.convert('RGBA')
        fr_rgba.paste(grad,(0,100),grad)
        fr_img=fr_rgba.convert('RGB')
        fr_draw=ImageDraw.Draw(fr_img)
        fr_draw.text((W//2,580),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        fr_draw.text((W//2,650),price,font=font_price,fill=GREEN,anchor='mm')
        fr_draw.text((W//2,720),'Safe · Spacious · Ready for the Road',font=font_sm,fill=(148,163,184),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            fr_img.paste(pr,(40,790),mask)
            fr_draw.ellipse([34,784,126,876],outline=GREEN,width=3)
        fr_draw.text((140,820),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        fr_draw.text((140,856),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        fr_draw.rectangle([0,920,W,1010],fill=(12,25,50))
        fr_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        fr_draw.text((W//2,976),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=fr_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=992
            fr_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            fr_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            fr_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=fr_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-fr_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            fr_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();fr_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: getapproved ───────────────────────────────────────────────
    if template == 'getapproved':
        ga_img = Image.new('RGB', (W, H), NAVY)
        ga_draw = ImageDraw.Draw(ga_img)
        ga_draw.rectangle([0,0,W,90],fill=GREEN)
        ga_draw.text((W//2,45),'✅ GET APPROVED TODAY',font=font_bold_lg,fill=NAVY,anchor='mm')
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,400/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,400),NAVY)
            region.paste(car_copy,((W-nw)//2,(400-nh)//2))
            ga_img.paste(region,(0,100))
        grad=Image.new('RGBA',(W,400),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(400):
            a=int(220*(i/400)**1.5)
            gd.line([0,i,W,i],fill=(30,41,59,min(a,255)))
        ga_rgba=ga_img.convert('RGBA')
        ga_rgba.paste(grad,(0,100),grad)
        ga_img=ga_rgba.convert('RGB')
        ga_draw=ImageDraw.Draw(ga_img)
        ga_draw.text((W//2,540),'All Credit Situations Welcome',font=font_bold_sm,fill=GREEN,anchor='mm')
        ga_draw.text((W//2,600),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ga_draw.text((W//2,670),price,font=font_price,fill=GREEN,anchor='mm')
        ga_draw.rounded_rectangle([60,720,W-60,790],radius=35,fill=GREEN)
        ga_draw.text((W//2,755),'Let\'s Get You On The Road Today',font=font_bold_sm,fill=NAVY,anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            ga_img.paste(pr,(40,820),mask)
            ga_draw.ellipse([34,814,126,906],outline=GREEN,width=3)
        ga_draw.text((140,850),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ga_draw.text((140,886),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        ga_draw.rectangle([0,940,W,1010],fill=(20,30,48))
        ga_draw.text((W//2,963),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        ga_draw.text((W//2,990),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ga_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-48-bh
            ga_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ga_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ga_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ga_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ga_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ga_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ga_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: allcredit ─────────────────────────────────────────────────
    if template == 'allcredit':
        ac_img = Image.new('RGB', (W, H), (10, 20, 40))
        ac_draw = ImageDraw.Draw(ac_img)
        ac_draw.rectangle([0,0,W,8],fill=GREEN)
        ac_draw.text((W//2,50),'ALL CREDIT WELCOME',font=font_bold_lg,fill=WHITE,anchor='mm')
        ac_draw.text((W//2,100),'Good · Fair · Bad · No Credit — We Work With Everyone',font=font_sm,fill=GREEN,anchor='mm')
        ac_draw.line([60,125,W-60,125],fill=(30,60,100),width=1)
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,380/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,380),(10,20,40))
            region.paste(car_copy,((W-nw)//2,(380-nh)//2))
            ac_img.paste(region,(0,140))
        grad=Image.new('RGBA',(W,380),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(380):
            a=int(210*(i/380)**1.5)
            gd.line([0,i,W,i],fill=(10,20,40,min(a,255)))
        ac_rgba=ac_img.convert('RGBA')
        ac_rgba.paste(grad,(0,140),grad)
        ac_img=ac_rgba.convert('RGB')
        ac_draw=ImageDraw.Draw(ac_img)
        ac_draw.text((W//2,565),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ac_draw.text((W//2,635),price,font=font_price,fill=GREEN,anchor='mm')
        ac_draw.text((W//2,705),'Don\'t let credit stop you. Let\'s talk.',font=font_sm,fill=(148,163,184),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            ac_img.paste(pr,(40,770),mask)
            ac_draw.ellipse([34,764,126,856],outline=GREEN,width=3)
        ac_draw.text((140,800),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ac_draw.text((140,836),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        ac_draw.rectangle([0,900,W,1010],fill=(6,12,25))
        ac_draw.text((W//2,928),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        ac_draw.text((W//2,956),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ac_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=972
            ac_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ac_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ac_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ac_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ac_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ac_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ac_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: firsttime ─────────────────────────────────────────────────
    if template == 'firsttime':
        ft2_img = Image.new('RGB', (W, H), (5, 30, 60))
        ft2_draw = ImageDraw.Draw(ft2_img)
        ft2_draw.rectangle([0,0,W,8],fill=GREEN)
        ft2_draw.text((W//2,50),'🌱 FIRST TIME BUYER?',font=font_bold_lg,fill=WHITE,anchor='mm')
        ft2_draw.text((W//2,100),'We\'ll walk you through every step.',font=font_sm,fill=GREEN,anchor='mm')
        ft2_draw.line([60,125,W-60,125],fill=(20,60,100),width=1)
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,400/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,400),(5,30,60))
            region.paste(car_copy,((W-nw)//2,(400-nh)//2))
            ft2_img.paste(region,(0,140))
        grad=Image.new('RGBA',(W,400),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(400):
            a=int(210*(i/400)**1.5)
            gd.line([0,i,W,i],fill=(5,30,60,min(a,255)))
        ft2_rgba=ft2_img.convert('RGBA')
        ft2_rgba.paste(grad,(0,140),grad)
        ft2_img=ft2_rgba.convert('RGB')
        ft2_draw=ImageDraw.Draw(ft2_img)
        ft2_draw.text((W//2,580),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ft2_draw.text((W//2,650),price,font=font_price,fill=GREEN,anchor='mm')
        ft2_draw.text((W//2,720),'No experience needed. Just reach out.',font=font_sm,fill=(148,163,184),anchor='mm')
        ft2_draw.rounded_rectangle([60,760,W-60,820],radius=30,fill=GREEN)
        ft2_draw.text((W//2,790),'I\'ll make it easy. I promise.',font=font_bold_sm,fill=NAVY,anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            ft2_img.paste(pr,(40,850),mask)
            ft2_draw.ellipse([34,844,126,936],outline=GREEN,width=3)
        ft2_draw.text((140,880),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ft2_draw.text((140,916),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        ft2_draw.rectangle([0,960,W,1010],fill=(3,18,38))
        ft2_draw.text((W//2,978),dealership+' · '+full_address,font=font_sm,fill=(80,100,130),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',18)
            except: font_badge=font_sm
            bbox=ft2_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+24;bh=bbox[3]-bbox[1]+10;bx=W-bw-20;by=H-50-bh
            ft2_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=8,fill=WHITE)
            ft2_draw.text((bx+8,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ft2_draw.text((bx+22,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ft2_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ft2_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ft2_draw.text((bx+26+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ft2_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: under20k ──────────────────────────────────────────────────
    if template == 'under20k':
        u20_img = Image.new('RGB', (W, H), NAVY)
        u20_draw = ImageDraw.Draw(u20_img)
        u20_draw.rectangle([0,0,W,8],fill=GREEN)
        u20_draw.text((W//2-20,-30),'UNDER',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',180) if True else font_bold_lg,fill=(0,200,81,30),anchor='mm')
        try:
            font_hero=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',130)
        except:
            font_hero=font_bold_lg
        u20_draw.text((W//2,80),'UNDER $20K',font=font_bold_lg,fill=GREEN,anchor='mm')
        u20_draw.text((W//2,130),'Quality cars that fit your budget',font=font_sm,fill=(148,163,184),anchor='mm')
        u20_draw.line([60,155,W-60,155],fill=(40,60,90),width=1)
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,420/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,420),NAVY)
            region.paste(car_copy,((W-nw)//2,(420-nh)//2))
            u20_img.paste(region,(0,165))
        grad=Image.new('RGBA',(W,420),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(420):
            a=int(220*(i/420)**1.5)
            gd.line([0,i,W,i],fill=(30,41,59,min(a,255)))
        u20_rgba=u20_img.convert('RGBA')
        u20_rgba.paste(grad,(0,165),grad)
        u20_img=u20_rgba.convert('RGB')
        u20_draw=ImageDraw.Draw(u20_img)
        u20_draw.text((W//2,630),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        u20_draw.text((W//2,700),price,font=font_price,fill=GREEN,anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((75,75))
            mask=Image.new('L',(75,75),0);ImageDraw.Draw(mask).ellipse([0,0,74,74],fill=255)
            u20_img.paste(pr,(40,790),mask)
            u20_draw.ellipse([34,784,121,871],outline=GREEN,width=3)
        u20_draw.text((130,815),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        u20_draw.text((130,850),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        u20_draw.rectangle([0,920,W,1010],fill=(20,30,48))
        u20_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        u20_draw.text((W//2,976),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=u20_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=992
            u20_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            u20_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            u20_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=u20_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-u20_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            u20_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();u20_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: lotclearance ──────────────────────────────────────────────
    if template == 'lotclearance':
        lc_img = Image.new('RGB', (W, H), (180,20,20))
        lc_draw = ImageDraw.Draw(lc_img)
        lc_draw.rectangle([0,0,W,8],fill=WHITE)
        lc_draw.text((W//2,60),'🏷️ LOT CLEARANCE',font=font_bold_lg,fill=WHITE,anchor='mm')
        lc_draw.text((W//2,110),'BEST DEALS ON THE LOT — TODAY ONLY',font=font_bold_sm,fill=(255,200,200),anchor='mm')
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,400/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,400),(180,20,20))
            region.paste(car_copy,((W-nw)//2,(400-nh)//2))
            lc_img.paste(region,(0,140))
        grad=Image.new('RGBA',(W,400),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(400):
            a=int(220*(i/400)**1.5)
            gd.line([0,i,W,i],fill=(180,20,20,min(a,255)))
        lc_rgba=lc_img.convert('RGBA')
        lc_rgba.paste(grad,(0,140),grad)
        lc_img=lc_rgba.convert('RGB')
        lc_draw=ImageDraw.Draw(lc_img)
        lc_draw.text((W//2,585),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        lc_draw.text((W//2,655),price,font=font_price,fill=WHITE,anchor='mm')
        lc_draw.text((W//2,725),'Move fast — this won\'t last',font=font_sm,fill=(255,200,200),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((75,75))
            mask=Image.new('L',(75,75),0);ImageDraw.Draw(mask).ellipse([0,0,74,74],fill=255)
            lc_img.paste(pr,(40,800),mask)
            lc_draw.ellipse([34,794,121,871],outline=WHITE,width=3)
        lc_draw.text((130,820),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        lc_draw.text((130,856),'cardeals.autos/'+slug,font=font_sm,fill=(255,220,220),anchor='lm')
        lc_draw.rectangle([0,920,W,1010],fill=(120,10,10))
        lc_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        lc_draw.text((W//2,976),full_address,font=font_sm,fill=(255,180,180),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=lc_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=992
            lc_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            lc_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            lc_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=lc_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-lc_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            lc_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();lc_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: truckready ────────────────────────────────────────────────
    if template == 'truckready':
        tr_img = Image.new('RGB', (W, H), (20,15,10))
        tr_draw = ImageDraw.Draw(tr_img)
        tr_draw.rectangle([0,0,W,8],fill=(180,100,20))
        tr_draw.text((W//2,50),'🛻 TRUCK READY',font=font_bold_lg,fill=(180,100,20),anchor='mm')
        tr_draw.text((W//2,100),'Built for work. Priced to move.',font=font_sm,fill=(148,130,110),anchor='mm')
        tr_draw.line([60,125,W-60,125],fill=(50,40,30),width=1)
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,420/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,420),(20,15,10))
            region.paste(car_copy,((W-nw)//2,(420-nh)//2))
            tr_img.paste(region,(0,140))
        grad=Image.new('RGBA',(W,420),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(420):
            a=int(220*(i/420)**1.5)
            gd.line([0,i,W,i],fill=(20,15,10,min(a,255)))
        tr_rgba=tr_img.convert('RGBA')
        tr_rgba.paste(grad,(0,140),grad)
        tr_img=tr_rgba.convert('RGB')
        tr_draw=ImageDraw.Draw(tr_img)
        tr_draw.text((W//2,600),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        tr_draw.text((W//2,670),price,font=font_price,fill=(180,100,20),anchor='mm')
        tr_draw.text((W//2,740),'Ready to haul. Ready to work.',font=font_sm,fill=(148,130,110),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((75,75))
            mask=Image.new('L',(75,75),0);ImageDraw.Draw(mask).ellipse([0,0,74,74],fill=255)
            tr_img.paste(pr,(40,800),mask)
            tr_draw.ellipse([34,794,121,871],outline=(180,100,20),width=3)
        tr_draw.text((130,820),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        tr_draw.text((130,856),'cardeals.autos/'+slug,font=font_sm,fill=(180,100,20),anchor='lm')
        tr_draw.rectangle([0,920,W,1010],fill=(10,8,5))
        tr_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        tr_draw.text((W//2,976),full_address,font=font_sm,fill=(100,90,80),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=tr_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=992
            tr_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            tr_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            tr_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=tr_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-tr_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            tr_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();tr_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: sporty ────────────────────────────────────────────────────
    if template == 'sporty':
        sp2_img = Image.new('RGB', (W, H), (5,5,15))
        sp2_draw = ImageDraw.Draw(sp2_img)
        sp2_draw.rectangle([0,0,W,8],fill=(150,0,255))
        sp2_draw.text((W//2,50),'🏎️ SPORTY & AFFORDABLE',font=font_bold_lg,fill=(150,0,255),anchor='mm')
        sp2_draw.text((W//2,100),'Drive something you\'re proud of.',font=font_sm,fill=(100,80,130),anchor='mm')
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,460/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,460),(5,5,15))
            region.paste(car_copy,((W-nw)//2,(460-nh)//2))
            sp2_img.paste(region,(0,130))
        grad=Image.new('RGBA',(W,460),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(460):
            a=int(230*(i/460)**1.4)
            gd.line([0,i,W,i],fill=(5,5,15,min(a,255)))
        sp2_rgba=sp2_img.convert('RGBA')
        sp2_rgba.paste(grad,(0,130),grad)
        sp2_img=sp2_rgba.convert('RGB')
        sp2_draw=ImageDraw.Draw(sp2_img)
        sp2_draw.text((W//2,635),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        sp2_draw.text((W//2,705),price,font=font_price,fill=(150,0,255),anchor='mm')
        sp2_draw.text((W//2,770),'Fun to drive. Easy to own.',font=font_sm,fill=(100,80,130),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((75,75))
            mask=Image.new('L',(75,75),0);ImageDraw.Draw(mask).ellipse([0,0,74,74],fill=255)
            sp2_img.paste(pr,(40,820),mask)
            sp2_draw.ellipse([34,814,121,891],outline=(150,0,255),width=3)
        sp2_draw.text((130,840),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        sp2_draw.text((130,876),'cardeals.autos/'+slug,font=font_sm,fill=(150,0,255),anchor='lm')
        sp2_draw.rectangle([0,930,W,1010],fill=(3,3,10))
        sp2_draw.text((W//2,955),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        sp2_draw.text((W//2,982),full_address,font=font_sm,fill=(80,70,100),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=sp2_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-42-bh
            sp2_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            sp2_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            sp2_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=sp2_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-sp2_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            sp2_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();sp2_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: weekendwarrior ────────────────────────────────────────────
    if template == 'weekendwarrior':
        ww_img = Image.new('RGB', (W, H), (8,25,15))
        ww_draw = ImageDraw.Draw(ww_img)
        ww_draw.rectangle([0,0,W,8],fill=GREEN)
        ww_draw.text((W//2,50),'🌄 WEEKEND WARRIOR',font=font_bold_lg,fill=GREEN,anchor='mm')
        ww_draw.text((W//2,100),'Adventure starts in the driveway.',font=font_sm,fill=(80,120,90),anchor='mm')
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,460/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,460),(8,25,15))
            region.paste(car_copy,((W-nw)//2,(460-nh)//2))
            ww_img.paste(region,(0,130))
        grad=Image.new('RGBA',(W,460),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(460):
            a=int(230*(i/460)**1.4)
            gd.line([0,i,W,i],fill=(8,25,15,min(a,255)))
        ww_rgba=ww_img.convert('RGBA')
        ww_rgba.paste(grad,(0,130),grad)
        ww_img=ww_rgba.convert('RGB')
        ww_draw=ImageDraw.Draw(ww_img)
        ww_draw.text((W//2,635),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ww_draw.text((W//2,705),price,font=font_price,fill=GREEN,anchor='mm')
        ww_draw.text((W//2,770),'Ready for wherever the road takes you.',font=font_sm,fill=(80,120,90),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((75,75))
            mask=Image.new('L',(75,75),0);ImageDraw.Draw(mask).ellipse([0,0,74,74],fill=255)
            ww_img.paste(pr,(40,820),mask)
            ww_draw.ellipse([34,814,121,891],outline=GREEN,width=3)
        ww_draw.text((130,840),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ww_draw.text((130,876),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        ww_draw.rectangle([0,930,W,1010],fill=(5,15,8))
        ww_draw.text((W//2,955),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        ww_draw.text((W//2,982),full_address,font=font_sm,fill=(60,100,70),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ww_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-42-bh
            ww_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ww_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ww_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ww_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ww_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ww_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ww_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: suvseason ─────────────────────────────────────────────────
    if template == 'suvseason':
        ss_img = Image.new('RGB', (W, H), (10,20,35))
        ss_draw = ImageDraw.Draw(ss_img)
        ss_draw.rectangle([0,0,W,8],fill=GREEN)
        ss_draw.text((W//2,50),'🚙 SUV SEASON',font=font_bold_lg,fill=GREEN,anchor='mm')
        ss_draw.text((W//2,100),'Room for everyone. Ready for anything.',font=font_sm,fill=(80,110,140),anchor='mm')
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,460/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,460),(10,20,35))
            region.paste(car_copy,((W-nw)//2,(460-nh)//2))
            ss_img.paste(region,(0,130))
        grad=Image.new('RGBA',(W,460),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(460):
            a=int(230*(i/460)**1.4)
            gd.line([0,i,W,i],fill=(10,20,35,min(a,255)))
        ss_rgba=ss_img.convert('RGBA')
        ss_rgba.paste(grad,(0,130),grad)
        ss_img=ss_rgba.convert('RGB')
        ss_draw=ImageDraw.Draw(ss_img)
        ss_draw.text((W//2,635),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ss_draw.text((W//2,705),price,font=font_price,fill=GREEN,anchor='mm')
        ss_draw.text((W//2,770),'Space · Safety · Style',font=font_sm,fill=(80,110,140),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((75,75))
            mask=Image.new('L',(75,75),0);ImageDraw.Draw(mask).ellipse([0,0,74,74],fill=255)
            ss_img.paste(pr,(40,820),mask)
            ss_draw.ellipse([34,814,121,891],outline=GREEN,width=3)
        ss_draw.text((130,840),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        ss_draw.text((130,876),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        ss_draw.rectangle([0,930,W,1010],fill=(6,12,22))
        ss_draw.text((W//2,955),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        ss_draw.text((W//2,982),full_address,font=font_sm,fill=(60,90,120),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ss_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=H-42-bh
            ss_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ss_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ss_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ss_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ss_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ss_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ss_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: freshstart ────────────────────────────────────────────────
    if template == 'freshstart':
        fs2_img = Image.new('RGB', (W, H), (5,20,10))
        fs2_draw = ImageDraw.Draw(fs2_img)
        fs2_draw.rectangle([0,0,W,8],fill=GREEN)
        fs2_draw.text((W//2,50),'🔄 FRESH START',font=font_bold_lg,fill=GREEN,anchor='mm')
        fs2_draw.text((W//2,100),'Everyone deserves a second chance.',font=font_sm,fill=(60,120,70),anchor='mm')
        fs2_draw.line([60,125,W-60,125],fill=(20,60,30),width=1)
        if car_img:
            car_copy=car_img.convert('RGB')
            scale=max(W/car_copy.width,400/car_copy.height)
            nw,nh=int(car_copy.width*scale),int(car_copy.height*scale)
            car_copy=car_copy.resize((nw,nh))
            region=Image.new('RGB',(W,400),(5,20,10))
            region.paste(car_copy,((W-nw)//2,(400-nh)//2))
            fs2_img.paste(region,(0,140))
        grad=Image.new('RGBA',(W,400),(0,0,0,0))
        gd=ImageDraw.Draw(grad)
        for i in range(400):
            a=int(210*(i/400)**1.5)
            gd.line([0,i,W,i],fill=(5,20,10,min(a,255)))
        fs2_rgba=fs2_img.convert('RGBA')
        fs2_rgba.paste(grad,(0,140),grad)
        fs2_img=fs2_rgba.convert('RGB')
        fs2_draw=ImageDraw.Draw(fs2_img)
        fs2_draw.text((W//2,580),vehicle_name,font=font_bold_lg,fill=WHITE,anchor='mm')
        fs2_draw.text((W//2,650),price,font=font_price,fill=GREEN,anchor='mm')
        fs2_draw.text((W//2,720),'Rebuilding credit? I work with lenders who can help.',font=font_sm,fill=(100,150,110),anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((80,80))
            mask=Image.new('L',(80,80),0);ImageDraw.Draw(mask).ellipse([0,0,79,79],fill=255)
            fs2_img.paste(pr,(40,790),mask)
            fs2_draw.ellipse([34,784,126,876],outline=GREEN,width=3)
        fs2_draw.text((140,820),name,font=font_bold_sm,fill=WHITE,anchor='lm')
        fs2_draw.text((140,856),'cardeals.autos/'+slug,font=font_sm,fill=GREEN,anchor='lm')
        fs2_draw.rectangle([0,920,W,1010],fill=(3,12,6))
        fs2_draw.text((W//2,948),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        fs2_draw.text((W//2,976),full_address,font=font_sm,fill=(60,100,70),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=fs2_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=992
            fs2_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            fs2_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            fs2_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=fs2_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-fs2_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            fs2_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();fs2_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: earngifts ─────────────────────────────────────────────────
    if template == 'earngifts':
        eg_img = Image.new('RGB', (W, H), NAVY)
        eg_draw = ImageDraw.Draw(eg_img)
        eg_draw.rectangle([0,0,W,8],fill=GREEN)
        eg_draw.text((W//2,60),'🎀 EARN GIFTS WITH ME',font=font_bold_lg,fill=GREEN,anchor='mm')
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((200,200))
            mask=Image.new('L',(200,200),0);ImageDraw.Draw(mask).ellipse([0,0,199,199],fill=255)
            eg_img.paste(pr,(W//2-100,100),mask)
            eg_draw.ellipse([W//2-106,94,W//2+106,306],outline=GREEN,width=5)
        eg_draw.text((W//2,360),name,font=font_bold_lg,fill=WHITE,anchor='mm')
        eg_draw.text((W//2,410),'Sales Professional · '+dealership,font=font_sm,fill=(148,163,184),anchor='mm')
        eg_draw.line([80,445,W-80,445],fill=(51,65,85),width=1)
        eg_draw.text((W//2,510),'Send me a buyer.',font=font_bold_md,fill=WHITE,anchor='mm')
        eg_draw.text((W//2,570),'They buy — I send you a Thank You gift.',font=font_sm,fill=(148,163,184),anchor='mm')
        eg_draw.rounded_rectangle([60,620,W-60,690],radius=35,fill=GREEN)
        eg_draw.text((W//2,655),'🎁 Refer · Buy · Receive',font=font_bold_md,fill=NAVY,anchor='mm')
        eg_draw.text((W//2,760),'cardeals.autos/'+slug,font=font_bold_md,fill=GREEN,anchor='mm')
        eg_draw.rectangle([0,830,W,1010],fill=(20,30,48))
        eg_draw.text((W//2,863),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        eg_draw.text((W//2,895),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=eg_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=912
            eg_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            eg_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            eg_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=eg_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-eg_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            eg_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();eg_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: helpme ────────────────────────────────────────────────────
    if template == 'helpme':
        hm_img = Image.new('RGB', (W, H), NAVY)
        hm_draw = ImageDraw.Draw(hm_img)
        hm_draw.rectangle([0,0,W,8],fill=GREEN)
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((220,220))
            mask=Image.new('L',(220,220),0);ImageDraw.Draw(mask).ellipse([0,0,219,219],fill=255)
            hm_img.paste(pr,(W//2-110,60),mask)
            hm_draw.ellipse([W//2-116,54,W//2+116,286],outline=GREEN,width=5)
        hm_draw.text((W//2,350),name,font=font_bold_lg,fill=WHITE,anchor='mm')
        hm_draw.text((W//2,400),'Sales Professional · '+dealership,font=font_sm,fill=(148,163,184),anchor='mm')
        hm_draw.line([80,435,W-80,435],fill=(51,65,85),width=1)
        try:
            font_ask=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf',52)
        except:
            font_ask=font_bold_md
        hm_draw.text((W//2,510),'Help me sell.',font=font_ask,fill=GREEN,anchor='mm')
        hm_draw.text((W//2,580),'Know someone shopping for a car?',font=font_bold_sm,fill=WHITE,anchor='mm')
        hm_draw.text((W//2,630),'Send them my way — I\'ll take care of the rest.',font=font_sm,fill=(148,163,184),anchor='mm')
        hm_draw.rounded_rectangle([60,680,W-60,750],radius=35,fill=GREEN)
        hm_draw.text((W//2,715),'🤝 They buy — You receive a Thank You gift',font=font_bold_sm,fill=NAVY,anchor='mm')
        hm_draw.text((W//2,810),'cardeals.autos/'+slug,font=font_bold_md,fill=GREEN,anchor='mm')
        hm_draw.rectangle([0,870,W,1010],fill=(20,30,48))
        hm_draw.text((W//2,903),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        hm_draw.text((W//2,935),full_address,font=font_sm,fill=(180,190,200),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=hm_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=952
            hm_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            hm_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            hm_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=hm_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-hm_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            hm_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();hm_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: knowsomeone ───────────────────────────────────────────────
    if template == 'knowsomeone':
        ks_img = Image.new('RGB', (W, H), (15,25,45))
        ks_draw = ImageDraw.Draw(ks_img)
        ks_draw.rectangle([0,0,W,8],fill=GREEN)
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((200,200))
            mask=Image.new('L',(200,200),0);ImageDraw.Draw(mask).ellipse([0,0,199,199],fill=255)
            ks_img.paste(pr,(W//2-100,80),mask)
            ks_draw.ellipse([W//2-106,74,W//2+106,286],outline=GREEN,width=5)
        ks_draw.text((W//2,340),name,font=font_bold_lg,fill=WHITE,anchor='mm')
        ks_draw.text((W//2,390),dealership,font=font_sm,fill=(148,163,184),anchor='mm')
        ks_draw.line([80,425,W-80,425],fill=(40,60,90),width=1)
        ks_draw.text((W//2,490),'Know someone buying a car?',font=font_bold_md,fill=WHITE,anchor='mm')
        ks_draw.text((W//2,550),'Tag them below 👇',font=font_bold_sm,fill=GREEN,anchor='mm')
        ks_draw.text((W//2,620),'I\'ll get them taken care of —',font=font_sm,fill=(148,163,184),anchor='mm')
        ks_draw.text((W//2,660),'no pressure, no runaround.',font=font_sm,fill=(148,163,184),anchor='mm')
        ks_draw.rounded_rectangle([60,710,W-60,780],radius=35,fill=GREEN)
        ks_draw.text((W//2,745),'👥 Refer · Relax · They\'ll Thank You',font=font_bold_sm,fill=NAVY,anchor='mm')
        ks_draw.text((W//2,840),'cardeals.autos/'+slug,font=font_bold_md,fill=GREEN,anchor='mm')
        ks_draw.rectangle([0,890,W,1010],fill=(10,18,32))
        ks_draw.text((W//2,918),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        ks_draw.text((W//2,946),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=ks_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=962
            ks_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            ks_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            ks_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=ks_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-ks_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            ks_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();ks_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')

    # ── TEMPLATE: tagafriend ────────────────────────────────────────────────
    if template == 'tagafriend':
        taf_img = Image.new('RGB', (W, H), (5,10,25))
        taf_draw = ImageDraw.Draw(taf_img)
        taf_draw.rectangle([0,0,W,8],fill=GREEN)
        if profile_img:
            pr=profile_img.convert('RGB');pw,ph=pr.size;side=min(pw,ph)
            pr=pr.crop(((pw-side)//2,0,(pw-side)//2+side,side)).resize((200,200))
            mask=Image.new('L',(200,200),0);ImageDraw.Draw(mask).ellipse([0,0,199,199],fill=255)
            taf_img.paste(pr,(W//2-100,80),mask)
            taf_draw.ellipse([W//2-106,74,W//2+106,286],outline=GREEN,width=5)
        taf_draw.text((W//2,340),name,font=font_bold_lg,fill=WHITE,anchor='mm')
        taf_draw.text((W//2,390),dealership,font=font_sm,fill=(148,163,184),anchor='mm')
        taf_draw.line([80,425,W-80,425],fill=(30,50,80),width=1)
        try:
            font_tag=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf',60)
        except:
            font_tag=font_bold_lg
        taf_draw.text((W//2,500),'Tag a friend.',font=font_tag,fill=GREEN,anchor='mm')
        taf_draw.text((W//2,570),'⬇️ Someone you know needs a car.',font=font_bold_sm,fill=WHITE,anchor='mm')
        taf_draw.text((W//2,630),'Tag them in the comments.',font=font_sm,fill=(148,163,184),anchor='mm')
        taf_draw.text((W//2,680),'I\'ll take it from there.',font=font_sm,fill=(148,163,184),anchor='mm')
        taf_draw.rounded_rectangle([60,730,W-60,800],radius=35,fill=GREEN)
        taf_draw.text((W//2,765),'📲 Tag · Connect · Drive Home Happy',font=font_bold_sm,fill=NAVY,anchor='mm')
        taf_draw.text((W//2,855),'cardeals.autos/'+slug,font=font_bold_md,fill=GREEN,anchor='mm')
        taf_draw.rectangle([0,900,W,1010],fill=(3,6,18))
        taf_draw.text((W//2,928),dealership,font=font_bold_sm,fill=WHITE,anchor='mm')
        taf_draw.text((W//2,956),full_address,font=font_sm,fill=(148,163,184),anchor='mm')
        if google_rating and google_review_count:
            try: font_badge=ImageFont.truetype('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',20)
            except: font_badge=font_sm
            bbox=taf_draw.textbbox((0,0),f'G * {google_rating} · {google_review_count} Google reviews',font=font_badge)
            bw=bbox[2]-bbox[0]+28;bh=bbox[3]-bbox[1]+12;bx=W//2-bw//2;by=972
            taf_draw.rounded_rectangle([bx,by,bx+bw,by+bh],radius=10,fill=WHITE)
            taf_draw.text((bx+10,by+bh//2),'G',font=font_badge,fill=(66,133,244),anchor='lm')
            taf_draw.text((bx+26,by+bh//2),f'* {google_rating}',font=font_badge,fill=(245,158,11),anchor='lm')
            sw=taf_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[2]-taf_draw.textbbox((0,0),f'* {google_rating}',font=font_badge)[0]
            taf_draw.text((bx+30+sw,by+bh//2),f' · {google_review_count} Google reviews',font=font_badge,fill=(100,116,139),anchor='lm')
        buf=io.BytesIO();taf_img.save(buf,format='PNG');buf.seek(0)
        return Response(buf.read(),content_type='image/png')


    # Return PNG (classic template)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.read(), content_type='image/png')