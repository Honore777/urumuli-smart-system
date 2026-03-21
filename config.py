# config.py
import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy

# Load environment from a local .env file in development
load_dotenv()

# Initialize database - imported globally
db = SQLAlchemy()

class Config:
    # Application
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = os.environ.get(
        'SQLALCHEMY_TRACK_MODIFICATIONS', 'False'
    ).lower() in ('1', 'true', 'yes')

    SUPABASE_URL=os.environ.get('DATABASE_URL')

    # Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes')
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() in ('1', 'true', 'yes')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

    # Optional Supabase (useful for storage/auth separate from DB)
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SERVICE_KEY')

    # SQLAlchemy engine options for robust connections (adjust pool_size for production)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_size': int(os.environ.get('POOL_SIZE', '7')),
        'max_overflow': int(os.environ.get('MAX_OVERFLOW', '10')),
        'pool_timeout': int(os.environ.get('POOL_TIMEOUT', '35')),
        'pool_recycle': int(os.environ.get('POOL_RECYCLE', '400')),
    }
