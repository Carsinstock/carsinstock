from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from app.models.user import User
from app.models.dealer import Dealer
from app.models.salesperson import Salesperson
from app.models.vehicle import Vehicle
from app.models.attribution import Attribution
from app.models.lead import Lead
