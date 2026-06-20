"""Placeholder denylist tests."""

import pytest

from hex.secrets.denylist import is_placeholder


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", False),
        ("   ", False),
        ("changeme", True),  # exact
        ("ADMIN", True),  # exact, case-insensitive
        ("your-secret-key", True),  # exact
        ("changeme-but-padded-out-to-look-longer", True),  # substring
        ("a-genuinely-random-looking-token-9fK2", False),
    ],
)
def test_is_placeholder(value: str, expected: bool) -> None:
    assert is_placeholder(value) is expected
