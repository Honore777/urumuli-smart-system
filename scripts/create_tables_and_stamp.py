#!/usr/bin/env python3
"""
Create all tables from SQLAlchemy models (db.create_all()) and exit.
Run this with your environment pointing to the target DB (DATABASE_URL).
"""
import os
import sys
from dotenv import load_dotenv

# Ensure project root is on sys.path so `from app import app, db` works when
# running this script from the `scripts/` directory.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

load_dotenv()

from app import app, db

with app.app_context():
    print('Creating tables from models...')
    db.create_all()
    print('Done creating tables.')
