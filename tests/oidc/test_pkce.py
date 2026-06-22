"""PKCE + CSRF helper tests."""

import base64
import hashlib

from hex.oidc import make_nonce, make_pkce_pair, make_state


def test_state_and_nonce_are_distinct_and_high_entropy() -> None:
    assert make_state() != make_state()
    assert make_nonce() != make_nonce()
    assert len(make_state()) >= 32
    assert len(make_nonce()) >= 32


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier, challenge = make_pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == expected


def test_pkce_pairs_are_unique() -> None:
    assert make_pkce_pair()[0] != make_pkce_pair()[0]
