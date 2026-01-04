from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app.models import User
from app.extensions import db

main = Blueprint("main", __name__)

# -------------------------
# Home
# -------------------------
@main.route("/")
def index():
    return render_template("index.html")

# -------------------------
# Login
# -------------------------
@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_url = request.args.get("next")
            return redirect(next_url or url_for("main.dashboard"))

        flash("Invalid email or password", "danger")
        return redirect(url_for("main.login"))

    return render_template("login.html")

# -------------------------
# Dashboard
# -------------------------
@main.route("/dashboard")
@login_required
def dashboard():
    # SAFE response (no DB writes, no loops)
    return f"Welcome {current_user.email}! Dashboard is LIVE 🚀"

# -------------------------
# Logout
# -------------------------
@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "success")
    return redirect(url_for("main.login"))
