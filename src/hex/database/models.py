"""SQLAlchemy models."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
