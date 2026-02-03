import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = "your-secret-key-change-this"

SQLALCHEMY_DATABASE_URI = "sqlite:////home/eddie/carsinstock/instance/carsinstock.db"
SQLALCHEMY_TRACK_MODIFICATIONS = False
