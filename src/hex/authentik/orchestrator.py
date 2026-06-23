"""First-run Authentik wiring orchestrator (runs during the BOOTSTRAP phase).

Drives the bundled Authentik to a working integration using the bootstrap token, then rotates
HEx onto its own scoped service-account token. Fail-secure and atomic: the verify, the
secret read-back, and the rotation either all land — persisted encrypted and audited in one
transaction — or nothing is persisted and the install stays in BOOTSTRAP (ADR 0001/0010,
docs/BOOTSTRAP.md). The bootstrap token and the read-back secrets never leave the server.
"""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from hex.audit import AuditSigner
from hex.authentik.admin_client import AuthentikAdminClient
from hex.authentik.errors import WiringFailed
from hex.authentik.names import GROUP_NAME, PROVIDER_NAME, SA_TOKEN_IDENTIFIER, SA_USERNAME
from hex.authentik.wiring_client import AuthentikWiringClient
from hex.config import Settings
from hex.database import AuditLogManager, AuthentikIntegrationManager
from hex.database.models import AuditAction, AuditResult, AuditSeverity
from hex.secrets.broker import SecretsBroker


@dataclass(frozen=True)
class WireResult:
    """Non-secret outcome of a successful wiring (client_id is public)."""

    client_id: str
    provider_pk: int


async def wire_authentik(
    *,
    settings: Settings,
    http: httpx.AsyncClient,
    broker: SecretsBroker,
    session: AsyncSession,
    audit_signer: AuditSigner,
) -> WireResult:
    """Verify, read back the secret, rotate to a scoped token, persist + audit atomically.

    Raises an ``AuthentikError`` on any failure (the caller audits the failure and stays in
    BOOTSTRAP). On success the integration row and both HIGH-severity audit rows commit together.
    """
    token = settings.authentik_bootstrap_token.get_secret_value()
    if not token:
        raise WiringFailed("Authentik bootstrap token is not configured")
    base = settings.authentik_server_base_url
    if not base:
        raise WiringFailed("Authentik base URL is not configured")

    # Confirm the blueprint objects exist and the SA is least-privilege (non-negotiable #3).
    admin = AuthentikAdminClient(base, token, http)
    report = await admin.verify(
        app_slug=settings.authentik_oidc_app_slug,
        provider_name=PROVIDER_NAME,
        sa_username=SA_USERNAME,
        group_name=GROUP_NAME,
    )

    # Read back the confidential secret and mint HEx's own scoped token (the rotation target).
    wiring = AuthentikWiringClient(base, token, http)
    client_secret = await wiring.get_provider_secret(report.provider_pk)
    sa_token = await wiring.ensure_service_account_token(report.sa_pk, SA_TOKEN_IDENTIFIER)

    # Persist encrypted + audit in one transaction — wiring that isn't recorded never takes effect.
    await AuthentikIntegrationManager(session).set_oidc(
        base_url=settings.authentik_base_url,
        internal_base_url=settings.authentik_internal_base_url,
        client_id=report.client_id,
        client_secret_enc=broker.encrypt(client_secret),
        provider_pk=report.provider_pk,
        app_slug=settings.authentik_oidc_app_slug,
        sa_token_enc=broker.encrypt(sa_token),
    )
    audit = AuditLogManager(session, audit_signer)
    await audit.append(
        action=AuditAction.AUTHENTIK_WIRING_SUCCEEDED,
        severity=AuditSeverity.HIGH,
        result=AuditResult.SUCCESS,
        actor="system",
        target=f"authentik_provider:{report.provider_pk}",
    )
    await audit.append(
        action=AuditAction.BOOTSTRAP_TOKEN_ROTATED,
        severity=AuditSeverity.HIGH,
        result=AuditResult.SUCCESS,
        actor="system",
        target=f"authentik_user:{report.sa_pk}",
    )
    await session.commit()
    return WireResult(client_id=report.client_id, provider_pk=report.provider_pk)
