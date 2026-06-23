"""Authentik wiring errors. Bootstrap surfaces these as fail-secure setup problems, never 500s."""


class AuthentikError(Exception):
    """Base for all Authentik admin-API failures. Messages are non-leaky (no tokens/secrets)."""


class AuthentikUnreachable(AuthentikError):
    """Authentik did not become healthy or rejected the bootstrap credential."""


class BlueprintObjectMissing(AuthentikError):
    """An object the HEx blueprint should have created was not found — wiring cannot proceed."""


class OverprivilegedServiceAccount(AuthentikError):
    """The provisioning service account is a superuser — refused (non-negotiable #3)."""


class WiringFailed(AuthentikError):
    """Authentik responded but the wiring step could not complete (missing secret/token/field)."""
