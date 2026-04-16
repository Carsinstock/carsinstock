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
        'SELECT name, city, address, state, zip FROM dealerships WHERE id=?',
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
        'full_address': ((dealership_row['address'] + ', ') if dealership_row and dealership_row['address'] else '') + city + ', ' + ((dealership_row['state']) if dealership_row and dealership_row['state'] else 'NJ') + ' ' + ((dealership_row['zip']) if dealership_row and dealership_row['zip'] else ''),
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
        draw.text((W//2, next_y+40), 'Know someone? Refer them -- they buy -- you get $100', font=font_bold_sm, fill=(6, 95, 70), anchor='mm')
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
        pb_draw.text((60, 710), 'Sales Professional', font=font_sm, fill=GREEN, anchor='lm')

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
        pb_draw.text((W-40, 860), dealership, font=font_bold_sm, fill=WHITE, anchor='rm')

        # Dealership address
        pb_draw.rectangle([0, 920, W, 1010], fill=(15, 23, 42))
        pb_draw.text((W//2, 948), full_address, font=font_sm, fill=(180, 190, 200), anchor='mm')
        try:
            font_tiny = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
        except:
            font_tiny = font_sm
        pb_draw.text((W-30, 990), 'Powered by CarsInStock', font=font_tiny, fill=(160, 170, 185), anchor='rm')

        buf = io.BytesIO()
        pb_img.save(buf, format='PNG')
        buf.seek(0)
        return Response(buf.read(), content_type='image/png')

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
