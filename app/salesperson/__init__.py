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


    # Return PNG (classic template)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.read(), content_type='image/png')


@salesperson_bp.route('/sp/leads/delete/<int:lead_id>', methods=['POST'])
def delete_lead(lead_id):
    from flask import session, redirect
    import sqlite3
    team_member_id = session.get('team_member_id')
    if not team_member_id:
        return redirect('/login')
    db = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    db.execute('DELETE FROM leads WHERE lead_id=?', (lead_id,))
    db.commit()
    db.close()
    return redirect('/sp-dashboard')


@salesperson_bp.route('/sp/vehicles/renew/<int:vehicle_id>', methods=['POST'])
def sp_renew_vehicle(vehicle_id):
    from flask import session, redirect
    from datetime import datetime, timedelta
    import sqlite3
    team_member_id = session.get('team_member_id')
    if not team_member_id:
        return redirect('/login')
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    cur = conn.cursor()
    new_expiry = datetime.utcnow() + timedelta(days=7)
    cur.execute('''UPDATE vehicles SET expires_at=?, created_at=?, expiration_warning_sent=0 
                   WHERE id=? AND pick_user_id=?''',
                (new_expiry, datetime.utcnow(), vehicle_id, team_member_id))
    conn.commit()
    conn.close()
    return redirect('/sp-dashboard')
