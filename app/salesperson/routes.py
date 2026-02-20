import re
from flask import render_template, redirect, url_for, flash, request, session, jsonify
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

            sent, errors = send_vehicle_email(email_list, vehicle, sp, personal_msg)

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

    @bp.route("/api/chatbot", methods=["POST"])
    def chatbot_api():
        from app.utils.ai import chatbot_response
        from app.models.salesperson import Salesperson
        data = request.get_json()
        message = data.get("message", "")
        history = data.get("history", [])
        slug = data.get("slug", "")
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
        return jsonify({"response": response})
