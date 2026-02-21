#!/usr/bin/env python3
"""Cron job: Send expiration warning emails for vehicles expiring within 24 hours."""
import sys
sys.path.insert(0, '/home/eddie/carsinstock')

from app import create_app
from app.models import db
from app.models.vehicle import Vehicle
from app.models.salesperson import Salesperson
from app.utils.email import send_email
from datetime import datetime, timedelta

app = create_app()

with app.app_context():
    now = datetime.utcnow()
    tomorrow = now + timedelta(hours=24)
    
    # Find vehicles expiring in the next 24 hours that haven't been warned
    vehicles = Vehicle.query.filter(
        Vehicle.expires_at > now,
        Vehicle.expires_at <= tomorrow,
        Vehicle.status == 'available',
        Vehicle.expiration_warning_sent == False
    ).all()
    
    print(f"[{now}] Found {len(vehicles)} vehicles expiring within 24 hours")
    
    for v in vehicles:
        sp = Salesperson.query.filter_by(salesperson_id=v.salesperson_id).first()
        if not sp or not sp.email:
            continue
        
        expire_time = v.expires_at.strftime("%B %d, %Y at %I:%M %p UTC")
        edit_url = f"https://carsinstock.com/vehicles/edit/{v.id}"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #6C2BD9;">
                <h1 style="color: #6C2BD9; margin: 0; font-size: 28px;">CarsInStock</h1>
            </div>
            <div style="padding: 30px 20px;">
                <div style="background: #fef3cd; border: 1px solid #f59e0b; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <p style="color: #92400e; font-size: 16px; font-weight: bold; margin: 0;">Listing Expiring Soon</p>
                </div>
                <h2 style="color: #333; margin-bottom: 5px;">{v.year} {v.make} {v.model} {v.trim or ''}</h2>
                <p style="color: #666; font-size: 15px;">VIN: {v.vin or 'N/A'}</p>
                <p style="color: #555; font-size: 16px; line-height: 1.6;">
                    This listing will expire on <strong>{expire_time}</strong>. 
                    If this vehicle is still available, renew it to keep it visible on your storefront.
                </p>
                <div style="text-align: center; padding: 25px 0;">
                    <a href="{edit_url}"
                       style="background-color: #6C2BD9; color: white; padding: 14px 32px;
                              text-decoration: none; border-radius: 6px; font-size: 16px;
                              font-weight: bold; display: inline-block;">
                        Renew Listing
                    </a>
                </div>
                <p style="color: #999; font-size: 13px;">
                    Listings on CarsInStock expire after 7 days to keep inventory fresh. Renewing is free.
                </p>
            </div>
            <div style="border-top: 1px solid #eee; padding: 20px 0; text-align: center;">
                <p style="color: #999; font-size: 12px; margin: 0;">
                    CarsInStock | 76 RT 37 East, Toms River, NJ 08753
                </p>
            </div>
        </div>
        """
        
        try:
            send_email(sp.email, f"Listing Expiring Soon: {v.year} {v.make} {v.model}", html_content)
            v.expiration_warning_sent = True
            db.session.commit()
            print(f"  Warning sent for {v.year} {v.make} {v.model} to {sp.email}")
        except Exception as e:
            print(f"  Error sending warning for vehicle {v.id}: {e}")
    
    print(f"Done. {len(vehicles)} warnings processed.")
