"""Argon2id passphrase verification: accept, reject, and never-raise on malformed input."""

from argon2 import PasswordHasher

from hex.breakglass.password import decoy_verify, verify_password

_PH = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1)


def test_accepts_correct_passphrase() -> None:
    assert verify_password("s3cret-passphrase", _PH.hash("s3cret-passphrase")) is True


def test_rejects_wrong_passphrase() -> None:
    assert verify_password("wrong", _PH.hash("s3cret-passphrase")) is False


def test_rejects_malformed_hash_without_raising() -> None:
    assert verify_password("whatever", "not-a-valid-argon2-hash") is False


def test_rejects_empty_hash_without_raising() -> None:
    assert verify_password("whatever", "") is False


def test_decoy_verify_never_raises() -> None:
    decoy_verify("anything")  # exercises the absent-credential timing path; must not raise
