from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app.models import User
from app import db

# Blueprint
main = Blueprint("main", __name__)
# --------------------
# Index (Homepage)
# --------------------
@main.route("/")
def index():
    return render_template("index.html")

# --------------------
# Home
# --------------------

# --------------------
# Health check (for curl / uptime)
# --------------------
@main.route("/health")
def health():
    return "OK", 200

# --------------------
# Login
# --------------------
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

# --------------------
# Register
# --------------------
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
            flash("Email already registered", "danger")
            return redirect(url_for("main.register"))

        user = User(
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for("main.dashboard"))

    return render_template("register.html")
