from app.models import db
from datetime import datetime

class Salesperson(db.Model):
    __tablename__ = 'salespeople'
    
    salesperson_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    dealer_id = db.Column(db.Integer, db.ForeignKey('dealers.dealer_id'), nullable=True)
    display_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text)
    profile_url_slug = db.Column(db.String(255), unique=True, nullable=False)
    subscription_tier = db.Column(db.String(50), default='free')
    profile_photo = db.Column(db.String(500))
    cover_photo = db.Column(db.String(500))
    status = db.Column(db.String(50), default='active')
    hired_at = db.Column(db.DateTime, default=datetime.utcnow)
    terminated_at = db.Column(db.DateTime)
    
    # Relationships
    attributions = db.relationship('Attribution', backref='salesperson')
    leads = db.relationship('Lead', backref='salesperson')
