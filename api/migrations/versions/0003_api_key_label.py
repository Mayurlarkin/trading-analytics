"""Add api_keys.label so a person can tell their keys apart.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("label", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "label")
