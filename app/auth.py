from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_user, logout_user, login_required
from .models import User

auth = Blueprint("auth", __name__)

@auth.route("/login")
def login():
    return "Login page coming next"

@auth.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))
