from flask import Flask

def create_app():
    app = Flask(__name__)

    # Basic config
    app.config["SECRET_KEY"] = "change-this-later"

    # Register blueprints (ONCE)
    from app.routes import main
    app.register_blueprint(main)

    return app
