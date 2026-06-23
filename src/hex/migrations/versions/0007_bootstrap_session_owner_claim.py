"""Bootstrap session hash on setup_state + owner.claimed audit action.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
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
)
_PRIOR_ACTIONS = _AUDIT_ACTIONS[:12]


def _set_audit_action_check(values: Sequence[str]) -> None:
    """Drop + recreate the named ``auditaction`` CHECK with the given allowed values."""
    allowed = ", ".join(f"'{v}'" for v in values)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("auditaction", "audit_log", type_="check")
        op.create_check_constraint("auditaction", "audit_log", f"action IN ({allowed})")
    else:  # SQLite (and others): rebuild the table via batch
        with op.batch_alter_table("audit_log") as batch:
            batch.drop_constraint("auditaction", type_="check")
            batch.create_check_constraint("auditaction", f"action IN ({allowed})")


def upgrade() -> None:
    with op.batch_alter_table("setup_state") as batch:
        batch.add_column(sa.Column("bootstrap_session_hash", sa.String(length=64), nullable=True))
    _set_audit_action_check(_AUDIT_ACTIONS)


def downgrade() -> None:
    _set_audit_action_check(_PRIOR_ACTIONS)
    with op.batch_alter_table("setup_state") as batch:
        batch.drop_column("bootstrap_session_hash")
