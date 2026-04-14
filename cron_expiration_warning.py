#!/usr/bin/env python3
"""Cron job: Send expiration warning emails to dealership team members for vehicles expiring within 48 hours."""
import sys
sys.path.insert(0, '/home/eddie/carsinstock')
from app import create_app
from datetime import datetime, timedelta
import sqlite3
import os

app = create_app()

with app.app_context():
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To

    now = datetime.utcnow()
    warning_cutoff = now + timedelta(hours=48)

    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row

    vehicles = conn.execute("""
        SELECT v.id, v.year, v.make, v.model, v.price, v.expires_at, v.expiration_warning_sent,
               t.name as rep_name, t.email as rep_email, t.slug as rep_slug
        FROM vehicles v
        JOIN dealership_team t ON v.pick_user_id = t.id
        WHERE v.status = "available"
        AND v.expires_at > ?
        AND v.expires_at <= ?
        AND (v.expiration_warning_sent = 0 OR v.expiration_warning_sent IS NULL)
        AND t.is_active = 1
        AND t.email IS NOT NULL
    """, (now, warning_cutoff)).fetchall()

    print(f"[{now}] Found {len(vehicles)} vehicles expiring within 48 hours")

    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))

    for v in vehicles:
        expires_dt = datetime.strptime(str(v["expires_at"]).split(".")[0], "%Y-%m-%d %H:%M:%S")
        days_left = max(0, int((expires_dt - now).total_seconds() / 86400))
        badge_color = "#DC2626" if days_left <= 1 else "#F97316"
        first_name = v["rep_name"].split()[0]

        html = f"""<div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
            <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;">
                <span style="color:white;font-weight:400;font-size:18px;">Cars</span><span style="color:#00C851;font-weight:700;font-size:18px;"> IN STOCK</span>
            </div>
            <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                <div style="background:{badge_color};color:white;border-radius:8px;padding:8px 16px;display:inline-block;font-weight:700;font-size:14px;margin-bottom:16px;">
                    ⏰ {days_left} Day{"s" if days_left != 1 else ""} Left
                </div>
                <h2 style="color:#1E293B;font-size:20px;margin:0 0 8px;">{v["year"]} {v["make"]} {v["model"]}</h2>
                <p style="color:#475569;font-size:15px;margin:0 0 20px;">
                    Hey {first_name} — your listing is expiring soon. Log in and tap Renew to keep it live on your storefront.
                </p>
                <a href="https://carsinstock.com/sp-dashboard" style="background:#00C851;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;margin-bottom:16px;">
                    🔄 Renew My Listing →
                </a>
                <p style="color:#94A3B8;font-size:12px;margin:16px 0 0;">— The CarsInStock Team</p>
            </div>
        </div>"""

        try:
            msg = Mail(
                from_email=Email("sales@carsinstock.com", "CarsInStock"),
                to_emails=To(v["rep_email"]),
                subject=f"⏰ {v['year']} {v['make']} {v['model']} expires in {days_left} day{'s' if days_left != 1 else ''} — renew now",
                html_content=html
            )
            sg.send(msg)
            conn.execute("UPDATE vehicles SET expiration_warning_sent=1 WHERE id=?", (v["id"],))
            conn.commit()
            print(f"  Alert sent: {v['year']} {v['make']} {v['model']} to {v['rep_email']}")
        except Exception as e:
            print(f"  Error for vehicle {v['id']}: {e}")

    conn.close()
    print(f"Done. {len(vehicles)} alerts processed.")
