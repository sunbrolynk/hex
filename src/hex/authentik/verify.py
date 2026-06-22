"""`python -m hex.authentik.verify` — drive the read-only admin client against a live Authentik.

A bootstrap diagnostic (and the Slice 3a-1 demo harness): confirms the blueprint applied and
the provisioning service account is least-privilege. Slice 3a-2 folds this verification into
the in-app bootstrap orchestrator. The bootstrap token is read from the environment so no
secret is passed on the command line.
"""

import argparse
import asyncio
import sys

import httpx

from hex.authentik.admin_client import AuthentikAdminClient
from hex.authentik.errors import AuthentikError
from hex.config import get_settings

# Canonical names of the objects deploy/authentik/blueprints/hex.yaml creates.
_PROVIDER_NAME = "HEx web BFF"
_SA_USERNAME = "hex-provisioner"
_GROUP_NAME = "HEx Provisioners"


async def _run(base_url: str) -> int:
    settings = get_settings()
    token = settings.authentik_bootstrap_token.get_secret_value()
    if not token:
        print("error: AUTHENTIK_BOOTSTRAP_TOKEN is not set in the environment", file=sys.stderr)
        return 2
    async with httpx.AsyncClient(timeout=10.0) as http:
        client = AuthentikAdminClient(base_url, token, http)
        try:
            report = await client.verify(
                app_slug=settings.authentik_oidc_app_slug,
                provider_name=_PROVIDER_NAME,
                sa_username=_SA_USERNAME,
                group_name=_GROUP_NAME,
            )
        except AuthentikError as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    print("OK — HEx Authentik wiring verified:")
    print(f"  application      {report.app_slug}")
    print(f"  provider         {report.provider_name} (pk={report.provider_pk})")
    print(f"  client_id        {report.client_id}")
    print(f"  service account  {report.sa_username} (pk={report.sa_pk}) — not a superuser")
    print(f"  group            {report.group_name}")
    return 0


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="hex.authentik.verify")
    parser.add_argument(
        "--base-url",
        default=settings.authentik_server_base_url or "http://localhost:9000",
        help="Authentik base URL (default: HEx's configured server base, else localhost:9000).",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.base_url)))


if __name__ == "__main__":
    main()
