from flask import Flask

def create_referral_app():
    app = Flask(__name__, 
                template_folder='templates/mycarreferral',
                static_folder='../app/static')
    
    import os
    app.secret_key = os.environ.get('SECRET_KEY', 'mycarreferral-secret-2026')

    from referral_app.routes import referral_bp
    app.register_blueprint(referral_bp)

    return app
