"""Invite capabilities + invite audit actions.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Full audit-action set after this revision.
_AUDIT_ACTIONS = (
    "setup_token.issued",
    "setup.unlock.succeeded",
    "setup.unlock.failed",
    "setup.unlock.throttled",
    "setup.unlock.locked_out",
    "oidc.login.succeeded",
    "oidc.login.failed",
    "oidc.logout",
    "audit.chain.verification_failed",
    "authentik.wiring.succeeded",
    "authentik.wiring.failed",
    "bootstrap.token.rotated",
    "owner.claimed",
    "breakglass.login.succeeded",
    "breakglass.login.failed",
    "breakglass.login.locked_out",
    "invite.created",
    "invite.revoked",
)
_PRIOR_ACTIONS = _AUDIT_ACTIONS[:16]


def _set_audit_action_check(values: Sequence[str]) -> None:
    """Drop + recreate the named ``auditaction`` CHECK with the given allowed values."""
    allowed = ", ".join(f"'{v}'" for v in values)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("auditaction", "audit_log", type_="check")
        op.create_check_constraint("auditaction", "audit_log", f"action IN ({allowed})")
    else:
        with op.batch_alter_table("audit_log") as batch:
            batch.drop_constraint("auditaction", type_="check")
            batch.create_check_constraint("auditaction", f"action IN ({allowed})")


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("default_grants", sa.JSON(), nullable=False),
        sa.Column("requestable", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"]),
    )
    op.create_index("ix_invites_token_hash", "invites", ["token_hash"])
    _set_audit_action_check(_AUDIT_ACTIONS)


def downgrade() -> None:
    _set_audit_action_check(_PRIOR_ACTIONS)
    op.drop_index("ix_invites_token_hash", table_name="invites")
    op.drop_table("invites")
