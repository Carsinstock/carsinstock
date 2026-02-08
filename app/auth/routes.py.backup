from flask import render_template
from . import auth

@auth.route("/login", methods=["GET"])
def login():
    return render_template("auth/login.html")

@auth.route("/register", methods=["GET"])
def register():
    return render_template("auth/register.html")

@auth.route("/logout", methods=["GET"])
def logout():
    # Placeholder only — real session logout comes later
    return render_template("auth/logout.html")
