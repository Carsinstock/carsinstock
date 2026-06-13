"""Shared birddog creation logic.

Both the public /join/<rep_slug>/submit flow (referral blueprint) and
the rep-side /api/birddog/signup endpoint (salesperson blueprint) call
create_birddog() here so birddogs from either path are identical:
real slug, real token, multi-tenant dealership_id, idempotent on
phone + team_member_id.
"""

import re
import secrets


def _slugify(name):
    """Lowercase-alphanumeric slug from a name. 'John Smith' -> 'johnsmith'."""
    base = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    return base or 'birddog'


def _unique_slug(conn, base, dealership_id):
    """Dedup slug within a dealership: johnsmith -> johnsmith2 -> johnsmith3..."""
    slug = base
    n = 1
    while conn.execute(
        "SELECT 1 FROM birddogs WHERE slug = ? AND dealership_id = ?",
        (slug, dealership_id)
    ).fetchone():
        n += 1
        slug = f"{base}{n}"
    return slug


def create_birddog(conn, *, team_member_id, name, phone, email='', dealership_id=1):
    """Create a birddog under the given rep, or return the existing row if
    phone+team_member_id already matches. Caller manages connection lifecycle.

    Returns a dict: id, name, phone, email, slug, token, team_member_id,
    dealership_id, existing (True if returned existing row, False if newly created).
    """
    existing = conn.execute(
        "SELECT id, name, phone, email, slug, token, team_member_id, dealership_id "
        "FROM birddogs WHERE phone = ? AND team_member_id = ?",
        (phone, team_member_id)
    ).fetchone()
    if existing:
        d = dict(existing)
        d['existing'] = True
        return d

    slug = _unique_slug(conn, _slugify(name), dealership_id)
    token = secrets.token_urlsafe(16)
    cur = conn.execute(
        "INSERT INTO birddogs "
        "(team_member_id, name, email, phone, token, slug, dealership_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (team_member_id, name, email, phone, token, slug, dealership_id)
    )
    conn.commit()
    return {
        'id': cur.lastrowid,
        'name': name,
        'phone': phone,
        'email': email,
        'slug': slug,
        'token': token,
        'team_member_id': team_member_id,
        'dealership_id': dealership_id,
        'existing': False,
    }

def attribute_lead_to_birddog(lead_id, customer_name, customer_email, customer_phone, member, mcr_attr_cookie):
    """Issue 2 fix: read mcr_attr cookie, insert birddog_referrals row. Returns birddog dict if attributed (rep-owned), else None."""
    if not mcr_attr_cookie or '-' not in mcr_attr_cookie: return None
    import sqlite3
    try:
        bd_slug = mcr_attr_cookie.partition('-')[2]
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        conn.row_factory = sqlite3.Row
        bd = conn.execute("SELECT id, name, team_member_id FROM birddogs WHERE slug=? AND dealership_id=?", (bd_slug, member['dealership_id'])).fetchone()
        result = None
        if bd and bd['team_member_id'] == member['id']:
            conn.execute("INSERT INTO birddog_referrals (birddog_id, team_member_id, buyer_name, buyer_phone, buyer_email, lead_id, status, dealership_id, attribution_source) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 'cookie')", (bd['id'], bd['team_member_id'], customer_name, customer_phone, customer_email, lead_id, member['dealership_id']))
            conn.commit()
            result = dict(bd)
        conn.close()
        return result
    except Exception as e:
        print(f"attribute_lead_to_birddog error: {e}")
        return None
