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

    # SECTION 1: Profile (0-220px)
    draw.rectangle([0, 0, W, 220], fill=WHITE)

    # Profile circle
    cx, cy, cr = 110, 110, 70
    profile_img = fetch_img(profile_photo)
    if profile_img:
        profile_img = profile_img.resize((cr*2, cr*2))
        mask = Image.new('L', (cr*2, cr*2), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, cr*2-1, cr*2-1], fill=255)
        profile_img = profile_img.convert('RGB')
        img.paste(profile_img, (cx-cr, cy-cr), mask)
    # Green ring
    draw.ellipse([cx-cr-6, cy-cr-6, cx+cr+6, cy+cr+6], outline=GREEN, width=5)

    # Name and dealership
    tx = cx + cr + 30
    draw.text((tx, 65), name, font=font_bold_lg, fill=NAVY)
    draw.text((tx, 125), dealership + ' - ' + city + ', NJ', font=font_reg, fill=GRAY)

    # Fresh Inventory badge
    draw.rounded_rectangle([W-260, 25, W-25, 80], radius=25, fill=GREEN)
    draw.text((W-145, 52), 'Fresh Inventory', font=font_bold_sm, fill=WHITE, anchor='mm')

    # Divider
    draw.line([40, 205, W-40, 205], fill=(226, 232, 240), width=2)

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
    draw.text((tx, 125), dealership + ' - ' + city + ', NJ', font=font_reg, fill=GRAY)
    draw.rounded_rectangle([W-260, 25, W-25, 80], radius=25, fill=GREEN)
    draw.text((W-145, 52), 'Fresh Inventory', font=font_bold_sm, fill=WHITE, anchor='mm')
    draw.line([40, 205, W-40, 205], fill=(226, 232, 240), width=2)

    # Days left badge
    if days_left > 0:
        badge_color = (220, 38, 38) if days_left <= 2 else (249, 115, 22) if days_left <= 4 else GREEN
        draw.rounded_rectangle([24, car_y+20, 250, car_y+76], radius=28, fill=badge_color)
        draw.text((137, car_y+48), str(days_left) + ' Days Left', font=font_bold_sm, fill=WHITE, anchor='mm')

    # Car name and price overlay
    draw.text((30, car_y+car_h-70), vehicle_name, font=font_car, fill=WHITE)
    bbox = draw.textbbox((0,0), price, font=font_price)
    draw.text((W-30-(bbox[2]-bbox[0]), car_y+car_h-15), price, font=font_price, fill=GREEN, anchor='lb')

    # SECTION 3: Stats bar (660-760px)
    draw.rectangle([0, 660, W, 760], fill=NAVY)
    stats = [(cars_live, 'Cars Live'), (starting_at, 'Starting At'), (city+', NJ', 'Location')]
    for i, (val, label) in enumerate(stats):
        sx = int((W/3)*i + (W/3)/2)
        draw.text((sx, 700), val, font=font_bold_md, fill=GREEN, anchor='mm')
        draw.text((sx, 738), label, font=font_sm, fill=(200, 210, 220), anchor='mm')
        if i < 2:
            draw.line([(W//3)*(i+1), 678, (W//3)*(i+1), 748], fill=(60, 80, 100), width=1)

    # SECTION 4: Referral (760-840px, conditional)
    next_y = 760
    if include_referral:
        draw.rectangle([0, next_y, W, next_y+80], fill=(240, 253, 244))
        draw.rectangle([0, next_y, W, next_y+80], outline=(187, 247, 208), width=2)
        draw.text((W//2, next_y+40), 'Know someone? Refer them -- they buy -- you get $100', font=font_bold_sm, fill=(6, 95, 70), anchor='mm')
        next_y += 80

    # SECTION 5: URL pill
    url_y = next_y + 20
    draw.rectangle([0, next_y, W, next_y+120], fill=LIGHT)
    draw.rounded_rectangle([W//2-260, url_y, W//2+260, url_y+60], radius=30, fill=NAVY)
    draw.text((W//2, url_y+30), 'carsinstock.com/' + slug, font=font_bold_sm, fill=GREEN, anchor='mm')
    draw.text((W//2, url_y+80), dealership + ' - ' + city + ', NJ', font=font_sm, fill=GRAY, anchor='mm')

    # SECTION 6: Watermark
    wm_y = next_y + 120
    draw.rectangle([0, wm_y, W, H], fill=(241, 245, 249))
    draw.text((W-30, wm_y+40), 'Powered by CarsInStock', font=font_sm, fill=GRAY, anchor='rm')

    # Return PNG
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.read(), content_type='image/png')
