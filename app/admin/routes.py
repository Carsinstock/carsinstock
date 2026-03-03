from flask import render_template, session, redirect, flash, request, url_for
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

    @bp.route("/")
    @admin_required
    def dashboard():
        user_count = User.query.count()
        vehicle_count = Vehicle.query.count()
        lead_count = Lead.query.count()
        sp_count = Salesperson.query.count()
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        return render_template("admin/dashboard.html",
            user_count=user_count, vehicle_count=vehicle_count,
            lead_count=lead_count, sp_count=sp_count, recent_users=recent_users)

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
        all_vehicles = Vehicle.query.order_by(Vehicle.created_at.desc()).all()
        return render_template("admin/vehicles.html", vehicles=all_vehicles)

    @bp.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
    @admin_required
    def delete_vehicle(vehicle_id):
        vehicle = Vehicle.query.get_or_404(vehicle_id)
        db.session.delete(vehicle)
        db.session.commit()
        flash("Vehicle deleted.", "success")
        return redirect(url_for("admin.vehicles"))

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
            paragraphs = body_text.strip().split("\n\n")
            html_body = ""
            for p in paragraphs:
                p = p.replace("\n", "<br>")
                html_body += '<p style="color:#333;font-size:15px;line-height:1.7;margin-bottom:16px;">' + p + '</p>'
            return '<div style="max-width:600px;margin:0 auto;font-family:Inter,Arial,sans-serif;"><div style="background:#1E293B;padding:24px;text-align:center;border-radius:12px 12px 0 0;"><h1 style="margin:0;font-size:28px;"><span style="color:white;">Cars</span><span style="color:#00C851;">InStock</span></h1><p style="color:#94A3B8;font-size:14px;margin:6px 0 0;">Real Salespeople. Real Inventory. Real Fresh.</p></div><div style="height:4px;background:linear-gradient(to right,#00C851,#1E293B);"></div><div style="padding:32px 24px;background:white;">' + html_body + '<div style="text-align:center;margin:30px 0;"><a href="https://carsinstock.com/track/click/' + tracking_id + '" style="display:inline-block;background:#00C851;color:white;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600;text-decoration:none;">See the Demo &rarr;</a></div></div><div style="border-top:1px solid #E2E8F0;padding:20px;text-align:center;background:#F8FAFC;border-radius:0 0 12px 12px;"><p style="color:#64748B;font-size:13px;margin:0;">Fresh Cars. Real People.</p><p style="color:#94A3B8;font-size:12px;margin:4px 0 0;">CarsInStock.com</p></div></div>'

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
                success = send_recruitment_email("ecastillo@pinebeltauto.com", test_subject, html)
                if success:
                    flash("Test email sent to ecastillo@pinebeltauto.com", "success")
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
                    contacts_to_send = RecruitmentContact.query.filter(RecruitmentContact.id.in_(sel_ids)).all()
                else:
                    contacts_to_send = RecruitmentContact.query.all()

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

