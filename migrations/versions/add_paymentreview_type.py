"""Add type column to PaymentReview table

Revision ID: add_paymentreview_type
Revises: 213d0c722846
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_paymentreview_type'
down_revision = '213d0c722846'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('payment_review', schema=None) as batch_op:
        batch_op.add_column(sa.Column('type', sa.String(length=32), nullable=True))

def downgrade():
    with op.batch_alter_table('payment_review', schema=None) as batch_op:
        batch_op.drop_column('type')
