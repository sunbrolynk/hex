"""Append-only audit log + hash-chain head.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        # VARCHAR + emitted CHECK (native_enum=False) so SQLite and Postgres agree.
        sa.Column(
            "action",
            sa.Enum(
                "setup_token.issued",
                "setup.unlock.succeeded",
                "setup.unlock.failed",
                "setup.unlock.throttled",
                "setup.unlock.locked_out",
                native_enum=False,
                create_constraint=True,
                length=40,
                name="auditaction",
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "info",
                "notice",
                "high",
                native_enum=False,
                create_constraint=True,
                length=8,
                name="auditseverity",
            ),
            nullable=False,
        ),
        sa.Column(
            "result",
            sa.Enum(
                "success",
                "failure",
                native_enum=False,
                create_constraint=True,
                length=8,
                name="auditresult",
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # A duplicate/forked hash fails closed at the DB.
        sa.UniqueConstraint("entry_hash", name="uq_audit_log_entry_hash"),
    )
    op.create_table(
        "audit_chain_head",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="ck_audit_chain_head_singleton"),
    )


def downgrade() -> None:
    op.drop_table("audit_chain_head")
    op.drop_table("audit_log")
