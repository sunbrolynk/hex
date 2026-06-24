"""Argon2id verification for the break-glass passphrase.

The passphrase is low-entropy (human-chosen), so Argon2id — not a bare hash — is the right
at-rest form (contrast hex.setup.token, which hashes a ≥256-bit token). Parameters are tuned
above the OWASP floor (m=19456, t=2, p=1) per SECURITY_MODEL §3.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_HASHER = PasswordHasher(memory_cost=65536, time_cost=3, parallelism=1)
# A real Argon2id hash to verify against when no credential is on file, so the absent/disabled
# path costs the same as a genuine check — no timing oracle for "does break-glass exist?".
_DECOY_HASH = _HASHER.hash("\x00break-glass-decoy")


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-work Argon2id check. False on mismatch or a malformed hash; never raises."""
    try:
        return _HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def decoy_verify(password: str) -> None:
    """Burn an equivalent Argon2id verify so non-credential paths match timing."""
    try:
        _HASHER.verify(_DECOY_HASH, password)
    except VerificationError:
        pass
