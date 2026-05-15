from flask import Blueprint, render_template, request, jsonify, session, redirect
import sqlite3

referral_bp = Blueprint('referral', __name__)
DB = '/home/eddie/carsinstock/instance/carsinstock.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@referral_bp.route('/')
def homepage():
    return render_template('homepage.html')

@referral_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        if not phone:
            return render_template('login.html', error='Please enter your phone number.')
        conn = get_db()
        birddogs = conn.execute(
            'SELECT b.*, dt.name as rep_name, dt.slug as rep_slug, d.name as dealership_name '
            'FROM birddogs b '
            'JOIN dealership_team dt ON b.team_member_id = dt.id '
            'JOIN dealerships d ON dt.dealership_id = d.id '
            'WHERE b.phone=? ORDER BY b.created_at DESC', (phone,)
        ).fetchall()
        conn.close()
        if not birddogs:
            return render_template('login.html', error='No account found with that phone number. Sign up through a referral link first.')
        session['birddog_phone'] = phone
        session['birddog_name'] = birddogs[0]['name']
        return redirect('/dashboard')
    return render_template('login.html', error=None)

@referral_bp.route('/dashboard')
def dashboard():
    if 'birddog_phone' not in session:
        return redirect('/login')
    phone = session['birddog_phone']
    conn = get_db()
    birddogs = conn.execute(
        'SELECT b.*, dt.name as rep_name, dt.slug as rep_slug, dt.profile_photo as rep_photo, '
        'd.name as dealership_name, d.city as dealership_city '
        'FROM birddogs b '
        'JOIN dealership_team dt ON b.team_member_id = dt.id '
        'JOIN dealerships d ON dt.dealership_id = d.id '
        'WHERE b.phone=? ORDER BY b.created_at DESC', (phone,)
    ).fetchall()
    all_referrals = []
    for bd in birddogs:
        refs = conn.execute(
            'SELECT * FROM birddog_referrals WHERE birddog_id=? ORDER BY created_at DESC',
            (bd['id'],)
        ).fetchall()
        all_referrals.append({
            'birddog': dict(bd),
            'referrals': [dict(r) for r in refs]
        })
    conn.close()
    total_sent = sum(len(x['referrals']) for x in all_referrals)
    total_closed = sum(1 for x in all_referrals for r in x['referrals'] if r['status'] == 'sold')
    total_pending = sum(1 for x in all_referrals for r in x['referrals'] if r['status'] in ('pending','submitted'))
    return render_template('dashboard.html',
        name=session['birddog_name'],
        groups=all_referrals,
        total_sent=total_sent,
        total_closed=total_closed,
        total_pending=total_pending)

@referral_bp.route('/submit-referral', methods=['POST'])
def submit_referral():
    if 'birddog_phone' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    birddog_id = data.get('birddog_id')
    team_member_id = data.get('team_member_id')
    buyer_name = data.get('buyer_name', '').strip()
    buyer_phone = data.get('buyer_phone', '').strip()
    if not buyer_name or not buyer_phone or not birddog_id:
        return jsonify({'error': 'Missing fields'}), 400
    conn = get_db()
    conn.execute(
        'INSERT INTO birddog_referrals (birddog_id, team_member_id, buyer_name, buyer_phone, status) VALUES (?,?,?,?,?)',
        (birddog_id, team_member_id, buyer_name, buyer_phone, 'pending')
    )
    conn.commit()
    rep = conn.execute('SELECT name, email FROM dealership_team WHERE id=?', (team_member_id,)).fetchone()
    birddog = conn.execute('SELECT name FROM birddogs WHERE id=?', (birddog_id,)).fetchone()
    conn.close()
    if rep and rep['email']:
        try:
            import sys
            sys.path.insert(0, '/home/eddie/carsinstock')
            from app.utils.email import send_email
            send_email(
                to_email=rep['email'],
                subject='New Referral from ' + (birddog['name'] if birddog else 'a birddog') + ' — ' + buyer_name,
                html_content='<p><strong>' + (birddog['name'] if birddog else 'A birddog') + '</strong> sent you a referral via mycarreferral.com:</p><p><strong>Buyer:</strong> ' + buyer_name + '<br><strong>Phone:</strong> ' + buyer_phone + '</p><p>Log in to your CarsInStock dashboard to follow up.</p>'
            )
        except Exception as e:
            print(f"Email error: {e}")
    return jsonify({'success': True})

@referral_bp.route('/join/<slug>')
def join(slug):
    conn = get_db()
    rep = conn.execute(
        'SELECT dt.*, d.name as dealership_name, d.city, d.address, d.state, d.zip '
        'FROM dealership_team dt '
        'JOIN dealerships d ON dt.dealership_id = d.id '
        'WHERE dt.slug=? AND dt.is_active=1', (slug,)
    ).fetchone()
    conn.close()
    if not rep:
        return render_template('404.html'), 404
    return render_template('join.html', rep=dict(rep))

@referral_bp.route('/api/join', methods=['POST'])
def api_join():
    import secrets
    data = request.get_json()
    name = data.get('name','').strip()
    email = data.get('email','').strip()
    phone = data.get('phone','').strip()
    team_member_id = data.get('team_member_id')
    if not name or not phone or not team_member_id:
        return jsonify({'error': 'Missing required fields'}), 400
    conn = get_db()
    existing = conn.execute('SELECT id, token FROM birddogs WHERE phone=? AND team_member_id=?', (phone, team_member_id)).fetchone()
    if existing:
        conn.close()
        # Set session
        session['birddog_phone'] = phone
        session['birddog_name'] = name
        return jsonify({'success': True, 'token': existing['token'], 'existing': True})
    token = secrets.token_urlsafe(16)
    conn.execute('INSERT INTO birddogs (team_member_id, name, email, phone, token) VALUES (?,?,?,?,?)',
                 (team_member_id, name, email, phone, token))
    conn.commit()
    rep = conn.execute('SELECT name FROM dealership_team WHERE id=?', (team_member_id,)).fetchone()
    conn.close()
    session['birddog_phone'] = phone
    session['birddog_name'] = name
    if email:
        try:
            import sys
            sys.path.insert(0, '/home/eddie/carsinstock')
            from app.utils.email import send_email
            rep_name = rep['name'] if rep else 'your rep'
            send_email(
                to_email=email,
                subject="You joined " + rep_name + " referral network on MyCarReferral",
                html_content='<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"><div style="background:#1E293B;padding:20px;text-align:center;border-radius:12px 12px 0 0;"><h1 style="color:#00C851;margin:0;">MyCarReferral</h1></div><div style="background:#f8fafc;padding:30px;border-radius:0 0 12px 12px;"><h2 style="color:#1E293B;">You are in ' + rep_name + ' referral network!</h2><p style="color:#555;font-size:16px;line-height:1.6;">Every time someone you refer buys a car, you receive a Thank You gift. Track everything at mycarreferral.com.</p><div style="text-align:center;margin:30px 0;"><a href="https://mycarreferral.com/login" style="background:#00C851;color:#1E293B;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:700;">Go to My Dashboard</a></div></div></div>'
            )
        except Exception as e:
            print(f"Email error: {e}")
    return jsonify({'success': True, 'token': token, 'existing': False})


@referral_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/login')
