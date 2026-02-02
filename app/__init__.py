from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Load config first
    app.config.from_pyfile("/home/eddie/carsinstock/config.py")

    # Init DB
    db.init_app(app)

    # Register routes blueprint
    from app.routes import main
    app.register_blueprint(main)

    return app
