import sys
import os
import site

# Add venv site-packages
site.addsitedir('/home/eddie/carsinstock/venv/lib/python3.10/site-packages')

# Add project to path
sys.path.insert(0, '/home/eddie/carsinstock')

# Load environment variables
from dotenv import load_dotenv
load_dotenv('/home/eddie/carsinstock/.env')

from app import create_app
# === MyCarReferral host-header middleware ===
# Rewrites mycarreferral.com paths to use /mcr prefix internally.
# Users on mycarreferral.com see clean URLs (/, /login, /me, etc.)
# Internally these map to /mcr, /mcr/login, /mcr/me on the same Flask app.
# /static/* paths pass through unchanged (shared across both domains).
class HostBasedURLPrefixMiddleware:
    REFERRAL_HOSTS = ('mycarreferral.com', 'www.mycarreferral.com')
    PREFIX = '/mcr'

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        host = environ.get('HTTP_HOST', '').split(':')[0].lower()
        is_referral = host in self.REFERRAL_HOSTS

        if is_referral:
            path = environ.get('PATH_INFO', '/')
            if not path.startswith('/static') and not path.startswith(self.PREFIX):
                environ['PATH_INFO'] = self.PREFIX + path

        if not is_referral:
            return self.wsgi_app(environ, start_response)

        # Strip /mcr from Location headers so users see clean URLs after redirects
        prefix = self.PREFIX
        def wrapped_start_response(status, headers, exc_info=None):
            new_headers = []
            for name, value in headers:
                if name.lower() == 'location':
                    if value == prefix or value.startswith(prefix + '/'):
                        value = value[len(prefix):] or '/'
                new_headers.append((name, value))
            return start_response(status, new_headers, exc_info)

        return self.wsgi_app(environ, wrapped_start_response)

application = create_app()

application.wsgi_app = HostBasedURLPrefixMiddleware(application.wsgi_app)
