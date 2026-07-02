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

# Codepoints that must never appear: C0 (incl. CR/LF/NUL), DEL, C1, the Unicode line/paragraph
# separators, and the invisible/BiDi-control chars (zero-width, LRM/RLM, embeddings, overrides,
# isolates, BOM) that enable visual spoofing of an owner-facing label. Everything else — accents,
# emoji, RTL *letters* — is allowed; only the explicit control chars are blocked.
_FORBIDDEN = frozenset({0x7F, 0x2028, 0x2029, 0xFEFF})


def _has_control(value: str) -> bool:
    return any(
        cp < 0x20
        or 0x80 <= cp <= 0x9F
        or 0x200B <= cp <= 0x200F  # zero-width space/joiners + LRM/RLM
        or 0x202A <= cp <= 0x202E  # BiDi embeddings + overrides
        or 0x2060 <= cp <= 0x2064  # word joiner + invisible operators
        or 0x2066 <= cp <= 0x2069  # BiDi isolates
        or cp in _FORBIDDEN
        for cp in map(ord, value)
    )


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
