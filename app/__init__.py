from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"

# ✅ REQUIRED FOR FLASK-LOGIN (THIS WAS MISSING)
@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "change-this-later"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///carsinstock.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    return app
