from flask import Blueprint, render_template
from .models import Salesperson

# Blueprint for main site pages
main = Blueprint("main", __name__)


@main.route("/s/<slug>")
def salesperson_page(slug):
    # Look up the salesperson by slug (e.g. "eddie")
    salesperson = Salesperson.query.filter_by(slug=slug).first()
    if not salesperson:
        return "Salesperson not found", 404

    # Get that salesperson's inventory
    inventory = salesperson.vehicles

    # Render the profile page
    return render_template(
        "salesperson.html",
        salesperson=salesperson,
        inventory=inventory,
    )


@main.route("/")
def index():
    # Simple home route so the app has a root page
    return "CarsInStock home page"
