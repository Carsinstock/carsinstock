"""MyCarReferral routes — public-facing referral platform.

Mounted internally at /mcr. Users on mycarreferral.com see clean paths
(e.g. mycarreferral.com/login) via host-header middleware.

Pine Belt pilot: dealership_id=1, brand_prefix='pbu'.
"""
import re
import sqlite3
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
    return render_template('referral/signup_landing.html', rep=dict(rep))


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
                error='No account found with that phone number. Sign up through a referral link first.'
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
    conn.close()
    referrals = [dict(r) for r in refs]
    pending_count = sum(1 for r in referrals if r['status'] in ('pending', 'submitted'))
    closed_count = sum(1 for r in referrals if r['status'] == 'sold')
    return render_template(
        'referral/dashboard.html',
        birddog=dict(bd),
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
