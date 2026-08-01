"""initial schema

Revision ID: a1eb30c8bda2
Revises: 
Create Date: 2026-07-15 20:33:46.402015
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1eb30c8bda2'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id",              sa.Integer(),     primary_key=True, index=True),
        sa.Column("username",        sa.String(150),   nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(),      nullable=False),
        sa.Column("role",            sa.String(50),    nullable=False, server_default="customer"),
    )
    op.create_table(
        "accounts",
        sa.Column("id",       sa.Integer(),                    primary_key=True, index=True),
        sa.Column("currency", sa.String(3),                    nullable=False),
        sa.Column("balance",  sa.Numeric(precision=18, scale=4), nullable=False, server_default="0"),
        sa.Column("type",     sa.String(50),                   nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "transfers",
        sa.Column("id",               sa.Integer(), primary_key=True, index=True),
        sa.Column("idempotency_key",  sa.String(),  nullable=False, unique=True),
        sa.Column("from_account_id",  sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("to_account_id",    sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("amount",           sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency",         sa.String(3), nullable=False),
        sa.Column("status",           sa.String(50), nullable=False, server_default="completed"),
    )
    op.create_table(
        "entries",
        sa.Column("id",          sa.Integer(), primary_key=True, index=True),
        sa.Column("account_id",  sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("transfer_id", sa.Integer(), sa.ForeignKey("transfers.id"), nullable=False),
        sa.Column("amount",      sa.Numeric(precision=18, scale=4), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("entries")
    op.drop_table("transfers")
    op.drop_table("accounts")
    op.drop_table("users")
