"""Add change_reason to PaymentReview and soft-delete metadata to payments

Revision ID: add_change_reason_soft_delete_001
Revises: mpr_min_001
Create Date: 2026-03-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'chg_rev_softdel_001'
down_revision = 'mpr_min_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add change_reason to payment_review
    with op.batch_alter_table('payment_review', schema=None) as batch_op:
        batch_op.add_column(sa.Column('change_reason', sa.Text(), nullable=True))

    # Add soft-delete metadata to copper tables
    with op.batch_alter_table('supplier_payment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('worker_payment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))

    # Add soft-delete metadata to cassiterite tables
    with op.batch_alter_table('cassiterite_supplier_payment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('cassiterite_worker_payment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deleted_by_id', sa.Integer(), nullable=True))


def downgrade():
    # Remove added columns in reverse order
    with op.batch_alter_table('cassiterite_worker_payment', schema=None) as batch_op:
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')

    with op.batch_alter_table('cassiterite_supplier_payment', schema=None) as batch_op:
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')

    with op.batch_alter_table('worker_payment', schema=None) as batch_op:
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')

    with op.batch_alter_table('supplier_payment', schema=None) as batch_op:
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')

    with op.batch_alter_table('payment_review', schema=None) as batch_op:
        batch_op.drop_column('change_reason')
