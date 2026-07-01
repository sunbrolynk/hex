"""OIDCClient: authorize URL, code exchange, and the ID-token validation matrix."""

from typing import Any

import httpx
import pytest
import respx

from hex.oidc import (
    DiscoveryCache,
    OIDCClaims,
    OIDCClient,
    OIDCConfig,
    OIDCExchangeError,
    OIDCNotConfigured,
    OIDCValidationError,
)
from hex.oidc.client import _clean_invite_nonce
from tests.oidc import _oidc

_REDIRECT = "http://localhost:52000/auth/callback"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("abc123", "abc123"), ("", None), (None, None), (42, None), (True, None), ([], None)],
)
def test_clean_invite_nonce(value: object, expected: str | None) -> None:
    # Fail-closed: only a non-empty string survives; a missing/non-string claim yields None.
    assert _clean_invite_nonce(value) == expected


async def _exchange(
    *,
    id_token: str,
    nonce: str = _oidc.NONCE,
    config: OIDCConfig | None = None,
    jwks: dict[str, Any] | None = None,
    token_status: int = 200,
) -> OIDCClaims:
    """Mock discovery+JWKS+token and run a full code exchange. Call inside @respx.mock."""
    respx.get(_oidc.DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=_oidc.discovery_doc())
    )
    respx.get(_oidc.JWKS_URL).mock(return_value=httpx.Response(200, json=jwks or _oidc.jwks_dict()))
    body = {"id_token": id_token, "access_token": "a", "token_type": "Bearer"}
    respx.post(_oidc.TOKEN_URL).mock(return_value=httpx.Response(token_status, json=body))
    async with httpx.AsyncClient() as http:
        client = OIDCClient(config or _oidc.oidc_config(), http, DiscoveryCache(http))
        return await client.exchange_code(
            code="auth-code", code_verifier="verifier", redirect_uri=_REDIRECT, nonce=nonce
        )


@respx.mock
async def test_authorize_url_carries_code_flow_params() -> None:
    respx.get(_oidc.DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=_oidc.discovery_doc())
    )
    async with httpx.AsyncClient() as http:
        client = OIDCClient(_oidc.oidc_config(), http, DiscoveryCache(http))
        url = await client.authorize_url(
            state="st", nonce="no", code_challenge="ch", redirect_uri=_REDIRECT
        )
    assert url.startswith(_oidc.AUTHORIZE_URL)
    for fragment in (
        "response_type=code",
        f"client_id={_oidc.CLIENT_ID}",
        "scope=openid+profile+email",
        "state=st",
        "nonce=no",
        "code_challenge=ch",
        "code_challenge_method=S256",
    ):
        assert fragment in url


@respx.mock
async def test_exchange_happy_path_returns_claims() -> None:
    claims = await _exchange(id_token=_oidc.id_token())
    assert claims.sub == "ak-user-1"
    assert claims.email == "owner@example.com"
    assert claims.preferred_username == "owner"


@respx.mock
async def test_rejects_invalid_signature() -> None:
    # Signed with a different key than the one JWKS publishes for this kid.
    forged = _oidc.id_token(priv=_oidc.other_key())
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=forged)


@respx.mock
async def test_rejects_wrong_audience() -> None:
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=_oidc.id_token(aud="some-other-client"))


@respx.mock
async def test_rejects_wrong_issuer() -> None:
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=_oidc.id_token(iss="http://evil.test/"))


@respx.mock
async def test_rejects_expired_token() -> None:
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=_oidc.id_token(exp_delta=-300))


@respx.mock
async def test_accepts_within_clock_skew_leeway() -> None:
    # 10s past exp, but the 30s leeway tolerates it.
    claims = await _exchange(id_token=_oidc.id_token(exp_delta=-10))
    assert claims.sub == "ak-user-1"


@respx.mock
async def test_rejects_bad_nonce() -> None:
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=_oidc.id_token(nonce="attacker-nonce"), nonce=_oidc.NONCE)


@respx.mock
async def test_rejects_alg_none() -> None:
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=_oidc.alg_none_token(kid=_oidc.KID))


@respx.mock
async def test_rejects_missing_kid() -> None:
    with pytest.raises(OIDCValidationError):
        await _exchange(id_token=_oidc.id_token(kid=None))


@respx.mock
async def test_token_endpoint_error_is_clean() -> None:
    with pytest.raises(OIDCExchangeError):
        await _exchange(id_token=_oidc.id_token(), token_status=400)


async def test_unconfigured_client_raises() -> None:
    client = OIDCClient(OIDCConfig(), httpx.AsyncClient(), DiscoveryCache(httpx.AsyncClient()))
    with pytest.raises(OIDCNotConfigured):
        await client.authorize_url(state="s", nonce="n", code_challenge="c", redirect_uri=_REDIRECT)
