from flask import Blueprint

salesperson = Blueprint('salesperson', __name__)

from app.salesperson import routes
