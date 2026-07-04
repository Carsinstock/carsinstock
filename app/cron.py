import sqlite3, os, logging
from datetime import datetime, timedelta
from pytz import timezone

logger = logging.getLogger(__name__)
DB_PATH = '/home/eddie/carsinstock/instance/carsinstock.db'
EST = timezone('US/Eastern')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.row_factory = sqlite3.Row
    return conn

def send_blast_email(sp_data, customer, subject, html):
    import sendgrid, os
    from sendgrid.helpers.mail import Mail
    try:
        sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
        msg = Mail(
            from_email=(os.environ.get('SENDGRID_FROM_EMAIL', 'sales@carsinstock.com'), sp_data['display_name'] + ' via CarsInStock'),
            to_emails=customer['email'],
            subject=subject,
            html_content=html
        )
        sg.send(msg)
        return True
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Phase 2.6 — blast guardrails. One layer both blast paths call.
#   MAX_BLAST_PER_RUN : hard per-run ceiling; over it -> halt, no send.
#   BLAST_DRY_RUN     : env flag; runs full logic, sends nothing, writes nothing.
#   QUARANTINE_SOURCE : the CyberLeads population, walled off from all blasts.
# ─────────────────────────────────────────────────────────────
MAX_BLAST_PER_RUN = 500
BLAST_DRY_RUN = os.environ.get('BLAST_DRY_RUN') == '1'
QUARANTINE_SOURCE = 'cyberleads_quarantine'

# Dry-run counter (reset at the top of each blast function).
_DRY_RUN_WOULD_SEND = 0

def _reset_dry_counter():
    global _DRY_RUN_WOULD_SEND
    _DRY_RUN_WOULD_SEND = 0

def _halt_and_alert(sp_id, reason, off_target=0, total=0):
    """Log + best-effort email. NEVER raises — a broken alert must not crash the halt.
    Returns False so callers can `if _halt_and_alert(...): continue` cleanly."""
    line = f"ALERT: blast halted sp={sp_id} — {reason} — off_target={off_target} of total={total}"
    logger.error(line)
    print(line)
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
        sg.send(Mail(
            from_email='noreply@carsinstock.com',
            to_emails='edward@carsinstock.com',
            subject=f'[BLAST HALT] sp={sp_id} — {reason}',
            html_content=f'<p style="font-family:Arial">{line}</p>'
            f'<p style="color:#64748B;font-size:12px">Off-target recipients: {off_target} of {total}. '
            f'Run halted before any send. No emails went out for this salesperson.</p>'
        ))
    except Exception as _e:
        logger.error(f"halt-alert email failed (non-fatal, halt still enforced): {_e}")
    return False

def _guarded_send(sp_data, customer, subject, html):
    """Single send chokepoint. Dry-run: count and report success WITHOUT sending.
    Live: delegate to the real send. Callers must still gate blast_log on BLAST_DRY_RUN."""
    global _DRY_RUN_WOULD_SEND
    if BLAST_DRY_RUN:
        _DRY_RUN_WOULD_SEND += 1
        return True
    return send_blast_email(sp_data, customer, subject, html)

def build_blast_html(sp_data, customer, message, template_id, storefront_url, vehicles, unsubscribe_html):
    first = customer['first_name'] or customer['email'].split('@')[0]
    personal_body = message.replace('{{first_name}}', first).replace('{{First_Name}}', first)
    phone_line = f'<div><a href="tel:{sp_data["phone"]}" style="color:#00C851;text-decoration:none;">{sp_data["phone"]}</a></div>' if sp_data.get('phone') else ''

    heroes = {
        '1': ('#1E293B', '#00C851', "This Week's Top Picks"),
        '2': ('#0f172a', '#00C851', "Fresh. In Stock. Right Now."),
        '3': ('#7f1d1d', '#f97316', "These Won't Last Long"),
        '4': ('#1E293B', '#00C851', "I Found Some Cars You Might Love"),
        '5': ('#1E293B', '#00C851', "Before These Are Gone"),
    }
    bg, accent, headline = heroes.get(str(template_id), heroes['1'])
    hero_html = f'<div style="background:{bg};padding:28px 20px;text-align:center;border-radius:8px 8px 0 0;"><span style="color:{accent};font-size:22px;font-weight:800;">{headline}</span></div>'

    profile_photo = f'<img src="{sp_data["profile_photo"]}" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:3px solid #00C851;" />' if sp_data.get('profile_photo') else ''
    profile_html = f'<div style="text-align:center;padding:16px 0;">{profile_photo}<div style="font-size:16px;font-weight:700;color:#1E293B;margin-top:8px;">{sp_data["display_name"]}</div><div style="font-size:13px;color:#64748B;">{sp_data.get("dealership_name","")}</div></div>'

    vehicle_html = ''
    for v in vehicles:
        price = f'${v["price"]:,.0f}' if v['price'] else 'Contact for price'
        mileage = f'{v["mileage"]:,} miles' if v.get('mileage') else ''
        img_tag = f'<img src="{v["image_url"]}" style="width:100%;height:200px;object-fit:cover;display:block;border-radius:8px 8px 0 0;">' if v.get('image_url') else ''
        vehicle_html += (
            f'<div style="background:#ffffff;border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
            f'{img_tag}'
            f'<div style="padding:16px;">'
            f'<div style="font-size:17px;font-weight:700;color:#1E293B;margin-bottom:6px;line-height:1.3;">{v["year"]} {v["make"]} {v["model"]}</div>'
            f'<div style="font-size:20px;font-weight:800;color:#00C851;margin-bottom:4px;">{price}</div>'
            f'<div style="font-size:13px;color:#64748B;margin-bottom:16px;">{mileage}</div>'
            f'<a href="{storefront_url}" style="display:block;width:100%;box-sizing:border-box;text-align:center;background:#1E293B;color:#ffffff;padding:13px 0;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;letter-spacing:0.3px;">I\'m Interested</a>'
            f'</div></div>'
        )

    ctas = {'1':'View All My Inventory →','2':'See What\'s New →','3':'Claim Your Deal →','4':'Let\'s Talk →','5':'View This Week\'s Specials →'}
    cta_label = ctas.get(str(template_id), 'View My Inventory →')
    cta_html = f'<div style="text-align:center;margin:24px 0;"><a href="{storefront_url}" style="background:#00C851;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap;display:inline-block;">{cta_label}</a></div>'

    url_box = f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:8px 14px;margin:0 0 8px;"><span style="font-size:13px;color:#64748B;">🌐</span><a href="{storefront_url}" style="font-size:13px;font-weight:600;color:#1E293B;text-decoration:none;margin-left:6px;">{storefront_url.replace("https://","")}</a></div>'
    referral_box = f'<div style="background:#f0fdf4;border:1px solid #00C851;border-radius:8px;padding:8px 14px;margin:0 0 12px;"><span style="font-size:12px;font-weight:600;color:#1E293B;">🤝 Know someone? If they buy, they get a deal — and you receive a Thank You gift.</span><a href="{storefront_url}" style="display:inline-block;background:#00C851;color:white;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:700;text-decoration:none;margin-left:8px;white-space:nowrap;">Share →</a></div>'

    return f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">
    <div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
        {hero_html}{profile_html}
        <div style="padding:0 16px 8px;">
            <p style="font-size:15px;color:#334155;line-height:1.7;margin:0 0 16px;">{personal_body}</p>
            {vehicle_html}{cta_html}{url_box}{referral_box}
        </div>
        <div style="background:#f8fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;font-size:13px;color:#64748B;">
            {phone_line}{unsubscribe_html}
        </div>
    </div></div>"""

def run_onboarding_blast(app):
    """Daily 8AM — add next N customers to active list and send their first blast"""
    with app.app_context():
        conn = get_db()
        try:
            schedules = conn.execute('SELECT * FROM blast_schedule WHERE is_active=1').fetchall()
            _abort_run = False
            for sched in schedules:
                if _abort_run:
                    break
                sp_id = sched['salesperson_id']
                per_day = sched['onboarding_per_day'] or 200
                message = sched['weekly_message'] or 'Hey {{first_name}}, check out my latest picks this week!'
                template_id = sched['template_id'] or '1'

                sp = conn.execute('SELECT * FROM salespeople WHERE salesperson_id=?', (sp_id,)).fetchone()
                if not sp:
                    continue

                # Get onboarding position
                pos = conn.execute('SELECT last_customer_id FROM blast_onboard_position WHERE salesperson_id=?', (sp_id,)).fetchone()
                last_id = pos['last_customer_id'] if pos else 0

                # Get next batch of customers not yet onboarded
                already_sent = conn.execute('SELECT customer_id FROM blast_log WHERE salesperson_id=?', (sp_id,)).fetchall()
                sent_ids = {r['customer_id'] for r in already_sent}

                customers = conn.execute(
                    'SELECT * FROM customers WHERE salesperson_id=? AND unsubscribed=0 AND source != "cyberleads_quarantine" AND email IS NOT NULL AND email != "" AND id > ? ORDER BY id LIMIT ?',
                    (sp_id, last_id, per_day)
                ).fetchall()

                if not customers:
                    logger.info(f"Onboarding complete for salesperson {sp_id}")
                    continue

                storefront_url = f"https://carsinstock.com/{sp['profile_url_slug']}"
                vehicles = conn.execute(
                    'SELECT * FROM vehicles WHERE salesperson_id=? AND status="available" ORDER BY ' + (
                        'price ASC' if sp['vehicle_sort_order'] == 'price_low' else
                        'price DESC' if sp['vehicle_sort_order'] == 'price_high' else
                        'created_at DESC'
                    ) + ''
                    , (sp_id,)
                ).fetchall()

                # ── Phase 2.6 guardrails: cap (skip sp) + source tripwire (abort run) ──
                _reset_dry_counter()
                if len(customers) > MAX_BLAST_PER_RUN:
                    _halt_and_alert(sp_id, 'cap exceeded (onboarding)', off_target=0, total=len(customers))
                    continue  # skip THIS salesperson; local failure, others proceed
                _off = sum(1 for c in customers if (c['source'] if 'source' in c.keys() else None) == QUARANTINE_SOURCE)
                if _off:
                    _halt_and_alert(sp_id, 'QUARANTINE BREACH (onboarding) — wall failed', off_target=_off, total=len(customers))
                    _abort_run = True
                    break  # abort ENTIRE run; systemic failure. finally: still closes conn.
                sent = 0
                last_sent_id = last_id
                for customer in customers:
                    if customer['id'] in sent_ids:
                        continue
                    slug = sp['profile_url_slug']
                    cid = customer['id']
                    unsubscribe_html = f'<p style="font-size:11px;color:#94A3B8;margin-top:8px;"><a href="https://carsinstock.com/storefront/unsubscribe/{slug}?cid={cid}" style="color:#94A3B8;">Unsubscribe</a></p>'
                    html = build_blast_html(dict(sp), dict(customer), message, template_id, storefront_url, [dict(v) for v in vehicles], unsubscribe_html)
                    subject = f"{sp['display_name']} — This Week's Top Picks"
                    if _guarded_send(dict(sp), dict(customer), subject, html):
                        if not BLAST_DRY_RUN:
                            conn.execute('INSERT INTO blast_log (salesperson_id, customer_id, blast_type) VALUES (?,?,?)', (sp_id, customer['id'], 'onboarding'))
                        sent += 1
                    last_sent_id = customer['id']

                # Update position (skip in dry-run — must not poison the next real run)
                if not BLAST_DRY_RUN:
                    conn.execute('INSERT OR REPLACE INTO blast_onboard_position (salesperson_id, last_customer_id, updated_at) VALUES (?,?,?)',
                        (sp_id, last_sent_id, datetime.utcnow()))
                    conn.commit()
                if BLAST_DRY_RUN:
                    logger.info(f"[DRY-RUN] onboarding sp={sp_id}: WOULD send {_DRY_RUN_WOULD_SEND} (cap={MAX_BLAST_PER_RUN}); wrote nothing")
                else:
                    logger.info(f"Onboarding blast: sent {sent} emails for salesperson {sp_id}")
        finally:
            conn.close()

def run_weekly_blast(app):
    """Sunday 9AM EST — blast all active subscribers, staggered over 4 hours"""
    import time
    with app.app_context():
        conn = get_db()
        try:
            schedules = conn.execute('SELECT * FROM blast_schedule WHERE is_active=1').fetchall()
            _abort_run = False
            for sched in schedules:
                if _abort_run:
                    break
                sp_id = sched['salesperson_id']
                message = sched['weekly_message'] or 'Hey {{first_name}}, check out my latest picks this week!'
                template_id = sched['template_id'] or '1'

                sp = conn.execute('SELECT * FROM salespeople WHERE salesperson_id=?', (sp_id,)).fetchone()
                if not sp:
                    continue

                # Get all active subscribers (ever received onboarding blast)
                onboarded = conn.execute(
                    'SELECT DISTINCT customer_id FROM blast_log WHERE salesperson_id=? AND blast_type="onboarding" AND DATE(sent_at) < DATE("now")',
                    (sp_id,)
                ).fetchall()
                onboarded_ids = [r['customer_id'] for r in onboarded]
                if not onboarded_ids:
                    continue

                customers = conn.execute(
                    f'SELECT * FROM customers WHERE id IN ({",".join("?" for _ in onboarded_ids)}) AND unsubscribed=0 AND source != "cyberleads_quarantine" AND email IS NOT NULL AND email != ""',
                    onboarded_ids
                ).fetchall()

                if not customers:
                    continue

                storefront_url = f"https://carsinstock.com/{sp['profile_url_slug']}"
                vehicles = conn.execute(
                    'SELECT * FROM vehicles WHERE salesperson_id=? AND status="available" ORDER BY ' + (
                        'price ASC' if sp['vehicle_sort_order'] == 'price_low' else
                        'price DESC' if sp['vehicle_sort_order'] == 'price_high' else
                        'created_at DESC'
                    ) + ''
                    , (sp_id,)
                ).fetchall()

                total = len(customers)
                # ── Phase 2.6 guardrails: cap (skip sp) + source tripwire (abort run) ──
                _reset_dry_counter()
                if total > MAX_BLAST_PER_RUN:
                    _halt_and_alert(sp_id, 'cap exceeded (weekly)', off_target=0, total=total)
                    continue  # skip THIS salesperson; local failure, others proceed
                _off = sum(1 for c in customers if (c['source'] if 'source' in c.keys() else None) == QUARANTINE_SOURCE)
                if _off:
                    _halt_and_alert(sp_id, 'QUARANTINE BREACH (weekly) — wall failed', off_target=_off, total=total)
                    _abort_run = True
                    break  # abort ENTIRE run; systemic failure. finally: still closes conn.
                # Stagger over 4 hours = 14400 seconds (skipped entirely in dry-run)
                delay_per_email = 14400 / total if total > 0 else 0

                sent = 0
                for i, customer in enumerate(customers):
                    if i > 0 and delay_per_email > 0 and not BLAST_DRY_RUN:
                        time.sleep(min(delay_per_email, 2))  # cap at 2s per email max
                    slug = sp['profile_url_slug']
                    cid = customer['id']
                    unsubscribe_html = f'<p style="font-size:11px;color:#94A3B8;margin-top:8px;"><a href="https://carsinstock.com/storefront/unsubscribe/{slug}?cid={cid}" style="color:#94A3B8;">Unsubscribe</a></p>'
                    html = build_blast_html(dict(sp), dict(customer), message, template_id, storefront_url, [dict(v) for v in vehicles], unsubscribe_html)
                    subject = f"{sp['display_name']} — This Week's Top Picks"
                    if _guarded_send(dict(sp), dict(customer), subject, html):
                        if not BLAST_DRY_RUN:
                            conn.execute('INSERT INTO blast_log (salesperson_id, customer_id, blast_type) VALUES (?,?,?)', (sp_id, customer['id'], 'weekly'))
                            if sent % 50 == 0:
                                conn.commit()
                        sent += 1

                if not BLAST_DRY_RUN:
                    conn.commit()
                if BLAST_DRY_RUN:
                    logger.info(f"[DRY-RUN] weekly sp={sp_id}: WOULD send {_DRY_RUN_WOULD_SEND} of {total} (cap={MAX_BLAST_PER_RUN}); wrote nothing")
                else:
                    logger.info(f"Weekly blast: sent {sent}/{total} emails for salesperson {sp_id}")
        finally:
            conn.close()

def init_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = BackgroundScheduler(timezone='US/Eastern')
    # Daily onboarding at 8AM EST
    scheduler.add_job(
        func=lambda: run_onboarding_blast(app),
        trigger=CronTrigger(hour=8, minute=0, timezone='US/Eastern'),
        id='onboarding_blast',
        replace_existing=True
    )
    # Weekly blast Sunday 9AM EST
    scheduler.add_job(
        func=lambda: run_weekly_blast(app),
        trigger=CronTrigger(day_of_week='sun', hour=9, minute=0, timezone='US/Eastern'),
        id='weekly_blast',
        replace_existing=True
    )
    scheduler.start()
    logger.info("Blast scheduler started")
    return scheduler
