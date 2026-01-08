from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app.models import User
from app import db

main = Blueprint("main", __name__)

# -------------------------
# Home
# -------------------------
@main.route("/")
def index():
    return render_template("index.html")

# -------------------------
# Health check (for curl)
# -------------------------
@main.route("/health")
def health():
    return "OK", 200

# -------------------------
# Login
# -------------------------
@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password required", "danger")
            return redirect(url_for("main.login"))

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("main.dashboard"))

        flash("Invalid email or password", "danger")
        return redirect(url_for("main.login"))

    return render_template("login.html")

# -------------------------
# Register
# -------------------------
@main.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password required", "danger")
            return redirect(url_for("main.register"))

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("User already exists. Please log in.", "warning")
            return redirect(url_for("main.login"))

        user = User(
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("main.login"))

    return render_template("register.html")

# -------------------------
# Dashboard (protected)
# -------------------------
@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# -------------------------
# Logout
# -------------------------
@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "success")
    return redirect(url_for("main.login"))
