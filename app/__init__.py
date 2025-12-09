from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

# create the db object at the package level
db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # attach db to this app
    db.init_app(app)

    # import and register blueprints AFTER app + db are set up
    from .routes import main
    app.register_blueprint(main)

    return app
