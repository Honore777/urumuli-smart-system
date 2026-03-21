#!/usr/bin/env python3
"""
Create an initial admin user.

Usage:
    python scripts/create_admin.py --username admin --email admin@example.com --password secret

If the user exists, script will exit safely.
"""
import argparse
from getpass import getpass
from app import app, db
from core.models import User

parser = argparse.ArgumentParser(description='Create initial admin user')
parser.add_argument('--username', help='username for admin', required=False)
parser.add_argument('--email', help='email for admin', required=False)
parser.add_argument('--password', help='password for admin (avoid on CLI)', required=False)
args = parser.parse_args()

username = args.username or input('Username [admin]: ') or 'admin'
email = args.email or input('Email [admin@example.com]: ') or 'admin@example.com'
password = args.password
if not password:
    password = getpass('Password: ')
    password2 = getpass('Confirm password: ')
    if password != password2:
        print('Passwords do not match.')
        raise SystemExit(1)

with app.app_context():
    existing = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing:
        print('User with that username or email already exists:', existing.username, existing.email)
        raise SystemExit(1)

    user = User(username=username, email=email, role='admin', is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    print('Admin user created: id=%s username=%s email=%s' % (user.id, user.username, user.email))
