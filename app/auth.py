from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    return "<h2>Login Page</h2>"

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.home"))
