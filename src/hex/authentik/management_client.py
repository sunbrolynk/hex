"""Runtime mutating Authentik calls, authed by HEx's rotated service-account token.

Distinct from ``AuthentikWiringClient`` (one-time, bootstrap-token-authed): this is the ongoing
runtime writer. The SA token is decrypted at point of use (runtime_config.resolve_sa_credentials),
passed in here, and never logged (non-negotiable #4). All calls are defensively coded and fail
closed — an uncertain result raises rather than silently proceeding.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from hex.authentik.errors import AuthentikUnreachable, WiringFailed

_API = "/api/v3"


class AuthentikManagementClient:
    """SA-token-authed writer for runtime Authentik management (e.g. enrollment invitations)."""

    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._http = http

    async def _flow_pk(self, slug: str) -> str:
        try:
            resp = await self._http.get(
                f"{self._base}{_API}/flows/instances/",
                params={"slug": slug},
                headers=self._headers,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthentikUnreachable("could not read the enrollment flow") from exc
        if not results:
            raise WiringFailed(f"enrollment flow {slug!r} not found in Authentik")
        return str(results[0]["pk"])

    async def create_invitation(
        self,
        *,
        name: str,
        flow_slug: str,
        fixed_data: dict[str, Any],
        ttl_seconds: int,
        single_use: bool = True,
    ) -> str:
        """Mint a single-use, expiring invitation bound to ``flow_slug``; return its token (pk).

        The user is redirected to ``…/if/flow/<flow_slug>/?itoken=<token>`` to enroll.
        """
        flow_pk = await self._flow_pk(flow_slug)
        expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        try:
            resp = await self._http.post(
                f"{self._base}{_API}/stages/invitation/invitations/",
                json={
                    "name": name,
                    "single_use": single_use,
                    "expires": expires,
                    "fixed_data": fixed_data,
                    "flow": flow_pk,
                },
                headers=self._headers,
            )
            resp.raise_for_status()
            token = resp.json().get("pk")
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthentikUnreachable("could not create the enrollment invitation") from exc
        if not token:
            raise WiringFailed("invitation create returned no token")
        return str(token)
