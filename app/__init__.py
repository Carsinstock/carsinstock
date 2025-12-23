from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = 'replace-this'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///carsinstock.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from app import models  # 👈 CRITICAL (loads models AFTER db)
    from app.routes import main
    app.register_blueprint(main)

    return app
