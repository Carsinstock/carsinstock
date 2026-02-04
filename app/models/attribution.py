from app.models import db
from datetime import datetime, timedelta

class Attribution(db.Model):
    __tablename__ = 'attributions'
    
    attribution_id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.vehicle_id'), nullable=False)
    salesperson_id = db.Column(db.Integer, db.ForeignKey('salespeople.salesperson_id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    removed_at = db.Column(db.DateTime)
    assignment_type = db.Column(db.String(50), default='manual')
    
    def __init__(self, **kwargs):
        super(Attribution, self).__init__(**kwargs)
        if not self.expires_at and self.assigned_at:
            self.expires_at = self.assigned_at + timedelta(days=7)
        elif not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(days=7)
