import sys
import os

project_dir = "/home/eddie/carsinstock"
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from app import create_app
application = create_app()
