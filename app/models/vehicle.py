from app.models import db
from datetime import datetime, timedelta
import math

class Vehicle(db.Model):
    __tablename__ = 'vehicles'

    id = db.Column(db.Integer, primary_key=True)
    dealer_id = db.Column(db.Integer, db.ForeignKey('dealers.dealer_id'), nullable=True)
    salesperson_id = db.Column(db.Integer, db.ForeignKey('salespeople.salesperson_id'), nullable=False)

    # Basic info
    year = db.Column(db.Integer, nullable=False)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    trim = db.Column(db.String(50))
    vin = db.Column(db.String(17), unique=True, nullable=False)

    # Details
    mileage = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    exterior_color = db.Column(db.String(50))
    interior_color = db.Column(db.String(50))
    transmission = db.Column(db.String(50))
    fuel_type = db.Column(db.String(50))

    # Images
    image_url = db.Column(db.String(500))

    # Status & Expiration
    status = db.Column(db.String(20), default='available')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

    expiration_warning_sent = db.Column(db.Boolean, default=False)

    # Approval workflow (dealership tier)
    approval_status = db.Column(db.String(20), default='approved')  # 'approved' | 'pending' | 'rejected'
    rejection_reason = db.Column(db.Text, nullable=True)

    # Notifications (dismissible banners on sp-dashboard)
    approval_notified = db.Column(db.Boolean, default=False)   # True = banner dismissed

    # Approval (dealership tier only)
    approval_status = db.Column(db.String(20), default='approved')  # 'approved' | 'pending' | 'rejected'
    rejection_reason = db.Column(db.Text)

    # Team Pick (dealership tier only)
    is_team_pick = db.Column(db.Boolean, default=False)
    pick_user_id = db.Column(db.Integer, db.ForeignKey('salespeople.salesperson_id'), nullable=True)
    pick_blurb = db.Column(db.String(150))
    pick_salesperson = db.relationship('Salesperson', foreign_keys='Vehicle.pick_user_id', primaryjoin='Vehicle.pick_user_id == Salesperson.salesperson_id', uselist=False)

    # Relationship
    salesperson = db.relationship('Salesperson', foreign_keys='Vehicle.salesperson_id', backref='vehicles')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(days=7)

    @property
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    @property
    def days_remaining(self):
        delta = self.expires_at - datetime.utcnow()
        return max(0, math.ceil(delta.total_seconds() / 86400))
