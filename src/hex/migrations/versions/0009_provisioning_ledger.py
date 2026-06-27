"""Provisioning ledger: append-only provisioning_events table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = ("granted", "pending_manual", "pending_external_claim", "partial", "failed", "revoked")


def _create_immutability_triggers() -> None:
    """Block UPDATE/DELETE on provisioning_events — append-only at the DB (mirrors audit_log)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE OR REPLACE FUNCTION hex_provisioning_events_immutable() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'provisioning_events is append-only'; END; $$ LANGUAGE plpgsql;"
        )
        op.execute(
            "CREATE TRIGGER hex_provisioning_events_no_update BEFORE UPDATE ON provisioning_events "
            "FOR EACH ROW EXECUTE FUNCTION hex_provisioning_events_immutable();"
        )
        op.execute(
            "CREATE TRIGGER hex_provisioning_events_no_delete BEFORE DELETE ON provisioning_events "
            "FOR EACH ROW EXECUTE FUNCTION hex_provisioning_events_immutable();"
        )
    else:
        op.execute(
            "CREATE TRIGGER hex_provisioning_events_no_update BEFORE UPDATE ON provisioning_events "
            "BEGIN SELECT RAISE(ABORT, 'provisioning_events is append-only'); END;"
        )
        op.execute(
            "CREATE TRIGGER hex_provisioning_events_no_delete BEFORE DELETE ON provisioning_events "
            "BEGIN SELECT RAISE(ABORT, 'provisioning_events is append-only'); END;"
        )


def _drop_immutability_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS hex_provisioning_events_no_update ON provisioning_events")
    op.execute("DROP TRIGGER IF EXISTS hex_provisioning_events_no_delete ON provisioning_events")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS hex_provisioning_events_immutable()")


def upgrade() -> None:
    op.create_table(
        "provisioning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        # VARCHAR + emitted CHECK (native_enum=False) so SQLite and Postgres agree.
        sa.Column(
            "state",
            sa.Enum(
                *_STATES,
                native_enum=False,
                create_constraint=True,
                length=24,
                name="provisionstate",
            ),
            nullable=False,
        ),
        sa.Column("grant_data", sa.JSON(), nullable=False),  # "grant" is a reserved SQL keyword
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("partial", sa.JSON(), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        # FK does not cascade — the ledger outlives a deleted user row (disaster-recovery record).
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_provisioning_events_user_provider", "provisioning_events", ["user_id", "provider_id"]
    )
    _create_immutability_triggers()


def downgrade() -> None:
    _drop_immutability_triggers()
    op.drop_index("ix_provisioning_events_user_provider", table_name="provisioning_events")
    op.drop_table("provisioning_events")
