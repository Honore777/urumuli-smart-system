"""Add indexes to stock tables to support aggregate queries

Revision ID: 20260322_add_indexes_on_stock_tables
Revises: 
Create Date: 2026-03-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260322_add_indexes_on_stock_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Copper indexes
    op.create_index('ix_copper_stock_date', 'copper_stock', ['date'], unique=False)
    op.create_index('ix_copper_stock_date_id', 'copper_stock', ['date', 'id'], unique=False)
    op.create_index('ix_copper_stock_local_balance', 'copper_stock', ['local_balance'], unique=False)

    # Cassiterite indexes
    op.create_index('ix_cassiterite_stock_date', 'cassiterite_stock', ['date'], unique=False)
    op.create_index('ix_cassiterite_stock_date_id', 'cassiterite_stock', ['date', 'id'], unique=False)
    op.create_index('ix_cassiterite_stock_local_balance', 'cassiterite_stock', ['local_balance'], unique=False)


def downgrade():
    # Drop cassiterite indexes
    op.drop_index('ix_cassiterite_stock_local_balance', table_name='cassiterite_stock')
    op.drop_index('ix_cassiterite_stock_date_id', table_name='cassiterite_stock')
    op.drop_index('ix_cassiterite_stock_date', table_name='cassiterite_stock')

    # Drop copper indexes
    op.drop_index('ix_copper_stock_local_balance', table_name='copper_stock')
    op.drop_index('ix_copper_stock_date_id', table_name='copper_stock')
    op.drop_index('ix_copper_stock_date', table_name='copper_stock')
