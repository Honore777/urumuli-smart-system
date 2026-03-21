#!/usr/bin/env python3
"""
Test connection to Supabase/Postgres using `DATABASE_URL` or `SUPABASE_URL`.

Usage:
    python scripts/test_supabase_connection.py

This script uses SQLAlchemy (your project already depends on it via Flask-SQLAlchemy).
It loads environment variables from a local `.env` (via python-dotenv) if present.
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

# Prefer DATABASE_URL, fall back to SUPABASE_URL
db_url =  os.environ.get("DATABASE_URL")
if not db_url:
    print("Error: neither DATABASE_URL nor SUPABASE_URL found in environment.")
    print("Set one in your .env or export it in your environment.")
    sys.exit(2)

print("Using DB URL:", db_url if len(db_url) < 120 else db_url[:120] + "...")

# Create engine and test a simple query
try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version();")).scalar()
        one = conn.execute(text("SELECT 1;")).scalar()
    print("Connection successful.")
    print("Server version:\n", version)
    print("Test query returned:", one)
    sys.exit(0)
except SQLAlchemyError as exc:
    print("Connection failed:")
    print(exc)
    sys.exit(1)
