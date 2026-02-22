from flask import Flask
import os

def create_app():
    app = Flask(__name__)

    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'carsinstock.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'cis-mvp-2026-x7k9m2p4q8r1w5'

    from app.models import db
    db.init_app(app)

    from app.models.user import User
    from app.models.salesperson import Salesperson
    from app.models.dealer import Dealer
    from app.models.vehicle import Vehicle
    from app.models.lead import Lead
    from app.models.attribution import Attribution

    from app.routes import main
    app.register_blueprint(main)

    from app.auth import auth
    app.register_blueprint(auth)

    from app.salesperson import salesperson_bp
    from app.salesperson.routes import register_routes
    register_routes(salesperson_bp)
    app.register_blueprint(salesperson_bp)

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template("500.html"), 500

    return app
