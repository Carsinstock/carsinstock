from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    from app.auth import auth
    app.register_blueprint(auth)

    # Load config
    app.config.from_object("config")

    # Init extensions
    db.init_app(app)

    # Register blueprints
    from app.routes import main
    app.register_blueprint(main)
# Register salesperson blueprint
    from app.salesperson import salesperson
    app.register_blueprint(salesperson)
    return app
