cat > app/__init__.py << 'EOF'
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.models import db

def create_app():
    app = Flask(__name__)
    
    # Database configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///carsinstock.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
    
    # Initialize database
    db.init_app(app)
    
    # Load config
    app.config.from_object("config")
    
    # Register blueprints
    from app.routes import main
    app.register_blueprint(main)
    
    # Register auth blueprint
    from app.auth import auth
    app.register_blueprint(auth)
    
    # Register salesperson blueprint
    from app.salesperson import salesperson
    app.register_blueprint(salesperson)
    
    return app
EOF
