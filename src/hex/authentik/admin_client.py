"""Read-only Authentik admin client used during first-run bootstrap to verify HEx's wiring.

Slice 3a-1 scope: confirm the blueprint-created objects exist and the provisioning service
account is **not** a superuser. It mutates nothing and reads no secrets — the confidential
client secret read-back, token rotation, and persistence are Slice 3a-2.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, cast

import httpx

from hex.authentik.errors import (
    AuthentikUnreachable,
    BlueprintObjectMissing,
    OverprivilegedServiceAccount,
)

_API = "/api/v3"
_READY = "/-/health/ready/"


@dataclass(frozen=True)
class VerifyReport:
    """The non-secret outcome of verifying HEx's Authentik objects. client_id is public."""

    app_slug: str
    provider_name: str
    client_id: str
    provider_pk: int
    sa_username: str
    sa_pk: int
    group_name: str


class AuthentikAdminClient:
    """Bootstrap-token-authed reader for Authentik's v3 API. Read-only by construction."""

    def __init__(self, base_url: str, token: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._http = http

    async def await_healthy(self, *, attempts: int = 30, delay: float = 2.0) -> None:
        """Poll the unauthenticated readiness endpoint until Authentik is up.

        Fail-secure: exhausting the attempts raises rather than letting wiring run against a
        half-started Authentik.
        """
        last_exc: Exception | None = None
        for _ in range(attempts):
            try:
                resp = await self._http.get(f"{self._base}{_READY}")
                if resp.status_code < 300:
                    return
            except httpx.HTTPError as exc:
                last_exc = exc
            await asyncio.sleep(delay)
        raise AuthentikUnreachable("Authentik did not become ready") from last_exc

    async def _get_one(self, path: str, field: str, value: str, what: str) -> dict[str, Any]:
        """GET a list-filtered endpoint and return the single match, or raise.

        A transport error or non-2xx (incl. 401 on a bad bootstrap token) is unreachable; an
        empty result set means the blueprint object is missing.
        """
        try:
            resp = await self._http.get(
                f"{self._base}{_API}{path}", params={field: value}, headers=self._headers
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthentikUnreachable(f"could not read {what} from Authentik") from exc
        if not results:
            raise BlueprintObjectMissing(f"{what} not found (blueprint not applied?)")
        return cast("dict[str, Any]", results[0])

    async def get_application(self, slug: str) -> dict[str, Any]:
        return await self._get_one("/core/applications/", "slug", slug, f"application '{slug}'")

    async def get_oauth2_provider(self, name: str) -> dict[str, Any]:
        return await self._get_one("/providers/oauth2/", "name", name, f"OAuth2 provider '{name}'")

    async def get_service_account(self, username: str) -> dict[str, Any]:
        return await self._get_one(
            "/core/users/", "username", username, f"service account '{username}'"
        )

    async def get_group(self, name: str) -> dict[str, Any]:
        return await self._get_one("/core/groups/", "name", name, f"group '{name}'")

    @staticmethod
    def assert_not_superuser(sa: dict[str, Any]) -> None:
        """Refuse a superuser provisioning account (non-negotiable #3)."""
        if sa.get("is_superuser"):
            raise OverprivilegedServiceAccount(
                f"service account '{sa.get('username')}' is a superuser"
            )

    async def verify(
        self,
        *,
        app_slug: str,
        provider_name: str,
        sa_username: str,
        group_name: str,
        wait: bool = True,
    ) -> VerifyReport:
        """Confirm every HEx object exists and the SA is least-privilege. Raises on any gap.

        Fail-secure: waits for health first (unless disabled), then fetches each object;
        the superuser check runs before the report is returned, so an overprivileged SA can
        never read as verified.
        """
        if wait:
            await self.await_healthy()
        app = await self.get_application(app_slug)
        provider = await self.get_oauth2_provider(provider_name)
        group = await self.get_group(group_name)
        sa = await self.get_service_account(sa_username)
        self.assert_not_superuser(sa)
        return VerifyReport(
            app_slug=app["slug"],
            provider_name=provider["name"],
            client_id=provider["client_id"],
            provider_pk=provider["pk"],
            sa_username=sa["username"],
            sa_pk=sa["pk"],
            group_name=group["name"],
        )
