from flask import render_template, session, redirect, flash, request, url_for, jsonify
from functools import wraps
from app.models import db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.salesperson import Salesperson
from app.models.lead import Lead


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in.", "error")
            return redirect(url_for("auth.login"))
        user = User.query.get(user_id)
        if not user or not user.is_admin:
            flash("Access denied.", "error")
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


def register_admin_routes(bp):
    if len(bp.deferred_functions) > 0:
        return  # Already registered
    @bp.route("/team")
    def team():
        import sqlite3
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        cur = conn.cursor()
        members = cur.execute("SELECT * FROM dealership_team WHERE is_active=1 ORDER BY name").fetchall()
        conn.close()
        return render_template("admin/team.html", team=members)

    @bp.route("/team/add", methods=["POST"])
    def add_team_member():
        import sqlite3, cloudinary.uploader
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        slug = request.form.get("slug", "").strip().lower().replace(" ", "")
        photo_url = None
        photo = request.files.get("photo")
        if photo and photo.filename:
            result = cloudinary.uploader.upload(photo, folder="carsinstock/team")
            photo_url = result["secure_url"]
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        conn.execute(
            "INSERT INTO dealership_team (name, phone, email, profile_photo, slug) VALUES (?,?,?,?,?)",
            (name, phone, email, photo_url, slug)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin.team"))

    @bp.route("/team/<int:member_id>/edit", methods=["POST"])
    def edit_team_member(member_id):
        import sqlite3, cloudinary.uploader
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        photo = request.files.get("photo")
        if photo and photo.filename:
            result = cloudinary.uploader.upload(photo, folder="carsinstock/team")
            photo_url = result["secure_url"]
            conn.execute("UPDATE dealership_team SET name=?, phone=?, email=?, profile_photo=? WHERE id=?",
                (name, phone, email, photo_url, member_id))
        else:
            conn.execute("UPDATE dealership_team SET name=?, phone=?, email=? WHERE id=?",
                (name, phone, email, member_id))
        conn.commit()
        conn.close()
        return redirect(url_for("admin.team"))

    @bp.route("/team/<int:member_id>/delete", methods=["POST"])
    def delete_team_member(member_id):
        import sqlite3
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        conn.execute("DELETE FROM dealership_team WHERE id=?", (member_id,))
        conn.commit()
        conn.close()
        return redirect(url_for("admin.team"))

    @bp.route("/dealership-leads")
    @admin_required
    def dealership_leads():
        import sqlite3
        conn = sqlite3.connect("/home/eddie/carsinstock/instance/carsinstock.db")
        conn.row_factory = sqlite3.Row
        leads = conn.execute("SELECT * FROM dealership_leads ORDER BY submitted_at DESC").fetchall()
        conn.close()
        return render_template("admin/dealership_leads.html", leads=leads)



    @bp.route("/")
    @admin_required
    def dashboard():
        user_count = User.query.count()
        vehicle_count = Vehicle.query.count()
        lead_count = Lead.query.count()
        sp_count = Salesperson.query.count()
        try:
            recruit_count = db.engine.execute(db.text("SELECT COUNT(*) FROM recruitment_contacts")).scalar()
        except:
            recruit_count = 0
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        return render_template("admin/dashboard.html",
            user_count=user_count, vehicle_count=vehicle_count,
            lead_count=lead_count, sp_count=sp_count, recruit_count=recruit_count, recent_users=recent_users)

    @bp.route("/users")
    @admin_required
    def users():
        all_users = User.query.order_by(User.created_at.desc()).all()
        # Get salesperson info for each user
        user_data = []
        for u in all_users:
            sp = Salesperson.query.filter_by(user_id=u.id).first()
            vehicle_count = Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).count() if sp else 0
            user_data.append({"user": u, "salesperson": sp, "vehicle_count": vehicle_count})
        return render_template("admin/users.html", user_data=user_data)

    @bp.route("/users/<int:user_id>/suspend", methods=["POST"])
    @admin_required
    def suspend_user(user_id):
        user = User.query.get_or_404(user_id)
        user.is_active = not user.is_active
        db.session.commit()
        status = "activated" if user.is_active else "suspended"
        flash(f"User {user.email} {status}.", "success")
        return redirect(url_for("admin.users"))

    @bp.route("/users/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def delete_user(user_id):
        user = User.query.get_or_404(user_id)
        if user.is_admin:
            flash("Cannot delete admin users.", "error")
            return redirect(url_for("admin.users"))
        # Delete associated salesperson, vehicles, leads
        sp = Salesperson.query.filter_by(user_id=user.id).first()
        if sp:
            Vehicle.query.filter_by(salesperson_id=sp.salesperson_id).delete()
            Lead.query.filter_by(salesperson_id=sp.salesperson_id).delete()
            db.session.delete(sp)
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.email} and all associated data deleted.", "success")
        return redirect(url_for("admin.users"))

    @bp.route("/vehicles")
    @admin_required
    def vehicles():
        pending_vehicles = Vehicle.query.filter_by(approval_status='pending').order_by(Vehicle.created_at.desc()).all()
        all_vehicles = Vehicle.query.filter(Vehicle.approval_status != 'pending').order_by(Vehicle.created_at.desc()).all()
        import sqlite3 as _sq3
        _conn = _sq3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        _conn.row_factory = _sq3.Row
        all_salespeople = _conn.execute("SELECT * FROM dealership_team WHERE is_active=1 ORDER BY name").fetchall()
        _conn.close()
        # Build team member lookup for pending queue names
        _tm_rows = _conn.execute("SELECT id, name FROM dealership_team WHERE is_active=1").fetchall()
        team_member_lookup = {r['id']: r['name'] for r in _tm_rows}
        return render_template("admin/vehicles.html",
            vehicles=all_vehicles,
            pending_vehicles=pending_vehicles,
            pending_count=len(pending_vehicles),
            all_salespeople=all_salespeople,
            team_member_lookup=team_member_lookup)

    @bp.route("/vehicles/<int:vehicle_id>/approve", methods=["POST"])
    @admin_required
    def approve_vehicle(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models import db
        import os
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        vehicle.approval_status = 'approved'
        vehicle.rejection_reason = None
        db.session.commit()
        # Write in-app notification + send email
        try:
            import sqlite3 as _sq3
            _conn = _sq3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
            _conn.row_factory = _sq3.Row
            if vehicle.pick_user_id:
                _conn.execute(
                    "INSERT INTO team_notifications (team_member_id, vehicle_id, type, message) VALUES (?,?,?,?)",
                    (vehicle.pick_user_id, vehicle.id, 'approved',
                     f"Your {vehicle.year} {vehicle.make} {vehicle.model} was approved and is now live!")
                )
                _conn.commit()
            member = _conn.execute("SELECT * FROM dealership_team WHERE id=? AND is_active=1", (vehicle.pick_user_id,)).fetchone() if vehicle.pick_user_id else None
            _conn.close()
            if member and member['email']:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail, Email, To
                sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
                html = f"""
                <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
                  <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;">
                    <span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span>
                  </div>
                  <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                    <h2 style="color:#1E293B;font-size:20px;margin:0 0 8px;">✅ Your vehicle was approved!</h2>
                    <p style="color:#475569;font-size:15px;margin:0 0 20px;">Your <strong>{vehicle.year} {vehicle.make} {vehicle.model}</strong> is now live on the store and visible to customers.</p>
                    <a href="https://carsinstock.com/pinebeltusedcars" style="background:#00C851;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;">View My Store →</a>
                    <p style="color:#94A3B8;font-size:12px;margin:24px 0 0;">— The CarsInStock Team</p>
                  </div>
                </div>"""
                msg = Mail(from_email=Email('sales@carsinstock.com', 'CarsInStock'), to_emails=To(member['email']), subject=f"✅ Approved: {vehicle.year} {vehicle.make} {vehicle.model}", html_content=html)
                sg.send(msg)
        except Exception as e:
            print(f"Approval email error: {e}")
        flash(f"{vehicle.year} {vehicle.make} {vehicle.model} approved and now live.", "success")
        return redirect(url_for("admin.vehicles"))

    @bp.route("/vehicles/<int:vehicle_id>/reject", methods=["POST"])
    @admin_required
    def reject_vehicle(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models import db
        import os
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        reason = request.form.get("rejection_reason", "").strip()
        vehicle.approval_status = 'rejected'
        vehicle.rejection_reason = reason if reason else None
        db.session.commit()
        # Write in-app notification + send email
        try:
            import sqlite3 as _sq3
            _conn = _sq3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
            _conn.row_factory = _sq3.Row
            if vehicle.pick_user_id:
                msg_text = f"Your {vehicle.year} {vehicle.make} {vehicle.model} wasn't approved."
                if reason:
                    msg_text += f" Reason: {reason}"
                _conn.execute(
                    "INSERT INTO team_notifications (team_member_id, vehicle_id, type, message) VALUES (?,?,?,?)",
                    (vehicle.pick_user_id, vehicle.id, 'rejected', msg_text)
                )
                _conn.commit()
            member = _conn.execute("SELECT * FROM dealership_team WHERE id=? AND is_active=1", (vehicle.pick_user_id,)).fetchone() if vehicle.pick_user_id else None
            _conn.close()
            if member and member['email']:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail, Email, To
                sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
                reason_block = f'<p style="background:#FEF2F2;border-left:3px solid #EF4444;padding:12px 16px;border-radius:0 6px 6px 0;color:#7F1D1D;font-size:14px;margin:0 0 20px;"><strong>Reason:</strong> {reason}</p>' if reason else ''
                html = f"""
                <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:24px;">
                  <div style="background:#1E293B;padding:16px 24px;border-radius:10px 10px 0 0;">
                    <span style="color:white;font-weight:400;">Cars</span><span style="color:#00C851;font-weight:700;"> IN STOCK</span>
                  </div>
                  <div style="background:#fff;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 10px 10px;padding:28px;">
                    <h2 style="color:#1E293B;font-size:20px;margin:0 0 8px;">❌ Vehicle needs a change</h2>
                    <p style="color:#475569;font-size:15px;margin:0 0 16px;">Your <strong>{vehicle.year} {vehicle.make} {vehicle.model}</strong> wasn't approved this time.</p>
                    {reason_block}
                    <p style="color:#475569;font-size:14px;margin:0 0 20px;">You can resubmit after making the necessary changes.</p>
                    <a href="https://carsinstock.com/vehicles/add" style="background:#1E293B;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;">Submit Another Vehicle →</a>
                    <p style="color:#94A3B8;font-size:12px;margin:24px 0 0;">— The CarsInStock Team</p>
                  </div>
                </div>"""
                msg = Mail(from_email=Email('sales@carsinstock.com', 'CarsInStock'), to_emails=To(member['email']), subject=f"❌ Not approved: {vehicle.year} {vehicle.make} {vehicle.model}", html_content=html)
                sg.send(msg)
        except Exception as e:
            print(f"Rejection email error: {e}")
        flash(f"{vehicle.year} {vehicle.make} {vehicle.model} rejected.", "success")
        return redirect(url_for("admin.vehicles"))

    @bp.route("/vehicles/<int:vehicle_id>/dismiss-notification", methods=["POST"])
    def dismiss_vehicle_notification(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models import db
        vehicle = Vehicle.query.get(vehicle_id)
        if vehicle:
            vehicle.approval_notified = True
            db.session.commit()
        return ("", 204)

    @bp.route("/vehicles/<int:vehicle_id>/team-pick", methods=["POST"])
    def set_team_pick(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models import db
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        pick_user_id = request.form.get("pick_user_id", type=int)
        pick_blurb = request.form.get("pick_blurb", "").strip()[:150]
        vehicle.is_team_pick = True
        vehicle.pick_user_id = pick_user_id
        vehicle.pick_blurb = pick_blurb
        db.session.commit()
        return redirect(url_for("admin.vehicles"))

    @bp.route("/vehicles/<int:vehicle_id>/team-pick/remove", methods=["POST"])
    def remove_team_pick(vehicle_id):
        from app.models.vehicle import Vehicle
        from app.models import db
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        vehicle.is_team_pick = False
        vehicle.pick_user_id = None
        vehicle.pick_blurb = None
        db.session.commit()
        return redirect(url_for("admin.vehicles"))

    @bp.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
    @admin_required
    def delete_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        db.session.delete(vehicle)
        db.session.commit()
        flash("Vehicle deleted.", "success")
        return redirect(url_for("admin.vehicles"))


    @bp.route("/leads")
    @admin_required
    def leads():
        from app.models.lead import Lead
        all_leads = Lead.query.order_by(Lead.created_at.desc()).all()
        lead_data = []
        for l in all_leads:
            sp = Salesperson.query.get(l.salesperson_id)
            v = Vehicle.query.get(l.vehicle_id) if l.vehicle_id else None
            lead_data.append({"lead": l, "salesperson": sp, "vehicle": v})
        salespeople = Salesperson.query.all()
        return render_template("admin/leads.html", lead_data=lead_data, salespeople=salespeople)

    @bp.route("/email-log")
    @admin_required
    def email_log():
        return render_template("admin/email_log.html")

    @bp.route("/recruitment", methods=["GET", "POST"])
    @admin_required
    def recruitment():
        from app.utils.email import send_email, generate_unsubscribe_token
        if request.method == "POST":
            action = request.form.get("action")

            if action == "upload_csv":
                import csv, io
                file = request.files.get("csv_file")
                if file:
                    content = file.stream.read().decode("utf-8")
                    reader = csv.reader(io.StringIO(content))
                    count = 0
                    for row in reader:
                        if row and "@" in row[0]:
                            email = row[0].strip()
                            name = row[1].strip() if len(row) > 1 else ""
                            existing = db.session.execute(
                                db.text("SELECT id FROM recruitment_prospects WHERE email = :e"),
                                {"e": email}
                            ).fetchone()
                            if not existing:
                                db.session.execute(
                                    db.text("INSERT INTO recruitment_prospects (email, name, unsubscribed) VALUES (:e, :n, 0)"),
                                    {"e": email, "n": name}
                                )
                                count += 1
                    db.session.commit()
                    flash(f"Imported {count} new prospect(s).", "success")

            elif action == "send_recruitment":
                subject = request.form.get("subject", "")
                body_html = request.form.get("body", "")
                prospects = db.session.execute(
                    db.text("SELECT id, email, name FROM recruitment_prospects WHERE unsubscribed = 0")
                ).fetchall()
                sent = 0
                for p in prospects:
                    unsub_url = f"https://carsinstock.com/recruitment/unsubscribe/{p.id}"
                    full_html = f"""
                    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
                        <div style="text-align:center;padding:20px 0;border-bottom:3px solid #00C851;">
                            <h1 style="margin:0;font-size:28px;"><span style="color:#1E293B;font-weight:400;">Cars</span> <span style="color:#00C851;font-weight:700;">IN STOCK</span></h1>
                        </div>
                        <div style="padding:20px;">{body_html}</div>
                        <div style="border-top:1px solid #eee;padding:20px 0;text-align:center;">
                            <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>
                            <p style="color:#999;font-size:11px;"><a href="{unsub_url}" style="color:#999;">Unsubscribe</a></p>
                        </div>
                    </div>
                    """
                    try:
                        send_email(p.email, subject, full_html)
                        sent += 1
                    except:
                        pass
                flash(f"Recruitment email sent to {sent} prospect(s).", "success")

        prospects = db.session.execute(
            db.text("SELECT * FROM recruitment_prospects ORDER BY id DESC")
        ).fetchall()
        return render_template("admin/recruitment.html", prospects=prospects)

    @bp.route("/email-log-data")
    @admin_required
    def email_log_data():
        from flask import jsonify
        import os
        try:
            from sendgrid import SendGridAPIClient
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            response = sg.client.messages.get(query_params={"limit": 20})
            import json
            data = json.loads(response.body.decode())
            return jsonify(data)
        except Exception as e:
            return jsonify({"messages": [], "error": str(e)})


    @bp.route("/recruit", methods=["GET", "POST"])
    @admin_required
    def recruit():
        from app.models.recruitment_contact import RecruitmentContact
        import uuid, csv, io, json, math
        from datetime import datetime, timedelta

        RECRUIT_TEMPLATES = {
            "bdc_killer": {"name": "Template 1 — The BDC Killer", "subject": "{{First Name}} — would you like to sell more cars?", "body": "{{First Name}} —\n\nLet me ask you something.\n\nWhen a customer submits a lead on your dealer\u2019s website, who calls them first — you or the BDC?\n\nExactly.\n\nWhat if you had your own page — CarsInStock.com/your-name — with YOUR best cars, YOUR name, YOUR phone number? And when a buyer clicks \"I'm Interested\" — that lead goes to YOU. Not the BDC. Not the internet department. You.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It sets you apart from every other salesperson at your dealership — giving you the edge that nobody else has.\n\nYour cars. Your leads. Your money.\n\n14 days free. No credit card. No catch."},
            "ghost_car": {"name": "Template 2 — The Ghost Car", "subject": "{{First Name}} — how many ghost cars are on your website?", "body": "{{First Name}} —\n\nHow many cars on your dealer\u2019s website have already been sold?\n\nYour customers see them. They drive in. The car\u2019s gone. They leave. You never even knew they came.\n\nThat\u2019s the ghost car problem. And it\u2019s costing you deals every single week.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It gives you your own personal page with ONLY the cars you actually have — updated by you, fresh every 7 days. No ghost cars. No stale inventory. Just your best picks, ready to sell.\n\nThis is what sets you apart from every other salesperson. This is your edge.\n\n2 minutes to set up. 14 days free. Your name. Your cars. Your leads."},
            "top_performer": {"name": "Template 3 — The Top Performer", "subject": "{{First Name}} — would you like to sell more cars?", "body": "{{First Name}} —\n\nThe top salespeople don\u2019t wait for ups. They don\u2019t wait for the BDC to hand them a lead. They don\u2019t wait for anything.\n\nThey have their own system.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. CarsInStock gives you your own personal storefront — CarsInStock.com/your-name — with the cars YOU choose, an AI assistant that talks to buyers for you 24/7, and every lead goes directly to your phone. Not the dealer\u2019s. Yours.\n\nThis is what sets you apart from every other salesperson at your store. This is the edge.\n\nFree for 14 days. Set up in 2 minutes. No credit card needed.\n\nThe ones who move first win."},
            "rookie": {"name": "Template 4 — The Rookie", "subject": "{{First Name}} — want an unfair advantage?", "body": "{{First Name}} —\n\nWhen you\u2019re new in this business, the deck is stacked against you. The veterans get the best ups. The BDC feeds leads to their favorites. And your name? Nobody knows it yet.\n\nSo how do you compete?\n\nYou build your own lane.\n\nCarsInStock gives you your own personal storefront — CarsInStock.com/your-name — where YOU pick the cars, YOU get the leads, and buyers come to YOU. Not the guy who\u2019s been there 15 years. You.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It gives you the edge that levels the playing field — the same tools the top producers wish they had when they started.\n\n14 days free. Set up in 2 minutes. No credit card.\n\nStart building your name now."},
            "personal_brand": {"name": "Template 5 — The Personal Brand", "subject": "{{First Name}} — where do your customers find YOU?", "body": "{{First Name}} —\n\nQuick question. If a customer wants to buy a car from YOU specifically — not your dealership, not your coworker, YOU — where do they go?\n\nYour dealer\u2019s website? Your name isn\u2019t even on it.\nFacebook? Buried under memes and marketplace posts.\nInstagram? Maybe, if they scroll long enough.\n\nWhat if you had one link — CarsInStock.com/your-name — with your face, your phone number, your best cars, and a button that says \"I'm Interested\"? One link you put in your bio, your email signature, your business card, your texts.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It\u2019s your professional online identity as a car salesperson — and it\u2019s the edge that sets you apart from everyone else at your store.\n\n14 days free. 2 minutes to set up. Your name. Your brand. Your money."},
            "money_play": {"name": "Template 6 — The Money Play", "subject": "{{First Name}} — would you like to sell more cars?", "body": "{{First Name}} —\n\nWhat if you could sell 2 more cars a month?\n\nAt $300-$500 a pop in commission, that\u2019s an extra $7,000\u201312,000 a year. From one tool that takes 2 minutes to set up.\n\nCarsInStock gives you your own personal page — CarsInStock.com/your-name. You post your best cars. Buyers find you. They click \"I'm Interested\" and the lead goes straight to your phone. No BDC. No internet manager. Just you and the customer.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It\u2019s the edge that sets you apart — your own storefront, your own leads, your own brand.\n\nAnd it costs less than one car deal a year.\n\n14 days free. No credit card. No catch.\n\nYour cars. Your leads. Your money."},
            "follow_up": {"name": "Template 7 — The Follow-Up", "subject": "{{First Name}} — still thinking about it?", "body": "{{First Name}} —\n\nI reached out a few days ago about CarsInStock. No pressure — just wanted to make sure you saw it.\n\nWould you like to sell more cars? That\u2019s what our program does.\n\nHere\u2019s the quick version: you get your own page with your cars, your name, and your phone number. Buyers contact you directly. No BDC, no middleman. Takes 2 minutes to set up and it\u2019s free for 14 days.\n\nIf it\u2019s not for you, no worries. But the salespeople who move first get the best URLs."},
            "scarcity": {"name": "Template 8 — The Scarcity Play", "subject": "{{First Name}} — someone at your dealership is going to grab this first", "body": "{{First Name}} —\n\nWe\u2019re opening up CarsInStock to salespeople in your area.\n\nHere\u2019s the thing — there\u2019s only one CarsInStock.com/your-name. Once someone at your store takes their URL, it\u2019s gone.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. Your own personal storefront. Your cars. Your leads. An AI chatbot that talks to buyers for you 24/7. And every lead goes to you — not the BDC.\n\nThis is the edge that sets you apart.\n\nClaim your page before someone else does.\n\n14 days free. 2 minutes to set up. No credit card."},
            "customer_email": {"name": "Template 9 — The Customer Email", "subject": "{{First Name}} — when's the last time you emailed your customers?", "body": "{{First Name}} —\n\nYou\u2019ve sold how many cars — 100? 200? 500?\n\nEvery one of those customers knows your name. Trusts you. Would buy from you again.\n\nBut when\u2019s the last time you reached out to them? When\u2019s the last time you said \"Hey, here\u2019s what I\u2019ve got on my lot right now\"?\n\nCarsInStock lets you do exactly that. Upload your customer list, hit one button, and send your personal storefront to up to 50 people a day. Your face. Your cars. Your phone number. One click.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It\u2019s the edge — your own page, your own leads, and now a way to reach every customer you\u2019ve ever sold to.\n\n14 days free. 2 minutes to set up."},
            "ai_angle": {"name": "Template 10 — The AI Angle", "subject": "{{First Name}} — what if AI could sell cars for you while you sleep?", "body": "{{First Name}} —\n\nWhat happens when a customer visits your dealer\u2019s website at 11 PM? Nothing. Nobody\u2019s there. That lead is gone by morning.\n\nWhat if you had an AI assistant on YOUR personal page that talks to buyers 24/7 — answers their questions, tells them about your cars, and captures their info so you can follow up first thing in the morning?\n\nThat\u2019s CarsInStock.\n\nYour own storefront. Your cars. Your AI chatbot. Your leads. All working for you while you sleep.\n\nWould you like to sell more cars?\n\nOur program is designed to do exactly that. It\u2019s the edge that puts you ahead of every other salesperson who clocks out at 6 PM and hopes for the best.\n\nThe future of car sales is personal. Be first.\n\n14 days free. Set up in 2 minutes. No credit card."}
        }

        def build_recruitment_email(body_text, tracking_id):
            import re
            paragraphs = body_text.strip().split("\n\n")
            html_body = ""
            for p in paragraphs:
                p = p.replace("\n", "<br>")
                html_body += '<p style="color:#333;font-size:15px;line-height:1.7;margin-bottom:16px;">' + p + '</p>'
            html_body = re.sub(r'CarsInStock\.com/[-\w]+', lambda m: '<span style="color:#00C851;font-weight:600;">' + m.group(0) + '</span>', html_body)
            unsub = '<p style="color:#94A3B8;font-size:11px;margin-top:12px;"><a href="https://carsinstock.com/recruit/unsubscribe/' + tracking_id + '" style="color:#94A3B8;text-decoration:underline;">Unsubscribe</a></p>'
            return '<div style="max-width:600px;margin:0 auto;font-family:Inter,Arial,sans-serif;"><div style="background:#1E293B;padding:24px;text-align:center;border-radius:12px 12px 0 0;"><h1 style="margin:0;font-size:28px;"><span style="color:white;">Cars</span><span style="color:#00C851;">InStock</span></h1><p style="color:#94A3B8;font-size:14px;margin:6px 0 0;">Real Salespeople. Real Inventory. Real Fresh.</p></div><div style="height:4px;background:linear-gradient(to right,#00C851,#1E293B);"></div><div style="padding:32px 24px;background:white;">' + html_body + '<div style="text-align:center;margin:30px 0;"><a href="https://carsinstock.com/track/click/' + tracking_id + '" style="display:inline-block;background:#00C851;color:white;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600;text-decoration:none;">See the Demo &rarr;</a></div></div><div style="border-top:1px solid #E2E8F0;padding:20px;text-align:center;background:#F8FAFC;border-radius:0 0 12px 12px;"><p style="color:#64748B;font-size:13px;margin:0;">Fresh Cars. Real People.</p><p style="color:#94A3B8;font-size:12px;margin:4px 0 0;">CarsInStock.com</p><p style="color:#94A3B8;font-size:11px;margin-top:8px;">&copy; 2026 CarsInStock LLC. All rights reserved.</p>' + unsub + '</div></div>'

        def replace_merge_vars(text, contact):
            text = text.replace("{{First Name}}", contact.first_name or "")
            text = text.replace("{{Last Name}}", contact.last_name or "")
            text = text.replace("{{Dealership Name}}", contact.dealership_name or "")
            text = text.replace("{{City/State}}", contact.city_state or "")
            text = text.replace("{{Custom}}", contact.custom_field or "")
            return text

        def send_recruitment_email(to_email, subject, html_content):
            import os
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Email, To
            try:
                sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
                from_email = Email(email='sales@carsinstock.com', name='CarsInStock')
                message = Mail(from_email=from_email, to_emails=To(to_email), subject=subject, html_content=html_content)
                response = sg.send(message)
                print("Recruitment email sent to " + to_email + ", status: " + str(response.status_code))
                return response.status_code in [200, 201, 202]
            except Exception as e:
                print("Recruitment email error: " + str(e))
                return False

        action = request.form.get("action", "")

        if request.method == "POST":
            if action == "add_contact":
                email = request.form.get("email", "").strip().lower()
                if not email or not request.form.get("first_name", "").strip():
                    flash("First name and email are required.", "error")
                else:
                    existing = RecruitmentContact.query.filter_by(email=email).first()
                    if existing:
                        flash("Contact with email " + email + " already exists.", "error")
                    else:
                        c = RecruitmentContact(first_name=request.form.get("first_name", "").strip(), last_name=request.form.get("last_name", "").strip(), email=email, dealership_name=request.form.get("dealership_name", "").strip(), city_state=request.form.get("city_state", "").strip(), custom_field=request.form.get("custom_field", "").strip())
                        db.session.add(c)
                        db.session.commit()
                        flash("Contact " + c.first_name + " added.", "success")

            elif action == "import_csv":
                file = request.files.get("csv_file")
                if file and file.filename.endswith('.csv'):
                    content = file.stream.read().decode("utf-8")
                    reader = csv.DictReader(io.StringIO(content))
                    imported = 0
                    skipped = 0
                    for row in reader:
                        email = row.get("email", "").strip().lower()
                        if not email:
                            skipped += 1
                            continue
                        existing = RecruitmentContact.query.filter_by(email=email).first()
                        if existing:
                            skipped += 1
                            continue
                        c = RecruitmentContact(first_name=row.get("first_name", "").strip(), last_name=row.get("last_name", "").strip(), email=email, dealership_name=row.get("dealership_name", "").strip(), city_state=row.get("city_state", "").strip(), custom_field=row.get("custom_field", "").strip())
                        db.session.add(c)
                        imported += 1
                    db.session.commit()
                    flash("Imported " + str(imported) + " new contacts, " + str(skipped) + " duplicates skipped.", "success")
                else:
                    flash("Please upload a valid CSV file.", "error")

            elif action == "delete_selected":
                ids = request.form.getlist("selected_ids")
                if ids:
                    RecruitmentContact.query.filter(RecruitmentContact.id.in_(ids)).delete(synchronize_session=False)
                    db.session.commit()
                    flash("Deleted " + str(len(ids)) + " contacts.", "success")

            elif action == "send_test":
                subject = request.form.get("subject", "")
                body = request.form.get("body", "")
                class DummyContact:
                    first_name = "Eddie"
                    last_name = "Test"
                    dealership_name = "Test Motors"
                    city_state = "Toms River, NJ"
                    custom_field = "Sample"
                dummy = DummyContact()
                test_subject = replace_merge_vars(subject, dummy)
                test_body = replace_merge_vars(body, dummy)
                html = build_recruitment_email(test_body, "test-preview")
                success = send_recruitment_email("edward@carsinstock.com", test_subject, html)
                if success:
                    flash("Test email sent to edward@carsinstock.com", "success")
                else:
                    flash("Failed to send test email.", "error")

            elif action == "send_campaign":
                template_name = request.form.get("template_name", "Custom Email")
                subject = request.form.get("subject", "")
                body = request.form.get("body", "")
                recipient_filter = request.form.get("recipient_filter", "all")
                batch_mode = request.form.get("batch_mode", "all_at_once")
                batch_size = int(request.form.get("batch_size", "10"))
                selected_ids_str = request.form.get("campaign_selected_ids", "")

                if recipient_filter == "new_only":
                    contacts_to_send = RecruitmentContact.query.filter_by(status="new").all()
                elif recipient_filter == "selected":
                    sel_ids = [int(x) for x in selected_ids_str.split(",") if x.strip()]
                    contacts_to_send = RecruitmentContact.query.filter(RecruitmentContact.id.in_(sel_ids), RecruitmentContact.status != "unsubscribed").all()
                else:
                    contacts_to_send = RecruitmentContact.query.filter(RecruitmentContact.status != "unsubscribed").all()

                if not contacts_to_send:
                    flash("No contacts match the selected criteria.", "error")
                    return redirect(url_for("admin.recruit"))

                if batch_mode == "all_at_once":
                    sent = 0
                    failed = 0
                    for c in contacts_to_send:
                        tracking_id = str(uuid.uuid4())[:12]
                        c.tracking_id = tracking_id
                        c_subject = replace_merge_vars(subject, c)
                        c_body = replace_merge_vars(body, c)
                        html = build_recruitment_email(c_body, tracking_id)
                        success = send_recruitment_email(c.email, c_subject, html)
                        if success:
                            c.status = "sent"
                            c.sent_at = datetime.utcnow()
                            c.template_used = template_name
                            sent += 1
                        else:
                            failed += 1
                    db.session.commit()
                    flash("Campaign sent: " + str(sent) + " delivered, " + str(failed) + " failed.", "success" if failed == 0 else "warning")
                else:
                    contact_ids = [c.id for c in contacts_to_send]
                    total_batches = math.ceil(len(contact_ids) / batch_size)
                    first_batch = contact_ids[:batch_size]
                    remaining = contact_ids[batch_size:]
                    sent = 0
                    failed = 0
                    for cid in first_batch:
                        c = RecruitmentContact.query.get(cid)
                        if not c:
                            continue
                        tracking_id = str(uuid.uuid4())[:12]
                        c.tracking_id = tracking_id
                        c_subject = replace_merge_vars(subject, c)
                        c_body = replace_merge_vars(body, c)
                        html = build_recruitment_email(c_body, tracking_id)
                        success = send_recruitment_email(c.email, c_subject, html)
                        if success:
                            c.status = "sent"
                            c.sent_at = datetime.utcnow()
                            c.template_used = template_name
                            sent += 1
                        else:
                            failed += 1
                    if remaining:
                        next_send = datetime.utcnow() + timedelta(days=1)
                        db.engine.execute(db.text("INSERT INTO batch_queue (template_key, subject, body, recipient_filter, selected_ids, batch_size, total_contacts, batches_sent, total_batches, status, next_send_at) VALUES (:tk, :subj, :body, :rf, :sids, :bs, :tc, :bsent, :tb, :st, :ns)"), {"tk": request.form.get("template_key", "custom"), "subj": subject, "body": body, "rf": recipient_filter, "sids": json.dumps(remaining), "bs": batch_size, "tc": len(contact_ids), "bsent": 1, "tb": total_batches, "st": "active", "ns": next_send})
                    db.session.commit()
                    flash("Batch 1 of " + str(total_batches) + " sent (" + str(sent) + " delivered, " + str(failed) + " failed). Next batch sends tomorrow.", "success")

            return redirect(url_for("admin.recruit"))

        # GET request
        contacts = RecruitmentContact.query.order_by(RecruitmentContact.created_at.desc()).all()
        total = len(contacts)
        total_sent = len([c for c in contacts if c.status != "new"])
        total_clicked = len([c for c in contacts if c.status == "clicked"])
        click_rate = round((total_clicked / total_sent * 100), 1) if total_sent > 0 else 0
        count_new = len([c for c in contacts if c.status == "new"])
        dealerships = sorted(set(c.dealership_name for c in contacts if c.dealership_name))
        sent_contacts = sorted([c for c in contacts if c.status != "new"], key=lambda x: x.clicked_at or x.sent_at or x.created_at, reverse=True)

        try:
            active_batches = db.engine.execute(db.text("SELECT * FROM batch_queue WHERE status = 'active'")).fetchall()
        except:
            active_batches = []

        contacts_json = json.dumps([{"id": c.id, "first_name": c.first_name, "last_name": c.last_name or "", "email": c.email, "dealership_name": c.dealership_name or "", "city_state": c.city_state or "", "status": c.status, "sent_at": c.sent_at.strftime("%m/%d/%Y") if c.sent_at else "", "clicked_at": c.clicked_at.strftime("%m/%d/%Y") if c.clicked_at else "", "template_used": c.template_used or ""} for c in contacts])
        templates_json = json.dumps({k: {"name": v["name"], "subject": v["subject"], "body": v["body"]} for k, v in RECRUIT_TEMPLATES.items()})

        return render_template("admin/recruit.html", contacts=contacts, total=total, total_sent=total_sent, total_clicked=total_clicked, click_rate=click_rate, count_new=count_new, dealerships=dealerships, sent_contacts=sent_contacts, active_batches=active_batches, contacts_json=contacts_json, templates_json=templates_json, templates=RECRUIT_TEMPLATES)



    @bp.route("/lead-engine")
    @admin_required
    def lead_engine():
        import json
        # Stats
        try:
            total_dealerships = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_dealerships")).scalar()
            total_contacts = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts")).scalar()
            pending_count = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE status='pending'")).scalar()
            approved_count = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE status='approved'")).scalar()
            pushed_count = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE recruit_synced=1")).scalar()
            rejected_count = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE status='rejected'")).scalar()
            raw_domains = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_dealerships WHERE status='raw'")).scalar()
            daily_limit = db.engine.execute(db.text("SELECT value FROM lead_engine_settings WHERE key='daily_send_limit'")).scalar() or '10'
            recent_runs = db.engine.execute(db.text("SELECT * FROM lead_engine_runs ORDER BY created_at DESC LIMIT 10")).fetchall()
            pending_contacts = db.engine.execute(db.text("SELECT c.*, d.name as dealer_name FROM lead_engine_contacts c LEFT JOIN lead_engine_dealerships d ON c.dealership_id = d.id WHERE c.status='pending' ORDER BY c.created_at DESC LIMIT 50")).fetchall()
            approved_contacts = db.engine.execute(db.text("SELECT * FROM lead_engine_contacts WHERE status='approved' ORDER BY approved_at DESC")).fetchall()
        except Exception as e:
            print("Lead engine stats error: " + str(e))
            total_dealerships = total_contacts = pending_count = approved_count = pushed_count = rejected_count = raw_domains = 0
            daily_limit = '10'
            recent_runs = []
            pending_contacts = []
            approved_contacts = []
        return render_template("admin/lead_engine.html",
            total_dealerships=total_dealerships, total_contacts=total_contacts,
            pending_count=pending_count, approved_count=approved_count,
            pushed_count=pushed_count, rejected_count=rejected_count,
            raw_domains=raw_domains, daily_limit=daily_limit,
            recent_runs=recent_runs, pending_contacts=pending_contacts,
            approved_contacts=approved_contacts)

    @bp.route("/lead-engine/scrape", methods=["POST"])
    @admin_required
    def le_scrape():
        import os, requests, json
        from datetime import datetime
        search_term = request.form.get("search_term", "car dealerships")
        search_location = request.form.get("search_location", "Toms River, NJ")
        from dotenv import load_dotenv
        load_dotenv("/home/eddie/carsinstock/.env")
        api_key = os.environ.get("APIFY_API_KEY")
        if not api_key:
            return jsonify({"error": "APIFY_API_KEY not set"}), 500
        # Create run record
        db.engine.execute(db.text("INSERT INTO lead_engine_runs (run_type, search_term, search_location, status, created_at) VALUES ('apify_scrape', :st, :sl, 'running', :now)"),
            {"st": search_term, "sl": search_location, "now": datetime.utcnow()})
        run_row = db.engine.execute(db.text("SELECT id FROM lead_engine_runs ORDER BY id DESC LIMIT 1")).fetchone()
        run_id = run_row.id
        try:
            resp = requests.post(
                "https://api.apify.com/v2/acts/compass~crawler-google-places/runs",
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json={
                    "searchStringsArray": [search_term],
                    "locationQuery": search_location,
                    "maxCrawledPlacesPerSearch": 10,
                    "language": "en"
                },
                timeout=30
            )
            data = resp.json()
            if isinstance(data, str):
                import json as json_mod
                data = json_mod.loads(data)
            apify_run_id = data.get("data", {}).get("id", "")
            return jsonify({"success": True, "run_id": run_id, "apify_run_id": apify_run_id})
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            with open("/home/eddie/carsinstock/scrape_error.log", "a") as ef:
                ef.write(err_detail + "\n")
            try:
                db.engine.execute(db.text("UPDATE lead_engine_runs SET status='failed', error_message=:err, completed_at=:now WHERE id=:rid"),
                    {"err": str(e), "now": datetime.utcnow(), "rid": run_id})
            except:
                pass
            return jsonify({"error": str(e)}), 500

    @bp.route("/lead-engine/scrape/status/<apify_run_id>")
    @admin_required
    def le_scrape_status(apify_run_id):
        import os, requests, json
        from datetime import datetime
        from urllib.parse import urlparse
        from dotenv import load_dotenv
        load_dotenv("/home/eddie/carsinstock/.env")
        api_key = os.environ.get("APIFY_API_KEY")
        try:
            resp = requests.get(
                "https://api.apify.com/v2/actor-runs/" + apify_run_id,
                headers={"Authorization": "Bearer " + api_key},
                timeout=15
            )
            status = resp.json().get("data", {}).get("status", "RUNNING")
            if status == "SUCCEEDED":
                # Fetch results
                results_resp = requests.get(
                    "https://api.apify.com/v2/actor-runs/" + apify_run_id + "/dataset/items",
                    headers={"Authorization": "Bearer " + api_key},
                    timeout=30
                )
                items = results_resp.json()
                inserted = 0
                skipped = 0
                for item in items:
                    name = item.get("title", "")
                    website = item.get("website") or item.get("url") or ""
                    if not website:
                        skipped += 1
                        continue
                    # Extract domain
                    try:
                        parsed = urlparse(website if website.startswith("http") else "https://" + website)
                        domain = parsed.netloc.replace("www.", "").lower()
                    except:
                        skipped += 1
                        continue
                    if not domain:
                        skipped += 1
                        continue
                    # Check duplicate domain
                    existing = db.engine.execute(db.text("SELECT id FROM lead_engine_dealerships WHERE domain=:d"), {"d": domain}).fetchone()
                    if existing:
                        skipped += 1
                        continue
                    address = item.get("address") or item.get("street") or ""
                    city = item.get("city") or ""
                    state = item.get("state") or ""
                    phone = item.get("phone") or item.get("phoneUnformatted") or ""
                    search_term = item.get("searchString") or ""
                    db.engine.execute(db.text("INSERT INTO lead_engine_dealerships (name, website, domain, address, city, state, phone, search_term, search_location, status, created_at) VALUES (:n, :w, :d, :a, :c, :s, :p, :st, :sl, 'raw', :now)"),
                        {"n": name, "w": website, "d": domain, "a": address, "c": city, "s": state, "p": phone, "st": search_term, "sl": request.args.get("location", ""), "now": datetime.utcnow()})
                    inserted += 1
                # Update run record
                db.engine.execute(db.text("UPDATE lead_engine_runs SET status='complete', records_found=:rf, completed_at=:now WHERE run_type='apify_scrape' AND status='running' ORDER BY id DESC LIMIT 1"),
                    {"rf": inserted, "now": datetime.utcnow()})
                return jsonify({"status": "SUCCEEDED", "inserted": inserted, "skipped": skipped})
            return jsonify({"status": status})
        except Exception as e:
            return jsonify({"status": "ERROR", "error": str(e)}), 500

    @bp.route("/lead-engine/discover", methods=["POST"])
    @admin_required
    def le_discover():
        import os, requests, json, time, re
        from datetime import datetime
        from dotenv import load_dotenv
        load_dotenv("/home/eddie/carsinstock/.env")
        api_key = os.environ.get("ANYMAILFINDER_API_KEY")
        if not api_key:
            return jsonify({"error": "ANYMAILFINDER_API_KEY not set"}), 500
        # Get raw domains
        domains = db.engine.execute(db.text("SELECT id, name, domain, city, state FROM lead_engine_dealerships WHERE status='raw'")).fetchall()
        if not domains:
            return jsonify({"error": "No raw domains to process"}), 400
        # Create run record
        db.engine.execute(db.text("INSERT INTO lead_engine_runs (run_type, search_term, records_found, emails_found, status, created_at) VALUES ('anymailfinder', :st, :rf, 0, 'running', :now)"),
            {"st": str(len(domains)) + " domains", "rf": len(domains), "now": datetime.utcnow()})
        GENERIC_PREFIXES = ['info', 'sales', 'service', 'parts', 'finance', 'reception', 'contact', 'support', 'admin', 'hr', 'marketing', 'webmaster', 'noreply', 'no-reply']
        total_emails = 0
        for d in domains:
            try:
                resp = requests.post(
                    "https://api.anymailfinder.com/v5.0/search/company.json",
                    headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                    json={"domain": d.domain},
                    timeout=15
                )
                data = resp.json()
                if not data.get("success"):
                    db.engine.execute(db.text("UPDATE lead_engine_dealerships SET status='processed' WHERE id=:did"), {"did": d.id})
                    time.sleep(0.5)
                    continue
                results_obj = data.get("results", {})
                emails_list = results_obj.get("emails", []) if isinstance(results_obj, dict) else []
                validation = results_obj.get("validation", "unknown") if isinstance(results_obj, dict) else "unknown"
                for r in emails_list:
                    email = str(r).lower().strip()
                    if not email or "@" not in email:
                        continue
                    prefix = email.split("@")[0]
                    if prefix in GENERIC_PREFIXES:
                        continue
                    # Parse name from email
                    first_name = ""
                    last_name = ""
                    if "." in prefix:
                        parts = prefix.split(".")
                        first_name = parts[0].capitalize()
                        last_name = parts[-1].capitalize()
                    elif "_" in prefix:
                        parts = prefix.split("_")
                        first_name = parts[0].capitalize()
                        last_name = parts[-1].capitalize()
                    elif len(prefix) > 1 and prefix[0].isalpha():
                        # Single word like 'kkowalik' -> First: K, Last: Kowalik
                        first_name = prefix[0].upper()
                        last_name = prefix[1:].capitalize()
                    else:
                        first_name = prefix.capitalize()
                    city_state = ""
                    if d.city and d.state:
                        city_state = d.city + ", " + d.state
                    elif d.city:
                        city_state = d.city
                    try:
                        db.engine.execute(db.text("INSERT OR IGNORE INTO lead_engine_contacts (dealership_id, first_name, last_name, email, email_status, dealership_name, city_state, status, created_at) VALUES (:did, :fn, :ln, :em, :es, :dn, :cs, 'pending', :now)"),
                            {"did": d.id, "fn": first_name, "ln": last_name, "em": email, "es": validation if validation != "valid" else "verified", "dn": d.name, "cs": city_state, "now": datetime.utcnow()})
                        total_emails += 1
                    except:
                        pass
                db.engine.execute(db.text("UPDATE lead_engine_dealerships SET status='processed' WHERE id=:did"), {"did": d.id})
                time.sleep(0.5)
            except Exception as e:
                print("Anymailfinder error for " + d.domain + ": " + str(e))
                continue
        # Update run
        db.engine.execute(db.text("UPDATE lead_engine_runs SET status='complete', emails_found=:ef, completed_at=:now WHERE run_type='anymailfinder' AND status='running' ORDER BY id DESC LIMIT 1"),
            {"ef": total_emails, "now": datetime.utcnow()})
        return jsonify({"success": True, "emails_found": total_emails, "domains_processed": len(domains)})

    @bp.route("/lead-engine/contacts/approve", methods=["POST"])
    @admin_required
    def le_approve():
        import json
        from datetime import datetime
        ids = request.json.get("ids", [])
        if not ids:
            return jsonify({"error": "No contacts selected"}), 400
        for cid in ids:
            db.engine.execute(db.text("UPDATE lead_engine_contacts SET status='approved', approved_at=:now WHERE id=:cid AND status='pending'"),
                {"now": datetime.utcnow(), "cid": cid})
        return jsonify({"success": True, "approved": len(ids)})

    @bp.route("/lead-engine/contacts/reject", methods=["POST"])
    @admin_required
    def le_reject():
        import json
        ids = request.json.get("ids", [])
        if not ids:
            return jsonify({"error": "No contacts selected"}), 400
        for cid in ids:
            db.engine.execute(db.text("UPDATE lead_engine_contacts SET status='rejected' WHERE id=:cid AND status='pending'"), {"cid": cid})
        return jsonify({"success": True, "rejected": len(ids)})

    @bp.route("/lead-engine/contacts/approve-all", methods=["POST"])
    @admin_required
    def le_approve_all():
        import json
        from datetime import datetime
        result = db.engine.execute(db.text("UPDATE lead_engine_contacts SET status='approved', approved_at=:now WHERE status='pending'"), {"now": datetime.utcnow()})
        return jsonify({"success": True})

    @bp.route("/lead-engine/contacts/edit", methods=["POST"])
    @admin_required
    def le_edit_contact():
        import json
        cid = request.json.get("id")
        db.engine.execute(db.text("UPDATE lead_engine_contacts SET first_name=:fn, last_name=:ln, dealership_name=:dn, city_state=:cs, custom=:cu WHERE id=:cid"),
            {"fn": request.json.get("first_name", ""), "ln": request.json.get("last_name", ""), "dn": request.json.get("dealership_name", ""), "cs": request.json.get("city_state", ""), "cu": request.json.get("custom", ""), "cid": cid})
        return jsonify({"success": True})

    @bp.route("/lead-engine/push-to-recruit", methods=["POST"])
    @admin_required
    def le_push_to_recruit():
        import json
        from datetime import datetime
        from app.models.recruitment_contact import RecruitmentContact
        contacts = db.engine.execute(db.text("SELECT * FROM lead_engine_contacts WHERE status='approved' AND recruit_synced=0")).fetchall()
        pushed = 0
        skipped = 0
        for c in contacts:
            existing = RecruitmentContact.query.filter_by(email=c.email).first()
            if existing:
                db.engine.execute(db.text("UPDATE lead_engine_contacts SET recruit_synced=1, recruit_contact_id=:rcid WHERE id=:cid"), {"rcid": existing.id, "cid": c.id})
                skipped += 1
                continue
            rc = RecruitmentContact(first_name=c.first_name or "", last_name=c.last_name or "", email=c.email, dealership_name=c.dealership_name or "", city_state=c.city_state or "", custom_field=c.custom or "")
            db.session.add(rc)
            db.session.flush()
            db.engine.execute(db.text("UPDATE lead_engine_contacts SET recruit_synced=1, recruit_contact_id=:rcid WHERE id=:cid"), {"rcid": rc.id, "cid": c.id})
            pushed += 1
        db.session.commit()
        return jsonify({"success": True, "pushed": pushed, "skipped": skipped})

    @bp.route("/lead-engine/export-csv")
    @admin_required
    def le_export_csv():
        import csv, io
        from datetime import datetime
        from flask import Response
        contacts = db.engine.execute(db.text("SELECT first_name, last_name, email, dealership_name, city_state, custom FROM lead_engine_contacts WHERE status='approved'")).fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["first_name", "last_name", "email", "dealership_name", "city_state", "custom_field"])
        for c in contacts:
            writer.writerow([c.first_name or "", c.last_name or "", c.email, c.dealership_name or "", c.city_state or "", c.custom or ""])
        filename = "CarsInStock_Leads_" + datetime.utcnow().strftime("%Y-%m-%d") + ".csv"
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=" + filename})

    @bp.route("/lead-engine/import-csv", methods=["POST"])
    @admin_required
    def le_import_csv():
        import csv, io, json
        from datetime import datetime
        file = request.files.get("csv_file")
        if not file or not file.filename.endswith(".csv"):
            return jsonify({"error": "Invalid CSV file"}), 400
        content = file.stream.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        imported = 0
        skipped = 0
        for row in reader:
            email = row.get("email", "").strip().lower()
            if not email:
                skipped += 1
                continue
            # Check both tables
            existing_le = db.engine.execute(db.text("SELECT id FROM lead_engine_contacts WHERE email=:e"), {"e": email}).fetchone()
            existing_rc = db.engine.execute(db.text("SELECT id FROM recruitment_contacts WHERE email=:e"), {"e": email}).fetchone()
            if existing_le or existing_rc:
                skipped += 1
                continue
            db.engine.execute(db.text("INSERT INTO lead_engine_contacts (first_name, last_name, email, dealership_name, city_state, custom, status, created_at) VALUES (:fn, :ln, :em, :dn, :cs, :cu, 'pending', :now)"),
                {"fn": row.get("first_name", ""), "ln": row.get("last_name", ""), "em": email, "dn": row.get("dealership_name", ""), "cs": row.get("city_state", ""), "cu": row.get("custom_field", row.get("custom", "")), "now": datetime.utcnow()})
            imported += 1
        return jsonify({"success": True, "imported": imported, "skipped": skipped})

    @bp.route("/lead-engine/send-limit", methods=["POST"])
    @admin_required
    def le_send_limit():
        import json
        limit = request.json.get("limit", 10)
        if int(limit) > 100:
            limit = 100
        db.engine.execute(db.text("UPDATE lead_engine_settings SET value=:v WHERE key='daily_send_limit'"), {"v": str(limit)})
        return jsonify({"success": True, "limit": limit})

    @bp.route("/lead-engine/stats")
    @admin_required
    def le_stats():
        import json
        total_dealerships = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_dealerships")).scalar()
        total_contacts = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts")).scalar()
        pending = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE status='pending'")).scalar()
        approved = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE status='approved'")).scalar()
        pushed = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE recruit_synced=1")).scalar()
        rejected = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_contacts WHERE status='rejected'")).scalar()
        raw = db.engine.execute(db.text("SELECT COUNT(*) FROM lead_engine_dealerships WHERE status='raw'")).scalar()
        return jsonify({"total_dealerships": total_dealerships, "total_contacts": total_contacts, "pending": pending, "approved": approved, "pushed": pushed, "rejected": rejected, "raw_domains": raw})

    @bp.route("/recruitment/unsubscribe/<int:prospect_id>")
    def recruitment_unsubscribe(prospect_id):
        try:
            db.engine.execute(
                db.text("UPDATE recruitment_prospects SET unsubscribed = 1 WHERE id = :pid"),
                {"pid": prospect_id}
            )
        except:
            pass
        return render_template("admin/recruitment_unsub.html")

    @bp.route("/blast-analytics")
    @admin_required
    def blast_analytics():
        import sqlite3
        conn = sqlite3.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        blasts = cur.execute("""
            SELECT id, subject, blast_type, sent_at, recipient_count
            FROM email_blasts
            ORDER BY sent_at DESC
        """).fetchall()

        analytics = []
        for b in blasts:
            bid = b['id']
            total = b['recipient_count'] or 0
            opens  = cur.execute("SELECT COUNT(*) FROM blast_events WHERE blast_id=? AND event_type='open'", (bid,)).fetchone()[0]
            clicks = cur.execute("SELECT COUNT(*) FROM blast_events WHERE blast_id=? AND event_type='click'", (bid,)).fetchone()[0]
            unsubs = cur.execute("SELECT COUNT(*) FROM blast_events WHERE blast_id=? AND event_type='unsubscribe'", (bid,)).fetchone()[0]
            spams  = cur.execute("SELECT COUNT(*) FROM blast_events WHERE blast_id=? AND event_type='spam'", (bid,)).fetchone()[0]
            top_link = cur.execute("""
                SELECT url_clicked FROM blast_events
                WHERE blast_id=? AND event_type='click' AND url_clicked IS NOT NULL
                GROUP BY url_clicked ORDER BY COUNT(*) DESC LIMIT 1
            """, (bid,)).fetchone()
            analytics.append({
                'id':         bid,
                'subject':    b['subject'] or '(no subject)',
                'blast_type': b['blast_type'],
                'sent_at':    b['sent_at'],
                'total':      total,
                'opens':      opens,
                'clicks':     clicks,
                'unsubs':     unsubs,
                'spams':      spams,
                'open_rate':  round(opens  / total * 100, 1) if total else 0,
                'click_rate': round(clicks / total * 100, 1) if total else 0,
                'unsub_rate': round(unsubs / total * 100, 1) if total else 0,
                'top_link':   top_link[0] if top_link else None,
            })

        conn.close()
        return render_template('admin/blast_analytics.html', analytics=analytics)
