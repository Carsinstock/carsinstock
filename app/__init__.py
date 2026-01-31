from flask import Flask
from app.extensions import db, migrate, login_manager


def create_app():
    app = Flask(__name__)
    app.config.from_object("config")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app.routes import main_bp
    from app.auth import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")

    return app
