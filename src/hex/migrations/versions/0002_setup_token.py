"""Add the first-run setup-token columns to setup_state.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: only set while in FIRST_RUN, cleared on unlock. No default needed.
    with op.batch_alter_table("setup_state") as batch:
        batch.add_column(sa.Column("setup_token_hash", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("setup_token_issued_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("setup_state") as batch:
        batch.drop_column("setup_token_issued_at")
        batch.drop_column("setup_token_hash")
