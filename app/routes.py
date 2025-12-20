from flask import Blueprint, render_template, abort
from app.models import Salesperson, Vehicle

main = Blueprint(
    "main",
    __name__,
    template_folder="templates",
    static_folder="static"
)

@main.route("/")
def index():
    return render_template("index.html")

@main.route("/s/<slug>")
def salesperson_page(slug):
    salesperson = Salesperson.query.filter_by(slug=slug).first_or_404()

    inventory = (
        Vehicle.query.filter_by(salesperson_id=salesperson.id)
        .order_by(Vehicle.id.desc())
        .all()
    )

    return render_template(
        "salesperson.html",
        salesperson=salesperson,
        inventory=inventory
    )

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
