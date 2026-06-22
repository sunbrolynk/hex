"""OIDC relying-party errors. Routes map these to clean responses + audited failures, never 500s."""


class OIDCError(Exception):
    """Base for all OIDC relying-party failures. Messages are non-leaky (no tokens/secrets)."""


class OIDCNotConfigured(OIDCError):
    """The Authentik OIDC client trio is unset — login is unavailable until bootstrap wires it."""


class OIDCDiscoveryError(OIDCError):
    """The OIDC discovery document could not be fetched or parsed."""


class OIDCExchangeError(OIDCError):
    """The token endpoint rejected the authorization-code exchange."""


class OIDCValidationError(OIDCError):
    """The ID token failed validation (signature, iss, aud, exp/nbf, or nonce)."""
