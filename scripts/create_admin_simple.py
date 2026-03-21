#!/usr/bin/env python3
"""
Simple admin creation script (no argparse). Run with:

    python scripts/create_admin_simple.py

It prompts for username, email and password and creates or updates an admin user.
"""
import os
import sys
import getpass

# Ensure project root is on sys.path so imports work when running from scripts/
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app, db
from core.models import User


def prompt(text, default=None):
    if default:
        v = input(f"{text} [{default}]: ").strip()
        return v or default
    return input(f"{text}: ").strip()


def main():
    username = prompt("Username", "admin")
    email = prompt("Email", "admin@example.com")

    while True:
        pwd = getpass.getpass("Password: ")
        pwd2 = getpass.getpass("Confirm Password: ")
        if pwd != pwd2:
            print("Passwords do not match — try again.")
            continue
        if not pwd:
            print("Password cannot be empty.")
            continue
        break

    with app.app_context():
        u = User.query.filter((User.username == username) | (User.email == email)).first()
        if u:
            print(f"Updating existing user id={u.id} username={u.username}")
            u.username = username
            u.email = email
            u.role = 'admin'
            u.is_active = True
            u.set_password(pwd)
        else:
            u = User(username=username, email=email, role='admin', is_active=True)
            u.set_password(pwd)
            db.session.add(u)

        db.session.commit()
        print(f"Admin ready: id={u.id} username={u.username} email={u.email}")


if __name__ == '__main__':
    main()
