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
        if not errors:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                errors.append("An account with this email already exists.")
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("auth/register.html", email=email)
        new_user = User(email=email, password_hash=generate_password_hash(password))
        try:
            db.session.add(new_user)
            db.session.commit()
            send_welcome_email(email)
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            flash("Something went wrong. Please try again.", "error")
            return render_template("auth/register.html", email=email)
    return render_template("auth/register.html")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/login.html", email=email)
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["email"] = user.email
            from app.models.salesperson import Salesperson
            sp = Salesperson.query.filter_by(user_id=user.id).first()
            if sp and sp.profile_url_slug:
                session["slug"] = sp.profile_url_slug
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            flash("Welcome back!", "success")
            return redirect("/" + session.get("slug", ""))
        else:
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email)
    return render_template("auth/login.html")


@auth.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
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
                    <div style="text-align: center; padding: 20px 0; border-bottom: 3px solid #6C2BD9;">
                        <h1 style="color: #6C2BD9; margin: 0; font-size: 28px;">CarsInStock</h1>
                    </div>
                    <div style="padding: 30px 20px;">
                        <h2 style="color: #333; margin-bottom: 10px;">Password Reset Request</h2>
                        <p style="color: #555; font-size: 16px; line-height: 1.6;">
                            We received a request to reset your password. Click the button below to set a new password.
                        </p>
                        <div style="text-align: center; padding: 25px 0;">
                            <a href="{reset_url}"
                               style="background-color: #6C2BD9; color: white; padding: 14px 32px;
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
                            CarsInStock | 76 RT 37 East, Toms River, NJ 08753
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
