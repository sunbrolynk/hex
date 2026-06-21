"""Audit-chain signer: keyed HMAC-SHA256 over canonical entries (integrity, not encryption).

The audit log is tamper-evident via a hash chain — each entry's hash covers the previous
entry's hash plus the entry's canonical fields, keyed by ``HEX_AUDIT_KEY`` so only its holder
can forge or recompute it. This is an integrity key, not encryption (docs/SECURITY_MODEL §9).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hex.config import Settings
    from hex.database.models import AuditAction, AuditResult, AuditSeverity

# Enums/Settings are imported under TYPE_CHECKING only: a runtime import of hex.database.models
# here would form a cycle (models → database/__init__ → audit_manager → signer). The signer needs
# the enums for typing, not at runtime (it reads ``.value`` off instances passed in).

GENESIS_HASH = "0" * 64  # chain root: prev_hash of the first entry and the head's initial last_hash


def _canonical_dt(value: datetime) -> str:
    """UTC ISO-8601, tz-normalized so a DB round-trip (naive on SQLite) hashes identically."""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


class AuditSigner:
    """Computes and verifies the tamper-evident hash of a single audit entry."""

    def __init__(self, key: bytes) -> None:
        self._key = key

    @classmethod
    def from_settings(cls, settings: Settings) -> AuditSigner:
        """Build from the validated ``HEX_AUDIT_KEY``."""
        return cls(settings.audit_key.get_secret_value().encode())

    def hash_entry(
        self,
        prev_hash: str,
        *,
        action: AuditAction,
        severity: AuditSeverity,
        result: AuditResult,
        actor: str,
        target: str | None,
        meta: dict[str, Any],
        occurred_at: datetime,
    ) -> str:
        """Hex HMAC-SHA256 over the prev hash and the entry's canonical fields."""
        canonical = json.dumps(
            {
                "action": action.value,
                "severity": severity.value,
                "result": result.value,
                "actor": actor,
                "target": target,
                "meta": meta,
                "occurred_at": _canonical_dt(occurred_at),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hmac.new(self._key, bytes.fromhex(prev_hash) + canonical, hashlib.sha256).hexdigest()

    def verify_entry(
        self,
        prev_hash: str,
        entry_hash: str,
        *,
        action: AuditAction,
        severity: AuditSeverity,
        result: AuditResult,
        actor: str,
        target: str | None,
        meta: dict[str, Any],
        occurred_at: datetime,
    ) -> bool:
        """Constant-time check that ``entry_hash`` matches a recomputation of the entry."""
        expected = self.hash_entry(
            prev_hash,
            action=action,
            severity=severity,
            result=result,
            actor=actor,
            target=target,
            meta=meta,
            occurred_at=occurred_at,
        )
        return hmac.compare_digest(expected, entry_hash)
