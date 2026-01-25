from flask import Blueprint, render_template

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/health")
def health():
    return "OK", 200
@main.route("/inventory")
def inventory():
    return render_template("inventory.html")



