"""Application configuration."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from the environment.

    Secret fields are ``SecretStr`` so they never serialize into logs or API output.
    They default to empty so ``hex.secrets.validation`` can raise clear, non-leaky boot
    errors instead of pydantic's. Database/Authentik-wiring fields arrive with their slices.
    """

    model_config = SettingsConfigDict(env_prefix="HEX_", env_file=".env", extra="ignore")

    env: str = "production"

    # Authentik delivery (ADR 0013); enforcement/gating is bootstrap-slice work.
    authentik_mode: str = "bundled"

    # Built frontend path for single-origin serving; unset in dev/test.
    static_dir: str | None = None

    # Required secrets — validated at boot by hex.secrets (empty default so we own the errors).
    secret_key: SecretStr = SecretStr("")
    kek: SecretStr = SecretStr("")
    db_password: SecretStr = SecretStr("")
    proxy_shared_secret: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
