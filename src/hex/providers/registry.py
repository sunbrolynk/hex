"""Provider registry — the explicit set of available providers, keyed by stable id.

Phase 4 providers register their instance at app startup; the lifecycle engine and provider routes
look them up here. Kept deliberately simple (no entry-point/plugin magic).
"""

from hex.providers.base import Provider

# Class-level declarations every concrete provider must set. ABC enforces the abstract *methods*;
# this catches a forgotten declaration loudly at startup instead of an AttributeError later in a
# privileged provision/deprovision path ("disabled, not silently broken").
_REQUIRED_DECLARATIONS = (
    "id",
    "name",
    "category",
    "integration_mode",
    "identity_owner",
    "grant_model",
)


class ProviderRegistry:
    """An id→provider map with duplicate-id protection and declaration validation."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        """Add a provider; raise loudly at startup on a missing declaration or a duplicate id."""
        missing = [a for a in _REQUIRED_DECLARATIONS if getattr(provider, a, None) is None]
        if missing:
            raise ValueError(
                f"{type(provider).__name__} is missing provider declarations: {', '.join(missing)}"
            )
        if not provider.id.strip():
            raise ValueError(f"{type(provider).__name__} has an empty provider id")
        if provider.id in self._providers:
            raise ValueError(f"duplicate provider id: {provider.id!r}")
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> Provider | None:
        """The provider for ``provider_id``, or None if unknown."""
        return self._providers.get(provider_id)

    def all(self) -> list[Provider]:
        """Every registered provider, in registration order."""
        return list(self._providers.values())
