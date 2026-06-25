"""Break-glass: users.is_break_glass column + break-glass audit actions.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Full audit-action set after this revision (the VARCHAR+CHECK must allow all of them, or a
# breakglass.login.* append fails at the DB).
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
)
_PRIOR_ACTIONS = _AUDIT_ACTIONS[:13]


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
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("is_break_glass", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    _set_audit_action_check(_AUDIT_ACTIONS)


def downgrade() -> None:
    _set_audit_action_check(_PRIOR_ACTIONS)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_break_glass")
