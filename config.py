import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "change-this-later"
    SQLALCHEMY_DATABASE_URI = "sqlite:////home/eddie/carsinstock/instance/carsinstock.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
