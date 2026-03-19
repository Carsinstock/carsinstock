import sqlite3, os, logging
from datetime import datetime, timedelta
from pytz import timezone

logger = logging.getLogger(__name__)
DB_PATH = '/home/eddie/carsinstock/instance/carsinstock.db'
EST = timezone('US/Eastern')

def get_db():
    conn = sqlite3.connect(DB_PATH)
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
    for v in vehicles[:6]:
        price = f'${v["price"]:,.0f}' if v['price'] else ''
        mileage = f'<br><span style="color:#666;font-size:13px;">{v["mileage"]:,} miles</span>' if v.get('mileage') else ''
        vehicle_html += f'<div style="border:1px solid #eee;border-radius:8px;padding:12px;margin-bottom:10px;background:#fafafa;"><strong style="font-size:15px;color:#1E293B;">{v["year"]} {v["make"]} {v["model"]}</strong><br><span style="color:#00C851;font-weight:700;font-size:16px;">{price}</span>{mileage}</div>'

    ctas = {'1':'View All My Inventory →','2':'See What\'s New →','3':'Claim Your Deal →','4':'Let\'s Talk →','5':'View This Week\'s Specials →'}
    cta_label = ctas.get(str(template_id), 'View My Inventory →')
    cta_html = f'<div style="text-align:center;margin:24px 0;"><a href="{storefront_url}" style="background:#00C851;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap;display:inline-block;">{cta_label}</a></div>'

    url_box = f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:8px 14px;margin:0 0 8px;"><span style="font-size:13px;color:#64748B;">🌐</span><a href="{storefront_url}" style="font-size:13px;font-weight:600;color:#1E293B;text-decoration:none;margin-left:6px;">{storefront_url.replace("https://","")}</a></div>'
    referral_box = f'<div style="background:#f0fdf4;border:1px solid #00C851;border-radius:8px;padding:8px 14px;margin:0 0 12px;"><span style="font-size:12px;font-weight:600;color:#1E293B;">🤝 Know someone? If they buy, they get a deal — and you get $100.</span><a href="{storefront_url}" style="display:inline-block;background:#00C851;color:white;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:700;text-decoration:none;margin-left:8px;white-space:nowrap;">Share →</a></div>'

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
            for sched in schedules:
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
                    'SELECT * FROM customers WHERE salesperson_id=? AND unsubscribed=0 AND email IS NOT NULL AND email != "" AND id > ? ORDER BY id LIMIT ?',
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
                    ) + ' LIMIT 6',
                    (sp_id,)
                ).fetchall()

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
                    if send_blast_email(dict(sp), dict(customer), subject, html):
                        conn.execute('INSERT INTO blast_log (salesperson_id, customer_id, blast_type) VALUES (?,?,?)', (sp_id, customer['id'], 'onboarding'))
                        sent += 1
                    last_sent_id = customer['id']

                # Update position
                conn.execute('INSERT OR REPLACE INTO blast_onboard_position (salesperson_id, last_customer_id, updated_at) VALUES (?,?,?)',
                    (sp_id, last_sent_id, datetime.utcnow()))
                conn.commit()
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
            for sched in schedules:
                sp_id = sched['salesperson_id']
                message = sched['weekly_message'] or 'Hey {{first_name}}, check out my latest picks this week!'
                template_id = sched['template_id'] or '1'

                sp = conn.execute('SELECT * FROM salespeople WHERE salesperson_id=?', (sp_id,)).fetchone()
                if not sp:
                    continue

                # Get all active subscribers (ever received onboarding blast)
                onboarded = conn.execute(
                    'SELECT DISTINCT customer_id FROM blast_log WHERE salesperson_id=? AND blast_type="onboarding"',
                    (sp_id,)
                ).fetchall()
                onboarded_ids = [r['customer_id'] for r in onboarded]
                if not onboarded_ids:
                    continue

                customers = conn.execute(
                    f'SELECT * FROM customers WHERE id IN ({",".join("?" for _ in onboarded_ids)}) AND unsubscribed=0 AND email IS NOT NULL AND email != ""',
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
                    ) + ' LIMIT 6',
                    (sp_id,)
                ).fetchall()

                total = len(customers)
                # Stagger over 4 hours = 14400 seconds
                delay_per_email = 14400 / total if total > 0 else 0

                sent = 0
                for i, customer in enumerate(customers):
                    if i > 0 and delay_per_email > 0:
                        time.sleep(min(delay_per_email, 2))  # cap at 2s per email max
                    slug = sp['profile_url_slug']
                    cid = customer['id']
                    unsubscribe_html = f'<p style="font-size:11px;color:#94A3B8;margin-top:8px;"><a href="https://carsinstock.com/storefront/unsubscribe/{slug}?cid={cid}" style="color:#94A3B8;">Unsubscribe</a></p>'
                    html = build_blast_html(dict(sp), dict(customer), message, template_id, storefront_url, [dict(v) for v in vehicles], unsubscribe_html)
                    subject = f"{sp['display_name']} — This Week's Top Picks"
                    if send_blast_email(dict(sp), dict(customer), subject, html):
                        conn.execute('INSERT INTO blast_log (salesperson_id, customer_id, blast_type) VALUES (?,?,?)', (sp_id, customer['id'], 'weekly'))
                        sent += 1
                        if sent % 50 == 0:
                            conn.commit()

                conn.commit()
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
