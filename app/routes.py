from flask import Blueprint
from flask_login import login_required

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def home():
    return "<h1>Cars In Stock</h1><a href='/auth/login'>Login</a>"

@main_bp.route("/dashboard")
@login_required
def dashboard():
    return "<h2>Dealer Dashboard</h2>"



