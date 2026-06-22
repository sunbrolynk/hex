"""OIDC discovery-document + JWKS caching.

JWKS is fetched with httpx (async, and mockable by respx in tests) rather than PyJWT's
``PyJWKClient`` (which fetches synchronously via urllib and would block the loop / dodge respx).
Keys are cached and re-fetched once on an unknown ``kid`` so Authentik signing-key rotation
self-heals without a restart.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from hex.oidc.errors import OIDCDiscoveryError, OIDCValidationError


@dataclass(frozen=True)
class OIDCDiscovery:
    """The subset of the discovery document HEx uses.

    Discovery is fetched over the server-reachable (internal) base, so issuer/token/jwks carry that
    host — and the token's ``iss`` (minted when HEx exchanges over that host) matches. Only the
    browser-facing endpoints (authorize, end-session) are rewritten to the public base.
    """

    issuer: str  # server-host; matches the id_token iss
    authorization_endpoint: str  # rewritten to the public (browser-reachable) base
    token_endpoint: str  # server-reachable (as fetched)
    jwks_uri: str  # server-reachable (as fetched)
    end_session_endpoint: str | None  # rewritten to the public base


class DiscoveryCache:
    """Caches discovery docs (per server-base+slug) and JWKS sets (per jwks_uri)."""

    def __init__(self, http: httpx.AsyncClient, *, ttl_seconds: int = 3600) -> None:
        self._http = http
        self._ttl = ttl_seconds
        self._docs: dict[str, tuple[float, OIDCDiscovery]] = {}
        self._jwks: dict[str, tuple[float, jwt.PyJWKSet]] = {}

    async def get(self, public_base: str, server_base: str, slug: str) -> OIDCDiscovery:
        """Fetch+cache the discovery doc; rewrite server-side endpoints to the internal base."""
        key = f"{server_base}|{slug}"
        cached = self._docs.get(key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        url = f"{server_base.rstrip('/')}/application/o/{slug}/.well-known/openid-configuration"
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            doc: dict[str, Any] = resp.json()
            end_session = doc.get("end_session_endpoint")
            disco = OIDCDiscovery(
                issuer=doc["issuer"],
                authorization_endpoint=_to_public(
                    doc["authorization_endpoint"], server_base, public_base
                ),
                token_endpoint=doc["token_endpoint"],
                jwks_uri=doc["jwks_uri"],
                end_session_endpoint=(
                    _to_public(end_session, server_base, public_base) if end_session else None
                ),
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise OIDCDiscoveryError("could not fetch OIDC discovery document") from exc
        self._docs[key] = (now, disco)  # only successes are cached
        return disco

    async def signing_key(self, jwks_uri: str, kid: str) -> jwt.PyJWK:
        """The JWKS key for ``kid``; re-fetches once on a miss to absorb key rotation."""
        found = _match(await self._jwks_set(jwks_uri, force=False), kid)
        if found is None:
            found = _match(await self._jwks_set(jwks_uri, force=True), kid)
        if found is None:
            raise OIDCValidationError("no JWKS key matches the token key id")
        return found

    async def _jwks_set(self, jwks_uri: str, *, force: bool) -> jwt.PyJWKSet:
        cached = self._jwks.get(jwks_uri)
        now = time.monotonic()
        if not force and cached is not None and now - cached[0] < self._ttl:
            return cached[1]
        try:
            resp = await self._http.get(jwks_uri)
            resp.raise_for_status()
            jwks = jwt.PyJWKSet.from_dict(resp.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            raise OIDCValidationError("could not fetch JWKS") from exc
        self._jwks[jwks_uri] = (now, jwks)
        return jwks


def _match(jwks: jwt.PyJWKSet, kid: str) -> jwt.PyJWK | None:
    return next((key for key in jwks.keys if key.key_id == kid), None)


def _to_public(url: str, server_base: str, public_base: str) -> str:
    """Rewrite a server-base (internal) browser-facing endpoint to the public base.

    Authentik stamps every discovery URL with the request host, so endpoints fetched over the
    internal base point at the internal host; the browser-facing ones must be swapped to the
    public base. Matches the origin boundary (``srv + "/"``), not a bare prefix.
    """
    srv = server_base.rstrip("/")
    pub = public_base.rstrip("/")
    if srv and pub and srv != pub and url.startswith(srv + "/"):
        return pub + url[len(srv) :]
    return url
