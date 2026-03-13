from app.models import db
from datetime import datetime


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    salesperson_id = db.Column(db.Integer, db.ForeignKey('salespeople.salesperson_id'), nullable=False)
    first_name = db.Column(db.String(100), nullable=False, default='')
    last_name = db.Column(db.String(100), nullable=False, default='')
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    notes = db.Column(db.Text)
    unsubscribed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    salesperson = db.relationship('Salesperson', backref='customers')

    @property
    def name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email or ''

    def __repr__(self):
        return f'<Customer {self.name}>'
