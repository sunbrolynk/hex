"""Secrets subsystem errors."""


class InsecureConfigError(RuntimeError):
    """A required secret is missing, weak, or a known placeholder.

    Raised at boot to refuse to run insecure. The message names the offending variable
    and how to generate a strong value; it never contains the secret's value.
    """


class InvalidToken(Exception):
    """An envelope token could not be decrypted — tampered, truncated, or wrong KEK."""
