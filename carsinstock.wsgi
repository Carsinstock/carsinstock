import sys
import os

BASE_DIR = "/home/eddie/carsinstock"
sys.path.insert(0, BASE_DIR)

from app import create_app

application = create_app()
