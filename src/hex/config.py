"""Application configuration."""

from functools import lru_cache
from urllib.parse import quote

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from the environment.

    Secret fields are ``SecretStr`` so they never serialize into logs or API output.
    They default to empty so ``hex.secrets.validation`` can raise clear, non-leaky boot
    errors instead of pydantic's. Authentik-wiring fields arrive with their slices.
    """

    # populate_by_name lets programmatic construction use field names even where a
    # validation_alias is set for env reading (e.g. the shared bootstrap token).
    model_config = SettingsConfigDict(
        env_prefix="HEX_", env_file=".env", extra="ignore", populate_by_name=True
    )

    env: str = "production"

    # Authentik delivery (ADR 0013); enforcement/gating is bootstrap-slice work.
    authentik_mode: str = "bundled"

    # Built frontend path for single-origin serving; unset in dev/test.
    static_dir: str | None = None

    # Database connection (non-secret parts; the password is a required secret below).
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "hex"
    db_user: str = "hex"

    # Apply migrations to head on startup. Tests disable this and build schema directly.
    # In production with auto-migrate off, boot asserts the DB is already at head (fail-secure).
    db_auto_migrate: bool = True

    # First-run setup-token unlock throttle (defense-in-depth; the token is ≥256-bit already).
    setup_unlock_max_attempts: int = 3
    setup_unlock_window_seconds: float = 60.0
    # Cumulative failures (across windows) before the token is burned and setup hard-freezes;
    # recovery is a HEx restart, which re-mints. Distinct from the per-window throttle above.
    setup_unlock_lockout_threshold: int = 10

    # Required secrets — validated at boot by hex.secrets (empty default so we own the errors).
    secret_key: SecretStr = SecretStr("")
    kek: SecretStr = SecretStr("")
    db_password: SecretStr = SecretStr("")
    proxy_shared_secret: SecretStr = SecretStr("")
    # HMAC key for the tamper-evident audit-log hash chain (integrity, not encryption).
    audit_key: SecretStr = SecretStr("")

    # Authentik OIDC (relying-party login). Optional until first-run bootstrap wires them (Slice 3);
    # when unset the /auth surface reports "not configured" rather than refusing to boot.
    authentik_base_url: str = ""
    # Server-to-server base for token + JWKS fetch from inside the container; defaults to the public
    # base. Set it when the browser-facing URL differs from HEx's (Docker split-horizon).
    authentik_internal_base_url: str = ""
    authentik_oidc_client_id: str = ""
    authentik_oidc_client_secret: SecretStr = SecretStr("")
    authentik_oidc_app_slug: str = "hex"
    # Authentik's first-start API credential, used only during bootstrap to verify/finish wiring
    # and then rotated to HEx's own scoped service-account token (Slice 3a). Shared with the
    # bundled Authentik via the unprefixed AUTHENTIK_BOOTSTRAP_TOKEN; HEX_-prefixed overrides it.
    # validation_alias bypasses env_prefix, so the HEx-prefixed name is listed explicitly.
    authentik_bootstrap_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("HEX_AUTHENTIK_BOOTSTRAP_TOKEN", "AUTHENTIK_BOOTSTRAP_TOKEN"),
    )

    # Server-side session + OIDC login-flow lifetimes.
    session_lifetime_seconds: int = 60 * 60 * 8
    oidc_login_state_ttl_seconds: int = 600

    # Break-glass owner access (ADR 0008, SECURITY_MODEL §13) — the one local credential, for when
    # Authentik/OIDC is unreachable. DISABLED by default; enabling is validated at boot
    # (hex.breakglass.config) and refuses to boot if incompletely/insecurely configured.
    breakglass_enabled: bool = False
    breakglass_require_idp_down: bool = True  # accept only while the IdP fails its health check
    breakglass_local_only: bool = True  # LAN-only; enforced by the route's listener (Slice 4-2)
    breakglass_username: str = ""
    breakglass_password_hash: SecretStr = SecretStr("")  # Argon2id PHC string, never plaintext
    breakglass_totp_secret: SecretStr = SecretStr("")  # base32; offline second factor

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN. Credentials are percent-encoded; never log this."""
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def oidc_configured(self) -> bool:
        """True once the Authentik OIDC client trio is set — login is available."""
        return bool(
            self.authentik_base_url
            and self.authentik_oidc_client_id
            and self.authentik_oidc_client_secret.get_secret_value()
        )

    @property
    def authentik_server_base_url(self) -> str:
        """Base URL HEx uses for server-side token/JWKS calls (falls back to the public base)."""
        return self.authentik_internal_base_url or self.authentik_base_url

    @property
    def session_cookie_secure(self) -> bool:
        """Secure cookie in production; off in dev so it sets over http://localhost."""
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
