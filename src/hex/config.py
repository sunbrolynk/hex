"""Application configuration."""

from functools import lru_cache
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from the environment.

    Secret fields are ``SecretStr`` so they never serialize into logs or API output.
    They default to empty so ``hex.secrets.validation`` can raise clear, non-leaky boot
    errors instead of pydantic's. Authentik-wiring fields arrive with their slices.
    """

    model_config = SettingsConfigDict(env_prefix="HEX_", env_file=".env", extra="ignore")

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
    db_auto_migrate: bool = True

    # Required secrets — validated at boot by hex.secrets (empty default so we own the errors).
    secret_key: SecretStr = SecretStr("")
    kek: SecretStr = SecretStr("")
    db_password: SecretStr = SecretStr("")
    proxy_shared_secret: SecretStr = SecretStr("")

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN. Credentials are percent-encoded; never log this."""
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
