"""Resolve the effective OIDC config from env over the DB-persisted integration.

Precedence per field: an env (``Settings``) value wins; otherwise the bootstrap-wired DB row;
otherwise unset (login stays unavailable). This is the one place env-vs-DB is reconciled, so
external-mode operators configure purely via env while bundled-mode self-wires into the DB.
The confidential client secret is decrypted here, at the point of use, never stored decrypted.
"""

from dataclasses import dataclass

from pydantic import SecretStr

from hex.config import Settings
from hex.database.models import AuthentikIntegration
from hex.oidc.config import OIDCConfig
from hex.secrets.broker import SecretsBroker


def resolve_oidc_config(
    settings: Settings, integration: AuthentikIntegration | None, broker: SecretsBroker
) -> OIDCConfig:
    """Merge env over the DB row into the config ``OIDCClient`` consumes.

    Raises:
        InvalidToken: if a persisted client secret can't be decrypted (wrong/rotated KEK or
            tampering). The caller treats that as fail-secure "not configured", not a 500.
    """
    base_url = settings.authentik_base_url or (integration.base_url if integration else "")
    internal = settings.authentik_internal_base_url or (
        integration.internal_base_url if integration else ""
    )
    client_id = settings.authentik_oidc_client_id or (integration.client_id if integration else "")
    secret = settings.authentik_oidc_client_secret.get_secret_value()
    if not secret and integration and integration.client_secret_enc:
        secret = broker.decrypt(integration.client_secret_enc).decode()
    # app_slug always has an env default ("hex"), so env is authoritative for it.
    return OIDCConfig(
        authentik_base_url=base_url,
        authentik_internal_base_url=internal,
        authentik_oidc_client_id=client_id,
        authentik_oidc_client_secret=SecretStr(secret),
        authentik_oidc_app_slug=settings.authentik_oidc_app_slug,
    )


@dataclass(frozen=True)
class SACredentials:
    """The rotated service-account credential for runtime management calls (minting invitations).

    ``api_base`` is the server-to-server base (internal split-horizon) for API calls;
    ``browser_base`` is the public base used to build user-facing URLs (the enrollment redirect).
    """

    api_base: str
    browser_base: str
    token: str


def resolve_sa_credentials(
    settings: Settings, integration: AuthentikIntegration | None, broker: SecretsBroker
) -> SACredentials | None:
    """Decrypt the rotated SA token at point of use; None if HEx isn't wired to Authentik yet.

    Raises:
        InvalidToken: if the persisted SA token can't be decrypted (wrong/rotated KEK or tampering);
            the caller treats that as fail-secure "not configured", not a 500.
    """
    if integration is None or not integration.sa_token_enc:
        return None
    token = broker.decrypt(integration.sa_token_enc).decode()
    browser_base = settings.authentik_base_url or integration.base_url
    api_base = settings.authentik_internal_base_url or integration.internal_base_url or browser_base
    if not browser_base:
        return None
    return SACredentials(api_base=api_base, browser_base=browser_base, token=token)
