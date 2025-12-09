from app import db


class Salesperson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    dealership = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100))
    state = db.Column(db.String(10))
    tagline = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    bio = db.Column(db.Text)

    profile_color = db.Column(db.String(20), default="#3b77ff")
    total_deliveries = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, default=4.9)

    def __repr__(self):
        return f"<Salesperson {self.name}>"
