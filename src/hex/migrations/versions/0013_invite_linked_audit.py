"""Widen the audit-action CHECK for invite.linked.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    "invite.accepted",
    "invite.linked",
)
_PRIOR_ACTIONS = _AUDIT_ACTIONS[:19]


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
    _set_audit_action_check(_AUDIT_ACTIONS)


def downgrade() -> None:
    _set_audit_action_check(_PRIOR_ACTIONS)
