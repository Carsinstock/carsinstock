import sys
import os

# Activate virtualenv
activate_this = "/home/eddie/carsinstock/venv/bin/activate_this.py"
if os.path.exists(activate_this):
    exec(open(activate_this).read(), dict(__file__=activate_this))

sys.path.insert(0, "/home/eddie/carsinstock")
site_packages = "/home/eddie/carsinstock/venv/lib/python3.10/site-packages"
if site_packages not in sys.path:
    sys.path.insert(0, site_packages)

from app import create_app

application = create_app()
