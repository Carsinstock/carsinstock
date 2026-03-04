#!/usr/bin/env python3
"""Cron job: processes queued recruitment email batches daily."""
import os, sys, json
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
    return '<div style="max-width:600px;margin:0 auto;font-family:Inter,Arial,sans-serif;"><div style="background:#1E293B;padding:24px;text-align:center;border-radius:12px 12px 0 0;"><h1 style="margin:0;font-size:28px;"><span style="color:white;">Cars</span><span style="color:#00C851;">InStock</span></h1><p style="color:#94A3B8;font-size:14px;margin:6px 0 0;">Real Salespeople. Real Inventory. Real Fresh.</p></div><div style="height:4px;background:linear-gradient(to right,#00C851,#1E293B);"></div><div style="padding:32px 24px;background:white;">' + html_body + '<div style="text-align:center;margin:30px 0;"><a href="https://carsinstock.com/track/click/' + tracking_id + '" style="display:inline-block;background:#00C851;color:white;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600;text-decoration:none;">See the Demo &rarr;</a></div></div><div style="border-top:1px solid #E2E8F0;padding:20px;text-align:center;background:#F8FAFC;border-radius:0 0 12px 12px;"><p style="color:#64748B;font-size:13px;margin:0;">Fresh Cars. Real People.</p><p style="color:#94A3B8;font-size:12px;margin:4px 0 0;">CarsInStock.com</p>' + unsub + '</div></div>'

with app.app_context():
    import uuid
    from app.models.recruitment_contact import RecruitmentContact

    batches = db.engine.execute(
        db.text("SELECT * FROM batch_queue WHERE status = 'active' AND next_send_at <= :now"),
        {"now": datetime.utcnow()}
    ).fetchall()

    if not batches:
        print(f"[{datetime.utcnow()}] No active batches to process.")
        sys.exit(0)

    for batch in batches:
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
