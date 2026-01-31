from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

# -------------------------
# Dealership
# -------------------------
class Dealership(db.Model):
    __tablename__ = "dealerships"
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    legal_name = db.Column(db.String(200))
    address = db.Column(db.String(200))
    city = db.Column(db.String(80))
    state = db.Column(db.String(20))
    zip = db.Column(db.String(20))
    main_phone = db.Column(db.String(30))
    website = db.Column(db.String(200))
    logo_url = db.Column(db.String(500))
    primary_color = db.Column(db.String(20))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    users = db.relationship("User", backref="dealership", lazy=True)
    sites = db.relationship("Site", backref="dealership", lazy=True)

# -------------------------
# User (Salesperson)
# -------------------------
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)

    dealership_id = db.Column(db.Integer, db.ForeignKey("dealerships.id"), nullable=False)

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(30), default="salesperson", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    sites = db.relationship("Site", backref="user", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

# -------------------------
# Site (Mini-site)
# -------------------------
class Site(db.Model):
    __tablename__ = "sites"
    id = db.Column(db.Integer, primary_key=True)

    dealership_id = db.Column(db.Integer, db.ForeignKey("dealerships.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120))
    tagline = db.Column(db.String(180))
    bio = db.Column(db.Text)

    headshot_url = db.Column(db.String(500))
    banner_url = db.Column(db.String(500))
    theme_color = db.Column(db.String(20))
    social_links = db.Column(db.Text)

    contact_email_override = db.Column(db.String(120))
    contact_phone_override = db.Column(db.String(30))

    is_published = db.Column(db.Boolean, default=True, nullable=False)
    is_primary = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    vehicles = db.relationship("Vehicle", backref="site", lazy=True, cascade="all, delete-orphan")
    leads = db.relationship("Lead", backref="site", lazy=True, cascade="all, delete-orphan")

# -------------------------
# Vehicle
# -------------------------
class Vehicle(db.Model):
    __tablename__ = "vehicles"
    id = db.Column(db.Integer, primary_key=True)

    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    dealership_id = db.Column(db.Integer, db.ForeignKey("dealerships.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    status = db.Column(db.String(30), default="active", nullable=False)

    year = db.Column(db.Integer, nullable=False)
    make = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    trim = db.Column(db.String(80))

    price = db.Column(db.Integer)
    mileage = db.Column(db.Integer)
    vin = db.Column(db.String(32), index=True)
    stock_number = db.Column(db.String(40))

    exterior_color = db.Column(db.String(40))
    interior_color = db.Column(db.String(40))
    transmission = db.Column(db.String(40))
    drivetrain = db.Column(db.String(40))
    fuel = db.Column(db.String(40))

    description = db.Column(db.Text)
    featured = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

# -------------------------
# Lead
# -------------------------
class Lead(db.Model):
    __tablename__ = "leads"
    id = db.Column(db.Integer, primary_key=True)

    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    dealership_id = db.Column(db.Integer, db.ForeignKey("dealerships.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"))

    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    message = db.Column(db.Text)

    source = db.Column(db.String(40), default="website", nullable=False)
    status = db.Column(db.String(40), default="new", nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
