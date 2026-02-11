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
application = create_app()
