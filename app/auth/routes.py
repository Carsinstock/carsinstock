import os
from flask import render_template, redirect, url_for, flash, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from . import auth
from app.models import db
from app.models.user import User
from app.utils.email import send_email
import uuid


@auth.route("/register", methods=["GET", "POST"])
def register():
    from app.utils.email import send_welcome_email
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        errors = []
        if not email:
            errors.append("Email is required.")
        elif "@" not in email or "." not in email:
            errors.append("Please enter a valid email address.")
        if not password:
            errors.append("Password is required.")
        elif len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        # Command 3 — Block personal email domains
        blocked_domains = ['gmail.com','yahoo.com','hotmail.com','aol.com','icloud.com',
                          'outlook.com','live.com','msn.com','yahoo.co.uk','ymail.com',
                          'googlemail.com','me.com','mac.com']
        if not errors:
            email_domain = email.split('@')[-1].lower() if '@' in email else ''
            if email_domain in blocked_domains:
                errors.append("Please use your dealership email address to register. This helps us verify you're an active automotive professional.")
        if not errors:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                errors.append("An account with this email already exists.")
        # Verify Turnstile CAPTCHA
        turnstile_response = request.form.get("cf-turnstile-response", "")
        if not turnstile_response:
            errors.append("Please complete the CAPTCHA verification.")
        else:
            import requests as http_requests
            verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
            verify_data = {
                "secret": os.environ.get("TURNSTILE_SECRET_KEY", ""),
                "response": turnstile_response,
                "remoteip": request.remote_addr
            }
            try:
                verify_result = http_requests.post(verify_url, data=verify_data, timeout=5).json()
                if not verify_result.get("success"):
                    errors.append("CAPTCHA verification failed. Please try again.")
            except:
                pass  # Allow registration if Turnstile is unreachable

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("auth/register.html", email=email, turnstile_site_key=os.environ.get("TURNSTILE_SITE_KEY", ""))
        verification_token = str(uuid.uuid4())
        new_user = User(
            email=email,
            password_hash=generate_password_hash(password),
            verification_token=verification_token,
            verification_token_expires=datetime.utcnow() + timedelta(hours=24)
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            # Send verification email
            verify_url = f"https://carsinstock.com/verify-email/{verification_token}"
            verify_html = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
                <div style="text-align:center;padding:20px 0;border-bottom:3px solid #00C851;">
                    <h1 style="margin:0;font-size:28px;"><span style="color:#1E293B;font-weight:400;">Cars</span> <span style="color:#00C851;font-weight:700;">IN STOCK</span></h1>
                </div>
                <div style="padding:30px 20px;">
                    <h2 style="color:#333;">Verify Your Email</h2>
                    <p style="color:#555;font-size:16px;line-height:1.6;">
                        Thanks for signing up! Click the button below to verify your email and activate your account.
                    </p>
                    <div style="text-align:center;padding:25px 0;">
                        <a href="{verify_url}"
                           style="background-color:#00C851;color:white;padding:14px 32px;
                                  text-decoration:none;border-radius:6px;font-size:16px;
                                  font-weight:bold;display:inline-block;">
                            Verify My Email
                        </a>
                    </div>
                    <p style="color:#999;font-size:13px;">This link expires in 24 hours.</p>
                </div>
                <div style="border-top:1px solid #eee;padding:20px 0;text-align:center;">
                    <p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>
                </div>
            </div>
            """
            try:
                send_email(email, "Verify Your CarsInStock Account", verify_html)
            except Exception as email_err:
                print(f"Verification email failed: {email_err}")
            flash("Account created! Please check your email to verify your account.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            flash("Something went wrong. Please try again.", "error")
            return render_template("auth/register.html", email=email, turnstile_site_key=os.environ.get("TURNSTILE_SITE_KEY", ""))
    return render_template("auth/register.html", turnstile_site_key=os.environ.get("TURNSTILE_SITE_KEY", ""))



@auth.route("/api/check-slug", methods=["POST"])
def check_slug():
    import re
    from app.models.salesperson import Salesperson
    data = request.get_json()
    name = data.get("name", "").strip()
    slug = re.sub(r'[^a-z0-9]', '', name.lower())
    if not slug:
        return jsonify({"available": None, "slug": ""})
    reserved = ["admin","login","register","dashboard","logout","demo","how-to","search-cars","about","privacy","terms","contact","billing","verify","unsubscribe","manifest","qr-code","referral","recruit","leads","customers","vehicles","blast","chats","profile","storefront","api","static","salespeople"]
    if slug in reserved:
        return jsonify({"available": False, "slug": slug, "suggestions": [f"{slug}cars", f"{slug}auto", f"{slug}1"]})
    existing = Salesperson.query.filter_by(profile_url_slug=slug).first()
    if existing:
        suggestions = [f"{slug}cars", f"{slug}auto", f"{slug}2"]
        return jsonify({"available": False, "slug": slug, "suggestions": suggestions})
    return jsonify({"available": True, "slug": slug})

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/login.html", email=email)
        # Check dealership team member first
        import sqlite3 as _sqL
        _cL = _sqL.connect('/home/eddie/carsinstock/instance/carsinstock.db')
        _cL.row_factory = _sqL.Row
        _member = _cL.execute("SELECT * FROM dealership_team WHERE LOWER(email)=LOWER(?) AND is_active=1 AND password_hash IS NOT NULL", (email,)).fetchone()
        _cL.close()
        if _member:
            from werkzeug.security import check_password_hash as _cph
            if _cph(_member['password_hash'], password):
                session['team_member_id'] = _member['id']
                session['team_member_name'] = _member['name']
                session['team_member_email'] = _member['email']
                session['dealership_id'] = _member['dealership_id']
                return redirect('/sp-dashboard')
            else:
                flash("Invalid email or password.", "error")
                return render_template("auth/login.html", email=email)
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.email_verified:
                flash("Please verify your email before logging in. Check your inbox for the verification link.", "error")
                return render_template("auth/login.html", email=email, show_resend=True)
            session["user_id"] = user.id
            session["email"] = user.email
            from app.models.salesperson import Salesperson
            sp = Salesperson.query.filter_by(user_id=user.id).first()
            if sp and sp.profile_url_slug:
                session["slug"] = sp.profile_url_slug
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            if not sp or not sp.display_name:
                flash("Welcome! Let's set up your storefront.", "success")
                return redirect(url_for("salesperson.profile_setup"))
            flash("Welcome back!", "success")
            return redirect(url_for("salesperson.dashboard"))
        else:
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email)
    return render_template("auth/login.html")


@auth.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


@auth.route("/verify-email/<token>")
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash("Invalid verification link.", "error")
        return redirect(url_for("auth.login"))
    if user.verification_token_expires and user.verification_token_expires < datetime.utcnow():
        flash("This verification link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.login"))
    user.email_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    user.subscription_status = 'trial'
    if not user.trial_end_date:
        from datetime import timedelta
        user.trial_end_date = datetime.utcnow() + timedelta(days=14)
    db.session.commit()
    try:
        from app.utils.email import send_welcome_email
        send_welcome_email(user.email)
    except:
        pass
    flash("Email verified! Your 14-day free trial is now active. Log in to get started.", "success")
    return redirect(url_for("auth.login"))


@auth.route("/resend-verification", methods=["POST"])
def resend_verification():
    email = request.form.get("email", "").strip().lower()
    if email:
        user = User.query.filter_by(email=email, email_verified=False).first()
        if user:
            token = str(uuid.uuid4())
            user.verification_token = token
            user.verification_token_expires = datetime.utcnow() + timedelta(hours=24)
            db.session.commit()
            verify_url = "https://carsinstock.com/verify-email/" + token
            verify_html = (
                '<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">'
                '<div style="text-align:center;padding:20px 0;border-bottom:3px solid #00C851;">'
                '<h1 style="margin:0;font-size:28px;"><span style="color:#1E293B;font-weight:400;">Cars</span> <span style="color:#00C851;font-weight:700;">IN STOCK</span></h1></div>'
                '<div style="padding:30px 20px;">'
                '<h2 style="color:#333;">Verify Your Email</h2>'
                '<p style="color:#555;font-size:16px;line-height:1.6;">Click the button below to verify your email and activate your account.</p>'
                '<div style="text-align:center;padding:25px 0;">'
                '<a href="' + verify_url + '" style="background-color:#00C851;color:white;padding:14px 32px;text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold;display:inline-block;">Verify My Email</a>'
                '</div><p style="color:#999;font-size:13px;">This link expires in 24 hours.</p>'
                '</div><div style="border-top:1px solid #eee;padding:20px 0;text-align:center;">'
                '<p style="color:#999;font-size:12px;">Fresh Cars. Real People. | CarsInStock.com</p>'
                '</div></div>'
            )
            try:
                send_email(email, "Verify Your CarsInStock Account", verify_html)
            except:
                pass
    flash("If an unverified account exists with that email, a new verification link has been sent.", "success")
    return redirect(url_for("auth.login"))

@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        flash("If an account with that email exists, a password reset link has been sent.", "success")
        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                token = str(uuid.uuid4())
                user.reset_token = token
                user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
                db.session.commit()
                reset_url = f"https://carsinstock.com/reset-password/{token}"
                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #00C851;">
                        <h1 style="color: #00C851; margin: 0; font-size: 28px;">CarsInStock</h1>
                    </div>
                    <div style="padding: 30px 20px;">
                        <h2 style="color: #333; margin-bottom: 10px;">Password Reset Request</h2>
                        <p style="color: #555; font-size: 16px; line-height: 1.6;">
                            We received a request to reset your password. Click the button below to set a new password.
                        </p>
                        <div style="text-align: center; padding: 25px 0;">
                            <a href="{reset_url}"
                               style="background-color: #00C851; color: white; padding: 14px 32px;
                                      text-decoration: none; border-radius: 6px; font-size: 16px;
                                      font-weight: bold; display: inline-block;">
                                Reset My Password
                            </a>
                        </div>
                        <p style="color: #999; font-size: 13px;">
                            This link expires in 1 hour. If you did not request this, you can safely ignore this email.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #eee; padding: 20px 0; text-align: center;">
                        <p style="color: #999; font-size: 12px; margin: 0;">
                            Fresh Cars. Real People. | CarsInStock.com
                        </p>
                    </div>
                </div>
                """
                try:
                    send_email(email, "Reset Your CarsInStock Password", html_content)
                except Exception as e:
                    print(f"Password reset email error: {e}")
        return redirect(url_for("auth.forgot_password"))
    return render_template("auth/forgot_password.html")


@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash("This reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not password or len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/reset_password.html", token=token)
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token)
        user.password_hash = generate_password_hash(password)
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        flash("Password updated successfully. You can now log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token)
