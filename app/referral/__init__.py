"""MyCarReferral blueprint package.

Mounted internally at /mcr. Host-header middleware (Round 3) will rewrite
mycarreferral.com paths so users see clean URLs.
"""
from app.referral.routes import referral_bp
