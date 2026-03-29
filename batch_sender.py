#!/usr/bin/env python3
"""Cron job: processes queued recruitment email batches daily."""
import os, sys, json
from dotenv import load_dotenv
load_dotenv("/home/eddie/carsinstock/.env")
sys.path.insert(0, '/home/eddie/carsinstock')

from app import create_app
from app.models import db
from datetime import datetime, timedelta

app = create_app()

def send_recruitment_email(to_email, subject, html_content):
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To
    try:
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        from_email = Email(email='sales@carsinstock.com', name='CarsInStock')
        message = Mail(from_email=from_email, to_emails=To(to_email), subject=subject, html_content=html_content)
        response = sg.send(message)
        return response.status_code in [200, 201, 202]
    except Exception as e:
        print(f"Error sending to {to_email}: {e}")
        return False

def replace_merge_vars(text, contact):
    text = text.replace("{{First Name}}", contact.first_name or "")
    text = text.replace("{{Last Name}}", contact.last_name or "")
    text = text.replace("{{Dealership Name}}", contact.dealership_name or "")
    text = text.replace("{{City/State}}", contact.city_state or "")
    text = text.replace("{{Custom}}", contact.custom_field or "")
    return text

def build_recruitment_email(body_text, tracking_id):
    import re
    paragraphs = body_text.strip().split("\n\n")
    html_body = ""
    for p in paragraphs:
        p = p.replace("\n", "<br>")
        html_body += '<p style="color:#333;font-size:15px;line-height:1.7;margin-bottom:16px;">' + p + '</p>'
    html_body = re.sub(r'CarsInStock\.com/[-\w]+', lambda m: '<span style="color:#00C851;font-weight:600;">' + m.group(0) + '</span>', html_body)
    unsub = '<p style="color:#94A3B8;font-size:11px;margin-top:12px;"><a href="https://carsinstock.com/recruit/unsubscribe/' + tracking_id + '" style="color:#94A3B8;text-decoration:underline;">Unsubscribe</a></p>'
    return '<div style="max-width:600px;margin:0 auto;font-family:Inter,Arial,sans-serif;"><div style="background:#1E293B;padding:24px;text-align:center;border-radius:12px 12px 0 0;"><h1 style="margin:0;font-size:28px;"><span style="color:white;">Cars</span><span style="color:#00C851;">InStock</span></h1><p style="color:#94A3B8;font-size:14px;margin:6px 0 0;">Real Salespeople. Real Inventory. Real Fresh.</p></div><div style="height:4px;background:linear-gradient(to right,#00C851,#1E293B);"></div><div style="padding:32px 24px;background:white;">' + html_body + '<div style="text-align:center;margin:30px 0;"><a href="https://carsinstock.com/track/click/' + tracking_id + '" style="display:inline-block;background:#00C851;color:white;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600;text-decoration:none;">See the Demo &rarr;</a></div></div><div style="border-top:1px solid #E2E8F0;padding:20px;text-align:center;background:#F8FAFC;border-radius:0 0 12px 12px;"><p style="color:#64748B;font-size:13px;margin:0;">Fresh Cars. Real People.</p><p style="color:#94A3B8;font-size:12px;margin:4px 0 0;">CarsInStock.com</p><p style="color:#94A3B8;font-size:11px;margin-top:8px;">&copy; 2026 CarsInStock LLC. All rights reserved.</p>' + unsub + '</div></div>'


def process_salesperson_blast(batch):
    """Process a salesperson bulk email blast from batch_queue."""
    import json, os, sqlite3
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    from app.models.customer import Customer
    from app.models.vehicle import Vehicle
    from app.utils.email import _build_unsubscribe_footer

    meta = json.loads(batch.body)
    sp_id = meta.get("salesperson_id")
    template_id = str(meta.get("template_id", "1"))
    storefront_url = meta.get("storefront_url", "")
    sp_phone = meta.get("sp_phone", "")
    sp_display_name = meta.get("sp_display_name", "")
    sp_dealership = meta.get("sp_dealership", "")
    vehicle_ids = meta.get("vehicle_ids", [])

    # Pull personal message from email_blasts table
    try:
        _c = sqlite3.connect("/home/eddie/carsinstock/instance/carsinstock.db")
        row = _c.execute("SELECT body FROM email_blasts WHERE salesperson_id=? ORDER BY id DESC LIMIT 1", (sp_id,)).fetchone()
        personal_message = row[0] if row else ""
        _c.close()
    except Exception as e:
        print(f"  Could not load personal message: {e}")
        personal_message = ""

    # Fetch vehicles — always pull live active vehicles at send time
    from datetime import datetime as _now
    vehicles = Vehicle.query.filter_by(
        salesperson_id=sp_id, status='available'
    ).all()
    vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > _now.utcnow()]

    remaining_ids = json.loads(batch.selected_ids)
    this_batch = remaining_ids[:batch.batch_size]
    still_remaining = remaining_ids[batch.batch_size:]

    heroes = {
        "1": ("#1E293B", "#00C851", "This Week's Top Picks"),
        "2": ("#0f172a", "#00C851", "Fresh. In Stock. Right Now."),
        "3": ("#7f1d1d", "#f97316", "These Won't Last Long"),
        "4": ("#1E293B", "#00C851", "I Found Some Cars You Might Love"),
        "5": ("#1E293B", "#00C851", "Before These Are Gone"),
    }
    ctas = {
        "1": "View All My Inventory",
        "2": "See What's New",
        "3": "Claim Your Deal",
        "4": "Let's Talk",
        "5": "View This Week's Specials",
    }
    bg, accent, headline = heroes.get(template_id, heroes["1"])
    cta_label = ctas.get(template_id, "View My Inventory")

    hero_html = (
        f'<div style="background:{bg};padding:28px 20px;text-align:center;border-radius:8px 8px 0 0;">'
        f'<span style="color:{accent};font-size:22px;font-weight:800;letter-spacing:-0.5px;">{headline}</span>'
        f'</div>'
    )

    sp_header = (
        f'<div style="padding:16px;border-bottom:1px solid #f1f5f9;">'
        f'<div style="font-size:16px;font-weight:700;color:#1E293B;">{sp_display_name}</div>'
        f'<div style="font-size:13px;color:#64748B;">{sp_dealership}</div>'
        f'</div>'
    ) if sp_display_name else ""

    vehicle_html = ""
    for v in vehicles:
        price_str = f"${v.price:,.0f}" if v.price else "Contact for price"
        mileage_str = f"{v.mileage:,} miles" if v.mileage else ""
        img_tag = f'<img src="{v.image_url}" style="width:100%;max-height:220px;object-fit:cover;display:block;">' if v.image_url else ""
        vehicle_html += (
            f'<div style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin-bottom:16px;">'
            f'{img_tag}'
            f'<div style="padding:14px;">'
            f'<div style="font-size:16px;font-weight:700;color:#1E293B;margin-bottom:4px;">{v.year} {v.make} {v.model}</div>'
            f'<div style="font-size:18px;font-weight:800;color:#00C851;margin-bottom:4px;">{price_str}</div>'
            f'<div style="font-size:13px;color:#64748B;margin-bottom:12px;">{mileage_str}</div>'
            f'<a href="{storefront_url}" style="display:block;text-align:center;background:#1E293B;color:white;padding:10px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">I\'m Interested</a>'
            f'</div>'
            f'</div>'
        )

    cta_html = (
        f'<div style="text-align:center;margin:24px 0;">'
        f'<a href="{storefront_url}" style="background:#00C851;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">View All My Inventory &rarr;</a>'
        f'</div>'
    )

    phone_line = (
        f'<div style="margin-bottom:8px;">'
        f'<a href="tel:{sp_phone}" style="color:#00C851;text-decoration:none;font-weight:600;">{sp_phone}</a>'
        f'</div>'
    ) if sp_phone else ""

    sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
    sent = 0
    failed = 0

    for cid in this_batch:
        try:
            customer = Customer.query.get(cid)
            if not customer or customer.unsubscribed or not customer.email:
                continue
            first = customer.first_name or customer.email.split("@")[0]
            body_text = personal_message.replace("{{first_name}}", first).replace("{{First_Name}}", first)
            footer_html = _build_unsubscribe_footer(
                customer_id=customer.id,
                salesperson_name=sp_display_name,
                dealership_name=sp_dealership
            )
            html = (
                f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">'
                f'<div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">'
                f'{hero_html}'
                f'{sp_header}'
                f'<div style="padding:16px;">'
                f'<p style="font-size:15px;color:#334155;line-height:1.7;margin:0 0 20px;">{body_text}</p>'
                f'{vehicle_html}'
                f'{cta_html}'
                f'</div>'
                f'<div style="background:#f8fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;">'
                f'{phone_line}'
                f'{footer_html}'
                f'</div>'
                f'</div></div>'
            )
            msg = Mail(
                from_email=(os.environ.get("SENDGRID_FROM_EMAIL", "noreply@carsinstock.com"), sp_display_name + " via CarsInStock"),
                to_emails=customer.email,
                subject=batch.subject,
                html_content=html
            )
            sg.send(msg)
            sent += 1
        except Exception as e:
            print(f"  Failed {cid}: {e}")
            failed += 1

    return sent, failed, still_remaining


with app.app_context():
    import uuid
    from app.models.recruitment_contact import RecruitmentContact

    batches = db.engine.execute(
        db.text("SELECT * FROM batch_queue WHERE status = 'active' AND next_send_at <= :now"),
        {"now": datetime.utcnow()}
    ).fetchall()

    if not batches:
        print(f"[{datetime.utcnow()}] No active batches to process.")

    for batch in batches:
        print(f"[{datetime.utcnow()}] Processing batch {batch.id}, type={batch.template_key}")

        if batch.template_key and batch.template_key.startswith("salesperson_blast_"):
            sent, failed, still_remaining = process_salesperson_blast(batch)
        else:
            remaining_ids = json.loads(batch.selected_ids)
            batch_size = batch.batch_size
            this_batch = remaining_ids[:batch_size]
            still_remaining = remaining_ids[batch_size:]
            sent = 0
            failed = 0
            for cid in this_batch:
                c = RecruitmentContact.query.get(cid)
                if not c:
                    continue
                tracking_id = str(uuid.uuid4())[:12]
                c.tracking_id = tracking_id
                c_subject = replace_merge_vars(batch.subject, c)
                c_body = replace_merge_vars(batch.body, c)
                html = build_recruitment_email(c_body, tracking_id)
                success = send_recruitment_email(c.email, c_subject, html)
                if success:
                    c.status = "sent"
                    c.sent_at = datetime.utcnow()
                    c.template_used = batch.template_key
                    sent += 1
                else:
                    failed += 1

        new_batches_sent = batch.batches_sent + 1

        if still_remaining:
            next_send = datetime.utcnow() + timedelta(days=1)
            db.engine.execute(
                db.text("UPDATE batch_queue SET selected_ids = :sids, batches_sent = :bs, next_send_at = :ns WHERE id = :bid"),
                {"sids": json.dumps(still_remaining), "bs": new_batches_sent, "ns": next_send, "bid": batch.id}
            )
        else:
            db.engine.execute(
                db.text("UPDATE batch_queue SET status = 'complete', batches_sent = :bs WHERE id = :bid"),
                {"bs": new_batches_sent, "bid": batch.id}
            )

        db.session.commit()
        print(f"[{datetime.utcnow()}] Batch {batch.id}: sent {sent}, failed {failed}, remaining {len(still_remaining)}")

        # Blast confirmation receipt to edward@carsinstock.com
        if batch.template_key and batch.template_key.startswith("salesperson_blast_"):
            try:
                from sendgrid import SendGridAPIClient as _SG
                from sendgrid.helpers.mail import Mail as _Mail
                import sqlite3 as _sq2
                _sg = _SG(os.environ.get("SENDGRID_API_KEY"))
                from datetime import timezone, timedelta
                _est = timezone(timedelta(hours=-4))  # EDT (EST is -5, EDT is -4)
                _now_est = datetime.now(tz=_est)
                _now_str = _now_est.strftime("%B %d, %Y at %I:%M %p EST")
                _date_str = _now_est.strftime("%b %d, %Y")
                _spot_rows = []
                _vehicle_count = 0
                try:
                    _c2 = _sq2.connect("/home/eddie/carsinstock/instance/carsinstock.db")
                    _meta2 = json.loads(batch.body)
                    _sp_id2 = _meta2.get("salesperson_id")
                    _cur2 = _c2.cursor()
                    _cur2.execute("SELECT first_name, last_name, email FROM customers WHERE salesperson_id=? AND unsubscribed=0 AND email IS NOT NULL LIMIT 3", (_sp_id2,))
                    _spot_rows = _cur2.fetchall()
                    _vehicle_count = _cur2.execute("SELECT COUNT(*) FROM vehicles WHERE salesperson_id=? AND status='available'", (_sp_id2,)).fetchone()[0]
                    _c2.close()
                except:
                    pass
                _spot_html = "".join([
                    f'<tr><td style="padding:6px 8px;color:#334155;">{r[0] or ""} {r[1] or ""}</td><td style="padding:6px 8px;color:#64748B;">{r[2]}</td></tr>'
                    for r in _spot_rows
                ])
                _confirm_html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
                    <div style="background:#1E293B;padding:20px;border-radius:10px 10px 0 0;text-align:center;">
                        <h2 style="color:white;margin:0;font-size:20px;">Blast Confirmation ✅</h2>
                        <p style="color:#94A3B8;margin:4px 0 0;font-size:13px;">CarsInStock LLC</p>
                    </div>
                    <div style="background:white;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:24px;">
                        <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                            <tr style="background:#F8FAFC;"><td style="padding:10px 8px;color:#64748B;font-size:13px;width:40%;">Date &amp; Time</td><td style="padding:10px 8px;font-weight:600;color:#1E293B;font-size:13px;">{_now_str}</td></tr>
                            <tr><td style="padding:10px 8px;color:#64748B;font-size:13px;">Emails Sent</td><td style="padding:10px 8px;font-weight:700;color:#00C851;font-size:16px;">{sent}</td></tr>
                            <tr style="background:#F8FAFC;"><td style="padding:10px 8px;color:#64748B;font-size:13px;">Failed</td><td style="padding:10px 8px;font-weight:600;color:#EF4444;font-size:13px;">{failed}</td></tr>
                            <tr><td style="padding:10px 8px;color:#64748B;font-size:13px;">Template</td><td style="padding:10px 8px;font-weight:600;color:#1E293B;font-size:13px;">{batch.template_key}</td></tr>
                            <tr style="background:#F8FAFC;"><td style="padding:10px 8px;color:#64748B;font-size:13px;">Vehicles in Email</td><td style="padding:10px 8px;font-weight:600;color:#1E293B;font-size:13px;">{_vehicle_count}</td></tr>
                            <tr><td style="padding:10px 8px;color:#64748B;font-size:13px;">Subject</td><td style="padding:10px 8px;color:#1E293B;font-size:13px;">{batch.subject}</td></tr>
                            <tr style="background:#F8FAFC;"><td style="padding:10px 8px;color:#64748B;font-size:13px;">SendGrid Status</td><td style="padding:10px 8px;font-weight:600;color:#00C851;font-size:13px;">Accepted ✅</td></tr>
                        </table>
                        <h3 style="color:#1E293B;font-size:14px;margin:0 0 8px;">Spot Check — First 3 Recipients</h3>
                        <table style="width:100%;border-collapse:collapse;font-size:13px;border:1px solid #E2E8F0;border-radius:8px;overflow:hidden;">
                            <tr style="background:#F8FAFC;"><th style="padding:8px;text-align:left;color:#64748B;">Name</th><th style="padding:8px;text-align:left;color:#64748B;">Email</th></tr>
                            {_spot_html}
                        </table>
                    </div>
                </div>"""
                _msg = _Mail(
                    from_email=("noreply@carsinstock.com", "CarsInStock"),
                    to_emails="edward@carsinstock.com",
                    subject=f"CarsInStock Blast Confirmation — {_date_str} — {sent} Emails Sent",
                    html_content=_confirm_html
                )
                _sg.send(_msg)
                print(f"[{datetime.utcnow()}] Confirmation receipt sent to edward@carsinstock.com")
            except Exception as _e:
                print(f"[{datetime.utcnow()}] Confirmation email failed: {_e}")

def process_autopilot_schedules():
    """Check blast_schedule and queue any due blasts."""
    import sqlite3, json, pytz
    from datetime import datetime, timezone, timedelta

    est = pytz.timezone("US/Eastern")
    now_utc = datetime.utcnow()
    now_est = datetime.now(est)

    conn = sqlite3.connect("/home/eddie/carsinstock/instance/carsinstock.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    schedules = cur.execute("""
        SELECT * FROM blast_schedule
        WHERE is_active=1 AND next_blast IS NOT NULL AND next_blast <= ?
    """, (now_utc.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()

    for sched in schedules:
        sp_id = sched["salesperson_id"]
        test_mode = sched["test_mode"] if "test_mode" in sched.keys() else 1
        subject = sched["blast_subject"] if "blast_subject" in sched.keys() else "This Week's Top Picks"
        message = sched["weekly_message"] or ""
        template_id = sched["template_id"] or "1"
        batch_size = sched["onboarding_per_day"] or 200

        # Get salesperson info
        sp_row = cur.execute("SELECT * FROM salespeople WHERE salesperson_id=?", (sp_id,)).fetchone()
        if not sp_row:
            continue

        sp_display_name = sp_row["display_name"] or ""
        sp_dealership = sp_row["dealership_name"] or ""
        sp_phone = sp_row["phone"] or ""
        sp_slug = sp_row["profile_url_slug"] or ""
        storefront_url = f"https://carsinstock.com/{sp_slug}"

        # Get active vehicle IDs
        vehicle_ids = [r[0] for r in cur.execute(
            "SELECT id FROM vehicles WHERE salesperson_id=? AND status='available'", (sp_id,)
        ).fetchall()]

        if test_mode:
            # Test mode — send to edward@carsinstock.com only via direct send
            print(f"[{now_utc}] Autopilot TEST for sp_id={sp_id} — sending to edward@carsinstock.com")
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail
                from app.models.vehicle import Vehicle
                from app.utils.email import _build_unsubscribe_footer

                with app.app_context():
                    vehicles = Vehicle.query.filter_by(salesperson_id=sp_id, status='available').all()
                    vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > now_utc]

                    hero_html = f'<div style="background:#1E293B;padding:28px 20px;text-align:center;border-radius:8px 8px 0 0;"><span style="color:#00C851;font-size:22px;font-weight:800;">This Week\'s Top Picks</span></div>'
                    sp_header = f'<div style="padding:16px;border-bottom:1px solid #f1f5f9;"><div style="font-size:16px;font-weight:700;color:#1E293B;">{sp_display_name}</div><div style="font-size:13px;color:#64748B;">{sp_dealership}</div></div>'

                    vehicle_html = ""
                    for v in vehicles:
                        price_str = f"${v.price:,.0f}" if v.price else "Contact for price"
                        mileage_str = f"{v.mileage:,} miles" if v.mileage else ""
                        img_tag = f'<img src="{v.image_url}" style="width:100%;max-height:220px;object-fit:cover;display:block;">' if v.image_url else ""
                        vehicle_html += (
                            f'<div style="border:1px solid #E2E8F0;border-radius:10px;overflow:hidden;margin-bottom:16px;">'
                            f'{img_tag}<div style="padding:14px;">'
                            f'<div style="font-size:16px;font-weight:700;color:#1E293B;margin-bottom:4px;">{v.year} {v.make} {v.model}</div>'
                            f'<div style="font-size:18px;font-weight:800;color:#00C851;margin-bottom:4px;">{price_str}</div>'
                            f'<div style="font-size:13px;color:#64748B;margin-bottom:12px;">{mileage_str}</div>'
                            f'<a href="{storefront_url}" style="display:block;text-align:center;background:#1E293B;color:white;padding:10px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">I\'m Interested</a>'
                            f'</div></div>'
                        )

                    cta_html = f'<div style="text-align:center;margin:24px 0;"><a href="{storefront_url}" style="background:#00C851;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">View All My Inventory &rarr;</a></div>'
                    phone_line = f'<div style="margin-bottom:8px;"><a href="tel:{sp_phone}" style="color:#00C851;text-decoration:none;font-weight:600;">{sp_phone}</a></div>' if sp_phone else ""
                    footer_html = '<div style="border-top:1px solid #e2e8f0;padding:12px 0;text-align:center;"><a href="https://carsinstock.com/disclaimer" style="color:#94A3B8;font-size:11px;text-decoration:underline;">Legal Disclaimer</a></div>'
                    body_text = message.replace("{{first_name}}", "Edward").replace("{{First_Name}}", "Edward")

                    html = (
                        f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">'
                        f'<div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">'
                        f'{hero_html}{sp_header}'
                        f'<div style="padding:16px;"><p style="font-size:15px;color:#334155;line-height:1.7;margin:0 0 20px;">{body_text}</p>'
                        f'{vehicle_html}{cta_html}</div>'
                        f'<div style="background:#f8fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;">{phone_line}{footer_html}</div>'
                        f'</div></div>'
                    )

                    sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
                    msg = Mail(
                        from_email=(os.environ.get("SENDGRID_FROM_EMAIL", "noreply@carsinstock.com"), sp_display_name + " via CarsInStock"),
                        to_emails="edward@carsinstock.com",
                        subject=f"[AUTOPILOT TEST] {subject}",
                        html_content=html
                    )
                    sg.send(msg)
                    print(f"[{now_utc}] Autopilot test email sent to edward@carsinstock.com")
            except Exception as e:
                print(f"[{now_utc}] Autopilot test send failed: {e}")
        else:
            # Live mode — queue to batch_queue for full customer list
            blast_meta = json.dumps({
                "salesperson_id": sp_id,
                "template_id": template_id,
                "storefront_url": storefront_url,
                "vehicle_ids": vehicle_ids,
                "sp_phone": sp_phone,
                "sp_display_name": sp_display_name,
                "sp_dealership": sp_dealership,
                "sp_slug": sp_slug,
                "sp_photo_url": "",
            })
            total_contacts = cur.execute(
                "SELECT COUNT(*) FROM customers WHERE salesperson_id=? AND unsubscribed=0 AND email IS NOT NULL AND email!=''",
                (sp_id,)
            ).fetchone()[0]
            cur.execute("""INSERT INTO batch_queue
                (template_key, subject, body, recipient_filter, selected_ids, batch_size, total_contacts, batches_sent, total_batches, status, next_send_at)
                VALUES (?,?,?,?,?,?,?,0,?,\'active\',datetime(\'now\'))""",
                (f"salesperson_blast_{template_id}", subject, blast_meta, "all",
                 json.dumps([r[0] for r in cur.execute("SELECT id FROM customers WHERE salesperson_id=? AND unsubscribed=0 AND email IS NOT NULL AND email!=''", (sp_id,)).fetchall()]),
                 batch_size, total_contacts, 1)
            )
            print(f"[{now_utc}] Autopilot queued {total_contacts} recipients for sp_id={sp_id}")

        # Calculate next Sunday 9AM EST
        import pytz as _pytz
        _est = _pytz.timezone("US/Eastern")
        _now_est = datetime.now(_est)
        _days = (6 - _now_est.weekday()) % 7 or 7
        _next = (_now_est + timedelta(days=_days)).replace(hour=9, minute=0, second=0, microsecond=0)
        _next_utc = _next.astimezone(pytz.utc).replace(tzinfo=None)
        cur.execute("UPDATE blast_schedule SET next_blast=?, last_updated=? WHERE salesperson_id=?",
            (_next_utc.strftime("%Y-%m-%d %H:%M:%S"), now_utc.strftime("%Y-%m-%d %H:%M:%S"), sp_id))

    conn.commit()
    conn.close()


# Run autopilot check
try:
    process_autopilot_schedules()
except Exception as e:
    print(f"[{datetime.utcnow()}] Autopilot processor error: {e}")
