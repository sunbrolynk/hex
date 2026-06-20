"""Placeholder/default secret detection."""

# Exact (lowercased, stripped) values that are never acceptable secrets.
_EXACT: frozenset[str] = frozenset(
    {
        "changeme",
        "change-me",
        "password",
        "password123",
        "admin",
        "secret",
        "default",
        "example",
        "test",
        "placeholder",
        "your-secret-key",
        "your-secret-key-here",
    }
)

# Distinctive substrings that signal a placeholder even when padded; kept narrow to
# avoid false positives on random CSPRNG tokens.
_SUBSTRINGS: frozenset[str] = frozenset(
    {"changeme", "your-secret-key", "placeholder", "password123"}
)


def is_placeholder(value: str) -> bool:
    """True if the value is (or embeds) a known placeholder/default."""
    v = value.strip().lower()
    if not v:
        return False
    if v in _EXACT:
        return True
    return any(token in v for token in _SUBSTRINGS)
