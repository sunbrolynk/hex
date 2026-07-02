"""Recipient validation/normalization — the injection-safe, correctness-grade "who"."""

import socket

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
        ("label", "spoof‮evil"),  # BiDi override — visual spoofing
        ("label", "zero​width"),  # zero-width space
        ("email", "a​@b.com"),  # invisible char smuggled into email
        ("phone", "+1 555"),  # not a valid number plan
        ("phone", "banana"),  # unparseable
    ],
)
def test_bad_values_raise(kind: str, value: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — message text isn't part of the contract
        normalize_recipient(kind, value)  # type: ignore[arg-type]


def test_email_validation_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    # Non-negotiable #11 (no phone-home): email validation must never resolve DNS. Sabotage all
    # name resolution and assert the email path still succeeds (deliverability check is OFF).
    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("recipient validation attempted a network/DNS call")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    assert normalize_recipient("email", "who@example.com") == "who@example.com"


def test_over_length_is_rejected() -> None:
    # Passes email shape but exceeds the ceiling → still rejected (length guard before per-kind).
    long_local = "a" * MAX_LEN
    with pytest.raises(ValueError):  # noqa: PT011
        normalize_recipient("email", f"{long_local}@example.com")
