from app.models import db
from datetime import datetime

class Dealer(db.Model):
    __tablename__ = 'dealers'
    
    dealer_id = db.Column(db.Integer, primary_key=True)
    dealer_name = db.Column(db.String(255), nullable=False)
    dealer_license_number = db.Column(db.String(100))
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip = db.Column(db.String(20))
    subscription_tier = db.Column(db.String(50), default='basic')
    status = db.Column(db.String(50), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    salespeople = db.relationship('Salesperson', backref='dealer')
    vehicles = db.relationship('Vehicle', backref='dealer')
