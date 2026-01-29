from flask import Blueprint, render_template

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/search")
def search():
    # SAFE placeholder — NO DB, NO logic
    return render_template("search.html")

@main.route("/login")
def login():
    return render_template("login.html")

@main.route("/register")
def register():
    return render_template("register.html")

@main.route("/salespeople")
def salespeople():
    return render_template("salespeople.html")

@main.route("/customers")
def customers():
    return render_template("customers.html")

@main.route("/disclosure")
def disclosure():
    return render_template("disclosure.html")



