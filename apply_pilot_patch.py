#!/usr/bin/env python3
"""
CarsInStock — Pre-Pilot Patch: 4 Tasks
Run: cd /home/eddie/carsinstock && source venv/bin/activate && python apply_pilot_patch.py

Task 2: My Customers + Email Blast tabs in dashboard
Task 3: One-click Renew route
Task 4: Dealership name field in profile setup
Task 7: Onboarding redirect for new users
"""

import re

# ═══════════════════════════════════════════════════════════════
# TASK 4: Add dealership_name to Salesperson model
# ═══════════════════════════════════════════════════════════════

MODEL_FILE = "app/models/salesperson.py"
with open(MODEL_FILE, "r") as f:
    content = f.read()

if "dealership_name" not in content:
    content = content.replace(
        "    cover_photo = db.Column(db.String(500))",
        "    cover_photo = db.Column(db.String(500))\n    dealership_name = db.Column(db.String(200))"
    )
    with open(MODEL_FILE, "w") as f:
        f.write(content)
    print("✅ Task 4a: Added dealership_name to Salesperson model")
else:
    print("⏭  Task 4a: dealership_name already in model")

# ═══════════════════════════════════════════════════════════════
# TASK 3: Add one-click renew route to salesperson/routes.py
# ═══════════════════════════════════════════════════════════════

ROUTES_FILE = "app/salesperson/routes.py"
with open(ROUTES_FILE, "r") as f:
    content = f.read()

RENEW_ROUTE = '''
    @bp.route("/vehicles/renew/<int:vehicle_id>", methods=["POST"])
    @login_required
    def renew_vehicle(vehicle_id):
        from app.models.salesperson import Salesperson
        from app.models.vehicle import Vehicle
        from app.models import db
        from datetime import datetime, timedelta
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))
        vehicle = Vehicle.query.filter_by(id=vehicle_id, salesperson_id=sp.salesperson_id).first()
        if not vehicle:
            flash("Vehicle not found.", "error")
            return redirect(url_for("salesperson.dashboard"))
        vehicle.expires_at = datetime.utcnow() + timedelta(days=7)
        vehicle.created_at = datetime.utcnow()
        vehicle.expiration_warning_sent = False
        db.session.commit()
        flash(f"{vehicle.year} {vehicle.make} {vehicle.model} renewed for 7 days!", "success")
        return redirect(url_for("salesperson.dashboard"))
'''

if "renew_vehicle" not in content:
    # Insert before the dashboard route
    content = content.replace(
        '    @bp.route("/dashboard")',
        RENEW_ROUTE + '\n    @bp.route("/dashboard")'
    )
    with open(ROUTES_FILE, "w") as f:
        f.write(content)
    print("✅ Task 3a: Added /vehicles/renew/<id> route")
else:
    print("⏭  Task 3a: renew_vehicle route already exists")

# ═══════════════════════════════════════════════════════════════
# TASK 2: Update dashboard route to pass customers data
# ═══════════════════════════════════════════════════════════════

with open(ROUTES_FILE, "r") as f:
    content = f.read()

# Add customers to dashboard render
OLD_RENDER = 'return render_template("salesperson/dashboard.html", sp=sp,\n            active_vehicles=active_vehicles, expired_vehicles=expired_vehicles,\n            leads=leads, chats=chats)'

NEW_RENDER = '''# My Customers
        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Customer.name).all()
        # Email blast count today
        from datetime import timedelta
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            blast_count = db.session.execute(
                db.text("SELECT COUNT(*) FROM email_blasts WHERE salesperson_id = :sid AND sent_at >= :today"),
                {"sid": sp.salesperson_id, "today": today_start}
            ).scalar() or 0
        except:
            blast_count = 0
        return render_template("salesperson/dashboard.html", sp=sp,
            active_vehicles=active_vehicles, expired_vehicles=expired_vehicles,
            leads=leads, chats=chats, customers=customers, blast_count=blast_count)'''

if "customers=customers" not in content:
    content = content.replace(OLD_RENDER, NEW_RENDER)
    with open(ROUTES_FILE, "w") as f:
        f.write(content)
    print("✅ Task 2a: Dashboard route now passes customers + blast_count")
else:
    print("⏭  Task 2a: customers already passed to dashboard")

# ═══════════════════════════════════════════════════════════════
# TASK 4: Add dealership_name to profile_setup route
# ═══════════════════════════════════════════════════════════════

with open(ROUTES_FILE, "r") as f:
    content = f.read()

# Add dealership_name to POST handling - save on existing sp
if 'sp.bio = bio' in content and 'sp.dealership_name' not in content:
    content = content.replace(
        '                sp.bio = bio',
        '                sp.dealership_name = request.form.get("dealership_name", "").strip()\n                sp.bio = bio'
    )
    print("✅ Task 4b: Added dealership_name save to existing profile update")

# Add dealership_name to new Salesperson creation
if "dealership_name=request.form" not in content:
    # For new sp creation, we need to find where Salesperson() is called
    # and the profile_url_slug assignment
    old_new_sp = '''                sp = Salesperson(
                    user_id=user_id,
                    display_name=display_name,
                    phone=phone,
                    email=user.email,
                    bio=bio,
                    profile_url_slug=slug,
                    status="active",
                    hired_at=datetime.utcnow()
                )'''
    new_new_sp = '''                sp = Salesperson(
                    user_id=user_id,
                    display_name=display_name,
                    phone=phone,
                    email=user.email,
                    bio=bio,
                    dealership_name=request.form.get("dealership_name", "").strip(),
                    profile_url_slug=slug,
                    status="active",
                    hired_at=datetime.utcnow()
                )'''
    content = content.replace(old_new_sp, new_new_sp)
    print("✅ Task 4c: Added dealership_name to new Salesperson creation")

# Add dealership_name to template render on GET
if "dealership_name=sp.dealership_name" not in content:
    # Find the GET render for profile_setup - look for the pattern at end of function
    # We need to pass dealership_name to template
    # This varies - let's add it to the render_template calls
    pass  # We'll handle this in the template itself using sp.dealership_name

with open(ROUTES_FILE, "w") as f:
    f.write(content)

# ═══════════════════════════════════════════════════════════════
# TASK 7: Onboarding redirect in login route
# ═══════════════════════════════════════════════════════════════

AUTH_FILE = "app/auth/routes.py"
with open(AUTH_FILE, "r") as f:
    content = f.read()

# Replace login redirect: check if profile exists, redirect to setup if not
OLD_LOGIN_REDIRECT = '''            flash("Welcome back!", "success")
            return redirect("/" + session.get("slug", ""))'''

NEW_LOGIN_REDIRECT = '''            if not sp or not sp.display_name:
                flash("Welcome! Let's set up your storefront.", "success")
                return redirect(url_for("salesperson.profile_setup"))
            flash("Welcome back!", "success")
            return redirect(url_for("salesperson.dashboard"))'''

if "Let's set up your storefront" not in content:
    content = content.replace(OLD_LOGIN_REDIRECT, NEW_LOGIN_REDIRECT)
    with open(AUTH_FILE, "w") as f:
        f.write(content)
    print("✅ Task 7a: Login now redirects new users to profile setup")
else:
    print("⏭  Task 7a: Onboarding redirect already in login")

# Also update verify_email to redirect to login (which will then redirect to setup)
# This is already the case, so no change needed there.

print("\n✅ All route changes applied!")
print("Now apply template changes manually (see instructions below).\n")

# ═══════════════════════════════════════════════════════════════
# Print remaining manual template changes
# ═══════════════════════════════════════════════════════════════

print("=" * 60)
print("REMAINING: Template changes needed (paste into nano)")
print("=" * 60)
print("""
1. dashboard.html — Add Customers + Email Blast tabs
2. dashboard.html — Update Renew button to POST form
3. public_profile.html — Update Renew button to POST form
4. profile_setup.html — Add dealership_name field

Run: sudo systemctl restart apache2
""")
