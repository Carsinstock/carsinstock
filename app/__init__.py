from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')

    # REGISTER SQLALCHEMY WITH THE FLASK APP
    db.init_app(app)

    # IMPORT MODELS SO TABLE CREATION WORKS
    with app.app_context():
        from app import models
        db.create_all()

    # REGISTER ROUTES
    from app.routes import main
    app.register_blueprint(main)

    return app
