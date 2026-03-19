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
    slug = re.sub(r'[^a-z0-9]', '', display_name.lower().strip())
    if slug in RESERVED_SLUGS:
        slug = f"{slug}sp"
    base_slug = slug
    counter = 1
    while Salesperson.query.filter_by(profile_url_slug=slug).first():
        slug = f"{base_slug}{counter}"
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
                sp.banner_x_offset = max(0, min(100, int(request.form.get("banner_x_offset", 50) or 50)))
                sp.vehicle_sort_order = request.form.get("vehicle_sort_order", "newest")
                sp.bio = bio
                sp.financing_url = request.form.get("financing_url", "").strip()
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
                    financing_url=request.form.get("financing_url", "").strip(),
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

        from app.models.user import User as _User
        _u = _User.query.get(user_id)
        if _u and _u.is_locked:
            return redirect(url_for("billing.checkout"))

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
            if mileage and not mileage.replace(".", "").isdigit():
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
                mileage=int(mileage) if mileage else None,
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
            raw_mileage = request.form.get("mileage", "").strip().replace(",", "")
            vehicle.mileage = int(raw_mileage) if raw_mileage and raw_mileage.isdigit() else vehicle.mileage
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
                vehicle.expires_at = datetime.utcnow() + timedelta(days=7)
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

        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id, unsubscribed=False).filter(Customer.email != '', Customer.email != None).order_by(Customer.first_name).all()

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

            # Subscription gate
            from app.models.user import User as _User
            _u2 = _User.query.get(session["user_id"])
            if _u2 and _u2.is_locked:
                return redirect(url_for("billing.checkout"))
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




    @bp.route("/blast/ai-copy", methods=["POST"])
    @login_required
    def blast_ai_copy():
        import anthropic, os, json
        from flask import request, jsonify

        from app.models.salesperson import Salesperson
        data = request.get_json(force=True, silent=True) or {}
        template = data.get("template", "")
        tone = data.get("tone", "professional")
        template_name = data.get("template_name", template)

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return jsonify({"error": "Profile not found"}), 400

        tone_desc = {
            "professional": "professional and polished — trustworthy and clear",
            "casual": "casual and friendly — like a text from a friend who sells cars",
            "urgent": "urgent and sales-driven — create FOMO, drive action now"
        }.get(tone, "professional")

        prompt = f"""You are writing a bulk email blast for {sp.display_name}, a car salesperson at {sp.dealership_name or 'a dealership'}.

Template: {template_name}
Tone: {tone_desc}

Write a short, punchy email blast. Rules:
- Subject line: max 8 words, no quotes
- Message body: 2-4 sentences max, ALWAYS start with {{{{first_name}}}} as the literal text - never substitute a real name
- Do NOT mention specific prices or vehicle details — those are shown automatically below the message
- Sound like a real salesperson, not a robot
- No emojis in the body

Respond ONLY with valid JSON in this exact format, no markdown, no extra text:
{{"subject": "your subject line here", "body": "your message body here"}}"""

        try:
            from dotenv import load_dotenv
            load_dotenv('/home/eddie/carsinstock/.env')
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            msg = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text.strip()
            parsed = json.loads(raw)
            return jsonify({"subject": parsed["subject"], "body": parsed["body"]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/blast/test", methods=["POST"])
    @login_required
    def send_test_blast():
        from app.models import db
        from app.models.vehicle import Vehicle
        from app.models.user import User as _User
        from app.utils.email import _build_unsubscribe_footer
        from datetime import datetime
        import sendgrid, os
        from sendgrid.helpers.mail import Mail

        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return jsonify({"error": "Profile not found"}), 400

        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        if not subject or not body:
            return jsonify({"error": "Subject and message are required"}), 400

        user = _User.query.get(session["user_id"])
        test_email_raw = request.form.get("test_email", "").strip() or user.email
        test_emails = [e.strip() for e in test_email_raw.split(",") if e.strip() and "@" in e]
        test_email = test_emails[0] if test_emails else user.email

        sort = sp.vehicle_sort_order or 'newest'
        if sort == 'price_low':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').order_by(Vehicle.price.asc()).all()
        elif sort == 'price_high':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').order_by(Vehicle.price.desc()).all()
        else:
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').order_by(Vehicle.created_at.desc()).all()
        vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]

        storefront_url = f"https://carsinstock.com/{sp.profile_url_slug}"
        vehicle_html = ""
        for v in vehicles[:6]:
            price = f"${v.price:,.0f}" if v.price else ""
            vehicle_html += f"""
            <div style="border:1px solid #eee;border-radius:8px;padding:12px;margin-bottom:10px;background:#fafafa;">
                <strong style="font-size:15px;color:#1E293B;">{v.year} {v.make} {v.model}</strong><br>
                <span style="color:#00C851;font-weight:700;font-size:16px;">{price}</span>
                {f'<br><span style="color:#666;font-size:13px;">{v.mileage:,} miles</span>' if v.mileage else ''}
            </div>"""

        first = sp.display_name.split()[0] if sp.display_name else "there"
        personal_body = body.replace("{{first_name}}", first)
        footer_html = '<div style="border-top:1px solid #eee;padding:16px 0;text-align:center;"><p style="color:#999;font-size:12px;margin:0;">Fresh Cars. Real People. | CarsInStock.com</p><p style="color:#999;font-size:11px;margin:6px 0 0 0;"></p></div>'

        template_id = request.form.get("template_id", "1")

        def build_vehicle_cards_test(vehicles, template_id, storefront_url):
            cards = ""
            for v in vehicles[:6]:
                price = f"${v.price:,.0f}" if v.price else ""
                miles = f"{v.mileage:,} miles" if v.mileage else ""
                img = f'<img src="{v.image_url}" style="width:100%;height:160px;object-fit:cover;border-radius:6px 6px 0 0;display:block;" />' if v.image_url else ""
                days = v.days_remaining if hasattr(v, 'days_remaining') else 0
                days_badge = f'<div style="background:#EF4444;color:white;font-size:11px;font-weight:700;padding:3px 8px;border-radius:10px;display:inline-block;margin-bottom:6px;">{days} Days Left</div>' if template_id == "3" and days <= 7 else ""
                cards += f'''<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:12px;overflow:hidden;">{img}<div style="padding:12px;">{days_badge}<div style="font-size:15px;font-weight:700;color:#1E293B;">{v.year} {v.make} {v.model}</div><div style="font-size:18px;font-weight:800;color:#00C851;margin:4px 0;">{price}</div><div style="font-size:12px;color:#64748B;">{miles}</div><a href="{storefront_url}" style="display:inline-block;margin-top:8px;padding:6px 14px;background:#00C851;color:white;border-radius:6px;text-decoration:none;font-size:12px;font-weight:700;">I'm Interested</a></div></div>'''
            return cards

        def build_hero_test(template_id):
            heroes = {"1":("#1E293B","#00C851","This Week's Top Picks"),"2":("#0f172a","#00C851","Fresh. In Stock. Right Now."),"3":("#7f1d1d","#f97316","These Won't Last Long"),"4":("#1E293B","#00C851","I Found Some Cars You Might Love"),"5":("#1E293B","#00C851","Before These Are Gone")}
            bg,accent,headline = heroes.get(template_id,heroes["1"])
            return f'<div style="background:{bg};padding:28px 20px;text-align:center;border-radius:8px 8px 0 0;"><span style="color:{accent};font-size:22px;font-weight:800;">{headline}</span></div>'

        def build_profile_test(sp):
            photo = f'<img src="{sp.profile_photo}" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:3px solid #00C851;" />' if sp.profile_photo else ""
            return f'<div style="text-align:center;padding:16px 0;">{photo}<div style="font-size:16px;font-weight:700;color:#1E293B;margin-top:8px;">{sp.display_name or ""}</div><div style="font-size:13px;color:#64748B;">{sp.dealership_name or ""}</div></div>'

        ctas = {"1":"View All My Inventory →","2":"See What's New →","3":"Claim Your Deal →","4":"Let's Talk →","5":"View This Week's Specials →"}
        cta_label = ctas.get(template_id,"View My Inventory →")
        v_cards = build_vehicle_cards_test(vehicles, template_id, storefront_url)
        phone_line = f'<div><a href="tel:{sp.phone}" style="color:#00C851;">{sp.phone}</a></div>' if sp.phone else ""

        html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">
        <div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
            {build_hero_test(template_id)}
            {build_profile_test(sp)}
            <div style="padding:0 16px 8px;">
                <p style="font-size:15px;color:#334155;line-height:1.7;">{personal_body}</p>
                {v_cards}
                <div style="text-align:center;margin:24px 0;"><a href="{storefront_url}" style="background:#00C851;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap;display:inline-block;">{cta_label}</a></div>
            </div>
            <div style="background:#f8fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;font-size:13px;color:#64748B;">
                {phone_line}
                {footer_html}
            </div>
        </div></div>"""

        try:
            sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
            sent_to = []
            for te in test_emails:
                msg = Mail(
                    from_email=(os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@carsinstock.com'), sp.display_name + ' via CarsInStock'),
                    to_emails=te,
                    subject="Ed Castillo at Pine Belt Used Cars — I've got something worth your time this week.",
                    html_content=html
                )
                sg.send(msg)
                sent_to.append(te)
            return jsonify({"sent": len(sent_to), "email": ", ".join(sent_to)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/blast/send", methods=["POST"])
    @login_required
    def send_bulk_blast():
        from app.models import db
        from app.models.vehicle import Vehicle
        from app.models.customer import Customer
        from app.models.user import User as _User
        from app.utils.email import _build_unsubscribe_footer
        from datetime import datetime, timedelta
        import sendgrid
        from sendgrid.helpers.mail import Mail, To
        import os, re

        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return jsonify({"error": "Profile not found"}), 400

        _u = _User.query.get(session["user_id"])
        if _u and _u.is_locked:
            return jsonify({"error": "Subscription required"}), 402

        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        segment = request.form.get("segment", "all")

        if not subject or not body:
            return jsonify({"error": "Subject and message are required"}), 400

        # Daily limit check — 500/day
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            sent_today = db.session.execute(
                db.text("SELECT COALESCE(SUM(recipient_count),0) FROM email_blasts WHERE salesperson_id=:sid AND sent_at>=:today AND blast_type='bulk'"),
                {"sid": sp.salesperson_id, "today": today_start}
            ).scalar() or 0
        except:
            sent_today = 0

        if sent_today >= 1000:
            return jsonify({"error": "Daily send limit reached (1,000/day). Try again tomorrow."}), 429

        # Get customers
        q = Customer.query.filter_by(salesperson_id=sp.salesperson_id, unsubscribed=False).filter(Customer.email != None, Customer.email != '')
        customers = q.all()

        if not customers:
            return jsonify({"error": "No eligible customers to send to"}), 400

        # Cap at remaining daily allowance
        remaining = 1000 - int(sent_today)
        blast_limit = min(int(request.form.get("blast_limit", 200) or 200), remaining, 1000)
        customers = customers[:blast_limit]

        # Get active vehicles for storefront link section
        from math import ceil
        vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id, status='available').all()
        vehicles = [v for v in vehicles if not v.expires_at or v.expires_at > datetime.utcnow()]

        storefront_url = f"https://carsinstock.com/{sp.profile_url_slug}"

        # Build vehicle cards HTML
        template_id = request.form.get("template_id", "1")

        def build_vehicle_cards(vehicles, template_id):
            cards = ""
            for v in vehicles[:6]:
                price = f"${v.price:,.0f}" if v.price else ""
                miles = f"{v.mileage:,} miles" if v.mileage else ""
                img = f'<img src="{v.image_url}" style="width:100%;height:160px;object-fit:cover;border-radius:6px 6px 0 0;display:block;" />' if v.image_url else ""
                days = v.days_remaining if hasattr(v, 'days_remaining') else 0
                days_badge = f'<div style="background:#EF4444;color:white;font-size:11px;font-weight:700;padding:3px 8px;border-radius:10px;display:inline-block;margin-bottom:6px;">{days} Days Left</div>' if template_id == "3" and days <= 7 else ""
                cards += f"""
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:12px;overflow:hidden;">
                    {img}
                    <div style="padding:12px;">
                        {days_badge}
                        <div style="font-size:15px;font-weight:700;color:#1E293B;">{v.year} {v.make} {v.model}</div>
                        <div style="font-size:18px;font-weight:800;color:#00C851;margin:4px 0;">{price}</div>
                        <div style="font-size:12px;color:#64748B;">{miles}</div>
                        <a href="{storefront_url}" style="display:inline-block;margin-top:8px;padding:6px 14px;background:#00C851;color:white;border-radius:6px;text-decoration:none;font-size:12px;font-weight:700;">I'm Interested</a>
                    </div>
                </div>"""
            return cards

        vehicle_html = build_vehicle_cards(vehicles, template_id)

        def build_profile_header(sp, template_id):
            photo = f'<img src="{sp.profile_photo}" style="width:70px;height:70px;border-radius:50%;object-fit:cover;border:3px solid #00C851;" />' if sp.profile_photo else f'<div style="width:70px;height:70px;border-radius:50%;background:#00C851;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700;color:white;">{sp.display_name[0] if sp.display_name else "?"}</div>'
            name = sp.display_name or ""
            dealer = sp.dealership_name or ""
            if template_id == "4":
                return f'''<div style="text-align:center;padding:16px 0;">
                    <div style="display:inline-block;">{photo}</div>
                    <div style="font-size:18px;font-weight:700;color:#1E293B;margin-top:8px;">{name}</div>
                    <div style="font-size:13px;color:#64748B;">{dealer}</div>
                </div>'''
            elif template_id == "2":
                return f'''<div style="padding:16px;display:flex;align-items:center;gap:14px;background:#f8fafc;">
                    {photo}
                    <div><div style="font-size:16px;font-weight:700;color:#1E293B;">{name}</div>
                    <div style="font-size:13px;color:#64748B;">{dealer}</div></div>
                </div>'''
            else:
                return f'''<div style="text-align:center;padding:16px 0;">
                    <div style="display:inline-block;">{photo}</div>
                    <div style="font-size:16px;font-weight:700;color:#1E293B;margin-top:8px;">{name}</div>
                    <div style="font-size:13px;color:#64748B;">{dealer}</div>
                </div>'''

        def build_hero(template_id):
            heroes = {
                "1": ('#1E293B', '#00C851', "This Week's Top Picks"),
                "2": ('#0f172a', '#00C851', "Fresh. In Stock. Right Now."),
                "3": ('#7f1d1d', '#f97316', "These Won't Last Long"),
                "4": ('#1E293B', '#00C851', "I Found Some Cars You Might Love"),
                "5": ('#1E293B', '#00C851', "Before These Are Gone"),
            }
            bg, accent, headline = heroes.get(template_id, heroes["1"])
            return f'<div style="background:{bg};padding:28px 20px;text-align:center;border-radius:8px 8px 0 0;"><span style="color:{accent};font-size:22px;font-weight:800;letter-spacing:-0.5px;">{headline}</span></div>'

        def build_cta(template_id, storefront_url):
            ctas = {
                "1": "View All My Inventory →",
                "2": "See What's New →",
                "3": "Claim Your Deal →",
                "4": "Let's Talk →",
                "5": "View This Week's Specials →",
            }
            label = ctas.get(template_id, "View My Inventory →")
            return f'<div style="text-align:center;margin:24px 0;"><a href="{storefront_url}" style="background:#00C851;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap;display:inline-block;">{label}</a></div>'

        sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
        sent = 0
        failed = 0

        for customer in customers:
            try:
                first = customer.first_name or customer.email.split('@')[0]
                footer_html = _build_unsubscribe_footer(customer_id=customer.id)
                personal_body = body.replace('{{first_name}}', first).replace('{{First_Name}}', first)

                phone_line = f'<div><a href="tel:{sp.phone}" style="color:#00C851;text-decoration:none;">{sp.phone}</a></div>' if sp.phone else ""
                email_line = f'<div><a href="mailto:{sp.email if hasattr(sp, "email") else ""}" style="color:#00C851;text-decoration:none;">{user.email}</a></div>'

                html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f1f5f9;padding:16px;">
                <div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
                    {build_hero(template_id)}
                    {build_profile_header(sp, template_id)}
                    <div style="padding:0 16px 8px;">
                        <p style="font-size:15px;color:#334155;line-height:1.7;margin:0 0 16px;">{personal_body}</p>
                        {vehicle_html}
                        {build_cta(template_id, storefront_url)}
                        <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:8px 14px;margin:0 0 8px;display:table;width:100%;box-sizing:border-box;">
                            <span style="font-size:13px;color:#64748B;">🌐</span>
                            <a href="{storefront_url}" style="font-size:13px;font-weight:600;color:#1E293B;text-decoration:none;margin-left:6px;">{storefront_url.replace("https://","")}</a>
                        </div>
                        <div style="background:#f0fdf4;border:1px solid #00C851;border-radius:8px;padding:8px 14px;margin:0 0 12px;display:table;width:100%;box-sizing:border-box;">
                            <span style="font-size:12px;font-weight:600;color:#1E293B;">🤝 Know someone? If they buy, they get a deal — and you get $100.</span>
                            <a href="{storefront_url}" style="display:inline-block;background:#00C851;color:white;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:700;text-decoration:none;margin-left:8px;white-space:nowrap;">Share →</a>
                        </div>
                    </div>
                    <div style="background:#f8fafc;padding:16px;text-align:center;border-top:1px solid #e2e8f0;">
                        <div style="font-size:13px;color:#64748B;margin-bottom:6px;">
                            {phone_line}
                        </div>
                        {footer_html}
                    </div>
                </div></div>"""

                msg = Mail(
                    from_email=(os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@carsinstock.com'), sp.display_name + ' via CarsInStock'),
                    to_emails=customer.email,
                    subject=subject,
                    html_content=html
                )
                sg.send(msg)
                sent += 1
            except Exception as e:
                failed += 1

        # Log blast
        if sent > 0:
            db.session.execute(
                db.text("INSERT INTO email_blasts (salesperson_id, recipient_count, subject, body, blast_type, sent_at) VALUES (:sid, :count, :subject, :body, 'bulk', :now)"),
                {"sid": sp.salesperson_id, "count": sent, "subject": subject, "body": body, "now": datetime.utcnow()}
            )
            db.session.commit()

        return jsonify({"sent": sent, "failed": failed, "total": len(customers)})

    @bp.route("/customers/list", methods=["GET"])
    @login_required
    def my_customers():
        from app.models.salesperson import Salesperson
        from app.models.customer import Customer

        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            flash("Set up your profile first.", "error")
            return redirect(url_for("salesperson.profile_setup"))

        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Customer.first_name).all()
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
            customer.first_name = request.form.get("first_name", customer.first_name).strip()
            customer.last_name = request.form.get("last_name", customer.last_name).strip()
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

    @bp.route("/qr-code")
    @login_required
    def qr_code():
        import qrcode
        import io
        from flask import send_file
        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return "Profile not found", 404
        url = f"https://carsinstock.com/{sp.profile_url_slug}"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1E293B", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png", as_attachment=True, download_name=f"carsinstock-qr-{sp.profile_url_slug}.png")


    @bp.route("/referral/submit/<slug>", methods=["POST"])
    def submit_referral(slug):
        import sqlite3, os
        from datetime import datetime
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(profile_url_slug=slug).first()
        if not sp:
            return jsonify({"error": "not found"}), 404
        data = request.get_json() or request.form
        referrer_name = data.get("referrer_name", "").strip()
        referrer_phone = data.get("referrer_phone", "").strip()
        referrer_email = data.get("referrer_email", "").strip()
        friend_name = data.get("friend_name", "").strip()
        friend_phone = data.get("friend_phone", "").strip()
        message = data.get("message", "").strip()
        if not all([referrer_name, referrer_phone, referrer_email, friend_name, friend_phone]):
            return jsonify({"error": "Missing required fields"}), 400
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        cur = conn.cursor()
        cur.execute("""INSERT INTO referrals (salesperson_id, referrer_name, referrer_phone, referrer_email, friend_name, friend_phone, message, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (sp.salesperson_id, referrer_name, referrer_phone, referrer_email, friend_name, friend_phone, message, datetime.utcnow()))
        conn.commit()
        conn.close()
        sp_first = sp.display_name.split()[0] if sp.display_name else sp.display_name
        # Email confirmation to referrer
        try:
            sg = SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
            msg = Mail(
                from_email=(os.environ.get('SENDGRID_FROM_EMAIL', 'sales@carsinstock.com'), sp.display_name + ' via CarsInStock'),
                to_emails=referrer_email,
                subject=f"Got your referral — thanks, {referrer_name.split()[0]}!",
                html_content=f"""<div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:24px;">
                    <p style="font-size:16px;color:#1E293B;">Hey {referrer_name.split()[0]},</p>
                    <p style="font-size:15px;color:#334155;">Got it! If {friend_name} buys a car from {sp_first}, we'll make sure you get your $100. I'll reach out personally.</p>
                    <p style="font-size:15px;color:#334155;">— {sp.display_name}<br>{sp.dealership_name or ''}</p>
                    <p style="font-size:12px;color:#94A3B8;margin-top:24px;">Powered by CarsInStock.com</p>
                </div>"""
            )
            sg.send(msg)
        except Exception as e:
            print(f"Referral confirmation email error: {e}")
        # Notify salesperson
        try:
            from app.models.user import User as _User
            sp_user = _User.query.get(sp.user_id)
            if sp_user:
                sg2 = SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
                msg2 = Mail(
                    from_email=(os.environ.get('SENDGRID_FROM_EMAIL', 'sales@carsinstock.com'), 'CarsInStock'),
                    to_emails=sp_user.email,
                    subject=f"New Referral — {referrer_name} referred {friend_name}",
                    html_content=f"""<div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:24px;">
                        <h2 style="color:#1E293B;">New Referral Submitted</h2>
                        <p><strong>Referrer:</strong> {referrer_name} — {referrer_phone} — {referrer_email}</p>
                        <p><strong>Friend:</strong> {friend_name} — {friend_phone}</p>
                        <p><strong>Message:</strong> {message or 'None'}</p>
                        <p style="margin-top:16px;"><a href="https://carsinstock.com/dashboard" style="background:#00C851;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;">View in Dashboard</a></p>
                    </div>"""
                )
                sg2.send(msg2)
        except Exception as e:
            print(f"Referral notify email error: {e}")
        return jsonify({"success": True})

    @bp.route("/referrals", methods=["GET"])
    @login_required
    def get_referrals():
        import sqlite3
        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return jsonify([])
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        cur = conn.cursor()
        cur.execute("SELECT id, referrer_name, referrer_phone, referrer_email, friend_name, friend_phone, message, status, submitted_at FROM referrals WHERE salesperson_id=? ORDER BY submitted_at DESC", (sp.salesperson_id,))
        rows = cur.fetchall()
        conn.close()
        return jsonify([{"id":r[0],"referrer_name":r[1],"referrer_phone":r[2],"referrer_email":r[3],"friend_name":r[4],"friend_phone":r[5],"message":r[6],"status":r[7],"submitted_at":r[8]} for r in rows])

    @bp.route("/referrals/update/<int:referral_id>", methods=["POST"])
    @login_required
    def update_referral_status(referral_id):
        import sqlite3
        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return jsonify({"error": "not found"}), 404
        status = request.get_json().get("status")
        if status not in ["pending", "sold", "paid"]:
            return jsonify({"error": "invalid status"}), 400
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        cur = conn.cursor()
        cur.execute("UPDATE referrals SET status=? WHERE id=? AND salesperson_id=?", (status, referral_id, sp.salesperson_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})


    @bp.route("/autopilot", methods=["GET", "POST"])
    @login_required
    def autopilot():
        import sqlite3
        from app.models.salesperson import Salesperson
        sp = Salesperson.query.filter_by(user_id=session["user_id"]).first()
        if not sp:
            return redirect(url_for("salesperson.profile_setup"))
        conn = sqlite3.connect("/home/eddie/carsinstock/instance/carsinstock.db")
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_picks":
                message = request.form.get("weekly_message", "").strip()
                template_id = request.form.get("template_id", "1")
                is_active = int(request.form.get("is_active", 1))
                onboarding_per_day = min(int(request.form.get("onboarding_per_day", 200) or 200), 1000)
                cur.execute("SELECT id FROM blast_schedule WHERE salesperson_id=?", (sp.salesperson_id,))
                existing = cur.fetchone()
                if existing:
                    cur.execute("UPDATE blast_schedule SET weekly_message=?, template_id=?, is_active=?, onboarding_per_day=?, last_updated=? WHERE salesperson_id=?",
                        (message, template_id, is_active, onboarding_per_day, datetime.utcnow(), sp.salesperson_id))
                else:
                    cur.execute("INSERT INTO blast_schedule (salesperson_id, weekly_message, template_id, is_active, onboarding_per_day, last_updated) VALUES (?,?,?,?,?,?)",
                        (sp.salesperson_id, message, template_id, is_active, onboarding_per_day, datetime.utcnow()))
                conn.commit()
                flash("Weekly picks saved! Blast fires Sunday 9AM EST.", "success")
            elif action == "toggle":
                is_active = int(request.form.get("is_active", 1))
                cur.execute("UPDATE blast_schedule SET is_active=? WHERE salesperson_id=?", (is_active, sp.salesperson_id))
                conn.commit()
                return jsonify({"success": True, "is_active": is_active})
        # Get current schedule
        sched = cur.execute("SELECT * FROM blast_schedule WHERE salesperson_id=?", (sp.salesperson_id,)).fetchone()
        # Get stats
        total_active = cur.execute("SELECT COUNT(DISTINCT customer_id) FROM blast_log WHERE salesperson_id=?", (sp.salesperson_id,)).fetchone()[0]
        week_ago = datetime.utcnow() - timedelta(days=7)
        sent_week = cur.execute("SELECT COUNT(*) FROM blast_log WHERE salesperson_id=? AND sent_at>=?", (sp.salesperson_id, week_ago)).fetchone()[0]
        new_week = cur.execute("SELECT COUNT(*) FROM blast_log WHERE salesperson_id=? AND blast_type='onboarding' AND sent_at>=?", (sp.salesperson_id, week_ago)).fetchone()[0]
        unsub_week = cur.execute("SELECT COUNT(*) FROM customers WHERE salesperson_id=? AND unsubscribed=1", (sp.salesperson_id,)).fetchone()[0]
        onboard_pos = cur.execute("SELECT last_customer_id FROM blast_onboard_position WHERE salesperson_id=?", (sp.salesperson_id,)).fetchone()
        total_customers = cur.execute("SELECT COUNT(*) FROM customers WHERE salesperson_id=?", (sp.salesperson_id,)).fetchone()[0]
        conn.close()
        from datetime import timezone as tz
        import pytz
        est = pytz.timezone("US/Eastern")
        now_est = datetime.now(est)
        days_until_sunday = (6 - now_est.weekday()) % 7 or 7
        next_sunday = now_est + timedelta(days=days_until_sunday)
        next_blast = next_sunday.replace(hour=9, minute=0, second=0, microsecond=0)
        return render_template("salesperson/autopilot.html",
            sp=sp, sched=sched,
            total_active=total_active, sent_week=sent_week,
            new_week=new_week, unsub_week=unsub_week,
            next_blast=next_blast.strftime("%A, %B %d at 9:00 AM EST"),
            onboard_pos=onboard_pos["last_customer_id"] if onboard_pos else 0,
            total_customers=total_customers)

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
        sort = sp.vehicle_sort_order or 'newest'
        if sort == 'price_low':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.price.asc()).all()
        elif sort == 'price_high':
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.price.desc()).all()
        else:
            vehicles = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Vehicle.created_at.desc()).all()
        active_vehicles = [v for v in vehicles if not v.is_expired]
        expired_vehicles = [v for v in vehicles if v.is_expired]
        # My Leads
        from app.models.lead import Lead
        leads = Lead.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Lead.created_at.desc()).all()
        # Chat Transcripts
        chats = ChatConversation.query.filter_by(salesperson_id=sp.salesperson_id).order_by(ChatConversation.started_at.desc()).all()
        # My Customers
        customers = Customer.query.filter_by(salesperson_id=sp.salesperson_id).order_by(Customer.first_name).all()
        # Email blast count today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            blast_count = db.session.execute(
                db.text("SELECT COALESCE(SUM(recipient_count),0) FROM email_blasts WHERE salesperson_id = :sid AND sent_at >= :today"),
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

        from app.models import db as _db2
        try:
            blast_history = _db2.session.execute(
                _db2.text("SELECT id, subject, recipient_count, sent_at FROM email_blasts WHERE salesperson_id=:sid AND blast_type='bulk' ORDER BY sent_at DESC LIMIT 10"),
                {"sid": sp.salesperson_id}
            ).fetchall()
        except:
            blast_history = []
        return render_template("salesperson/dashboard.html", sp=sp,
            active_vehicles=active_vehicles, expired_vehicles=expired_vehicles,
            leads=leads, chats=chats, customers=customers, blast_count=blast_count, blast_history=blast_history,
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
                email_col = first_name_col = last_name_col = name_col = phone_col = notes_col = None
                for h in (reader.fieldnames or []):
                    hl = h.strip().lower()
                    if hl in ("email", "e-mail", "email_address", "emailaddress"): email_col = h
                    elif hl in ("first_name", "firstname", "first"): first_name_col = h
                    elif hl in ("last_name", "lastname", "last"): last_name_col = h
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
                    # Resolve first/last name from dedicated cols, or split full name col
                    if first_name_col or last_name_col:
                        first_name = row.get(first_name_col, "").strip() if first_name_col else ""
                        last_name = row.get(last_name_col, "").strip() if last_name_col else ""
                    elif name_col:
                        full = row.get(name_col, "").strip()
                        parts = full.split(" ", 1)
                        first_name = parts[0]
                        last_name = parts[1] if len(parts) > 1 else ""
                    else:
                        first_name = email.split("@")[0]
                        last_name = ""
                    phone = row.get(phone_col, "").strip() if phone_col else ""
                    notes = row.get(notes_col, "").strip() if notes_col else ""
                    c = Customer(salesperson_id=sp.salesperson_id, first_name=first_name, last_name=last_name, email=email, phone=phone, notes=notes)
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
- Your own page: CarsInStock.com/yourname - YOUR cars, YOUR leads
- No more BDC stealing your customers - buyers contact YOU directly
- Post the cars YOU want to sell, not what the dealer website shows
- 14-day free trial, then $39/month — unlimited vehicles, no per-car fees, cancel anytime
- AI chatbot on your page talks to customers for you 24/7
- Email your entire customer book with one click
- Every listing auto-expires in 7 days - your page always looks fresh
- Takes 2 minutes to set up

Always guide the conversation toward signing up. Never be pushy - be like a friend who is already making money doing this and wants to help you get in. KEEP RESPONSES TO 1-2 SHORT SENTENCES MAXIMUM. No long paragraphs. No lists. One punch, one CTA. That is it."""
        try:
            import anthropic, os
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            messages = [{"role": m["role"], "content": m["content"]} for m in history]
            messages.append({"role": "user", "content": message})
            resp = client.messages.create(
                model="claude-3-haiku-20240307",
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

