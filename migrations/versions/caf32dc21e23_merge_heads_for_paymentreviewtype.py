"""merge heads for paymentreviewtype

Revision ID: caf32dc21e23
Revises: 
Create Date: 2026-03-19 09:27:52.119084

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'caf32dc21e23'
# Merge the two divergent heads so Alembic has a single linear history
# The current heads are: '557ef87a0adf' and 'add_paymentreview_type'
down_revision = ('557ef87a0adf', 'add_paymentreview_type')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
