from app.models import db
from datetime import datetime

class RecruitmentContact(db.Model):
    __tablename__ = 'recruitment_contacts'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(255), nullable=False, unique=True)
    dealership_name = db.Column(db.String(255))
    city_state = db.Column(db.String(255))
    custom_field = db.Column(db.String(500))
    status = db.Column(db.String(50), default='new')
    clicked_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    template_used = db.Column(db.String(100))
    tracking_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    batch_queue_id = db.Column(db.Integer)
