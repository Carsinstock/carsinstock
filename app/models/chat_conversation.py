from app.models import db
from datetime import datetime

class ChatConversation(db.Model):
    __tablename__ = 'chat_conversations'
    id = db.Column(db.Integer, primary_key=True)
    salesperson_id = db.Column(db.Integer, db.ForeignKey('salespeople.salesperson_id'), nullable=False)
    session_id = db.Column(db.String(100), nullable=False)
    visitor_name = db.Column(db.String(100))
    visitor_email = db.Column(db.String(120))
    visitor_phone = db.Column(db.String(20))
    messages = db.Column(db.Text, nullable=False, default='[]')
    vehicle_discussed = db.Column(db.String(200))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow)
    transcript_sent = db.Column(db.Boolean, default=False)
    
    salesperson = db.relationship('Salesperson', backref='chat_conversations')
    
    def __repr__(self):
        return f'<ChatConversation {self.id} - {self.session_id}>'
