from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Load config
    app.config.from_object("config")

    # Init extensions
    db.init_app(app)

    # Register blueprints
    from app.routes import main
    app.register_blueprint(main)

    return app
