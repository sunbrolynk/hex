"""Recipient validation/normalization — the injection-safe, correctness-grade "who"."""

import pytest

from hex.api.recipient import MAX_LEN, normalize_recipient


def test_email_is_normalized() -> None:
    assert normalize_recipient("email", "User@Example.COM") == "User@example.com"


def test_phone_is_normalized_to_e164() -> None:
    assert normalize_recipient("phone", "+1 (415) 555-2671") == "+14155552671"


def test_label_is_trimmed_and_kept() -> None:
    assert normalize_recipient("label", "  Grandma’s tablet  ") == "Grandma’s tablet"


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("email", ""),
        ("email", "   "),
        ("email", "not-an-email"),
        ("email", "a@b.com\r\nBcc: evil@x.com"),  # CR/LF header injection
        ("label", "line break"),  # unicode line separator
        ("label", "bell\x07"),  # C0 control
        ("phone", "+1 555"),  # not a valid number plan
        ("phone", "banana"),  # unparseable
    ],
)
def test_bad_values_raise(kind: str, value: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — message text isn't part of the contract
        normalize_recipient(kind, value)  # type: ignore[arg-type]


def test_over_length_is_rejected() -> None:
    # Passes email shape but exceeds the ceiling → still rejected (length guard before per-kind).
    long_local = "a" * MAX_LEN
    with pytest.raises(ValueError):  # noqa: PT011
        normalize_recipient("email", f"{long_local}@example.com")
