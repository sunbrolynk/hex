"""Mutating Authentik calls used once, during first-run bootstrap wiring.

Kept separate from the read-only ``AuthentikAdminClient`` so that client keeps its
read-only-by-construction property. This one reads the confidential provider secret and mints
HEx's own scoped service-account token — the credential the bootstrap token is rotated onto.
Both are secrets: callers encrypt them at rest and never log them (non-negotiable #4).
"""

import httpx

from hex.authentik.errors import AuthentikUnreachable, WiringFailed

_API = "/api/v3"
# Authentik intents: an "api" token is the long-lived programmatic credential.
_API_INTENT = "api"


class AuthentikWiringClient:
    """Bootstrap-token-authed writer for the one-time wiring steps."""

    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._http = http

    async def get_provider_secret(self, provider_pk: int) -> str:
        """Read the confidential provider's generated ``client_secret`` for HEx to persist."""
        try:
            resp = await self._http.get(
                f"{self._base}{_API}/providers/oauth2/{provider_pk}/", headers=self._headers
            )
            resp.raise_for_status()
            secret = resp.json().get("client_secret")
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthentikUnreachable("could not read the provider client secret") from exc
        if not secret:
            raise WiringFailed("provider returned no client secret")
        return str(secret)

    async def ensure_service_account_token(self, user_pk: int, identifier: str) -> str:
        """Mint (idempotently) HEx's scoped SA token and return its key via ``view_key``.

        The create is idempotent on ``identifier`` — a duplicate (400) is fine; ``view_key`` is
        the authoritative read of the key either way.
        """
        try:
            created = await self._http.post(
                f"{self._base}{_API}/core/tokens/",
                json={
                    "identifier": identifier,
                    "intent": _API_INTENT,
                    "user": user_pk,
                    "expiring": False,
                },
                headers=self._headers,
            )
            # 201 created / 200 updated, and a 400 duplicate-identifier on re-run, are acceptable;
            # view_key is authoritative. Any other status is a transport/permission error.
            if created.status_code not in (200, 201, 400):
                created.raise_for_status()
            keyed = await self._http.get(
                f"{self._base}{_API}/core/tokens/{identifier}/view_key/", headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise AuthentikUnreachable("could not mint the service-account token") from exc
        # A 400 that wasn't a duplicate (e.g. a validation error) leaves no token, so view_key 404s:
        # a permanent wiring failure, not a transient one to retry.
        if keyed.status_code == 404:
            raise WiringFailed("service-account token was not created")
        try:
            keyed.raise_for_status()
            key = keyed.json().get("key")
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthentikUnreachable("could not read the service-account token key") from exc
        if not key:
            raise WiringFailed("service-account token has no key")
        return str(key)
