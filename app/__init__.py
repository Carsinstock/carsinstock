from flask import Flask
import os

def create_app():
    app = Flask(__name__)

    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'carsinstock.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'cis-mvp-2026-x7k9m2p4q8r1w5'
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

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

    from app.admin import admin_bp
    from app.admin.routes import register_admin_routes
    register_admin_routes(admin_bp)
    app.register_blueprint(admin_bp)

    from app.salesperson import salesperson_bp
    from app.salesperson.routes import register_routes
    register_routes(salesperson_bp)
    app.register_blueprint(salesperson_bp)

    from app.billing.routes import billing_bp
    app.register_blueprint(billing_bp)

    @app.context_processor
    def inject_pending_count():
        try:
            from app.models.vehicle import Vehicle
            from flask import request as _req
            if _req.endpoint and _req.endpoint.startswith('admin.'):
                count = Vehicle.query.filter_by(approval_status='pending').count()
                return {'pending_count': count}
        except Exception:
            pass
        return {'pending_count': 0}

    @app.route('/<path:slug>')
    def cardeals_redirect(slug):
        from flask import request, redirect
        import sqlite3, os
        host = request.host.lower()
        if 'cardeals.autos' in host:
            try:
                basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
                db_path = os.path.join(basedir, 'instance', 'carsinstock.db')
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                member = conn.execute(
                    "SELECT slug FROM dealership_team WHERE LOWER(slug) = ? OR LOWER(SUBSTR(name, 1, INSTR(name, ' ')-1)) = ? LIMIT 1",
                    (slug.lower(), slug.lower())
                ).fetchone()
                conn.close()
                if member:
                    return redirect(f'https://carsinstock.com/{member["slug"]}', code=301)
            except Exception:
                pass
            return redirect('https://carsinstock.com', code=301)
        from flask import abort
        abort(404)

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template("500.html"), 500

    # DISABLED: APScheduler double-fires with mod_wsgi processes=2 — using crontab
    # try:
    #     from app.cron import init_scheduler
    #     init_scheduler(app)
    # except Exception as e:
    #     app.logger.error(f"Scheduler failed to start: {e}")

    return app

def start_scheduler(app):
    import os
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        from app.cron import init_scheduler
        init_scheduler(app)
