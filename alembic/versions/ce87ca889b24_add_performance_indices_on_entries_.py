"""add performance indices on entries transfers accounts

Revision ID: ce87ca889b24
Revises: a1eb30c8bda2
Create Date: 2026-07-30

"""
from collections.abc import Sequence

from alembic import op

revision: str = 'ce87ca889b24'
down_revision: str | None = 'a1eb30c8bda2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_entries_account_id",        "entries",   ["account_id"])
    op.create_index("ix_entries_transfer_id",       "entries",   ["transfer_id"])
    op.create_index("ix_transfers_idempotency_key", "transfers", ["idempotency_key"], unique=True)
    op.create_index("ix_accounts_owner_id",         "accounts",  ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_entries_account_id",          table_name="entries")
    op.drop_index("ix_entries_transfer_id",         table_name="entries")
    op.drop_index("ix_transfers_idempotency_key",   table_name="transfers")
    op.drop_index("ix_accounts_owner_id",           table_name="accounts")
