"""OIDC relying-party client: authorize URL, code exchange, ID-token validation."""

import hmac
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from hex.oidc.config import OIDCConfig
from hex.oidc.discovery import DiscoveryCache, OIDCDiscovery
from hex.oidc.errors import OIDCExchangeError, OIDCNotConfigured, OIDCValidationError

_SCOPES = "openid profile email"
_LEEWAY_SECONDS = 30  # clock-skew tolerance for exp/nbf/iat


@dataclass(frozen=True)
class OIDCClaims:
    """The validated identity claims HEx consumes."""

    sub: str
    email: str | None
    preferred_username: str | None
    raw: dict[str, Any]


class OIDCClient:
    """Stateless relying-party helper; built per request from the resolved config."""

    def __init__(self, config: OIDCConfig, http: httpx.AsyncClient, cache: DiscoveryCache) -> None:
        self._config = config
        self._http = http
        self._cache = cache

    @property
    def configured(self) -> bool:
        return self._config.oidc_configured

    async def _discovery(self) -> OIDCDiscovery:
        if not self.configured:
            raise OIDCNotConfigured("Authentik OIDC client is not configured")
        return await self._cache.get(
            self._config.authentik_base_url,
            self._config.authentik_server_base_url,
            self._config.authentik_oidc_app_slug,
        )

    async def authorize_url(
        self, *, state: str, nonce: str, code_challenge: str, redirect_uri: str
    ) -> str:
        """Build the browser-facing authorize URL (Authorization-Code + PKCE S256)."""
        disco = await self._discovery()
        params = {
            "response_type": "code",
            "client_id": self._config.authentik_oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": _SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{disco.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OIDCClaims:
        """Exchange the code server-side (confidential client) and return validated claims."""
        disco = await self._discovery()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._config.authentik_oidc_client_id,
            "client_secret": self._config.authentik_oidc_client_secret.get_secret_value(),
            "code_verifier": code_verifier,
        }
        try:
            resp = await self._http.post(disco.token_endpoint, data=data)
            resp.raise_for_status()
            id_token = resp.json()["id_token"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise OIDCExchangeError("authorization-code exchange failed") from exc
        return await self._validate_id_token(id_token, disco=disco, nonce=nonce)

    async def _validate_id_token(
        self, id_token: str, *, disco: OIDCDiscovery, nonce: str
    ) -> OIDCClaims:
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
            if not kid:
                raise OIDCValidationError("ID token missing key id")
            key = await self._cache.signing_key(disco.jwks_uri, kid)
            claims = jwt.decode(
                id_token,
                key.key,
                algorithms=["RS256"],  # rejects alg=none and any non-RS256
                audience=self._config.authentik_oidc_client_id,
                issuer=disco.issuer,
                leeway=_LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "aud", "iss", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            raise OIDCValidationError("ID token failed validation") from exc
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OIDCValidationError("ID token nonce mismatch")
        return OIDCClaims(
            sub=claims["sub"],
            email=claims.get("email"),
            preferred_username=claims.get("preferred_username"),
            raw=claims,
        )
