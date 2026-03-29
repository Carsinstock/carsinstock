import os
from flask import Blueprint, render_template, request, redirect, flash, session
from app.models import db

main = Blueprint('main', __name__)

@main.route('/')
def home():
    return render_template('index.html')

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

@main.route('/<slug>')
def public_profile(slug):
    import re
    from flask import redirect
    # Redirect old hyphenated slugs to clean version
    clean_slug = re.sub(r'[^a-z0-9]', '', slug.lower())
    if slug != clean_slug:
        return redirect(f'/{clean_slug}', 301)
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
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.created_at.desc()).all()
    else:
        # Public only sees active, non-expired vehicles
        sort = sp.vehicle_sort_order or 'newest'
        if sort == 'price_low':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').order_by(Vehicle.price.asc()).all()
        elif sort == 'price_high':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').order_by(Vehicle.price.desc()).all()
        else:
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').order_by(Vehicle.created_at.desc()).all()
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

    return render_template('salesperson/public_profile.html', sp=sp, vehicles=vehicles, is_owner=is_owner, is_demo=False, hide_nav_auth=not is_owner, team_lookup=team_lookup)


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

    if not customer_name or not customer_email:
        flash("Name and email are required.", "error")
        return redirect(request.referrer or "/")

    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        flash("Vehicle not found.", "error")
        return redirect(request.referrer or "/")

    sp = Salesperson.query.get(vehicle.salesperson_id)

    lead = Lead(
        vehicle_id=vehicle.id,
        salesperson_id=vehicle.salesperson_id,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        message=message,
        source="storefront",
        status="new"
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
    storefront_url = f"https://carsinstock.com/{sp.profile_url_slug}"
    prompt = f"""Write social media posts for a car salesperson named {sp.display_name}. Sound personal, human, not corporate. Use their voice like a real person posting on their own Facebook.

Their current inventory:
{vehicle_lines}

Their storefront: {storefront_url}

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
