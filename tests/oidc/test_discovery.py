"""Discovery-doc + JWKS caching, split-horizon rewriting, and rotation."""

import httpx
import pytest
import respx

from hex.oidc import DiscoveryCache, OIDCDiscoveryError, OIDCValidationError
from hex.oidc.discovery import _to_public
from tests.oidc import _oidc


def test_to_public_only_rewrites_browser_endpoints_within_the_origin() -> None:
    pub, srv = "http://localhost:9000", "http://authentik-server:9000"
    # No split (srv == pub) → unchanged.
    assert (
        _to_public(f"{srv}/application/o/authorize/", srv, srv) == f"{srv}/application/o/authorize/"
    )
    # Server-origin browser endpoint → rewritten to the public base.
    assert (
        _to_public(f"{srv}/application/o/authorize/", srv, pub) == f"{pub}/application/o/authorize/"
    )
    # A look-alike host that merely shares the prefix must NOT be rewritten.
    assert (
        _to_public("http://authentik-server.evil/x", srv, pub) == "http://authentik-server.evil/x"
    )


@respx.mock
async def test_get_parses_and_caches_discovery() -> None:
    route = respx.get(_oidc.DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=_oidc.discovery_doc())
    )
    async with httpx.AsyncClient() as http:
        cache = DiscoveryCache(http)
        first = await cache.get(_oidc.BASE, _oidc.BASE, _oidc.SLUG)
        await cache.get(_oidc.BASE, _oidc.BASE, _oidc.SLUG)
    assert first.issuer == _oidc.ISS
    assert first.token_endpoint == _oidc.TOKEN_URL
    assert route.call_count == 1  # second call served from cache


@respx.mock
async def test_split_horizon_rewrites_authorize_to_public() -> None:
    # Authentik stamps the request host: fetched over the internal base → all-internal URLs.
    public, internal = "http://localhost:9000", "http://authentik-server:9000"
    doc = {
        "issuer": f"{internal}/application/o/hex/",
        "authorization_endpoint": f"{internal}/application/o/authorize/",
        "token_endpoint": f"{internal}/application/o/token/",
        "jwks_uri": f"{internal}/application/o/hex/jwks/",
        "end_session_endpoint": f"{internal}/application/o/hex/end-session/",
    }
    respx.get(f"{internal}/application/o/hex/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=doc)
    )
    async with httpx.AsyncClient() as http:
        disco = await DiscoveryCache(http).get(public, internal, "hex")
    # issuer/token/jwks stay internal (match the token iss minted internally; HEx-reachable).
    assert disco.issuer == f"{internal}/application/o/hex/"
    assert disco.token_endpoint == f"{internal}/application/o/token/"
    assert disco.jwks_uri == f"{internal}/application/o/hex/jwks/"
    # browser-facing endpoints rewritten to the public base.
    assert disco.authorization_endpoint == f"{public}/application/o/authorize/"
    assert disco.end_session_endpoint == f"{public}/application/o/hex/end-session/"


@respx.mock
async def test_discovery_failure_is_not_cached() -> None:
    route = respx.get(_oidc.DISCOVERY_URL)
    route.side_effect = [httpx.Response(503), httpx.Response(200, json=_oidc.discovery_doc())]
    async with httpx.AsyncClient() as http:
        cache = DiscoveryCache(http)
        with pytest.raises(OIDCDiscoveryError):
            await cache.get(_oidc.BASE, _oidc.BASE, _oidc.SLUG)
        recovered = await cache.get(_oidc.BASE, _oidc.BASE, _oidc.SLUG)  # not cached → retries
    assert recovered.issuer == _oidc.ISS


@respx.mock
async def test_signing_key_found() -> None:
    respx.get(_oidc.JWKS_URL).mock(return_value=httpx.Response(200, json=_oidc.jwks_dict()))
    async with httpx.AsyncClient() as http:
        key = await DiscoveryCache(http).signing_key(_oidc.JWKS_URL, _oidc.KID)
    assert key.key_id == _oidc.KID


@respx.mock
async def test_unknown_kid_refetches_then_raises() -> None:
    route = respx.get(_oidc.JWKS_URL).mock(return_value=httpx.Response(200, json=_oidc.jwks_dict()))
    async with httpx.AsyncClient() as http:
        with pytest.raises(OIDCValidationError):
            await DiscoveryCache(http).signing_key(_oidc.JWKS_URL, "no-such-kid")
    assert route.call_count == 2  # initial + one rotation refetch


@respx.mock
async def test_jwks_fetch_failure_raises_validation_error() -> None:
    respx.get(_oidc.JWKS_URL).mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as http:
        with pytest.raises(OIDCValidationError):
            await DiscoveryCache(http).signing_key(_oidc.JWKS_URL, _oidc.KID)


@respx.mock
async def test_rotation_self_heals_on_new_kid() -> None:
    route = respx.get(_oidc.JWKS_URL)
    route.side_effect = [
        httpx.Response(200, json=_oidc.jwks_dict(kid=_oidc.KID)),
        httpx.Response(200, json=_oidc.jwks_dict(kid="rotated-key")),
    ]
    async with httpx.AsyncClient() as http:
        cache = DiscoveryCache(http)
        await cache.signing_key(_oidc.JWKS_URL, _oidc.KID)  # caches first set
        key = await cache.signing_key(_oidc.JWKS_URL, "rotated-key")  # miss → refetch finds it
    assert key.key_id == "rotated-key"
    assert route.call_count == 2
