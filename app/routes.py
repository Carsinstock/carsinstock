import os
from flask import Blueprint, render_template, request, redirect, flash, session
from app.models import db

main = Blueprint('main', __name__)


@main.route('/sp-dashboard')
def sp_dashboard():
    from flask import session, redirect
    if 'team_member_id' not in session:
        return redirect('/login')
    import sqlite3
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row
    member = conn.execute("SELECT * FROM dealership_team WHERE id=?", (session['team_member_id'],)).fetchone()
    if not member:
        session.clear()
        return redirect('/login')
    # Get dealership salesperson record for vehicle access
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    from app.models.lead import Lead
    dealership_sp = Salesperson.query.filter_by(salesperson_id=member['dealership_id']).first()
    # Get ALL vehicles for this team member: approved, pending, rejected
    all_my_vehicles = Vehicle.query.filter_by(
        salesperson_id=member['dealership_id'],
        pick_user_id=member['id']
    ).order_by(Vehicle.created_at.desc()).all()
    # Only approved+available ones shown as active picks
    my_vehicles = [v for v in all_my_vehicles if v.approval_status in ('approved', None) and v.status == 'available']
    # Get all leads on their approved vehicles + referral leads
    my_vehicle_ids = [v.id for v in my_vehicles]
    _rep_slug_for_leads = member['slug'] if member['slug'] else ''
    from sqlalchemy import or_ as _or2
    if my_vehicle_ids and _rep_slug_for_leads:
        my_leads = Lead.query.filter(
            _or2(Lead.vehicle_id.in_(my_vehicle_ids), Lead.referred_by == _rep_slug_for_leads)
        ).order_by(Lead.created_at.desc()).limit(50).all()
    elif my_vehicle_ids:
        my_leads = Lead.query.filter(Lead.vehicle_id.in_(my_vehicle_ids)).order_by(Lead.created_at.desc()).limit(50).all()
    elif _rep_slug_for_leads:
        my_leads = Lead.query.filter(Lead.referred_by == _rep_slug_for_leads).order_by(Lead.created_at.desc()).limit(50).all()
    else:
        my_leads = []
    # Use rep's personal slug if set, otherwise fall back to dealership page
    _rep_slug = member['slug'] if member['slug'] else ''
    storefront_url = f"https://carsinstock.com/{_rep_slug}" if _rep_slug else (f"https://carsinstock.com/{dealership_sp.profile_url_slug}" if dealership_sp else "")
    # Load undismissed notifications
    notifications = conn.execute(
        "SELECT * FROM team_notifications WHERE team_member_id=? AND is_dismissed=0 ORDER BY created_at DESC",
        (member['id'],)
    ).fetchall()
    notifications = [dict(n) for n in notifications]
    conn.close()
    return render_template('salesperson/sp_dashboard.html',
        member=dict(member),
        my_vehicles=my_vehicles,
        all_my_vehicles=all_my_vehicles,
        my_leads=my_leads,
        storefront_url=storefront_url,
        dealership_sp=dealership_sp,
        notifications=notifications)

@main.route('/sp-notification/<int:notif_id>/dismiss', methods=['POST'])
def dismiss_notification(notif_id):
    import sqlite3
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.execute("UPDATE team_notifications SET is_dismissed=1 WHERE id=?", (notif_id,))
    conn.commit()
    conn.close()
    return ('', 204)

@main.route('/sp-logout')
def sp_logout():
    session.pop('team_member_id', None)
    session.pop('team_member_name', None)
    session.pop('team_member_email', None)
    session.pop('dealership_id', None)
    return redirect('/login')

@main.route('/sp/api/vin-decode/<vin>')
def vin_decode_public(vin):
    from flask import jsonify
    if 'team_member_id' not in session and 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if len(vin) != 17:
        return jsonify({'error': 'VIN must be 17 characters'}), 400
    from app.utils.vin_decoder import decode_vin
    result = decode_vin(vin.upper())
    if result:
        return jsonify(result)
    return jsonify({'error': 'Could not decode VIN'}), 404


@main.route('/sp/vehicles/<int:vehicle_id>/set-top-pick', methods=['POST'])
def sp_set_top_pick(vehicle_id):
    """Rep sets one of their approved vehicles as their featured Top Pick."""
    if 'team_member_id' not in session:
        return redirect('/login')
    import sqlite3 as _sq
    from app.models.vehicle import Vehicle
    from app.models import db
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    member = _conn.execute("SELECT * FROM dealership_team WHERE id=? AND is_active=1", (session['team_member_id'],)).fetchone()
    _conn.close()
    if not member:
        return redirect('/login')
    # Clear existing top pick for this rep
    old_picks = Vehicle.query.filter_by(
        pick_user_id=member['id'],
        is_team_pick=True
    ).all()
    for v in old_picks:
        v.is_team_pick = False
    # Set new top pick
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    if vehicle.pick_user_id == member['id'] and vehicle.approval_status in ('approved', None):
        vehicle.is_team_pick = True
        flash(f"{vehicle.year} {vehicle.make} {vehicle.model} is now your Top Pick!", "success")
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"set_top_pick error: {e}")
    return redirect('/sp-dashboard')


@main.route('/sp/vehicles/edit/<int:vehicle_id>', methods=['POST'])
def sp_edit_vehicle(vehicle_id):
    """Team member edits their own approved vehicle — no re-approval needed."""
    if 'team_member_id' not in session:
        return redirect('/login')
    import sqlite3 as _sq
    from app.models.vehicle import Vehicle
    from app.models import db
    from datetime import datetime, timedelta
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    member = _conn.execute("SELECT * FROM dealership_team WHERE id=? AND is_active=1", (session['team_member_id'],)).fetchone()
    _conn.close()
    if not member:
        return redirect('/login')
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    if vehicle.pick_user_id != member['id']:
        flash("You can only edit your own vehicles.", "error")
        return redirect('/sp-dashboard')
    # Only approved vehicles can be edited without re-approval
    if vehicle.approval_status not in ('approved', None):
        flash("Only approved vehicles can be edited.", "error")
        return redirect('/sp-dashboard')
    # Update price
    price = request.form.get('price', '').strip().replace(',', '').replace('$', '')
    if price:
        try:
            vehicle.price = float(price)
        except ValueError:
            pass
    # Update mileage
    mileage = request.form.get('mileage', '').strip().replace(',', '')
    if mileage and mileage.isdigit():
        vehicle.mileage = int(mileage)
    # Update photo if provided
    photo = request.files.get('photo')
    if photo and photo.filename:
        try:
            from app.utils.cloudinary_upload import upload_vehicle_image
            from app.models.salesperson import Salesperson
            dealership_sp = Salesperson.query.filter_by(salesperson_id=member['dealership_id']).first()
            new_url = upload_vehicle_image(photo, dealership_sp.salesperson_id if dealership_sp else 1)
            if new_url:
                vehicle.image_url = new_url
        except Exception as e:
            print(f"Photo update error: {e}")
    # Handle video upload — goes to pending_video_url for admin approval
    video = request.files.get('video')
    if video and video.filename:
        try:
            from app.utils.cloudinary_upload import upload_vehicle_video
            from app.models.salesperson import Salesperson
            dealership_sp = Salesperson.query.filter_by(salesperson_id=member['dealership_id']).first()
            vid_url, w, h = upload_vehicle_video(video, dealership_sp.salesperson_id if dealership_sp else 1, vehicle_id)
            if vid_url:
                vehicle.pending_video_url = vid_url
        except Exception as e:
            print(f"Video upload error: {e}")
    # Renew dates if checked
    if request.form.get('renew_dates'):
        vehicle.expires_at = datetime.utcnow() + timedelta(days=7)
        vehicle.expiration_warning_sent = False
        vehicle.status = 'available'
    try:
        db.session.commit()
        if video and video.filename:
            flash("Changes saved. Video submitted for review — goes live once approved.", "success")
        else:
            flash("Vehicle updated!", "success")
    except Exception as e:
        db.session.rollback()
        flash("Something went wrong.", "error")
        print(f"sp_edit_vehicle error: {e}")
    return redirect('/sp-dashboard')


@main.route('/sp/vehicles/delete/<int:vehicle_id>', methods=['POST'])
def sp_delete_vehicle(vehicle_id):
    """Team member deletes their own vehicle — no approval needed."""
    if 'team_member_id' not in session:
        return redirect('/login')
    from app.models.vehicle import Vehicle
    from app.models import db
    import sqlite3 as _sq
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    member = _conn.execute("SELECT * FROM dealership_team WHERE id=? AND is_active=1", (session['team_member_id'],)).fetchone()
    _conn.close()
    if not member:
        return redirect('/login')
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    # Only allow deleting vehicles assigned to this rep
    if vehicle.pick_user_id != member['id']:
        flash("You can only delete your own vehicles.", "error")
        return redirect('/sp-dashboard')
    try:
        db.session.delete(vehicle)
        db.session.commit()
        flash(f"Vehicle removed.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Something went wrong.", "error")
        print(f"sp_delete_vehicle error: {e}")
    return redirect('/sp-dashboard')


@main.route('/sp/vehicles/add', methods=['POST'])
def sp_add_vehicle():
    """Team member vehicle submission — goes straight to pending."""
    if 'team_member_id' not in session:
        return redirect('/login')
    import sqlite3 as _sq
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    member = _conn.execute("SELECT * FROM dealership_team WHERE id=? AND is_active=1", (session['team_member_id'],)).fetchone()
    _conn.close()
    if not member:
        return redirect('/login')

    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    from app.models import db
    from app.utils.cloudinary_upload import upload_vehicle_image
    from datetime import datetime

    dealership_sp = Salesperson.query.filter_by(salesperson_id=member['dealership_id']).first()
    if not dealership_sp:
        flash("Store not found.", "error")
        return redirect('/sp-dashboard')

    year = request.form.get('year', '').strip()
    make = request.form.get('make', '').strip()
    model = request.form.get('model', '').strip()
    trim = request.form.get('trim', '').strip()
    vin = request.form.get('vin', '').strip().upper()
    mileage = request.form.get('mileage', '').strip().replace(',', '').replace(' ', '')
    price = request.form.get('price', '').strip()
    exterior_color = request.form.get('exterior_color', '').strip()
    transmission = request.form.get('transmission', '').strip()
    fuel_type = request.form.get('fuel_type', '').strip()
    pick_blurb = request.form.get('pick_blurb', '').strip()[:150]
    photo = request.files.get('photo')

    errors = []
    if not year or not year.isdigit(): errors.append("Valid year required.")
    if not make: errors.append("Make required.")
    if not model: errors.append("Model required.")
    if not vin or len(vin) != 17: errors.append("Valid 17-character VIN required.")
    if not price: errors.append("Price required.")
    if not photo or photo.filename == '': errors.append("Photo required.")

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect('/sp-dashboard')

    try:
        price_val = float(price.replace(',', '').replace('$', ''))
    except ValueError:
        flash("Invalid price.", "error")
        return redirect('/sp-dashboard')

    image_url = None
    try:
        image_url = upload_vehicle_image(photo, dealership_sp.salesperson_id)
    except Exception as e:
        flash("Photo upload failed. Try again.", "error")
        return redirect('/sp-dashboard')

    vehicle = Vehicle(
        salesperson_id=dealership_sp.salesperson_id,
        dealer_id=dealership_sp.dealer_id,
        year=int(year),
        make=make,
        model=model,
        trim=trim,
        vin=vin,
        mileage=int(mileage) if mileage and mileage.isdigit() else None,
        price=price_val,
        exterior_color=exterior_color,
        transmission=transmission,
        fuel_type=fuel_type,
        image_url=image_url,
        is_team_pick=True,
        pick_user_id=member['id'],
        pick_blurb=pick_blurb if pick_blurb else None,
        approval_status='pending'
    )
    try:
        db.session.add(vehicle)
        db.session.commit()
        flash(f"{year} {make} {model} submitted! Your manager will review it shortly.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "error")
        print(f"sp_add_vehicle error: {e}")

    return redirect('/sp-dashboard')


@main.route('/<slug>/contact')
def public_contact(slug):
    import sqlite3
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row
    sql = "SELECT dt.*, d.name as dealership_name, d.address as d_address, d.city as d_city, d.state as d_state, d.zip as d_zip FROM dealership_team dt LEFT JOIN dealerships d ON dt.dealership_id=d.id WHERE dt.slug=? AND dt.is_active=1"
    member = conn.execute(sql, (slug,)).fetchone()
    conn.close()
    if not member:
        return "Not found", 404
    return render_template('salesperson/public_contact.html', member=dict(member))

@main.route('/<slug>/vcard')
def public_vcard(slug):
    import sqlite3
    from flask import Response
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row
    sql = "SELECT dt.*, d.name as dealership_name, d.address as d_address, d.city as d_city, d.state as d_state, d.zip as d_zip FROM dealership_team dt LEFT JOIN dealerships d ON dt.dealership_id=d.id WHERE dt.slug=? AND dt.is_active=1"
    member = conn.execute(sql, (slug,)).fetchone()
    conn.close()
    if not member:
        return "Not found", 404
    name = member['name'] or ''
    parts = name.strip().split(' ', 1)
    first = parts[0] if parts else name
    last = parts[1] if len(parts) > 1 else ''
    phone = member['phone'] or ''
    email = member['email'] or ''
    dealership = member['dealership_name'] or ''
    address = member['d_address'] or ''
    city = member['d_city'] or ''
    state = member['d_state'] or 'NJ'
    zip_code = member['d_zip'] or ''
    vcf = "BEGIN:VCARD\nVERSION:3.0\nN:" + last + ";" + first + ";;;\nFN:" + name + "\nORG:" + dealership + "\nTITLE:Sales Professional\nTEL;TYPE=CELL:" + phone + "\nEMAIL:" + email + "\nURL:https://cardeals.autos/" + slug + "\nADR;TYPE=WORK:;;" + address + ";" + city + ";" + state + ";" + zip_code + ";USA\nNOTE:View my inventory at cardeals.autos/" + slug + "\nEND:VCARD"
    response = Response(vcf, mimetype='text/x-vcard; charset=utf-8')
    response.headers['Content-Disposition'] = 'attachment; filename="' + slug + '.vcf"'
    response.headers['Cache-Control'] = 'no-cache'
    return response



@main.route('/<slug>/contact.vcf')
def public_vcard_vcf(slug):
    return public_vcard(slug)

@main.route('/<slug>/inventory')
def full_inventory(slug):
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    from sqlalchemy import or_
    from datetime import datetime
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if not sp or sp.subscription_tier != 'dealership':
        return redirect(f'/{slug}')
    vehicles = Vehicle.query.filter(
        Vehicle.salesperson_id == sp.salesperson_id,
        Vehicle.status == 'available',
        or_(Vehicle.approval_status == 'approved', Vehicle.approval_status == None)
    ).order_by(Vehicle.price.asc()).all()
    vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]
    import sqlite3 as _sq
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    _team_rows = _conn.execute("SELECT id, name, profile_photo FROM dealership_team WHERE is_active=1").fetchall()
    _conn.close()
    team_lookup = {r['id']: {'name': r['name'], 'photo': r['profile_photo']} for r in _team_rows}
    return render_template('salesperson/full_inventory.html', sp=sp, vehicles=vehicles, team_lookup=team_lookup)


@main.route('/')
def home():
    return render_template('index.html', hide_nav_auth=True)

@main.route('/salespeople')
def salespeople():
    return render_template('salespeople.html')

@main.route('/customers')
def customers():
    from flask import session
    if session.get('user_id'):
        return redirect('/customers/list')
    return render_template('customers.html')

@main.route('/customers/sample-csv')
def sample_csv():
    from flask import Response
    csv_content = "Name,Email,Phone\nJohn Smith,john@gmail.com,555-123-4567\nMaria Garcia,maria@yahoo.com,555-987-6543\nBob Johnson,bob@hotmail.com,555-456-7890\n"
    return Response(csv_content, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=sample_contacts.csv'})

@main.route('/search-cars')
def search_cars():
    from app.models.vehicle import Vehicle
    from app.models.salesperson import Salesperson
    from datetime import datetime
    q = request.args.get('q', '').strip()
    vehicles = []
    if q:
        search = f"%{q}%"
        vehicles = Vehicle.query.filter(
            Vehicle.status == 'available',
            db.or_(
                Vehicle.make.ilike(search),
                Vehicle.model.ilike(search),
                Vehicle.year.cast(db.String).ilike(search),
                Vehicle.trim.ilike(search),
                Vehicle.exterior_color.ilike(search),
                Vehicle.vin.ilike(search)
            )
        ).all()
        # Filter out expired
        vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]
    return render_template('search_cars.html', vehicles=vehicles, query=q)



@main.route('/how-to')
def howto():
    return render_template('howto.html')

@main.route('/demo')
def demo_page():
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    sp = Salesperson.query.filter_by(profile_url_slug="jsmith").first_or_404()
    vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status="available").all()
    return render_template("salesperson/public_profile.html", sp=sp, vehicles=vehicles, is_owner=False, is_demo=True, hide_nav_auth=True)


@main.route('/manifest/<slug>.json')
def dynamic_manifest(slug):
    from flask import jsonify
    from app.models.salesperson import Salesperson
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if not sp:
        return jsonify({"error": "not found"}), 404
    name = sp.display_name or "CarsInStock"
    manifest = {
        "name": name,
        "short_name": "CarsInStock",
        "description": "Fresh Cars. Real People.",
        "start_url": f"/{slug}",
        "display": "standalone",
        "background_color": "#1E293B",
        "theme_color": "#1E293B",
        "icons": [
            {"src": "/static/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }
    from flask import Response
    import json
    return Response(json.dumps(manifest), mimetype='application/manifest+json')


@main.route('/webhook/sendgrid', methods=['POST'])
def sendgrid_webhook():
    import sqlite3, json
    from datetime import datetime
    events = request.get_json() or []
    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db', timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    cur = conn.cursor()

    type_map = {
        'open':        'open',
        'click':       'click',
        'unsubscribe': 'unsubscribe',
        'spamreport':  'spam',
        'bounce':      'bounce',
    }

    for event in events:
        event_type = event.get('event')
        email      = event.get('email', '').lower().strip()
        our_type   = type_map.get(event_type)
        if not our_type:
            continue

        blast_id    = event.get('blast_id')
        customer_id = event.get('customer_id')
        url_clicked = event.get('url') if our_type == 'click' else None
        ts          = event.get('timestamp', 0)
        try:
            created_at = datetime.utcfromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
        except:
            created_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        # suppress email on bounce, unsubscribe, spam
        if our_type in ('bounce', 'unsubscribe', 'spam') and email:
            cur.execute("UPDATE customers SET unsubscribed=1 WHERE LOWER(email)=?", (email,))

        # write event row — deduplicate opens
        if blast_id and customer_id:
            try:
                if our_type == 'open':
                    exists = cur.execute(
                        "SELECT id FROM blast_events WHERE blast_id=? AND customer_id=? AND event_type='open'",
                        (int(blast_id), int(customer_id))
                    ).fetchone()
                    if exists:
                        continue
                cur.execute(
                    "INSERT INTO blast_events (blast_id, customer_id, event_type, url_clicked, created_at) VALUES (?,?,?,?,?)",
                    (int(blast_id), int(customer_id), our_type, url_clicked, created_at)
                )
            except Exception as e:
                pass

    conn.commit()
    conn.close()
    return '', 200

@main.route('/<team_slug>/leads', methods=['POST'])
def rep_submit_lead(team_slug):
    """Handle lead submission from a rep personal page."""
    import sqlite3 as _sq
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    from app.models.lead import Lead
    from app.models import db
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    member = _conn.execute("SELECT * FROM dealership_team WHERE slug=? AND is_active=1", (team_slug,)).fetchone()
    _conn.close()
    if not member:
        return redirect(f'/{team_slug}')
    dealership_sp = Salesperson.query.filter_by(salesperson_id=member['dealership_id']).first()
    vehicle_id = request.form.get('vehicle_id')
    customer_name = request.form.get('customer_name', '').strip()
    customer_email = request.form.get('customer_email', '').strip()
    customer_phone = request.form.get('customer_phone', '').strip()
    message = request.form.get('message', '').strip()
    if not customer_name:
        return redirect(f'/{team_slug}')
    lead = Lead(
        salesperson_id=dealership_sp.salesperson_id if dealership_sp else None,
        vehicle_id=int(vehicle_id) if vehicle_id and vehicle_id.isdigit() else None,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        message=message,
        source='rep_storefront',
        referred_by=team_slug,  # auto-credit the rep whose page it is
    )
    try:
        db.session.add(lead)
        db.session.commit()
        # Fire emails for rep personal page lead
        from app.utils.email import send_email as _se
        vehicle_obj = None
        if vehicle_id and vehicle_id.isdigit():
            from app.models.vehicle import Vehicle as _V
            vehicle_obj = _V.query.get(int(vehicle_id))
        v_name = f"{vehicle_obj.year} {vehicle_obj.make} {vehicle_obj.model}" if vehicle_obj else "a vehicle"
        # Email to rep
        try:
            _se(member['email'], f"🎯 New Lead from Your Page: {customer_name}",
                f"""<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
                <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;"><span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span></div>
                <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                  <h2 style="color:#1E293B;margin:0 0 8px;">🎯 New lead from your personal page!</h2>
                  <p style="color:#475569;font-size:15px;margin:0 0 16px;">Someone visited <strong>carsinstock.com/{team_slug}</strong> and is interested in <strong>{v_name}</strong>.</p>
                  <div style="background:#F0FDF4;border-radius:8px;padding:14px;">
                    <p style="margin:0 0 6px;font-size:14px;"><strong>Name:</strong> {customer_name}</p>
                    <p style="margin:0 0 6px;font-size:14px;"><strong>Phone:</strong> {customer_phone or 'Not provided'}</p>
                    <p style="margin:0;font-size:14px;"><strong>Email:</strong> {customer_email}</p>
                  </div>
                </div></div>""")
        except Exception as e:
            print(f"Rep page lead email error: {e}")
        # Email to dealership admin
        try:
            if dealership_sp and dealership_sp.email:
                _se(dealership_sp.email, f"📋 Lead via {member['name']}'s page: {customer_name}",
                    f"""<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
                    <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;"><span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span></div>
                    <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                      <h2 style="color:#1E293B;margin:0 0 8px;">📋 New Lead — Personal Page</h2>
                      <p style="color:#475569;font-size:14px;margin:0 0 4px;">Came through: <strong style="color:#00C851;">{member['name']}</strong>'s page (carsinstock.com/{team_slug})</p>
                      <p style="color:#475569;font-size:14px;margin:0 0 16px;">Vehicle: <strong>{v_name}</strong></p>
                      <div style="background:#F8FAFC;border-radius:8px;padding:14px;">
                        <p style="margin:0 0 6px;font-size:14px;"><strong>Customer:</strong> {customer_name}</p>
                        <p style="margin:0 0 6px;font-size:14px;"><strong>Phone:</strong> {customer_phone or 'Not provided'}</p>
                        <p style="margin:0;font-size:14px;"><strong>Email:</strong> {customer_email}</p>
                      </div>
                    </div></div>""")
        except Exception as e:
            print(f"Admin rep page lead email error: {e}")
    except Exception as e:
        db.session.rollback()
        print(f"rep lead error: {e}")
    flash("Thanks! We'll be in touch shortly.", "success")
    return redirect(f'/{team_slug}')


@main.route('/referral/submit/<slug>', methods=['POST'])
def referral_submit(slug):
    """Handle referral form submission from any storefront."""
    import sqlite3 as _sq, os
    from datetime import datetime
    from app.models.salesperson import Salesperson
    from flask import jsonify, request
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if not sp:
        return jsonify({"error": "not found"}), 404
    data = request.get_json() or {}
    referrer_name = data.get("referrer_name", "").strip()
    referrer_phone = data.get("referrer_phone", "").strip()
    referrer_email = data.get("referrer_email", "").strip()
    friend_name = data.get("friend_name", "").strip()
    friend_phone = data.get("friend_phone", "").strip()
    message = data.get("message", "").strip()
    if not all([referrer_name, referrer_phone, referrer_email, friend_name, friend_phone]):
        return jsonify({"error": "Missing required fields"}), 400
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.execute(
        "INSERT INTO referrals (salesperson_id, referrer_name, referrer_phone, referrer_email, friend_name, friend_phone, message, submitted_at) VALUES (?,?,?,?,?,?,?,?)",
        (sp.salesperson_id, referrer_name, referrer_phone, referrer_email, friend_name, friend_phone, message, datetime.utcnow())
    )
    _conn.commit()
    _conn.close()
    # Send confirmation email to referrer
    try:
        from app.utils.email import send_email
        html = f"""<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
          <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;"><span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span></div>
          <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
            <h2 style="color:#1E293B;margin:0 0 8px;">Got your referral!</h2>
            <p style="color:#475569;font-size:15px;margin:0 0 16px;">Hey {referrer_name.split()[0]}, we received your referral for {friend_name}. If they buy, you receive a Thank You gift.</p>
            <p style="color:#94A3B8;font-size:12px;margin:0;">— {sp.display_name} via CarsInStock</p>
          </div></div>"""
        send_email(referrer_email, f"Got your referral — thanks, {referrer_name.split()[0]}!", html)
    except Exception as e:
        print(f"Referral email error: {e}")
    # Notify salesperson
    try:
        from app.utils.email import send_email
        from app.models.user import User as _U
        sp_user = _U.query.get(sp.user_id)
        if sp_user:
            admin_html = f"""<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
              <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;"><span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span></div>
              <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                <h2 style="color:#1E293B;margin:0 0 8px;">New Referral Submitted</h2>
                <p style="color:#475569;font-size:14px;"><strong>Referrer:</strong> {referrer_name} — {referrer_phone} — {referrer_email}</p>
                <p style="color:#475569;font-size:14px;"><strong>Friend:</strong> {friend_name} — {friend_phone}</p>
                <p style="color:#475569;font-size:14px;"><strong>Notes:</strong> {message or 'None'}</p>
              </div></div>"""
            send_email(sp_user.email, f"New Referral: {referrer_name} referred {friend_name}", admin_html)
    except Exception as e:
        print(f"Referral admin email error: {e}")
    return jsonify({"success": True})


def rep_storefront(member):
    """Render a dealership team member's personal storefront page."""
    import sqlite3 as _sq
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    from app.models.lead import Lead
    from sqlalchemy import or_
    from datetime import datetime, timedelta

    dealership_sp = Salesperson.query.filter_by(salesperson_id=member['dealership_id']).first()
    if not dealership_sp:
        return render_template('404.html'), 404

    # Get approved vehicles assigned to this rep
    all_vehicles = Vehicle.query.filter(
        Vehicle.salesperson_id == member['dealership_id'],
        Vehicle.pick_user_id == member['id'],
        Vehicle.status == 'available',
        or_(Vehicle.approval_status == 'approved', Vehicle.approval_status == None)
    ).order_by(Vehicle.is_team_pick.desc(), Vehicle.price.asc()).all()
    vehicles = [v for v in all_vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]

    # Stats
    live_count = len(vehicles)
    avg_days = round(sum(v.days_remaining for v in vehicles) / live_count) if live_count else 0
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0)
    lead_ids = [v.id for v in vehicles]
    leads_this_month = Lead.query.filter(
        Lead.vehicle_id.in_(lead_ids),
        Lead.created_at >= month_start
    ).count() if lead_ids else 0

    min_price = min((v.price for v in vehicles if v.price), default=None)

    # Featured pick (first is_team_pick vehicle)
    featured = next((v for v in vehicles if v.is_team_pick), None)

    # Dynamic OG tags
    _fallback = 'https://res.cloudinary.com/dbpa9qqtb/image/upload/v1772163049/demo/demo_cover_photo.jpg'
    def _cld(url):
        if url and 'cloudinary.com' in url:
            return url.replace('/upload/', '/upload/w_1200,h_630,c_fill,g_auto,f_jpg,q_80/')
        return url
    og_image = _cld(featured.image_url if featured and featured.image_url else (member['profile_photo'] or _fallback))
    og_title = f"{member['name']} — This Week's Top Picks"
    if live_count and min_price:
        og_description = f"{live_count} car{'s' if live_count != 1 else ''} available · From ${min_price:,.0f} · Updated daily · Tap to browse"
    else:
        og_description = f"Browse {member['name']}'s inventory at CarsInStock — carsinstock.com/{member['slug']}"

    return render_template('salesperson/rep_storefront.html',
        member=member,
        dealership_sp=dealership_sp,
        vehicles=vehicles,
        featured=featured,
        live_count=live_count,
        avg_days=avg_days,
        leads_this_month=leads_this_month,
        og_image=og_image,
        og_title=og_title,
        og_description=og_description,
        hide_nav_auth=True,
    )


@main.route('/<slug>')
def public_profile(slug):
    import re
    from flask import redirect
    # Redirect old hyphenated slugs to clean version
    clean_slug = re.sub(r'[^a-z0-9]', '', slug.lower())
    if slug != clean_slug:
        return redirect(f'/{clean_slug}', 301)

    # Check if this is a dealership team member personal page
    import sqlite3 as _sqt
    _ct = _sqt.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _ct.row_factory = _sqt.Row
    _member = _ct.execute("SELECT * FROM dealership_team WHERE slug=? AND is_active=1", (slug,)).fetchone()
    _ct.close()
    if _member:
        return rep_storefront(dict(_member))

    from app.models.salesperson import Salesperson
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if not sp:
        return render_template('404.html'), 404
    from app.models.vehicle import Vehicle
    from datetime import datetime
    is_owner = (session.get('user_id') == sp.user_id)
    if is_owner:
        # Owner sees all vehicles, expired ones marked
        sort = sp.vehicle_sort_order or 'newest'
        if sort == 'price_low':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.price.asc()).all()
        elif sort == 'price_high':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.price.desc()).all()
        else:
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.price.asc()).all()
    else:
        # Public only sees active, non-expired, approved vehicles
        from sqlalchemy import or_ as _or
        sort = sp.vehicle_sort_order or 'newest'
        base_q = Vehicle.query.filter(
            Vehicle.salesperson_id == sp.salesperson_id,
            Vehicle.status == 'available',
            _or(Vehicle.approval_status == 'approved', Vehicle.approval_status == None)
        )
        if sort == 'price_high':
            vehicles = base_q.order_by(Vehicle.price.desc()).all()
        else:
            vehicles = base_q.order_by(Vehicle.price.asc()).all()
        vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]
    # Gate storefront if owner's subscription is locked
    from app.models.user import User as _User
    sp_user = _User.query.get(sp.user_id)
    if sp_user and sp_user.is_locked:
        return render_template('billing/storefront_locked.html', sp=sp), 402
    # Build team picks lookup from dealership_team
    import sqlite3 as _sq
    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    _conn.row_factory = _sq.Row
    _team_rows = _conn.execute("SELECT id, name, profile_photo FROM dealership_team WHERE is_active=1").fetchall()
    _conn.close()
    team_lookup = {r['id']: {'name': r['name'], 'photo': r['profile_photo']} for r in _team_rows}

    def _og_img(url):
        """Transform Cloudinary URL to OG-friendly 1200x630 crop."""
        if url and 'cloudinary.com' in url:
            # Insert transformation before /upload/
            return url.replace('/upload/', '/upload/w_1200,h_630,c_fill,g_auto,f_jpg,q_80/')
        return url

    # Store referral param in session
    _ref = request.args.get('ref', '').strip().lower()
    if _ref:
        session[f'ref_{slug}'] = _ref

    # Build dynamic OG tags
    _fallback_img = 'https://res.cloudinary.com/dbpa9qqtb/image/upload/v1772163049/demo/demo_cover_photo.jpg'
    _live_count = len(vehicles)
    _min_price = min((v.price for v in vehicles if v.price), default=None)

    if sp.subscription_tier == 'dealership':
        # For dealership: use featured pick vehicle photo but always show dealership name in title
        _og_image = _og_img(sp.cover_photo or sp.profile_photo or _fallback_img)
        _featured_pick = next((v for v in vehicles if v.is_team_pick and v.pick_user_id and team_lookup.get(v.pick_user_id) and team_lookup[v.pick_user_id].get('photo')), None)
        if _featured_pick and _featured_pick.image_url:
            _og_image = _og_img(_featured_pick.image_url)
        _og_title = f"{sp.display_name} — This Week's Top Picks"
        if _min_price and _live_count:
            _og_description = f"{_live_count} car{'s' if _live_count != 1 else ''} available · From ${_min_price:,.0f} · Updated weekly · carsinstock.com/{sp.profile_url_slug}"
        else:
            _og_description = f"Browse fresh inventory from {sp.display_name} at CarsInStock — carsinstock.com/{sp.profile_url_slug}"
    else:
        # Individual salesperson: their photo + name + car count
        _og_image = _og_img(sp.profile_photo or _fallback_img)
        _og_title = f"{sp.display_name} — {_live_count} Fresh Car{'s' if _live_count != 1 else ''} This Week"
        if _min_price and _live_count:
            _og_description = f"{_live_count} vehicle{'s' if _live_count != 1 else ''} available. Starting at ${_min_price:,.0f}. carsinstock.com/{sp.profile_url_slug}"
        else:
            _og_description = f"Check out {sp.display_name}'s inventory this week at CarsInStock — carsinstock.com/{sp.profile_url_slug}"

    # Dealership accounts — use personal storefront template + pass team members for Meet the Team
    if sp.subscription_tier == 'dealership':
        import sqlite3 as _sqd
        _cd = _sqd.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        _cd.row_factory = _sqd.Row
        _team_members = _cd.execute("SELECT * FROM dealership_team WHERE dealership_id=? AND is_active=1 ORDER BY name", (sp.salesperson_id,)).fetchall()
        _team_members = [dict(r) for r in _team_members]
        _cd.close()
        _ref_val = session.get(f'ref_{slug}', '')
        return render_template('salesperson/public_profile.html', sp=sp, vehicles=vehicles,
            is_owner=is_owner, is_demo=False, hide_nav_auth=not is_owner,
            team_lookup=team_lookup, team_members=_team_members,
            og_image=_og_image, og_title=_og_title, og_description=_og_description,
            ref_slug=_ref_val)

    _ref_val = session.get(f'ref_{slug}', '')
    return render_template('salesperson/public_profile.html', sp=sp, vehicles=vehicles,
        is_owner=is_owner, is_demo=False, hide_nav_auth=not is_owner,
        team_lookup=team_lookup, team_members=[],
        og_image=_og_image, og_title=_og_title, og_description=_og_description,
        ref_slug=_ref_val)


@main.route("/lead/submit", methods=["POST"])
def submit_lead():
    from app.models import db
    from app.models.lead import Lead
    from app.models.vehicle import Vehicle
    from app.models.salesperson import Salesperson
    from app.utils.email import send_email

    vehicle_id = request.form.get("vehicle_id")
    customer_name = request.form.get("customer_name", "").strip()
    customer_email = request.form.get("customer_email", "").strip()
    customer_phone = request.form.get("customer_phone", "").strip()
    message = request.form.get("message", "").strip()
    referred_by = request.form.get("referred_by", "").strip().lower() or None

    if not customer_name or not customer_email:
        flash("Name and email are required.", "error")
        return redirect(request.referrer or "/")

    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        flash("Vehicle not found.", "error")
        return redirect(request.referrer or "/")

    sp = Salesperson.query.get(vehicle.salesperson_id)

    # Resolve referring rep from slug
    _ref_member = None
    if referred_by:
        import sqlite3 as _sqr
        _cr = _sqr.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        _cr.row_factory = _sqr.Row
        _ref_member = _cr.execute("SELECT * FROM dealership_team WHERE slug=? AND is_active=1", (referred_by,)).fetchone()
        _cr.close()

    lead = Lead(
        vehicle_id=vehicle.id,
        salesperson_id=vehicle.salesperson_id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        message=message,
        source="storefront",
        status="new",
        referred_by=referred_by if _ref_member else None,
    )

    try:
        db.session.add(lead)
        db.session.commit()

        # Send email notification to salesperson
        if sp and sp.email:
            html = f"""
            <h2>🚗 New Lead on CarsInStock!</h2>
            <p><strong>Vehicle:</strong> {vehicle.year} {vehicle.make} {vehicle.model}</p>
            <p><strong>Price:</strong> ${vehicle.price:,.0f}</p>
            <hr>
            <p><strong>Customer Name:</strong> {customer_name}</p>
            <p><strong>Email:</strong> {customer_email}</p>
            <p><strong>Phone:</strong> {customer_phone or 'Not provided'}</p>
            <p><strong>Message:</strong> {message or 'No message'}</p>
            <hr>
            <p>Log in to <a href="https://carsinstock.com">CarsInStock</a> to manage your leads.</p>
            """
            try:
                send_email(sp.email, f"New Lead: {vehicle.year} {vehicle.make} {vehicle.model}", html)
            except Exception as e:
                print(f"Lead email error: {e}")


            # Also notify assigned team member if this is a Team Pick
            try:
                if vehicle.is_team_pick and vehicle.pick_user_id:
                    import sqlite3 as _sq
                    _conn = _sq.connect('/home/eddie/carsinstock/instance/carsinstock.db')
                    _member = _conn.execute("SELECT name, email FROM dealership_team WHERE id=? AND is_active=1", (vehicle.pick_user_id,)).fetchone()
                    _conn.close()
                    if _member and _member[1]:
                        team_html = f"""<h2>New Lead on Your Team Pick!</h2><p>A customer is interested in the <strong>{vehicle.year} {vehicle.make} {vehicle.model}</strong> — a vehicle you endorsed.</p><p><strong>Customer:</strong> {customer_name}</p><p><strong>Email:</strong> {customer_email}</p><p><strong>Phone:</strong> {customer_phone or 'Not provided'}</p><p><strong>Message:</strong> {message or 'No message'}</p><p style='color:#64748B;font-size:13px;'>This lead was routed to you because you endorsed this vehicle on CarsInStock.</p>"""
                        send_email(_member[1], f"New Lead on Your Pick: {vehicle.year} {vehicle.make} {vehicle.model}", team_html)
            except Exception as e:
                print(f"Team member lead email error: {e}")

            # Referral notifications — fire if this lead came via a rep's referral link
            if _ref_member:
                _ref_name = _ref_member['name']
                _ref_email = _ref_member['email']
                _ref_slug = _ref_member['slug']
                try:
                    # Email to referring rep
                    ref_rep_html = f"""
                    <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
                      <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;">
                        <span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span>
                      </div>
                      <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                        <h2 style="color:#1E293B;font-size:20px;margin:0 0 8px;">🎯 You got a referral lead!</h2>
                        <p style="color:#475569;font-size:15px;margin:0 0 16px;">Someone clicked your personal link and expressed interest in the <strong>{vehicle.year} {vehicle.make} {vehicle.model}</strong>.</p>
                        <div style="background:#F0FDF4;border-radius:8px;padding:14px;margin-bottom:20px;">
                          <p style="margin:0 0 6px;font-size:14px;"><strong>Customer:</strong> {customer_name}</p>
                          <p style="margin:0 0 6px;font-size:14px;"><strong>Phone:</strong> {customer_phone or 'Not provided'}</p>
                          <p style="margin:0 0 6px;font-size:14px;"><strong>Email:</strong> {customer_email}</p>
                          <p style="margin:0;font-size:14px;"><strong>Message:</strong> {message or 'No message'}</p>
                        </div>
                        <p style="color:#94A3B8;font-size:12px;margin:0;">Your referral link: carsinstock.com/{sp.profile_url_slug}?ref={_ref_slug}</p>
                      </div>
                    </div>"""
                    send_email(_ref_email, f"🎯 Referral Lead: {customer_name} is interested in the {vehicle.year} {vehicle.make} {vehicle.model}", ref_rep_html)
                except Exception as e:
                    print(f"Referral rep email error: {e}")
                try:
                    # Email to dealership admin (sp email) with ref attribution
                    ref_admin_html = f"""
                    <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
                      <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;">
                        <span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span>
                      </div>
                      <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                        <h2 style="color:#1E293B;font-size:20px;margin:0 0 8px;">📋 New Referral Lead</h2>
                        <p style="color:#475569;font-size:14px;margin:0 0 4px;">Referred by: <strong style="color:#00C851;">{_ref_name}</strong></p>
                        <p style="color:#475569;font-size:14px;margin:0 0 16px;">Vehicle: <strong>{vehicle.year} {vehicle.make} {vehicle.model}</strong></p>
                        <div style="background:#F8FAFC;border-radius:8px;padding:14px;margin-bottom:20px;">
                          <p style="margin:0 0 6px;font-size:14px;"><strong>Customer:</strong> {customer_name}</p>
                          <p style="margin:0 0 6px;font-size:14px;"><strong>Phone:</strong> {customer_phone or 'Not provided'}</p>
                          <p style="margin:0 0 6px;font-size:14px;"><strong>Email:</strong> {customer_email}</p>
                          <p style="margin:0;font-size:14px;"><strong>Message:</strong> {message or 'No message'}</p>
                        </div>
                      </div>
                    </div>"""
                    if sp and sp.email:
                        send_email(sp.email, f"📋 Referral Lead via {_ref_name}: {customer_name}", ref_admin_html)
                except Exception as e:
                    print(f"Referral admin email error: {e}")
        # Send confirmation to customer with unsubscribe link
        try:
            from app.models.customer import Customer
            from app.utils.email import generate_unsubscribe_token
            # Find or create customer record for unsubscribe token
            customer = Customer.query.filter_by(email=customer_email, salesperson_id=vehicle.salesperson_id).first()
            if customer:
                unsub_token = generate_unsubscribe_token(customer.id)
                unsub_url = f"https://carsinstock.com/unsubscribe/{unsub_token}"
                unsub_link = f'<p style="color:#999;font-size:11px;margin-top:12px;"><a href="{unsub_url}" style="color:#999;text-decoration:underline;">Unsubscribe from future emails</a></p>'
            else:
                unsub_link = ""
            customer_html = f"""
            <div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:0 auto;">
                <div style="background:#1E293B;padding:24px;text-align:center;border-radius:12px 12px 0 0;">
                    <h1 style="margin:0;font-size:24px;"><span style="color:#fff;">Cars</span> <span style="color:#00C851;">IN STOCK</span></h1>
                </div>
                <div style="padding:24px;">
                    <h2 style="color:#1E293B;">Thanks for your interest, {customer_name}!</h2>
                    <p style="color:#555;font-size:15px;line-height:1.6;">{sp.display_name} at {sp.dealership_name or 'the dealership'} has received your inquiry about the {vehicle.year} {vehicle.make} {vehicle.model} and will be in touch soon.</p>
                    <p style="color:#555;font-size:15px;">In the meantime, check out more inventory:</p>
                    <div style="text-align:center;margin:20px 0;">
                        <a href="https://carsinstock.com/{sp.profile_url_slug}" style="background:#00C851;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">View Full Inventory</a>
                    </div>
                </div>
                <div style="border-top:1px solid #eee;padding:16px;text-align:center;">
                    <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>
                    {unsub_link}
                </div>
            </div>"""
            send_email(customer_email, f"Thanks for your interest in the {vehicle.year} {vehicle.make} {vehicle.model}!", customer_html)
        except Exception as e:
            print(f"Customer confirmation email error: {e}")
        flash("Thanks! The salesperson will be in touch soon.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Something went wrong. Please try again.", "error")
        print(f"Lead submit error: {e}")

    return redirect(request.referrer or "/")

@main.route('/unsubscribe/<token>')
def unsubscribe(token):
    from app.models.customer import Customer
    from app.utils.email import verify_unsubscribe_token
    customer_id = verify_unsubscribe_token(token)
    if customer_id:
        customer = Customer.query.get(customer_id)
        if customer:
            customer.unsubscribed = True
            db.session.commit()
            return render_template('unsubscribe.html', name=customer.name, success=True)
    return render_template('unsubscribe.html', name=None, success=False)




@main.route('/storefront/unsubscribe/<slug>', methods=['GET', 'POST'])
def storefront_unsubscribe(slug):
    from app.models.salesperson import Salesperson
    from app.models.customer import Customer
    from app.models import db
    sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
    sp_name = sp.display_name if sp else "this salesperson"
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            return render_template('storefront_unsubscribe.html', sp_name=sp_name, slug=slug, error="Please enter your email address.")
        if sp:
            customer = Customer.query.filter_by(email=email, salesperson_id=sp.salesperson_id).first()
            if customer:
                customer.unsubscribed = True
                db.session.commit()
        return render_template('storefront_unsubscribe.html', sp_name=sp_name, slug=slug, success=True, email=email)
    return render_template('storefront_unsubscribe.html', sp_name=sp_name, slug=slug)

@main.route('/recruit/unsubscribe/<tracking_id>')
def recruit_unsubscribe(tracking_id):
    from datetime import datetime
    try:
        db.engine.execute(
            db.text("UPDATE recruitment_contacts SET status = 'unsubscribed' WHERE tracking_id = :tid"),
            {"tid": tracking_id}
        )
    except:
        pass
    return """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>*{margin:0;padding:0;box-sizing:border-box;}body{font-family:Inter,sans-serif;background:#f1f5f9;display:flex;justify-content:center;align-items:center;min-height:100vh;}
    .card{background:#fff;border-radius:12px;padding:40px;max-width:500px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.06);}
    h2{color:#1E293B;margin-bottom:12px;}p{color:#64748B;font-size:16px;}</style></head>
    <body><div class="card"><h2>You have been unsubscribed.</h2><p>You will not receive any more emails from CarsInStock.</p></div></body></html>"""

@main.route('/track/click/<tracking_id>')
def track_click(tracking_id):
    from datetime import datetime
    try:
        db.engine.execute(
            db.text("UPDATE recruitment_contacts SET status = 'clicked', clicked_at = :now WHERE tracking_id = :tid AND status != 'converted'"),
            {"now": datetime.utcnow(), "tid": tracking_id}
        )
    except:
        pass
    return redirect("https://carsinstock.com/demo")

@main.route('/contact', methods=['GET', 'POST'])
def contact():
    import os
    turnstile_site_key = os.environ.get("TURNSTILE_SITE_KEY", "")
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()

        # Verify Turnstile
        turnstile_response = request.form.get("cf-turnstile-response", "")
        if not turnstile_response:
            flash("Please complete the CAPTCHA verification.", "error")
            return render_template('contact.html', turnstile_site_key=turnstile_site_key)

        import requests as http_requests
        verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        verify_data = {
            "secret": os.environ.get("TURNSTILE_SECRET_KEY", ""),
            "response": turnstile_response,
            "remoteip": request.remote_addr
        }
        try:
            verify_result = http_requests.post(verify_url, data=verify_data, timeout=5).json()
            if not verify_result.get("success"):
                flash("CAPTCHA verification failed. Please try again.", "error")
                return render_template('contact.html', turnstile_site_key=turnstile_site_key)
        except:
            pass

        if not name or not email or not message:
            flash("All fields are required.", "error")
            return render_template('contact.html', turnstile_site_key=turnstile_site_key)

        # Send via SendGrid
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            msg = Mail(
                from_email=('noreply@carsinstock.com', 'CarsInStock Contact'),
                to_emails='support@carsinstock.com',
                subject=f'Contact Form: {name}',
                html_content=f"""
                <div style="font-family:Inter,sans-serif;max-width:600px;">
                    <h2 style="color:#1E293B;">New Contact Form Submission</h2>
                    <p><strong>Name:</strong> {name}</p>
                    <p><strong>Email:</strong> {email}</p>
                    <p><strong>Message:</strong></p>
                    <p style="background:#F8FAFC;padding:16px;border-radius:8px;color:#475569;">{message}</p>
                </div>
                """
            )
            msg.reply_to = email
            sg.send(msg)
        except Exception as e:
            print(f"Contact form email error: {e}")

        flash("Message sent! We'll get back to you soon.", "success")
        return redirect('/contact')

    return render_template('contact.html', turnstile_site_key=turnstile_site_key)


@main.route('/subscribe', methods=['POST'])
def subscribe():
    from flask import request, jsonify
    import sqlite3, os, re
    from datetime import datetime

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    turnstile_token = request.form.get('cf-turnstile-response', '')
    salesperson_id = int(request.form.get('salesperson_id', 1) or 1)

    if not first_name or not email:
        return jsonify({'success': False, 'message': 'Name and email are required.'}), 400

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({'success': False, 'message': 'Invalid email address.'}), 400

    # Verify Turnstile
    import urllib.request, json as _json
    try:
        ts_data = urllib.request.urlencode({
            'secret': os.environ.get('TURNSTILE_SECRET_KEY', ''),
            'response': turnstile_token
        }).encode()
        ts_req = urllib.request.Request('https://challenges.cloudflare.com/turnstile/v0/siteverify', data=ts_data)
        ts_resp = _json.loads(urllib.request.urlopen(ts_req).read())
        if not ts_resp.get('success'):
            return jsonify({'success': False, 'message': 'Captcha verification failed.'}), 400
    except:
        pass  # Don't block on captcha errors

    db_path = '/home/eddie/carsinstock/instance/carsinstock.db'
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Check if already subscribed (salesperson_id=1 is Pine Belt)
    existing = cur.execute('SELECT id, unsubscribed FROM customers WHERE email=? AND salesperson_id=1', (email,)).fetchone()
    if existing:
        if existing['unsubscribed']:
            cur.execute('UPDATE customers SET unsubscribed=0, first_name=?, last_name=? WHERE id=?',
                (first_name, last_name, existing['id']))
            conn.commit()
        conn.close()
        # Send confirmation anyway
        _send_subscribe_confirmation(first_name, email)
        return jsonify({'success': True, 'message': 'You\'re on the list!'})

    cur.execute('''INSERT INTO customers
        (salesperson_id, first_name, last_name, email, source, unsubscribed, created_at)
        VALUES (?, ?, ?, ?, 'web_signup', 0, ?)''',
        (salesperson_id, first_name, last_name, email, datetime.utcnow()))
    conn.commit()
    conn.close()

    _send_subscribe_confirmation(first_name, email)
    return jsonify({'success': True, 'message': 'You\'re on the list!'})

def _send_subscribe_confirmation(first_name, email):
    import os
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    try:
        html = f'''<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">
        <div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
            <div style="background:#1E293B;padding:28px 20px;text-align:center;border-radius:10px 10px 0 0;">
                <div style="font-size:24px;font-weight:800;"><span style="color:white;">Cars</span><span style="color:#00C851;">InStock</span></div>
            </div>
            <div style="padding:28px 24px;">
                <h2 style="color:#1E293B;margin:0 0 12px;">You\'re on the list, {first_name}! 🎉</h2>
                <p style="color:#334155;font-size:15px;line-height:1.7;">You\'ll receive this week\'s top car deals every week. Fresh inventory, real prices, straight to your inbox.</p>
                <p style="color:#334155;font-size:15px;line-height:1.7;">Stay tuned.</p>
            </div>
            <div style="background:#f8fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;">
                <p style="color:#94A3B8;font-size:11px;margin:0;">
                    <a href="https://carsinstock.com/unsubscribe" style="color:#94A3B8;text-decoration:underline;">Unsubscribe</a>
                    &middot;
                    <a href="https://carsinstock.com/disclaimer" style="color:#94A3B8;text-decoration:underline;">Legal Disclaimer</a>
                </p>
            </div>
        </div></div>'''
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        msg = Mail(
            from_email=('noreply@carsinstock.com', 'CarsInStock'),
            to_emails=email,
            subject="You\'re on the list — Weekly Specials from CarsInStock",
            html_content=html
        )
        sg.send(msg)
    except Exception as e:
        print(f"Subscribe confirmation email failed: {e}")


@main.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

@main.route('/about')
def about():
    return render_template('about.html')

@main.route('/privacy')
def privacy():
    return render_template('privacy.html')

@main.route('/terms')
def terms():
    return render_template('terms.html')

@main.route('/dealership', methods=['GET', 'POST'])
def dealership():
    import sqlite3, os
    from app.utils.email import send_email
    turnstile_site_key = os.environ.get('TURNSTILE_SITE_KEY', '')
    plan = request.args.get('plan', '')
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        dealership_name = request.form.get('dealership_name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        num_salespeople = request.form.get('num_salespeople', '').strip()
        plan_interest = request.form.get('plan_interest', '').strip()
        message = request.form.get('message', '').strip()
        # Turnstile
        import requests as http_requests
        turnstile_response = request.form.get('cf-turnstile-response', '')
        if turnstile_response:
            try:
                verify = http_requests.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', data={
                    'secret': os.environ.get('TURNSTILE_SECRET_KEY', ''),
                    'response': turnstile_response,
                    'remoteip': request.remote_addr
                }, timeout=5).json()
                if not verify.get('success'):
                    return render_template('dealership.html', error='CAPTCHA failed. Please try again.', plan=plan, turnstile_site_key=turnstile_site_key)
            except:
                pass
        # Save to DB
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        conn.execute('INSERT INTO dealership_leads (first_name, last_name, dealership_name, phone, email, num_salespeople, plan_interest, message) VALUES (?,?,?,?,?,?,?,?)',
            (first_name, last_name, dealership_name, phone, email, num_salespeople, plan_interest, message))
        conn.commit()
        conn.close()
        # Email notification
        html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:#1E293B;padding:20px;text-align:center;">
                <h1 style="color:#00C851;margin:0;font-size:24px;">New Dealership Lead</h1>
            </div>
            <div style="padding:24px;background:#f8fafc;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr><td style="padding:8px;font-weight:700;color:#1E293B;width:40%;">Name</td><td style="padding:8px;">{first_name} {last_name}</td></tr>
                    <tr style="background:#fff;"><td style="padding:8px;font-weight:700;color:#1E293B;">Dealership</td><td style="padding:8px;">{dealership_name}</td></tr>
                    <tr><td style="padding:8px;font-weight:700;color:#1E293B;">Phone</td><td style="padding:8px;">{phone}</td></tr>
                    <tr style="background:#fff;"><td style="padding:8px;font-weight:700;color:#1E293B;">Email</td><td style="padding:8px;">{email}</td></tr>
                    <tr><td style="padding:8px;font-weight:700;color:#1E293B;">Salespeople</td><td style="padding:8px;">{num_salespeople}</td></tr>
                    <tr style="background:#fff;"><td style="padding:8px;font-weight:700;color:#1E293B;">Plan Interest</td><td style="padding:8px;color:#00C851;font-weight:700;">{plan_interest}</td></tr>
                    <tr><td style="padding:8px;font-weight:700;color:#1E293B;">Message</td><td style="padding:8px;">{message or "—"}</td></tr>
                </table>
            </div>
        </div>"""
        try:
            send_email('sales@carsinstock.com', f'New Dealership Lead — {dealership_name}', html)
        except:
            pass
        return render_template('dealership.html', success=True, plan=plan, turnstile_site_key=turnstile_site_key)
    return render_template('dealership.html', plan=plan, turnstile_site_key=turnstile_site_key)

@main.route('/api/generate-pick-blurb', methods=['POST'])
def generate_pick_blurb():
    from flask import jsonify
    import anthropic, os
    data = request.get_json()
    year = data.get('year', '')
    make = data.get('make', '')
    model = data.get('model', '')
    price = data.get('price', '')
    mileage = data.get('mileage', '')
    sp_name = data.get('sp_name', 'the salesperson')
    prompt = f"Write exactly 1 sentence (under 140 characters, no headers, no labels, no quotes) endorsing this car as {sp_name}: {year} {make} {model}, ${price}, {mileage} miles. Be specific and enthusiastic. Output only the sentence."
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    if len(raw) > 150:
        raw = raw[:150].rsplit(' ', 1)[0]
    blurb = raw
    return jsonify({'blurb': blurb})

@main.route('/api/weekly_post', methods=['POST'])
def weekly_post():
    from flask import jsonify
    import anthropic, os
    data = request.get_json()
    sp_id = data.get('salesperson_id')
    member_slug = data.get('member_slug', '')
    member_name = data.get('member_name', '')
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    sp = Salesperson.query.filter_by(salesperson_id=sp_id).first()
    if not sp:
        return jsonify({'error': 'Not found'}), 404
    vehicles = Vehicle.query.filter_by(salesperson_id=sp_id, status='available').order_by(Vehicle.price.asc()).limit(5).all()
    if not vehicles:
        return jsonify({'error': 'No active vehicles'}), 400
    vehicle_lines = "\n".join([f"• {v.year} {v.make} {v.model} — ${v.price:,.0f}" + (f" | {v.mileage:,} miles" if v.mileage else "") for v in vehicles])
    image_urls = [v.image_url for v in vehicles if v.image_url][:5]
    rep_slug = member_slug or sp.profile_url_slug
    rep_name = member_name or sp.display_name
    storefront_url = f"https://cardeals.autos/{rep_slug}"
    contact_url = f"https://cardeals.autos/{rep_slug}/contact"
    prompt = f"""Write social media posts for a car salesperson named {rep_name}. Sound personal, human, not corporate. Use their voice like a real person posting on their own Facebook.

Their current inventory:
{vehicle_lines}

Their storefront: {storefront_url}
Their contact page (save to phone): {contact_url}

Output ONLY valid JSON with these exact keys:
{{
  "facebook_post": "full Facebook post with emoji, vehicle list, and storefront link, 3-5 sentences max",
  "instagram_caption": "shorter version under 150 chars with storefront link",
  "whatsapp_message": "personal casual text message version"
}}"""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    import json
    raw = message.content[0].text.strip()
    try:
        posts = json.loads(raw)
    except Exception:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        posts = json.loads(match.group()) if match else {}
    posts['image_urls'] = image_urls
    posts['storefront_url'] = storefront_url
    return jsonify(posts)
