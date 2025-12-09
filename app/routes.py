from flask import Blueprint, render_template, abort
from app.models import Salesperson, Vehicle

main = Blueprint("main", __name__)


@main.route("/")
def index():
    """
    Show directory of all salespeople from the database.
    """
    salespeople = Salesperson.query.order_by(Salesperson.name).all()
    return render_template("index.html", salespeople=salespeople)


@main.route("/s/<slug>")
def salesperson_page(slug):
    """
    Single salesperson mini-site.
    Loads the salesperson by slug and all of their vehicles from the DB.
    """
    salesperson = Salesperson.query.filter_by(slug=slug).first()

    if not salesperson:
        abort(404)

    # Pull this salesperson's inventory from the Vehicle table
    inventory = (
        Vehicle.query
        .filter_by(salesperson_id=salesperson.id, status="available")
        .order_by(Vehicle.year.desc(), Vehicle.make, Vehicle.model)
        .all()
    )

    return render_template(
        "salesperson.html",
        salesperson=salesperson,
        inventory=inventory,
    )
