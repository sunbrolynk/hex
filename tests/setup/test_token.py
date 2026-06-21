"""Setup-token crypto: entropy, hashing, constant-time verification."""

from hex.setup import hash_token, mint_token, verify_token


def test_mint_token_is_high_entropy_and_unique() -> None:
    a, b = mint_token(), mint_token()
    assert a != b
    # token_urlsafe(32) → 43 chars of URL-safe base64; never below the ≥128-bit floor.
    assert len(a) >= 43


def test_hash_is_deterministic_sha256_hex() -> None:
    token = mint_token()
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64
    assert hash_token(token) != token  # never store the plaintext


def test_verify_accepts_matching_token() -> None:
    token = mint_token()
    assert verify_token(token, hash_token(token)) is True


def test_verify_rejects_wrong_token() -> None:
    assert verify_token("nope", hash_token(mint_token())) is False


def test_verify_fails_secure_when_no_hash_on_file() -> None:
    # No token issued → never authenticates, even against the dummy comparison target.
    assert verify_token("anything", None) is False
    assert verify_token("0" * 64, None) is False
