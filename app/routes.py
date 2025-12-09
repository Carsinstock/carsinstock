from flask import Blueprint, render_template, abort
from app.models import Salesperson

main = Blueprint("main", __name__)

# Temporary demo inventory for each salesperson.
# Later this will also come from the database.
INVENTORY = {
    "eddie": [
        {
            "year": 2021,
            "make": "Honda",
            "model": "CR-V EX",
            "trim": "AWD • One owner",
            "miles": "28,430 miles",
            "price": "$24,995",
        },
        {
            "year": 2020,
            "make": "Chevrolet",
            "model": "Equinox LT",
            "trim": "FWD • Remote start",
            "miles": "34,100 miles",
            "price": "$19,995",
        },
        {
            "year": 2019,
            "make": "Toyota",
            "model": "Camry SE",
            "trim": "Sport • Backup camera",
            "miles": "41,250 miles",
            "price": "$18,495",
        },
    ],
    "kim": [
        {
            "year": 2022,
            "make": "Toyota",
            "model": "RAV4 XLE",
            "trim": "AWD • Moonroof",
            "miles": "28,800 miles",
            "price": "$27,995",
        },
        {
            "year": 2021,
            "make": "Toyota",
            "model": "Corolla LE",
            "trim": "Great on gas",
            "miles": "22,150 miles",
            "price": "$18,250",
        },
    ],
}


@main.route("/")
def index():
    # Show directory of all salespeople from the database
    salespeople = Salesperson.query.order_by(Salesperson.name).all()
    return render_template("index.html", salespeople=salespeople)


@main.route("/s/<slug>")
def salesperson_page(slug):
    # Single salesperson mini-site
    salesperson = Salesperson.query.filter_by(slug=slug).first()

    if not salesperson:
        abort(404)

    inventory = INVENTORY.get(slug, [])
    return render_template(
        "salesperson.html",
        salesperson=salesperson,
        inventory=inventory,
    )
