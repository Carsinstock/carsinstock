from flask import Blueprint, render_template, abort
from .models import Salesperson, Vehicle

# Blueprint for main site pages
main = Blueprint("main", __name__)


# ==============================
# Seller profile page
# ==============================
@main.route("/s/<slug>")
def salesperson_page(slug):
    # Look up the salesperson by slug (e.g. "eddie")
    salesperson = Salesperson.query.filter_by(slug=slug).first()

    if not salesperson:
        abort(404)

    # Get this salesperson's inventory
    inventory = salesperson.vehicles

    # Render the seller profile page
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
    vehicle = Vehicle.query.get_or_404(vehicle_id)

    # Safety check: vehicle must belong to this seller
    if vehicle.salesperson_id != salesperson.id:
        abort(404)

    return render_template(
        "vehicle_detail.html",
        salesperson=salesperson,
        vehicle=vehicle
    )


# ==============================
# Home / root page
# ==============================
@main.route("/")
def index():
    return "CarsInStock home page"
