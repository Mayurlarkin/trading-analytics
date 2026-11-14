"""Initial schema: users, accounts, api_keys, instruments, trades.

Revision ID: 0001
Revises:
Create Date: 2026-11-15

"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_instruments"),
        sa.UniqueConstraint("symbol", name="uq_instruments_symbol"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("broker", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("starting_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_accounts_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("user_id", "label", name="uq_accounts_user_id_label"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_api_keys_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])

    op.create_table(
        "trades",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("ticket", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("volume", sa.Numeric(12, 4), nullable=False),
        sa.Column("open_time", sa.DateTime(), nullable=False),
        sa.Column("close_time", sa.DateTime(), nullable=False),
        sa.Column("open_price", sa.Numeric(18, 5), nullable=False),
        sa.Column("close_price", sa.Numeric(18, 5), nullable=False),
        sa.Column("sl", sa.Numeric(18, 5), nullable=True),
        sa.Column("tp", sa.Numeric(18, 5), nullable=True),
        sa.Column("commission", sa.Numeric(18, 2), nullable=False),
        sa.Column("swap", sa.Numeric(18, 2), nullable=False),
        sa.Column("profit", sa.Numeric(18, 2), nullable=False),
        sa.Column("strategy_tag", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("direction IN ('buy', 'sell')", name="direction_valid"),
        sa.CheckConstraint("volume > 0", name="volume_positive"),
        sa.CheckConstraint("close_time >= open_time", name="close_not_before_open"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_trades_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_trades_instrument_id_instruments"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trades"),
        sa.UniqueConstraint("account_id", "ticket", name="uq_trades_account_id_ticket"),
    )
    op.create_index("ix_trades_account_id_close_time", "trades", ["account_id", "close_time"])
    op.create_index("ix_trades_account_id_instrument_id", "trades", ["account_id", "instrument_id"])


def downgrade() -> None:
    op.drop_table("trades")
    op.drop_table("api_keys")
    op.drop_table("accounts")
    op.drop_table("instruments")
    op.drop_table("users")
