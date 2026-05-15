import sys
import os
sys.path.insert(0, '/home/eddie/carsinstock')
os.environ.setdefault('FLASK_ENV', 'production')

# Load environment variables
from dotenv import load_dotenv
load_dotenv('/home/eddie/carsinstock/.env')

from referral_app import create_referral_app
application = create_referral_app()
