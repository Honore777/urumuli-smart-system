import os
import sys

# Ensure project root is on sys.path so `from app import ...` works when
# running this script from the `scripts/` folder.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app, db

with app.app_context():
    db.create_all()
    print("Database created successfully!")