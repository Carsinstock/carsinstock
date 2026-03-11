import re
from flask import render_template, redirect, url_for, flash, request, session, jsonify
from datetime import datetime
from functools import wraps

RESERVED_SLUGS = {
    'login', 'logout', 'register', 'profile', 'admin', 'api',
    'search-cars', 'salespeople', 'customers', 'about', 'contact', 'demo',
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
            
            # Handle profile photo upload
            profile_photo = request.files.get("profile_photo")
            cover_photo_file = request.files.get("cover_photo")

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
                sp.dealership_name = request.form.get("dealership_name", "").strip()
                sp.dealership_address = request.form.get("dealership_address", "").strip()
                sp.banner_template = request.form.get("banner_template", "").strip()
                sp.cover_photo_y_offset = max(0, min(100, int(request.form.get("cover_photo_y_offset", 50) or 50)))
                sp.bio = bio
                if profile_photo and profile_photo.filename:
                    from app.utils.cloudinary_upload import upload_profile_photo, upload_cover_photo
                    photo_url = upload_profile_photo(profile_photo, sp.salesperson_id)
                    if photo_url:
                        sp.profile_photo = photo_url
                if cover_photo_file and cover_photo_file.filename:
                    from app.utils.cloudinary_upload import upload_profile_photo, upload_cover_photo
                    cover_url = upload_cover_photo(cover_photo_file, sp.salesperson_id)
                    if cover_url:
                        sp.cover_photo = cover_url
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
                    dealership_name=request.form.get("dealership_name", "").strip(),
                    dealership_address=request.form.get("dealership_address", "").strip(),
                    profile_url_slug=slug,
                    status="active",
                    hired_at=datetime.utcnow()
                )
                if profile_photo and profile_photo.filename:
                    from app.utils.cloudinary_upload import upload_vehicle_image
                    db.session.add(sp)
                    db.session.flush()
                    photo_url = upload_vehicle_image(profile_photo, sp.salesperson_id)
                    if photo_url:
                        sp.profile_photo = photo_url
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
            mileage = request.form.get("mileage", "").strip().replace(",", "").replace(" ", "")
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
            if not mileage or not mileage.replace(".", "").isdigit():
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

    @bp.route("/api/vin-decode/<vin>")
    @login_required
    def vin_decode(vin):
        from flask import jsonify
        from app.utils.vin_decoder import decode_vin
        if len(vin) != 17:
            return jsonify({"error": "VIN must be 17 characters"}), 400
        result = decode_vin(vin.upper())
        if result:
            return jsonify(result)
        return jsonify({"error": "Could not decode VIN"}), 404


    @bp.route("/vehicles/edit/<int:vehicle_id>", methods=["GET", "POST"])
    @login_required
    def edit_vehicle(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models.salesperson import Salesperson
        import cloudinary.uploader

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        vehicle = Vehicle.query.get_or_404(vehicle_id)

        # Security: only the owner can edit
        if vehicle.salesperson_id != sp.salesperson_id:
            flash("You don't have permission to edit this vehicle.", "error")
            return redirect(url_for("salesperson.public_profile", slug=sp.profile_url_slug))

        if request.method == "POST":
            vehicle.year = int(request.form.get("year", vehicle.year))
            vehicle.make = request.form.get("make", vehicle.make)
            vehicle.model = request.form.get("model", vehicle.model)
            vehicle.trim = request.form.get("trim", vehicle.trim)
            vehicle.vin = request.form.get("vin", vehicle.vin)
            vehicle.mileage = int(request.form.get("mileage", vehicle.mileage))
            vehicle.exterior_color = request.form.get("exterior_color", vehicle.exterior_color)
            vehicle.interior_color = request.form.get("interior_color", vehicle.interior_color)
            vehicle.transmission = request.form.get("transmission", vehicle.transmission)
            vehicle.fuel_type = request.form.get("fuel_type", vehicle.fuel_type)

            price = request.form.get("price", "").replace(",", "").replace("$", "")
            try:
                vehicle.price = float(price)
            except ValueError:
                pass

            photo = request.files.get("photo")
            if photo and photo.filename:
                result = cloudinary.uploader.upload(photo)
                vehicle.image_url = result["secure_url"]

            # Renew expired listing
            if vehicle.is_expired:
                from datetime import datetime, timedelta
                vehicle.expires_at = datetime.utcnow() + timedelta(days=14)
                vehicle.status = 'available'
            try:
                from app.models import db
                db.session.commit()
                flash(f"{vehicle.year} {vehicle.make} {vehicle.model} updated!", "success")
                return redirect(f"/{sp.profile_url_slug}")
            except Exception as e:
                db.session.rollback()
                flash("Error updating vehicle.", "error")
                print(f"Vehicle edit error: {e}")

        return render_template("salesperson/edit_vehicle.html", vehicle=vehicle, sp=sp)


    @bp.route("/vehicles/delete/<int:vehicle_id>", methods=["POST"])
    @login_required
    def delete_vehicle(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models.salesperson import Salesperson
        from app.models import db

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        vehicle = Vehicle.query.get_or_404(vehicle_id)

        if vehicle.salesperson_id != sp.salesperson_id:
            flash("You don't have permission to delete this vehicle.", "error")
            return redirect(f"/{sp.profile_url_slug}")

        name = f"{vehicle.year} {vehicle.make} {vehicle.model}"
        try:
            db.session.delete(vehicle)
            db.session.commit()
            flash(f"{name} deleted.", "success")
        except Exception as e:
            db.session.rollback()
            flash("Error deleting vehicle.", "error")
            print(f"Vehicle delete error: {e}")

        return redirect(f"/{sp.profile_url_slug}")

    @bp.route("/vehicles/share/<int:vehicle_id>", methods=["GET", "POST"])
    @login_required
    def share_vehicle(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models.salesperson import Salesperson
        from app.utils.email import send_vehicle_email
        from app.models.customer import Customer

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        vehicle = Vehicle.query.get_or_404(vehicle_id)
        if vehicle.salesperson_id != sp.salesperson_id:
            flash("You don't have permission to share this vehicle.", "error")
            return redirect(f"/{sp.profile_url_slug}")

        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id, unsubscribed=False).filter(Customer.email != '', Customer.email != None).order_by(Customer.name).all()

        if request.method == "POST":
            emails_raw = request.form.get("emails", "")
            personal_msg = request.form.get("message", "")

            # Get emails from selected customers
            customer_ids = request.form.getlist("customer_ids")
            customer_emails = []
            if customer_ids:
                selected = Customer.query.filter(Customer.id.in_(customer_ids), Customer.salesperson_id == sp.salesperson_id, Customer.unsubscribed == False).all()
                customer_emails = [c.email for c in selected if c.email]

            # Split additional emails
            import re
            extra_emails = re.split(r'[,;\n]+', emails_raw)
            extra_emails = [e.strip() for e in extra_emails if e.strip() and "@" in e]

            email_list = list(set(customer_emails + extra_emails))

            if not email_list:
                flash("Please enter at least one valid email address.", "error")
                return render_template("salesperson/share_vehicle.html", vehicle=vehicle, sp=sp, customers=customers)

            # Rate limit: 50 blasts per day per salesperson
            from datetime import datetime, timedelta
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            try:
                from app.models import db as rate_db
                blast_count = rate_db.session.execute(
                    rate_db.text("SELECT COUNT(*) FROM email_blasts WHERE salesperson_id = :sid AND sent_at >= :today"),
                    {"sid": sp.salesperson_id, "today": today_start}
                ).scalar() or 0
            except:
                blast_count = 0
            if blast_count >= 50:
                flash("Daily email limit reached (50/day). Try again tomorrow.", "error")
                return render_template("salesperson/share_vehicle.html", vehicle=vehicle, sp=sp, customers=customers)

            # Build customer_map for unsubscribe links
            customer_map = {}
            if customer_ids:
                for c in selected:
                    if c.email:
                        customer_map[c.email] = c.id
            sent, errors = send_vehicle_email(email_list, vehicle, sp, personal_msg, customer_map=customer_map)

            if sent > 0:
                flash(f"Vehicle sent to {sent} recipient(s)!", "success")
            if errors > 0:
                flash(f"{errors} email(s) failed to send.", "error")

            return redirect(f"/{sp.profile_url_slug}")

        return render_template("salesperson/share_vehicle.html", vehicle=vehicle, sp=sp, customers=customers)

    @bp.route("/customers/list", methods=["GET"])
    @login_required
    def my_customers():
        from app.models.salesperson import Salesperson
        from app.models.customer import Customer

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Customer.name).all()
        return render_template("salesperson/my_customers.html", customers=customers, sp=sp)

    @bp.route("/customers/add", methods=["GET", "POST"])
    @login_required
    def add_customer():
        from app.models.salesperson import Salesperson
        from app.models.customer import Customer
        from app.models import db

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "error")
                return render_template("salesperson/add_customer.html", customer=None, sp=sp)

            customer = Customer(
                salesperson_id=sp.salesperson_id,
                name=name,
                email=request.form.get("email", "").strip(),
                phone=request.form.get("phone", "").strip(),
                notes=request.form.get("notes", "").strip()
            )
            db.session.add(customer)
            db.session.commit()
            flash(f"{name} added!", "success")
            return redirect(url_for("salesperson.my_customers"))

        return render_template("salesperson/add_customer.html", customer=None, sp=sp)

    @bp.route("/customers/edit/<int:customer_id>", methods=["GET", "POST"])
    @login_required
    def edit_customer(customer_id):
        from app.models.salesperson import Salesperson
        from app.models.customer import Customer
        from app.models import db

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return redirect(url_for("salesperson.profile_setup"))

        customer = Customer.query.get_or_404(customer_id)
        if customer.salesperson_id != sp.salesperson_id:
            flash("Permission denied.", "error")
            return redirect(url_for("salesperson.my_customers"))

        if request.method == "POST":
            customer.name = request.form.get("name", customer.name).strip()
            customer.email = request.form.get("email", "").strip()
            customer.phone = request.form.get("phone", "").strip()
            customer.notes = request.form.get("notes", "").strip()
            db.session.commit()
            flash(f"{customer.name} updated!", "success")
            return redirect(url_for("salesperson.my_customers"))

        return render_template("salesperson/add_customer.html", customer=customer, sp=sp)

    @bp.route("/customers/delete/<int:customer_id>", methods=["POST"])
    @login_required
    def delete_customer(customer_id):
        from app.models.salesperson import Salesperson
        from app.models.customer import Customer
        from app.models import db

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return redirect(url_for("salesperson.profile_setup"))

        customer = Customer.query.get_or_404(customer_id)
        if customer.salesperson_id != sp.salesperson_id:
            flash("Permission denied.", "error")
            return redirect(url_for("salesperson.my_customers"))

        name = customer.name
        db.session.delete(customer)
        db.session.commit()
        flash(f"{name} deleted.", "success")
        return redirect(url_for("salesperson.my_customers"))


    @bp.route("/profile/remove-photo/<photo_type>", methods=["POST"])
    @login_required
    def remove_photo(photo_type):
        from app.models import db
        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if sp:
            if photo_type == "profile":
                sp.profile_photo = None
                flash("Profile photo removed.", "success")
            elif photo_type == "cover":
                sp.cover_photo = None
                flash("Cover photo removed.", "success")
            db.session.commit()
        return redirect(url_for("salesperson.profile_setup"))

    @bp.route("/api/generate-bio", methods=["POST"])
    @login_required
    def generate_bio_api():
        from app.utils.ai import generate_bio
        data = request.get_json()
        name = data.get("name", "")
        years = data.get("years", "")
        dealership = data.get("dealership", "")
        specialties = data.get("specialties", "")
        bio = generate_bio(name, years, dealership, specialties)
        if bio:
            return jsonify({"success": True, "bio": bio})
        return jsonify({"success": False, "error": "Could not generate bio"}), 500

    @bp.route("/api/draft-email", methods=["POST"])
    @login_required
    def draft_email_api():
        from app.utils.ai import draft_email
        data = request.get_json()
        sp_name = data.get("salesperson_name", "")
        cust_name = data.get("customer_name", "")
        vehicle = data.get("vehicle_info", "")
        tone = data.get("tone", "friendly")
        email = draft_email(sp_name, cust_name, vehicle, tone)
        if email:
            return jsonify({"success": True, "email": email})
        return jsonify({"success": False, "error": "Could not draft email"}), 500


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

    @bp.route("/dashboard")
    @login_required
    def dashboard():
        from app.models.salesperson import Salesperson
        from app.models.vehicle import Vehicle
        from app.models.customer import Customer
        from app.models.chat_conversation import ChatConversation
        from app.models.user import User
        from app.models import db
        from datetime import datetime
        import json
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))
        # My Vehicles
        vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.created_at.desc()).all()
        active_vehicles = [v for v in vehicles if not v.is_expired]
        expired_vehicles = [v for v in vehicles if v.is_expired]
        # My Leads
        from app.models.lead import Lead
        leads = Lead.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Lead.created_at.desc()).all()
        # Chat Transcripts
        chats = ChatConversation.query.filter_by(salesperson_id=sp.salesperson_id).order_by(ChatConversation.started_at.desc()).all()
        # My Customers
        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Customer.name).all()
        # Email blast count today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            blast_count = db.session.execute(
                db.text("SELECT COUNT(*) FROM email_blasts WHERE salesperson_id = :sid AND sent_at >= :today"),
                {"sid": sp.salesperson_id, "today": today_start}
            ).scalar() or 0
        except:
            blast_count = 0
        # Trial calculation
        from app.models.user import User
        user = User.query.get(session["user_id"])
        from datetime import timedelta
        trial_end = user.created_at + timedelta(days=14)
        now = datetime.utcnow()
        trial_days_left = max(0, (trial_end - now).days)
        trial_active = trial_days_left > 0

        return render_template("salesperson/dashboard.html", sp=sp,
            active_vehicles=active_vehicles, expired_vehicles=expired_vehicles,
            leads=leads, chats=chats, customers=customers, blast_count=blast_count,
            trial_days_left=trial_days_left, trial_active=trial_active, is_admin=User.query.get(session.get("user_id")).is_admin)

    @bp.route("/customers/import", methods=["GET", "POST"])
    @login_required
    def import_customers():
        from app.models.salesperson import Salesperson
        from app.models.customer import Customer
        from app.models import db
        import csv, io, re
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))
        if request.method == "POST":
            paste_data = request.form.get("paste_emails", "").strip()
            if paste_data:
                lines = [l.strip() for l in paste_data.splitlines() if l.strip()]
                imported = 0
                skipped = 0
                for line in lines:
                    email = line.strip().lower()
                    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                        skipped += 1
                        continue
                    existing = Customer.query.filter_by(salesperson_id=sp.salesperson_id, email=email).first()
                    if existing:
                        skipped += 1
                        continue
                    c = Customer(salesperson_id=sp.salesperson_id, name=email.split("@")[0], email=email)
                    db.session.add(c)
                    imported += 1
                db.session.commit()
                flash(f"{imported} contacts imported. {skipped} skipped (duplicates or invalid).", "success")
                return redirect(url_for("salesperson.my_customers"))
            file = request.files.get("csv_file")
            if not file or not file.filename:
                flash("Please select a CSV file.", "error")
                return redirect(url_for("salesperson.import_customers"))
            if not file.filename.endswith(".csv"):
                flash("Only .csv files are accepted.", "error")
                return redirect(url_for("salesperson.import_customers"))
            try:
                stream = io.StringIO(file.stream.read().decode("utf-8"))
                reader = csv.DictReader(stream)
                email_col = name_col = phone_col = notes_col = None
                for h in (reader.fieldnames or []):
                    hl = h.strip().lower()
                    if hl in ("email", "e-mail", "email_address", "emailaddress"): email_col = h
                    elif hl in ("name", "full_name", "fullname", "customer_name", "contact"): name_col = h
                    elif hl in ("phone", "phone_number", "phonenumber", "mobile", "cell"): phone_col = h
                    elif hl in ("notes", "note", "comments", "comment"): notes_col = h
                if not email_col:
                    flash("CSV must have an Email column.", "error")
                    return redirect(url_for("salesperson.import_customers"))
                imported = 0
                skipped = 0
                for row in reader:
                    email = row.get(email_col, "").strip().lower()
                    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                        skipped += 1
                        continue
                    existing = Customer.query.filter_by(salesperson_id=sp.salesperson_id, email=email).first()
                    if existing:
                        skipped += 1
                        continue
                    name = row.get(name_col, "").strip() if name_col else email.split("@")[0]
                    phone = row.get(phone_col, "").strip() if phone_col else ""
                    notes = row.get(notes_col, "").strip() if notes_col else ""
                    c = Customer(salesperson_id=sp.salesperson_id, name=name or email.split("@")[0], email=email, phone=phone, notes=notes)
                    db.session.add(c)
                    imported += 1
                db.session.commit()
                flash(f"{imported} contacts imported. {skipped} skipped (duplicates or invalid).", "success")
                return redirect(url_for("salesperson.my_customers"))
            except Exception as e:
                flash(f"Error reading CSV: {str(e)}", "error")
                return redirect(url_for("salesperson.import_customers"))
        return render_template("salesperson/import_customers.html")

    @bp.route("/chat/delete/<int:chat_id>", methods=["POST"])
    @login_required
    def delete_chat(chat_id):
        from app.models.chat_conversation import ChatConversation
        from app.models.user import User
        from app.models.salesperson import Salesperson
        from app.models import db
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Profile not found.", "error")
            return redirect("/dashboard")
        chat = ChatConversation.query.get_or_404(chat_id)
        if chat.salesperson_id != sp.salesperson_id:
            flash("Permission denied.", "error")
            return redirect("/dashboard")
        db.session.delete(chat)
        db.session.commit()
        flash("Chat transcript deleted.", "success")
        return redirect("/dashboard")

    @bp.route("/api/chatbot", methods=["POST"])
    def chatbot_api():
        from app.utils.ai import chatbot_response
        from app.models.salesperson import Salesperson
        from app.models.chat_conversation import ChatConversation
        from app.models.user import User
        import json
        data = request.get_json()
        message = data.get("message", "")
        history = data.get("history", [])
        slug = data.get("slug", "")
        session_id = data.get("session_id", "")
        sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
        if not sp:
            return jsonify({"response": "Sorry, something went wrong."})
        # Get inventory summary
        from app.models.vehicle import Vehicle
        from datetime import datetime
        vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').all()
        vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]
        inv_summary = ", ".join([f"{v.year} {v.make} {v.model}" for v in vehicles]) if vehicles else "No vehicles currently listed"
        response = chatbot_response(message, sp.display_name, inv_summary, history)
        # Save conversation to database
        try:
            from app.models import db
            convo = ChatConversation.query.filter_by(session_id=session_id, salesperson_id=sp.salesperson_id).first()
            if not convo:
                convo = ChatConversation(
                    salesperson_id=sp.salesperson_id,
                    session_id=session_id,
                    messages=json.dumps([])
                )
                db.session.add(convo)
            msgs = json.loads(convo.messages)
            msgs.append({"role": "user", "content": message})
            msgs.append({"role": "assistant", "content": response})
            convo.messages = json.dumps(msgs)
            convo.last_message_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            print(f"Chat save error: {e}")
        return jsonify({"response": response})


    @bp.route("/api/chatbot/homepage", methods=["POST"])
    def homepage_chatbot():
        data = request.get_json()
        message = data.get("message", "")
        history = data.get("history", [])
        system_prompt = """You are the CarsInStock sales assistant on the homepage. Your job is to convince car salespeople to sign up for CarsInStock.

Your personality: You think like a top 10% car salesman. You are confident, direct, relatable, and you understand the pain points of working at a dealership. You know what it is like to lose deals to the BDC, to have customers ghosted by internet leads, and to watch other salespeople steal your ups.

Key selling points you should weave into conversation naturally:
- Your own page: CarsInStock.com/your-name - YOUR cars, YOUR leads
- No more BDC stealing your customers - buyers contact YOU directly
- Post the cars YOU want to sell, not what the dealer website shows
- 14-day free trial, then $20/month plus $2 per vehicle listed - way cheaper than any lead service
- AI chatbot on your page talks to customers for you 24/7
- Email up to 50 customers a day with one click
- Every listing auto-expires in 7 days - your page always looks fresh
- Takes 2 minutes to set up

Always guide the conversation toward signing up. Be helpful but always be closing. Never be pushy - be like a friend who is already making money doing this and wants to help you get in. Keep responses short - 2-3 sentences max. End every response with a soft CTA."""
        try:
            import anthropic, os
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            messages = [{"role": m["role"], "content": m["content"]} for m in history]
            messages.append({"role": "user", "content": message})
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=system_prompt,
                messages=messages
            )
            response = resp.content[0].text
        except Exception as e:
            print(f"Homepage chatbot error: {e}")
        return jsonify({"response": response})

    @bp.route("/api/chatbot/end", methods=["POST"])
    def chatbot_end():
        from app.models.salesperson import Salesperson
        from app.models.chat_conversation import ChatConversation
        from app.models.user import User
        from app.utils.email import send_email
        import json
        data = request.get_json()
        session_id = data.get("session_id", "")
        slug = data.get("slug", "")
        visitor_name = data.get("visitor_name", "")
        visitor_email = data.get("visitor_email", "")
        visitor_phone = data.get("visitor_phone", "")
        sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
        if not sp:
            return jsonify({"success": False})
        from app.models import db
        convo = ChatConversation.query.filter_by(session_id=session_id, salesperson_id=sp.salesperson_id).first()
        if not convo or convo.transcript_sent:
            return jsonify({"success": True})
        # Update visitor info if provided
        if visitor_name:
            convo.visitor_name = visitor_name
        if visitor_email:
            convo.visitor_email = visitor_email
        if visitor_phone:
            convo.visitor_phone = visitor_phone
        # Build transcript
        msgs = json.loads(convo.messages)
        if not msgs:
            return jsonify({"success": True})
        transcript_html = ""
        for m in msgs:
            if m["role"] == "user":
                transcript_html += f'<p style="margin:8px 0;"><strong style="color:#00C851;">Visitor:</strong> {m["content"]}</p>'
            else:
                transcript_html += f'<p style="margin:8px 0;"><strong style="color:#333;">Assistant:</strong> {m["content"]}</p>'
        visitor_info = ""
        if convo.visitor_name:
            visitor_info += f"<p><strong>Name:</strong> {convo.visitor_name}</p>"
        if convo.visitor_email:
            visitor_info += f"<p><strong>Email:</strong> {convo.visitor_email}</p>"
        if convo.visitor_phone:
            visitor_info += f"<p><strong>Phone:</strong> {convo.visitor_phone}</p>"
        from datetime import datetime
        time_str = convo.started_at.strftime("%B %d, %Y at %I:%M %p UTC") if convo.started_at else "Unknown"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #00C851;">
                <h1 style="color: #00C851; margin: 0; font-size: 28px;">CarsInStock</h1>
            </div>
            <div style="padding: 30px 20px;">
                <h2 style="color: #333; margin-bottom: 10px;">New Chat Transcript</h2>
                <p style="color: #666; font-size: 14px;">Started: {time_str}</p>
                {visitor_info if visitor_info else '<p style="color:#999;">No visitor contact info provided</p>'}
                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                <h3 style="color:#333;font-size:16px;">Conversation:</h3>
                {transcript_html}
            </div>
            <div style="border-top: 1px solid #eee; padding: 20px 0; text-align: center;">
                <p style="color: #999; font-size: 12px; margin: 0;">CarsInStock.com</p>
            </div>
        </div>
        """
        try:
            send_email(sp.email, "New Chat Transcript from Your Storefront", html_content)
            convo.transcript_sent = True
            db.session.commit()
        except Exception as e:
            print(f"Transcript email error: {e}")
        return jsonify({"success": True})

    # ---- ADMIN EMAIL BLAST ----
    @bp.route("/admin/blast", methods=["GET", "POST"])
    @login_required
    def admin_blast():
        from app.models import db
        from app.models.user import User
        from app.models.salesperson import Salesperson
        from app.utils.email import send_email

        user = User.query.get(session.get("user_id"))
        if not user or not user.is_admin:
            flash("Unauthorized", "error")
            return redirect("/")

        TEMPLATES = {
            "welcome": {
                "name": "Welcome & Announcement",
                "subject": "Welcome to CarsInStock — Your Personal Storefront is Ready",
                "body": """
                    <div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;">
                        <div style="background:#1E293B;padding:30px;text-align:center;">
                            <h1 style="color:#fff;margin:0;font-size:24px;">Cars <span style="color:#00C851;">IN STOCK</span></h1>
                        </div>
                        <div style="padding:30px 20px;">
                            <h2 style="color:#1E293B;">Your personal car storefront is here.</h2>
                            <p style="color:#555;font-size:16px;line-height:1.6;">CarsInStock gives you your own page — <strong>carsinstock.com/your-name</strong> — where buyers can see your real, current inventory and contact you directly.</p>
                            <p style="color:#555;font-size:16px;line-height:1.6;">No ghost cars. No stale listings. Every vehicle expires after 7 days so customers always see what is actually available.</p>
                            <div style="text-align:center;margin:30px 0;">
                                <a href="https://carsinstock.com/register" style="background:#00C851;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Claim Your Page — Free for 14 Days</a>
                            </div>
                            <p style="color:#555;font-size:14px;">Fresh Cars. Real People. That is what CarsInStock is all about.</p>
                        </div>
                        <div style="border-top:1px solid #eee;padding:20px 0;text-align:center;">
                            <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>
                        </div>
                    </div>"""
            },
            "feature": {
                "name": "Feature Update",
                "subject": "New on CarsInStock — Check Out What is New",
                "body": """
                    <div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;">
                        <div style="background:#1E293B;padding:30px;text-align:center;">
                            <h1 style="color:#fff;margin:0;font-size:24px;">Cars <span style="color:#00C851;">IN STOCK</span></h1>
                        </div>
                        <div style="padding:30px 20px;">
                            <h2 style="color:#1E293B;">We have been busy building for you.</h2>
                            <p style="color:#555;font-size:16px;line-height:1.6;">Here is what is new on your CarsInStock storefront:</p>
                            <ul style="color:#555;font-size:16px;line-height:2;">
                                <li>One-click vehicle renewal — keep your best listings fresh</li>
                                <li>AI-powered chatbot — engages buyers on your page 24/7</li>
                                <li>Email blast tool — send your inventory to up to 50 customers a day</li>
                            </ul>
                            <div style="text-align:center;margin:30px 0;">
                                <a href="https://carsinstock.com/login" style="background:#00C851;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Log In & Check It Out</a>
                            </div>
                        </div>
                        <div style="border-top:1px solid #eee;padding:20px 0;text-align:center;">
                            <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>
                        </div>
                    </div>"""
            },
            "engage": {
                "name": "Re-Engagement",
                "subject": "Your CarsInStock Page is Waiting — Buyers Are Looking",
                "body": """
                    <div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;">
                        <div style="background:#1E293B;padding:30px;text-align:center;">
                            <h1 style="color:#fff;margin:0;font-size:24px;">Cars <span style="color:#00C851;">IN STOCK</span></h1>
                        </div>
                        <div style="padding:30px 20px;">
                            <h2 style="color:#1E293B;">Buyers are searching. Are your cars listed?</h2>
                            <p style="color:#555;font-size:16px;line-height:1.6;">Your CarsInStock page is your 24/7 digital storefront. When you keep it fresh, buyers find you — not the other way around.</p>
                            <p style="color:#555;font-size:16px;line-height:1.6;">It only takes 5 minutes to post a few cars. Share your link and let the leads come to you.</p>
                            <div style="text-align:center;margin:30px 0;">
                                <a href="https://carsinstock.com/login" style="background:#00C851;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Update Your Inventory Now</a>
                            </div>
                        </div>
                        <div style="border-top:1px solid #eee;padding:20px 0;text-align:center;">
                            <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>
                        </div>
                    </div>"""
            }
        }

        results = None
        if request.method == "POST":
            template_key = request.form.get("template")
            if template_key not in TEMPLATES:
                flash("Invalid template selected", "error")
                return redirect(url_for("salesperson.admin_blast"))

            template = TEMPLATES[template_key]
            salespeople = Salesperson.query.filter_by(status="active").all()

            if not salespeople:
                flash("No active salespeople found", "error")
                return redirect(url_for("salesperson.admin_blast"))

            sent = 0
            failed = 0
            for sp in salespeople:
                if sp.email:
                    success = send_email(sp.email, template["subject"], template["body"])
                    if success:
                        sent += 1
                    else:
                        failed += 1

            results = {"sent": sent, "failed": failed, "template": template["name"]}
            flash(f"Blast sent: {sent} delivered, {failed} failed", "success" if failed == 0 else "warning")

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Email Blast - CarsInStock</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
            <style>
                * {{ margin:0; padding:0; box-sizing:border-box; }}
                body {{ font-family:Inter,sans-serif; background:#f1f5f9; }}
                .header {{ background:#1E293B; padding:20px 30px; display:flex; justify-content:space-between; align-items:center; }}
                .header h1 {{ color:#fff; font-size:20px; }}
                .header h1 span {{ color:#00C851; }}
                .header a {{ color:#94a3b8; text-decoration:none; font-size:14px; }}
                .container {{ max-width:800px; margin:30px auto; padding:0 20px; }}
                h2 {{ color:#1E293B; margin-bottom:20px; }}
                .template-card {{ background:#fff; border-radius:12px; padding:24px; margin-bottom:16px; border:2px solid #e2e8f0; cursor:pointer; transition:all 0.2s; }}
                .template-card:hover {{ border-color:#00C851; }}
                .template-card.selected {{ border-color:#00C851; background:#f0fdf4; }}
                .template-card h3 {{ color:#1E293B; margin-bottom:8px; }}
                .template-card p {{ color:#64748B; font-size:14px; }}
                .send-btn {{ background:#00C851; color:#fff; border:none; padding:14px 32px; border-radius:8px; font-size:16px; font-weight:600; cursor:pointer; margin-top:20px; }}
                .send-btn:hover {{ background:#00b348; }}
                .send-btn:disabled {{ background:#94a3b8; cursor:not-allowed; }}
                .results {{ background:#fff; border-radius:12px; padding:24px; margin-bottom:20px; border-left:4px solid #00C851; }}
                .back-link {{ color:#00C851; text-decoration:none; font-size:14px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Cars <span>IN STOCK</span> — Admin Blast</h1>
                <a href="/salesperson/dashboard">← Back to Dashboard</a>
            </div>
            <div class="container">
                {"<div class='results'><h3>Blast Results</h3><p>Template: " + results['template'] + "</p><p>Sent: " + str(results['sent']) + " | Failed: " + str(results['failed']) + "</p></div>" if results else ""}
                <h2>Send Email Blast to All Salespeople</h2>
                <form method="POST" id="blastForm">
                    <div class="template-card" onclick="selectTemplate('welcome', this)">
                        <h3>Welcome & Announcement</h3>
                        <p>Introduce CarsInStock to new salespeople. Includes CTA to claim their page with 14-day free trial.</p>
                    </div>
                    <div class="template-card" onclick="selectTemplate('feature', this)">
                        <h3>Feature Update</h3>
                        <p>Announce new features like one-click renewal, AI chatbot, and email blast tools.</p>
                    </div>
                    <div class="template-card" onclick="selectTemplate('engage', this)">
                        <h3>Re-Engagement</h3>
                        <p>Nudge inactive salespeople to update their inventory and start getting leads.</p>
                    </div>
                    <input type="hidden" name="template" id="templateInput" value="">
                    <button type="submit" class="send-btn" id="sendBtn" disabled>Select a Template to Send</button>
                </form>
            </div>
            <script>
                function selectTemplate(key, el) {{
                    document.querySelectorAll('.template-card').forEach(c => c.classList.remove('selected'));
                    el.classList.add('selected');
                    document.getElementById('templateInput').value = key;
                    var btn = document.getElementById('sendBtn');
                    btn.disabled = false;
                    btn.textContent = 'Send Blast Now';
                }}
                document.getElementById('blastForm').addEventListener('submit', function(e) {{
                    if (!document.getElementById('templateInput').value) {{
                        e.preventDefault();
                        alert('Please select a template first');
                    }} else if (!confirm('Send this blast to ALL active salespeople?')) {{
                        e.preventDefault();
                    }}
                }});
            </script>
        </body>
        </html>
        """

