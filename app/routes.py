from flask import Blueprint, render_template

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/salespeople")
def salespeople():
    return render_template("salespeople.html")
