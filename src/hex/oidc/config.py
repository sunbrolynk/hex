"""Resolved OIDC relying-party config that ``OIDCClient`` consumes.

The effective config is resolved per request from env over the DB-persisted Authentik
integration (env wins; see ``hex.authentik.runtime_config``), so bootstrap-wired values take
effect without a restart and env stays the authoritative power-user/external-mode override.
Field names mirror ``Settings`` so the client body is identical whichever supplies the config.
"""

from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(frozen=True)
class OIDCConfig:
    """The Authentik OIDC client settings, already merged (env over DB)."""

    authentik_base_url: str = ""
    authentik_internal_base_url: str = ""
    authentik_oidc_client_id: str = ""
    authentik_oidc_client_secret: SecretStr = SecretStr("")
    authentik_oidc_app_slug: str = "hex"

    @property
    def oidc_configured(self) -> bool:
        """True once base URL + client id + secret are all present — login is available."""
        return bool(
            self.authentik_base_url
            and self.authentik_oidc_client_id
            and self.authentik_oidc_client_secret.get_secret_value()
        )

    @property
    def authentik_server_base_url(self) -> str:
        """Base URL for server-side token/JWKS calls (falls back to the public base)."""
        return self.authentik_internal_base_url or self.authentik_base_url
