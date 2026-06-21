"""Initial setup_state singleton.

Revision ID: 0001
Revises:
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "setup_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column(
            "phase",
            # VARCHAR + emitted CHECK (native_enum=False) so SQLite and Postgres agree and a
            # bad phase fails closed at the DB.
            sa.Enum(
                "first_run",
                "bootstrap",
                "complete",
                native_enum=False,
                create_constraint=True,
                length=16,
                name="setupphase",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="ck_setup_state_singleton"),
    )


def downgrade() -> None:
    op.drop_table("setup_state")
