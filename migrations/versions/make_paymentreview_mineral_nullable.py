"""make paymentreview.mineral_type nullable

Revision ID: make_paymentreview_mineral_nullable
Revises: caf32dc21e23
Create Date: 2026-03-19 18:50:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'mpr_min_001'
down_revision = 'caf32dc21e23'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_review', schema=None) as batch_op:
        batch_op.alter_column('mineral_type', existing_type=sa.String(length=20), nullable=True)


def downgrade():
    with op.batch_alter_table('payment_review', schema=None) as batch_op:
        batch_op.alter_column('mineral_type', existing_type=sa.String(length=20), nullable=False)
