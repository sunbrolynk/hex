"""Boot-time secret validation — refuse to boot insecure (ADR 0005, docs/SECRETS.md)."""

from dataclasses import dataclass

from hex.config import Settings
from hex.secrets.denylist import is_placeholder
from hex.secrets.errors import InsecureConfigError


@dataclass(frozen=True)
class SecretRule:
    """A required secret and how to validate it."""

    field: str  # Settings attribute (a SecretStr)
    env_var: str  # the HEX_* variable name, for error messages
    min_length: int  # minimum raw length (entropy proxy for CSPRNG tokens)
    generate: str  # the generation command, for error messages


_RULES: tuple[SecretRule, ...] = (
    SecretRule(
        "secret_key",
        "HEX_SECRET_KEY",
        43,
        'python -c "import secrets; print(secrets.token_urlsafe(64))"',
    ),
    SecretRule(
        "kek",
        "HEX_KEK",
        44,
        'python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"',
    ),
    SecretRule(
        "db_password",
        "HEX_DB_PASSWORD",
        24,
        'python -c "import secrets; print(secrets.token_urlsafe(32))"',
    ),
    SecretRule(
        "proxy_shared_secret",
        "HEX_PROXY_SHARED_SECRET",
        32,
        'python -c "import secrets; print(secrets.token_urlsafe(48))"',
    ),
    SecretRule(
        "audit_key",
        "HEX_AUDIT_KEY",
        43,  # ≥256-bit floor: the HMAC key securing the audit chain's tamper-evidence.
        'python -c "import secrets; print(secrets.token_urlsafe(48))"',
    ),
)


def validate_secrets(settings: Settings) -> None:
    """Assert every required secret is present, strong, and not a placeholder.

    Raises:
        InsecureConfigError: On the first failure, naming the offending variable and its
            generation command — never the secret's value.
    """
    for rule in _RULES:
        secret = getattr(settings, rule.field)
        _check(rule, secret.get_secret_value())


def _check(rule: SecretRule, value: str) -> None:
    if not value:
        raise InsecureConfigError(
            f"{rule.env_var} is required but unset. Generate: {rule.generate}"
        )
    if len(value) < rule.min_length:
        raise InsecureConfigError(
            f"{rule.env_var} is too short/low-entropy (need ≥{rule.min_length} chars). "
            f"Generate: {rule.generate}"
        )
    if is_placeholder(value):
        raise InsecureConfigError(
            f"{rule.env_var} looks like a placeholder/default. Generate a real one: {rule.generate}"
        )
