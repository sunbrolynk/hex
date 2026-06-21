"""Audit-chain signer unit tests (no DB)."""

import secrets
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr

from hex.audit import GENESIS_HASH, AuditSigner
from hex.config import Settings
from hex.database.models import AuditAction, AuditResult, AuditSeverity

_NOW = datetime(2026, 6, 21, 12, 0, 0, 123456, tzinfo=UTC)


def _signer() -> AuditSigner:
    return AuditSigner(secrets.token_urlsafe(48).encode())


def _fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "action": AuditAction.SETUP_TOKEN_ISSUED,
        "severity": AuditSeverity.INFO,
        "result": AuditResult.SUCCESS,
        "actor": "system",
        "target": "setup_state:1",
        "meta": {"a": 1, "b": 2},
        "occurred_at": _NOW,
    }
    return base | overrides


def test_hex_audit_imports_before_hex_database() -> None:
    """Regression: importing hex.audit first must not trip a circular import (signer↔database)."""
    result = subprocess.run(
        [sys.executable, "-c", "import hex.audit"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_hash_is_deterministic() -> None:
    signer = _signer()
    first = signer.hash_entry(GENESIS_HASH, **_fields())
    second = signer.hash_entry(GENESIS_HASH, **_fields())
    assert first == second


def test_hash_independent_of_meta_key_order() -> None:
    signer = _signer()
    a = signer.hash_entry(GENESIS_HASH, **_fields(meta={"a": 1, "b": 2}))
    b = signer.hash_entry(GENESIS_HASH, **_fields(meta={"b": 2, "a": 1}))
    assert a == b


def test_hash_handles_target_none() -> None:
    signer = _signer()
    h = signer.hash_entry(GENESIS_HASH, **_fields(target=None))
    assert signer.verify_entry(GENESIS_HASH, h, **_fields(target=None)) is True


def test_verify_true_on_match() -> None:
    signer = _signer()
    h = signer.hash_entry(GENESIS_HASH, **_fields())
    assert signer.verify_entry(GENESIS_HASH, h, **_fields()) is True


def test_verify_false_on_mutated_field() -> None:
    signer = _signer()
    h = signer.hash_entry(GENESIS_HASH, **_fields())
    assert signer.verify_entry(GENESIS_HASH, h, **_fields(actor="attacker")) is False


def test_verify_false_on_mutated_prev() -> None:
    signer = _signer()
    h = signer.hash_entry(GENESIS_HASH, **_fields())
    assert signer.verify_entry("1" * 64, h, **_fields()) is False


def test_verify_false_with_wrong_key() -> None:
    h = _signer().hash_entry(GENESIS_HASH, **_fields())
    assert _signer().verify_entry(GENESIS_HASH, h, **_fields()) is False


def test_from_settings_uses_the_audit_key() -> None:
    key = secrets.token_urlsafe(48)
    from_settings = AuditSigner.from_settings(Settings(audit_key=SecretStr(key)))
    direct = AuditSigner(key.encode())
    assert from_settings.hash_entry(GENESIS_HASH, **_fields()) == direct.hash_entry(
        GENESIS_HASH, **_fields()
    )


def test_tz_naive_and_aware_hash_equal() -> None:
    """A DB round-trip can drop tzinfo on SQLite; canonicalization must hash both identically."""
    signer = _signer()
    aware = datetime(2026, 6, 21, 12, 0, 0, 123456, tzinfo=UTC)
    naive = datetime(2026, 6, 21, 12, 0, 0, 123456)
    assert signer.hash_entry(GENESIS_HASH, **_fields(occurred_at=aware)) == signer.hash_entry(
        GENESIS_HASH, **_fields(occurred_at=naive)
    )
