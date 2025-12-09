from app import db
from sqlalchemy.dialects.sqlite import JSON


class Salesperson(db.Model):
    __tablename__ = "salesperson"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)

    dealership = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100))
    state = db.Column(db.String(10))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    bio = db.Column(db.Text)

    tagline = db.Column(db.String(200))

    # Profile / branding
    avatar_url = db.Column(db.String(300))
    profile_color = db.Column(db.String(20), default="#3b77ff")

    # Google reviews
    google_rating = db.Column(db.Float, default=4.9)
    google_review_count = db.Column(db.Integer)
    review_highlight = db.Column(db.String(300))
    google_reviews_json = db.Column(JSON)

    # Relationship: one salesperson -> many vehicles
    vehicles = db.relationship("Vehicle", backref="salesperson", lazy=True)

    def __repr__(self):
        return f"<Salesperson {self.name}>"


class Vehicle(db.Model):
    __tablename__ = "vehicle"

    id = db.Column(db.Integer, primary_key=True)

    # Link back to the salesperson who posted this car
    salesperson_id = db.Column(
        db.Integer,
        db.ForeignKey("salesperson.id"),
        nullable=False
    )

    # Core fields used on the mini-site cards
    year = db.Column(db.Integer, nullable=False)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    trim = db.Column(db.String(120))
    miles = db.Column(db.Integer)        # store as plain miles number
    price = db.Column(db.String(20))     # display-ready, e.g. "$24,995"

    # Extra structure so we can grow later (C structure)
    body_style = db.Column(db.String(50))       # SUV, Sedan, Truck, etc.
    drivetrain = db.Column(db.String(50))       # AWD, FWD, RWD
    exterior_color = db.Column(db.String(50))
    interior_color = db.Column(db.String(50))
    transmission = db.Column(db.String(50))     # Automatic, CVT, etc.
    vin = db.Column(db.String(30))

    # Photos
    main_photo_url = db.Column(db.String(300))
    photo_urls_json = db.Column(JSON)           # list of extra photos

    # Status (available, pending, sold)
    status = db.Column(db.String(20), default="available")

    def __repr__(self):
        return f"<Vehicle {self.year} {self.make} {self.model}>"
