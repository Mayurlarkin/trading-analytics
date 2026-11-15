"""Add accounts.server_timezone for interpreting MT5 report times.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15

"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("server_timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "server_timezone")
