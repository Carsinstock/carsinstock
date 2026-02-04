from flask import Flask
import os

def create_app():
    app = Flask(__name__)
    
    # Database configuration
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'carsinstock.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
    
    # Initialize database
    from app.models import db
    db.init_app(app)
    
    # Register blueprints
    from app.routes import main
    app.register_blueprint(main)
    
    from app.auth import auth
    app.register_blueprint(auth)
    
    from app.salesperson import salesperson
    app.register_blueprint(salesperson)
    
    return app
