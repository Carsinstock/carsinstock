#!/usr/bin/env python3
"""Saturday 8AM EST — sends each active salesperson their weekly social post + QR code."""
import sys, os, fcntl, io, base64
sys.path.insert(0, '/home/eddie/carsinstock')
os.chdir('/home/eddie/carsinstock')
from dotenv import load_dotenv
load_dotenv('/home/eddie/carsinstock/.env')

LOCK_FILE = '/tmp/carsinstock_saturday.lock'
lock = open(LOCK_FILE, 'w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print('[saturday] Already running — skipping')
    sys.exit(0)

from app import create_app
app = create_app()

with app.app_context():
    import sqlite3, qrcode
    from app.models.salesperson import Salesperson
    from app.models.vehicle import Vehicle
    from app.utils.email import send_email
    from datetime import datetime

    conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
    conn.row_factory = sqlite3.Row

    # Send to actual salespeople in dealership_team, not dealership accounts
    team_members = conn.execute(
        "SELECT dt.id, dt.name, dt.email, dt.dealership_id FROM dealership_team dt WHERE dt.is_active=1 AND dt.email IS NOT NULL AND dt.email != ''"
    ).fetchall()

    for member in team_members:
        sp_name = member['name']
        sp_email = member['email']
        dealership_id = member['dealership_id']

        # Get the dealership salesperson to access vehicles and storefront slug
        sp = Salesperson.query.filter_by(salesperson_id=dealership_id).first()
        if not sp:
            continue

        # Get top 3-5 active vehicles for this dealership
        vehicles = Vehicle.query.filter_by(
            salesperson_id=sp.salesperson_id,
            status='available'
        ).order_by(Vehicle.price.asc()).limit(5).all()

        if not vehicles:
            continue

        storefront_url = f"https://carsinstock.com/{sp.profile_url_slug}"

        # Build vehicle list for post
        vehicle_lines = "\n".join([
            f"🚗 {v.year} {v.make} {v.model} — ${v.price:,.0f}" + (f" | {v.mileage:,} miles" if v.mileage else "")
            for v in vehicles
        ])

        # Facebook/Instagram post copy
        fb_post = f"""🚗 This week's picks from {sp.display_name}:

{vehicle_lines}

👉 See full inventory + photos: {storefront_url}

#CarsInStock #UsedCars #CarDeals #NJCars"""

        # Generate QR code as base64 for email embed
        qr = qrcode.QRCode(version=1, box_size=8, border=4)
        qr.add_data(storefront_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#1E293B", back_color="white")
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">
  <div style="background:#1E293B;padding:20px;text-align:center;border-radius:10px 10px 0 0;">
    <span style="color:#00C851;font-size:20px;font-weight:800;">Cars IN STOCK</span>
    <p style="color:#94A3B8;margin:4px 0 0;font-size:13px;">Your Weekly Social Reminder</p>
  </div>
  <div style="background:#fff;padding:24px;border-radius:0 0 10px 10px;">
    <h2 style="color:#1E293B;margin:0 0 8px;">Hey {sp_name} — post this today. It takes 60 seconds.</h2>
    <p style="color:#64748B;font-size:14px;margin:0 0 20px;">Copy the post below and share it on Facebook or Instagram right now.</p>

    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;padding:16px;margin-bottom:20px;">
      <p style="font-size:12px;font-weight:700;color:#94A3B8;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">📋 Copy & Post This</p>
      <pre style="font-family:Arial,sans-serif;font-size:14px;color:#1E293B;white-space:pre-wrap;margin:0;">{fb_post}</pre>
    </div>

    <div style="text-align:center;margin-bottom:20px;">
      <a href="{storefront_url}" style="background:#00C851;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">View My Storefront →</a>
    </div>

    <div style="text-align:center;border-top:1px solid #E2E8F0;padding-top:20px;">
      <p style="font-size:13px;color:#64748B;margin:0 0 12px;">Your QR Code — print it, share it, put it anywhere.</p>
      <img src="data:image/png;base64,{qr_b64}" alt="QR Code" style="width:160px;height:160px;">
      <p style="font-size:12px;color:#94A3B8;margin:8px 0 0;">{storefront_url}</p>
    </div>
  </div>
</div>
"""
        try:
            send_email(sp_email, f"Post this today — your weekly CarsInStock update 🚗", html)
            print(f'[saturday] Sent to {sp_name} ({sp_email})')
        except Exception as e:
            print(f'[saturday] Error sending to {sp.email}: {e}')

    conn.close()

fcntl.flock(lock, fcntl.LOCK_UN)
lock.close()
print('[saturday] Done')
