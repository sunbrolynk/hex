"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from the environment.

    Slice 0 loads only what the skeleton uses. Boot-time secret validation
    (presence, entropy, denylist, refuse-to-boot) and the database/secret fields
    arrive with the slices that introduce them; see docs/SECRETS.md.
    """

    model_config = SettingsConfigDict(env_prefix="HEX_", env_file=".env", extra="ignore")

    env: str = "production"

    # Authentik delivery (ADR 0013): "bundled" (HEx rolls up Authentik) or "external"
    # (point at an existing instance). Enforcement/gating is bootstrap-slice work.
    authentik_mode: str = "bundled"

    # Filesystem path to the built frontend bundle, set in the image for single-origin
    # serving; unset in dev/test so no SPA is mounted. See HEX_STATIC_DIR.
    static_dir: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
