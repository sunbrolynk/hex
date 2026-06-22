"""Runtime-wired Authentik integration (singleton).

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "authentik_integration",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("internal_base_url", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_enc", sa.Text(), nullable=True),
        sa.Column("provider_pk", sa.Integer(), nullable=True),
        sa.Column("sa_token_enc", sa.Text(), nullable=True),
        sa.Column("app_slug", sa.String(length=128), nullable=False),
        sa.Column("wired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="ck_authentik_integration_singleton"),
    )


def downgrade() -> None:
    op.drop_table("authentik_integration")
