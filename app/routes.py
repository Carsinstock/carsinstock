from flask import Blueprint, render_template
from flask_login import login_required

# NOTE:
# Salesperson routes are temporarily disabled until the Salesperson model
# is formally added back in Part 4 – Step 3.

main = Blueprint(
    "main",
    __name__,
    template_folder="templates",
    static_folder="static"
)

@main.route("/")
def index():
    return render_template("index.html")

@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
