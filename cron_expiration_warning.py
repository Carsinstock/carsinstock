#!/usr/bin/env python3
"""Cron job: Send expiration warning emails to dealership team members for vehicles expiring within 48 hours."""
import sys
sys.path.insert(0, '/home/eddie/carsinstock')
from app import create_app
from datetime import datetime, timedelta
import sqlite3
import os
from dotenv import load_dotenv
load_dotenv('/home/eddie/carsinstock/.env')

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

    # ZERO-WORK ALARM (calibrated): 0 in the 48h window is USUALLY correct.
    # But 0 in 48h AND 0 in the next 14 days means the query is probably broken --
    # Pine Belt always has cars on a 7-day clock. Silence is not success.
    if len(vehicles) == 0:
        _horizon = conn.execute("""
            SELECT COUNT(*) FROM vehicles v
            JOIN dealership_team t ON v.pick_user_id = t.id
            WHERE v.status = "available" AND v.expires_at > ?
              AND t.is_active = 1 AND t.email IS NOT NULL
        """, (now,)).fetchone()[0]
        if _horizon == 0:
            bar = "!" * 70
            print(bar, flush=True)
            print("!!! CRITICAL: 0 vehicles in the 48h window AND 0 upcoming at all.", flush=True)
            print("!!! Either every rep's inventory is expired/empty, or the query is broken.", flush=True)
            print("!!! This cron did NO WORK. That is almost certainly wrong.", flush=True)
            print(bar, flush=True)
            try:
                _k2 = os.environ.get('SENDGRID_API_KEY')
                if _k2:
                    _sg2 = SendGridAPIClient(_k2)
                    _m2 = Mail(from_email=Email("sales@carsinstock.com", "CarsInStock ALERT"),
                               to_emails=To("ecastillo@pinebeltauto.com"),
                               subject="[CRITICAL] Expiry cron did zero work - query may be broken",
                               html_content="<h2 style='color:#DC2626'>Expiry warning cron: ZERO WORK</h2>"
                                            "<p>0 vehicles in the 48h window, and 0 upcoming at all. "
                                            "Either all rep inventory is gone, or the recipient query is broken. "
                                            "Nobody was warned about anything.</p>")
                    _sg2.send(_m2)
                    print("!!! operator alert sent", flush=True)
            except Exception as _e2:
                print(f"!!! ALERT ALSO FAILED: {_e2}", flush=True)
            conn.close()
            sys.exit(1)
        else:
            print(f"    (0 in window is normal - {_horizon} vehicles upcoming beyond 48h)", flush=True)

    _key = os.environ.get('SENDGRID_API_KEY')
    if not _key:
        print("!!! CRITICAL: SENDGRID_API_KEY not set — aborting. NO WARNINGS SENT.", flush=True)
        sys.exit(1)
    sg = SendGridAPIClient(_key)

    _failures = []
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
            _failures.append(f"vehicle {v['id']} ({v['year']} {v['make']} {v['model']}) -> {v['rep_email']}: {e}")
            print(f"  Error for vehicle {v['id']}: {e}")

    conn.close()

    if _failures:
        banner = "!" * 70
        print(banner, flush=True)
        print(f"!!! CRITICAL: {len(_failures)} of {len(vehicles)} EXPIRY WARNINGS FAILED TO SEND", flush=True)
        print("!!! Reps were NOT warned. Their storefronts will go dark.", flush=True)
        for f in _failures:
            print(f"!!!   {f}", flush=True)
        print(banner, flush=True)
        try:
            alert = Mail(
                from_email=Email("sales@carsinstock.com", "CarsInStock ALERT"),
                to_emails=To("ecastillo@pinebeltauto.com"),
                subject=f"[CRITICAL] {len(_failures)} expiry warnings FAILED to send",
                html_content="<h2 style='color:#DC2626'>Expiry warnings failed</h2>"
                             f"<p><b>{len(_failures)} of {len(vehicles)}</b> warnings did not send. "
                             "These reps were NOT told their listings are expiring.</p><ul>"
                             + "".join(f"<li>{f}</li>" for f in _failures) + "</ul>"
            )
            sg.send(alert)
            print("!!! operator alert email sent", flush=True)
        except Exception as e:
            print(f"!!! COULD NOT EVEN SEND THE ALERT: {e}", flush=True)
        sys.exit(1)

    print(f"Done. {len(vehicles)} alerts processed, 0 failures.")
