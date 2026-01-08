import sys
import logging

logging.basicConfig(stream=sys.stderr)

sys.path.insert(0, "/home/eddie/carsinstock")

from app import create_app
application = create_app()
