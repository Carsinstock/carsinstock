"""MyCarReferral routes — public-facing referral platform.

Mounted internally at /mcr. Users on mycarreferral.com see clean paths
(e.g. mycarreferral.com/login) via host-header middleware.

Pine Belt pilot: dealership_id=1, brand_prefix='pbu'.
"""
import re
import secrets
import sqlite3
from datetime import datetime
from flask import Blueprint, render_template, request, session, redirect, url_for

referral_bp = Blueprint(
    'referral',
    __name__,
    url_prefix='/mcr',
    template_folder='templates',
)

DB_PATH = '/home/eddie/carsinstock/instance/carsinstock.db'


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _logged_in():
    return 'birddog_phone' in session


# ============ Public marketing surfaces ============

@referral_bp.route('/')
def homepage():
    """Public marketing homepage — organic visitors, no rep attribution."""
    return render_template('referral/homepage.html')


@referral_bp.route('/join/<rep_slug>')
def signup_landing(rep_slug):
    """Rep-specific signup landing. Trust transfer from rep -> platform."""
    conn = _db()
    rep = conn.execute(
        "SELECT dt.id, dt.name, dt.slug, dt.profile_photo, "
        "d.name AS dealership_name, d.city, d.state "
        "FROM dealership_team dt "
        "JOIN dealerships d ON dt.dealership_id = d.id "
        "WHERE dt.slug = ? AND dt.is_active = 1",
        (rep_slug,)
    ).fetchone()
    conn.close()
    if not rep:
        return render_template('referral/not_found.html'), 404

    name_parts = (rep['name'] or '').strip().split()
    rep_first_name = name_parts[0] if name_parts else ''
    rep_last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
    rep_initials = ''.join(p[0].upper() for p in name_parts[:2]) if name_parts else '?'

    return render_template(
        'referral/signup_landing.html',
        rep_first_name=rep_first_name,
        rep_last_name=rep_last_name,
        rep_initials=rep_initials,
        rep_photo_url=rep['profile_photo'],
        rep_slug=rep['slug'],
        dealership_name=rep['dealership_name'],
        dealership_city=rep['city'],
        dealership_state=rep['state'],
    )


def _slugify(name):
    """Lowercase-alphanumeric slug from a name. 'John Smith' -> 'johnsmith'."""
    base = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    return base or 'birddog'


def _unique_birddog_slug(conn, base, dealership_id):
    """Dedup within a dealership: johnsmith -> johnsmith2 -> johnsmith3..."""
    slug = base
    n = 1
    while conn.execute(
        "SELECT 1 FROM birddogs WHERE slug = ? AND dealership_id = ?",
        (slug, dealership_id)
    ).fetchone():
        n += 1
        slug = f"{base}{n}"
    return slug


@referral_bp.route('/join/<rep_slug>/submit', methods=['POST'])
def signup_submit(rep_slug):
    """Public birddog signup. Creates a real birddog under the rep matched by
    rep_slug, logs them in via phone-session, redirects to their portal.
    No password (phone-based auth, email-only per v1)."""
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()

    conn = _db()
    rep = conn.execute(
        "SELECT id, dealership_id FROM dealership_team "
        "WHERE slug = ? AND is_active = 1",
        (rep_slug,)
    ).fetchone()
    if not rep:
        conn.close()
        return render_template('referral/not_found.html'), 404

    if not name or not phone:
        conn.close()
        return redirect(url_for('referral.signup_landing', rep_slug=rep_slug))

    team_member_id = rep['id']
    dealership_id = rep['dealership_id']

    # Dedupe by phone+rep (matches sp_birddog_signup). Existing -> just log in.
    existing = conn.execute(
        "SELECT id, name FROM birddogs WHERE phone = ? AND team_member_id = ?",
        (phone, team_member_id)
    ).fetchone()
    if existing:
        conn.close()
        session['birddog_phone'] = phone
        session['birddog_name'] = existing['name']
        return redirect(url_for('referral.portal_home'))

    # New birddog: generate unique slug + token, insert with slug + dealership_id
    slug = _unique_birddog_slug(conn, _slugify(name), dealership_id)
    token = secrets.token_urlsafe(16)
    conn.execute(
        "INSERT INTO birddogs "
        "(team_member_id, name, email, phone, token, slug, dealership_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (team_member_id, name, email, phone, token, slug, dealership_id)
    )
    conn.commit()
    conn.close()

    session['birddog_phone'] = phone
    session['birddog_name'] = name
    return redirect(url_for('referral.portal_home'))


# ============ Birddog auth ============

@referral_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Phone-based birddog login. No password, no OTP (email-only per v1 spec)."""
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        if not phone:
            return render_template('referral/login.html', error='Please enter your phone number.')
        conn = _db()
        bd = conn.execute(
            "SELECT * FROM birddogs WHERE phone = ? ORDER BY created_at DESC LIMIT 1",
            (phone,)
        ).fetchone()
        conn.close()
        if not bd:
            return render_template(
                'referral/login.html',
                error='No account found for that number. Ask the rep who invited you for your signup link.'
            )
        session['birddog_phone'] = phone
        session['birddog_name'] = bd['name']
        return redirect(url_for('referral.portal_home'))
    return render_template('referral/login.html', error=None)


@referral_bp.route('/logout')
def logout():
    session.pop('birddog_phone', None)
    session.pop('birddog_name', None)
    return redirect(url_for('referral.homepage'))


@referral_bp.route('/signup')
def signup_placeholder():
    """Placeholder for organic homepage CTA. Redirects to login until CEO decides
    the no-rep onboarding path (default rep? dealership picker? need-invite page?)."""
    return redirect(url_for('referral.login'))


# ============ Birddog portal ============

@referral_bp.route('/me')
def portal_home():
    """Birddog dashboard. Empty state (§5.3) or active state (§5.4) based on activity."""
    if not _logged_in():
        return redirect(url_for('referral.login'))
    phone = session['birddog_phone']
    conn = _db()
    bd = conn.execute(
        "SELECT b.*, dt.name AS rep_name, dt.slug AS rep_slug, "
        "dt.profile_photo AS rep_photo, "
        "d.name AS dealership_name, d.city AS dealership_city, d.state AS dealership_state "
        "FROM birddogs b "
        "JOIN dealership_team dt ON b.team_member_id = dt.id "
        "JOIN dealerships d ON dt.dealership_id = d.id "
        "WHERE b.phone = ? ORDER BY b.created_at DESC LIMIT 1",
        (phone,)
    ).fetchone()
    if not bd:
        conn.close()
        session.clear()
        return redirect(url_for('referral.login'))
    refs = conn.execute(
        "SELECT * FROM birddog_referrals WHERE birddog_id = ? ORDER BY created_at DESC",
        (bd['id'],)
    ).fetchall()
    prog = conn.execute(
        "SELECT brand_prefix FROM referral_programs "
        "WHERE dealership_id = ? AND active = 1 LIMIT 1",
        (bd['dealership_id'],)
    ).fetchone()
    conn.close()

    prefix = prog['brand_prefix'] if prog else 'pbu'
    birddog = dict(bd)
    birddog['tracking_slug'] = f"{prefix}-{birddog['slug']}"

    referrals = []
    for r in refs:
        d = dict(r)
        d['name'] = d.get('buyer_name') or 'Someone'
        raw = str(d.get('created_at') or '').split('.')[0]
        try:
            d['created_display'] = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S').strftime('%b %-d')
        except ValueError:
            d['created_display'] = ''
        referrals.append(d)

    pending_count = sum(1 for r in referrals if r['status'] in ('pending', 'submitted'))
    closed_count = sum(1 for r in referrals if r['status'] == 'sold')
    return render_template(
        'referral/dashboard.html',
        birddog=birddog,
        referrals=referrals,
        pending_count=pending_count,
        closed_count=closed_count,
        gifts_count=closed_count,
        has_activity=len(referrals) > 0,
    )


# ============ Short-link tracking redirect ============
# Catches /<prefix>-<slug> e.g. /pbu-peterfranco
# Registered LAST so explicit routes (/login, /me, /join/...) take precedence

@referral_bp.route('/<token>')
def short_link(token):
    """Public tracking redirect. Sets attribution cookie, forwards to storefront."""
    if '-' not in token:
        return render_template('referral/not_found.html'), 404
    prefix, slug = token.split('-', 1)
    if not re.match(r'^[a-z0-9]+$', prefix) or not re.match(r'^[a-z0-9]+$', slug):
        return render_template('referral/not_found.html'), 404
    conn = _db()
    program = conn.execute(
        "SELECT * FROM referral_programs WHERE brand_prefix = ? AND active = 1",
        (prefix,)
    ).fetchone()
    if not program:
        conn.close()
        return render_template('referral/not_found.html'), 404
    rep = conn.execute(
        "SELECT slug FROM dealership_team WHERE slug = ? AND dealership_id = ? AND is_active = 1",
        (slug, program['dealership_id'])
    ).fetchone()
    target_slug = rep['slug'] if rep else None
    if not target_slug:
        bd = conn.execute(
            "SELECT slug, team_member_id FROM birddogs WHERE slug = ? AND dealership_id = ?",
            (slug, program['dealership_id'])
        ).fetchone()
        if bd:
            rep_for_bd = conn.execute(
                "SELECT slug FROM dealership_team WHERE id = ?",
                (bd['team_member_id'],)
            ).fetchone()
            target_slug = rep_for_bd['slug'] if rep_for_bd else None
    conn.close()
    if not target_slug:
        return render_template('referral/not_found.html'), 404
    response = redirect(f"https://carsinstock.com/{target_slug}")
    response.set_cookie('mcr_attr', f"{prefix}-{slug}", max_age=90 * 24 * 60 * 60)
    return response
