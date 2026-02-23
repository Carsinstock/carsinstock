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
                            <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock | 76 RT 37 East, Toms River, NJ 08753</p>
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

