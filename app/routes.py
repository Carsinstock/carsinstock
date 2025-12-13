from flask import Blueprint, render_template, abort
from .models import Salesperson, Vehicle

# Blueprint for main site pages
main = Blueprint("main", __name__)


# ==============================
# Home / root page
# ==============================
@main.route("/")
def index():
    return render_template("index.html")


# ==============================
# Seller profile page
# ==============================
@main.route("/s/<slug>")
def salesperson_page(slug):
    # Look up the salesperson by slug (e.g. "eddie")
    salesperson = Salesperson.query.filter_by(slug=slug).first_or_404()

    # Get this salesperson's inventory (newest first)
    inventory = Vehicle.query.filter_by(
        salesperson_id=salesperson.id
    ).order_by(Vehicle.id.desc()).all()

    return render_template(
        "salesperson.html",
        salesperson=salesperson,
        inventory=inventory
    )


# ==============================
# Vehicle detail page
# ==============================
@main.route("/s/<slug>/vehicle/<int:vehicle_id>")
def vehicle_detail(slug, vehicle_id):
    salesperson = Salesperson.query.filter_by(slug=slug).first_or_404()

    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        salesperson_id=salesperson.id
    ).first_or_404()

    return render_template(
        "vehicle_detail.html",
        salesperson=salesperson,
        vehicle=vehicle
    )
