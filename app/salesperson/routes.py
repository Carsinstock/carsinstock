import re
from flask import render_template, redirect, url_for, flash, request, session
from datetime import datetime
from functools import wraps

RESERVED_SLUGS = {
    'login', 'logout', 'register', 'profile', 'admin', 'api',
    'search-cars', 'salespeople', 'customers', 'about', 'contact',
    'pricing', 'terms', 'privacy', 'help', 'support', 'settings',
    'dashboard', 'static', 's', 'vehicles', 'leads', 'reports'
}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def generate_slug(display_name):
    from app.models.salesperson import Salesperson
    slug = display_name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    if slug in RESERVED_SLUGS:
        slug = f"{slug}-sp"
    base_slug = slug
    counter = 1
    while Salesperson.query.filter_by(profile_url_slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def register_routes(bp):
    @bp.route("/profile/setup", methods=["GET", "POST"])
    @login_required
    def profile_setup():
        from app.models import db
        from app.models.user import User
        from app.models.salesperson import Salesperson

        user_id = session["user_id"]
        sp = Salesperson.query.filter_by(user_id=user_id).first()

        if request.method == "POST":
            display_name = request.form.get("display_name", "").strip()
            phone = request.form.get("phone", "").strip()
            bio = request.form.get("bio", "").strip()

            errors = []
            if not display_name:
                errors.append("Display name is required.")
            if len(display_name) > 255:
                errors.append("Display name is too long.")

            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template("salesperson/profile_setup.html",
                    display_name=display_name, phone=phone, bio=bio, sp=sp)

            if sp:
                sp.display_name = display_name
                sp.phone = phone
                sp.bio = bio
                if not sp.profile_url_slug:
                    sp.profile_url_slug = generate_slug(display_name)
            else:
                slug = generate_slug(display_name)
                user = User.query.get(user_id)
                sp = Salesperson(
                    user_id=user_id,
                    display_name=display_name,
                    phone=phone,
                    email=user.email,
                    bio=bio,
                    profile_url_slug=slug,
                    status="active",
                    hired_at=datetime.utcnow()
                )
                db.session.add(sp)

            try:
                db.session.commit()
                flash("Profile saved!", "success")
                return redirect(f"/{sp.profile_url_slug}")
            except Exception as e:
                db.session.rollback()
                flash("Something went wrong. Please try again.", "error")

        return render_template("salesperson/profile_setup.html",
            display_name=sp.display_name if sp else "",
            phone=sp.phone if sp else "",
            bio=sp.bio if sp else "",
            sp=sp)

    @bp.route("/vehicles/add", methods=["GET", "POST"])
    @login_required
    def add_vehicle():
        from app.models import db
        from app.models.salesperson import Salesperson
        from app.models.vehicle import Vehicle
        from app.utils.cloudinary_upload import upload_vehicle_image

        user_id = session["user_id"]
        sp = Salesperson.query.filter_by(user_id=user_id).first()
        if not sp:
            flash("Please set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        if request.method == "POST":
            year = request.form.get("year", "").strip()
            make = request.form.get("make", "").strip()
            model = request.form.get("model", "").strip()
            trim = request.form.get("trim", "").strip()
            vin = request.form.get("vin", "").strip().upper()
            mileage = request.form.get("mileage", "").strip()
            price = request.form.get("price", "").strip()
            exterior_color = request.form.get("exterior_color", "").strip()
            interior_color = request.form.get("interior_color", "").strip()
            transmission = request.form.get("transmission", "").strip()
            fuel_type = request.form.get("fuel_type", "").strip()
            photo = request.files.get("photo")

            errors = []
            if not year or not year.isdigit():
                errors.append("Valid year is required.")
            if not make:
                errors.append("Make is required.")
            if not model:
                errors.append("Model is required.")
            if not vin or len(vin) != 17:
                errors.append("Valid 17-character VIN is required.")
            if not mileage or not mileage.isdigit():
                errors.append("Valid mileage is required.")
            if not price:
                errors.append("Price is required.")
            if not photo or photo.filename == "":
                errors.append("At least one photo is required.")

            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template("salesperson/add_vehicle.html", sp=sp)

            # Upload image to Cloudinary
            image_url = None
            if photo:
                image_url = upload_vehicle_image(photo, sp.salesperson_id)

            try:
                price_val = float(price.replace(",", "").replace("$", ""))
            except ValueError:
                flash("Invalid price format.", "error")
                return render_template("salesperson/add_vehicle.html", sp=sp)

            vehicle = Vehicle(
                salesperson_id=sp.salesperson_id,
                dealer_id=sp.dealer_id,
                year=int(year),
                make=make,
                model=model,
                trim=trim,
                vin=vin,
                mileage=int(mileage),
                price=price_val,
                exterior_color=exterior_color,
                interior_color=interior_color,
                transmission=transmission,
                fuel_type=fuel_type,
                image_url=image_url
            )

            try:
                db.session.add(vehicle)
                db.session.commit()
                flash(f"{year} {make} {model} added successfully!", "success")
                return redirect(f"/{sp.profile_url_slug}")
            except Exception as e:
                db.session.rollback()
                flash("Something went wrong. Please try again.", "error")
                print(f"Vehicle add error: {e}")

        return render_template("salesperson/add_vehicle.html", sp=sp)
