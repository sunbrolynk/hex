"""SQLAlchemy models."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hex.providers.types import ProvisionState


class Base(DeclarativeBase):
    """Declarative base for all HEx models."""


class SetupPhase(StrEnum):
    """First-run lifecycle (docs/BOOTSTRAP.md). 1b only ever sets FIRST_RUN."""

    FIRST_RUN = "first_run"
    BOOTSTRAP = "bootstrap"
    COMPLETE = "complete"


# Stored as a portable VARCHAR+CHECK (not a native PG enum) so sqlite tests and Postgres
# agree and adding a phase later needs no enum-type migration. create_constraint emits the
# CHECK so an out-of-range phase fails closed at the DB, not as a 500 on read.
_phase_column = SAEnum(
    SetupPhase,
    native_enum=False,
    create_constraint=True,
    values_callable=lambda enum: [member.value for member in enum],
    length=16,
)


class SetupState(Base):
    """Singleton row: where this install sits in first-run setup."""

    __tablename__ = "setup_state"
    # Belt-and-braces with SetupStateManager.get_or_create: the DB itself forbids a 2nd row.
    __table_args__ = (CheckConstraint("id = 1", name="ck_setup_state_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    phase: Mapped[SetupPhase] = mapped_column(_phase_column, default=SetupPhase.FIRST_RUN)
    # SHA-256 hex of the out-of-band first-run setup token; null once consumed or past FIRST_RUN.
    # The plaintext is never persisted — only logged once at boot (docs/BOOTSTRAP.md).
    setup_token_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    setup_token_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # SHA-256 of the bootstrap session cookie minted at unlock; proves the caller is the one who
    # unlocked. Set on BOOTSTRAP entry, cleared when setup completes. Plaintext only in the cookie.
    bootstrap_session_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditAction(StrEnum):
    """Privileged actions recorded in the audit log (docs/SECURITY_MODEL §9)."""

    SETUP_TOKEN_ISSUED = "setup_token.issued"  # noqa: S105 — an action name, not a credential
    SETUP_UNLOCK_SUCCEEDED = "setup.unlock.succeeded"
    SETUP_UNLOCK_FAILED = "setup.unlock.failed"
    SETUP_UNLOCK_THROTTLED = "setup.unlock.throttled"
    SETUP_UNLOCK_LOCKED_OUT = "setup.unlock.locked_out"
    OIDC_LOGIN_SUCCEEDED = "oidc.login.succeeded"
    OIDC_LOGIN_FAILED = "oidc.login.failed"
    OIDC_LOGOUT = "oidc.logout"
    AUDIT_CHAIN_VERIFICATION_FAILED = "audit.chain.verification_failed"
    AUTHENTIK_WIRING_SUCCEEDED = "authentik.wiring.succeeded"
    AUTHENTIK_WIRING_FAILED = "authentik.wiring.failed"
    BOOTSTRAP_TOKEN_ROTATED = "bootstrap.token.rotated"  # noqa: S105 — action name, not a credential
    OWNER_CLAIMED = "owner.claimed"
    BREAKGLASS_SUCCEEDED = "breakglass.login.succeeded"
    BREAKGLASS_FAILED = "breakglass.login.failed"
    BREAKGLASS_LOCKED_OUT = "breakglass.login.locked_out"
    INVITE_CREATED = "invite.created"
    INVITE_REVOKED = "invite.revoked"
    INVITE_ACCEPTED = "invite.accepted"
    INVITE_LINKED = "invite.linked"


class AuditSeverity(StrEnum):
    """Event weight; bootstrap/lockout/break-glass events are HIGH."""

    INFO = "info"
    NOTICE = "notice"
    HIGH = "high"


class AuditResult(StrEnum):
    """Outcome of the audited action."""

    SUCCESS = "success"
    FAILURE = "failure"


def _audit_enum(enum_cls: type[StrEnum], length: int) -> SAEnum:
    """Portable VARCHAR+CHECK column type for an audit StrEnum (see ``_phase_column``)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda enum: [member.value for member in enum],
        length=length,
    )


class AuditChainHead(Base):
    """Singleton chain tip. Locked FOR UPDATE on append so concurrent appends can't fork."""

    __tablename__ = "audit_chain_head"
    __table_args__ = (CheckConstraint("id = 1", name="ck_audit_chain_head_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    # Genesis sentinel — must equal hex.audit.signer.GENESIS_HASH; manager sets it on create.
    last_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    seq: Mapped[int] = mapped_column(default=0)


class AuditLogEntry(Base):
    """One immutable, hash-chained audit record. Append-only: never updated or deleted."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)  # autoincrement → the chain ordinal
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    action: Mapped[AuditAction] = mapped_column(_audit_enum(AuditAction, 40))
    severity: Mapped[AuditSeverity] = mapped_column(_audit_enum(AuditSeverity, 8))
    result: Mapped[AuditResult] = mapped_column(_audit_enum(AuditResult, 8))
    # Non-PII identifier: "system" for boot issuance, "client:<ip>" for unlock attempts.
    actor: Mapped[str] = mapped_column(String(255))
    target: Mapped[str | None] = mapped_column(String(255), default=None)
    # Small structured context — never secrets or full PII (reference by id).
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)


class User(Base):
    """A HEx user, keyed to an Authentik identity (the OIDC ``sub``)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    authentik_sub: Mapped[str] = mapped_column(String(255), unique=True)
    username: Mapped[str | None] = mapped_column(String(255), default=None)
    email: Mapped[str | None] = mapped_column(String(320), default=None)
    # Owner-vs-user determination + enforcement lands in Slice 3 (owner setup); default false.
    is_owner: Mapped[bool] = mapped_column(default=False)
    # True for the local break-glass owner identity (ADR 0008) — not an Authentik user. Marks the
    # account for audit/UI and to exempt it from any future inactive-user cleanup.
    is_break_glass: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSession(Base):
    """A server-side session. The cookie carries the raw token; only its SHA-256 is stored."""

    __tablename__ = "user_sessions"

    session_token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class OIDCLoginState(Base):
    """Transient one-time state for an in-flight Authorization-Code round-trip."""

    __tablename__ = "oidc_login_state"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64))
    code_verifier: Mapped[str] = mapped_column(String(128))
    redirect_to: Mapped[str] = mapped_column(String(512), default="/")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthentikIntegration(Base):
    """Singleton row holding the runtime-wired Authentik config (bootstrap fills it, Slice 3a-2).

    Secrets are stored as broker-encrypted envelope tokens, never plaintext (non-negotiable #4).
    Env (``Settings``) overrides every field at resolve time, so external-mode operators never
    touch this row. ``client_id`` is public; only ``*_enc`` columns hold secrets.
    """

    __tablename__ = "authentik_integration"
    __table_args__ = (CheckConstraint("id = 1", name="ck_authentik_integration_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    base_url: Mapped[str] = mapped_column(String(512), default="")
    internal_base_url: Mapped[str] = mapped_column(String(512), default="")
    client_id: Mapped[str] = mapped_column(String(255), default="")
    client_secret_enc: Mapped[str | None] = mapped_column(Text, default=None)
    provider_pk: Mapped[int | None] = mapped_column(default=None)
    sa_token_enc: Mapped[str | None] = mapped_column(Text, default=None)
    app_slug: Mapped[str] = mapped_column(String(128), default="hex")
    # Set when bootstrap completes the wiring (rotation + persist); null until then.
    wired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProvisioningEvent(Base):
    """One append-only provisioning-ledger event for a ``(user, provider)``.

    The current state of a grant is the *latest* event for that pair (derived by query, never a
    mutable row), so the log is tamper-evident and a disaster-recovery source of truth alongside
    Authentik. Append-only: a DB trigger blocks UPDATE/DELETE (migration 0009). See
    docs/PROVIDER_CONTRACT.md. The FK deliberately does not cascade — history outlives the user row.
    """

    __tablename__ = "provisioning_events"
    __table_args__ = (Index("ix_provisioning_events_user_provider", "user_id", "provider_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)  # autoincrement → event ordinal
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    provider_id: Mapped[str] = mapped_column(String(64))
    state: Mapped[ProvisionState] = mapped_column(_audit_enum(ProvisionState, 24))
    # DB column is ``grant_data`` — ``grant`` is a reserved SQL keyword (Postgres); the Python
    # attribute stays ``grant`` to match the contract.
    grant: Mapped[dict[str, Any]] = mapped_column("grant_data", JSON, default=dict)
    external_ref: Mapped[str | None] = mapped_column(String(255), default=None)
    detail: Mapped[str | None] = mapped_column(Text, default=None)
    partial: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Invite(Base):
    """A single-use, expiring invite capability (non-negotiable #5).

    The owner creates it; a prospective user accepts it once to begin signup. Only the token's
    SHA-256 is stored (the raw token is shown to the owner once). ``default_grants`` maps provider
    id → structured grant applied on signup; ``requestable`` is the provider-id allowlist the user
    may later request. Single-use is enforced at acceptance (Slice 6-2) by setting ``accepted_at``.
    """

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    default_grants: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    requestable: Mapped[list[str]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    # SHA-256 of a server-minted nonce set at acceptance and carried in an httponly cookie through
    # the Authentik enrollment trip; Slice 6-2c looks the invite up by it to provision. A fresh
    # capability (not the burned token) so a guessed/forged cookie can't hijack provisioning.
    accept_nonce_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
