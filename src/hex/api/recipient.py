"""Recipient ("who") validation + normalization for invites.

Injection-safe by construction: control characters — CR/LF above all, which enable email-header
injection once the delivery slice sends to these — are rejected for every kind before any per-kind
check. Email and phone are validated to a canonical form with real libraries (email-validator /
phonenumbers), not hand-rolled shape checks, so genuine contacts aren't rejected and garbage is.
Deliverability is NOT checked (no DNS/outbound — non-negotiable #11). This is a contact hint, never
identity (Authentik owns that).
"""

from typing import Literal

import phonenumbers
from email_validator import EmailNotValidError, validate_email

RecipientKind = Literal["email", "phone", "label"]

MAX_LEN = 320  # RFC 5321 email ceiling; also caps phone/label

# Control/separator codepoints that must never appear: C0 (incl. CR/LF/NUL), DEL, C1, and the
# Unicode line/paragraph separators. Everything else (accents, emoji, scripts) is allowed in labels.
_FORBIDDEN = frozenset({0x7F, 0x2028, 0x2029})


def _has_control(value: str) -> bool:
    return any(cp < 0x20 or 0x80 <= cp <= 0x9F or cp in _FORBIDDEN for cp in map(ord, value))


def normalize_recipient(kind: RecipientKind, value: str) -> str:
    """Return the canonical recipient for ``kind``; raise ``ValueError`` if invalid.

    Email → RFC-normalized address; phone → E.164; label → trimmed text. The raw value is trimmed
    and screened for control chars first, so the per-kind step never sees an injection vector.
    """
    value = value.strip()
    if not value:
        raise ValueError("recipient is empty")
    if len(value) > MAX_LEN:
        raise ValueError("recipient too long")
    if _has_control(value):
        raise ValueError("recipient contains control characters")

    if kind == "email":
        try:
            return validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise ValueError("invalid email address") from exc
    if kind == "phone":
        try:
            parsed = phonenumbers.parse(value, None)  # None → must be international (leading +)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("invalid phone number") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("invalid phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return value  # label: already trimmed, control-free, length-bounded
