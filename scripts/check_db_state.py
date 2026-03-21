#!/usr/bin/env python3
"""
Check DB state: lists public tables and reports alembic_version.
Usage: set your environment (DATABASE_URL or SUPABASE_URL) then:
    python scripts/check_db_state.py
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

url = os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_URL')
if not url:
    print('No DATABASE_URL or SUPABASE_URL found in environment.')
    raise SystemExit(2)

print('Using DB URL:', url if len(url) < 180 else url[:180] + '...')
engine = create_engine(url)

with engine.connect() as conn:
    print('\nPublic tables:')
    rows = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"))
    tables = [r[0] for r in rows]
    if tables:
        for t in tables:
            print(' -', t)
    else:
        print(' (no public tables found)')

    print('\nAlembic version table:')
    try:
        v = conn.execute(text("SELECT version_num FROM alembic_version;"))
        vals = [r[0] for r in v]
        if vals:
            for val in vals:
                print(' -', val)
        else:
            print(' (alembic_version table is empty)')
    except Exception as e:
        print(' Could not read alembic_version table:', e)

    print('\nCount of migrations in migrations/versions:')
    try:
        import glob
        files = glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', 'versions', '*.py'))
        print(' ', len(files), 'files')
        if files:
            for f in sorted(files):
                print('  -', os.path.basename(f))
    except Exception as e:
        print(' Could not list migration files:', e)

print('\nDone.')
