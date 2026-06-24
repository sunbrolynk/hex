"""End-to-end break-glass outcomes, including the fail-secure / uniform-failure guarantees."""

from collections.abc import Callable

import pytest

from hex.breakglass import BreakGlassConfig, BreakGlassOutcome, verify_breakglass
from hex.config import Settings

from .conftest import FOR_TIME, PASSPHRASE


class _Spy:
    """Counts calls and returns a fixed value, for monkeypatched timing/factor assertions."""

    def __init__(self, returns: object = None) -> None:
        self.count = 0
        self._returns = returns

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.count += 1
        return self._returns


def _spy(monkeypatch: pytest.MonkeyPatch, target: str, *, returns: object = None) -> _Spy:
    spy = _Spy(returns)
    monkeypatch.setattr(target, spy)
    return spy


def _verify(
    config: BreakGlassConfig,
    *,
    username: str = "owner-recovery-7x",
    password: str = PASSPHRASE,
    totp: str,
    idp_healthy: bool = False,
) -> BreakGlassOutcome:
    return verify_breakglass(
        config,
        username=username,
        password_attempt=password,
        totp_code=totp,
        idp_healthy=idp_healthy,
        for_time=FOR_TIME,
    )


def test_ok_when_all_factors_correct_and_idp_down(
    valid_config: BreakGlassConfig, valid_totp: str
) -> None:
    assert _verify(valid_config, totp=valid_totp) is BreakGlassOutcome.OK


def test_disabled_config_returns_disabled(
    make_settings: Callable[..., Settings], valid_totp: str
) -> None:
    config = BreakGlassConfig.from_settings(make_settings(breakglass_enabled=False))
    assert _verify(config, totp=valid_totp) is BreakGlassOutcome.DISABLED


def test_condition_not_met_when_idp_healthy(
    valid_config: BreakGlassConfig, valid_totp: str
) -> None:
    # Right credentials, but a healthy IdP — the path stays closed and credentials aren't honoured.
    assert (
        _verify(valid_config, totp=valid_totp, idp_healthy=True)
        is BreakGlassOutcome.CONDITION_NOT_MET
    )


def test_wrong_password_is_bad_credentials(valid_config: BreakGlassConfig, valid_totp: str) -> None:
    assert (
        _verify(valid_config, password="nope", totp=valid_totp) is BreakGlassOutcome.BAD_CREDENTIALS
    )


def test_wrong_username_is_indistinguishable_bad_credentials(
    valid_config: BreakGlassConfig, valid_totp: str
) -> None:
    # Same outcome as a wrong password — the caller can't tell which factor failed.
    assert (
        _verify(valid_config, username="someone-else", totp=valid_totp)
        is BreakGlassOutcome.BAD_CREDENTIALS
    )


def test_wrong_totp_is_bad_credentials(valid_config: BreakGlassConfig, wrong_totp: str) -> None:
    assert _verify(valid_config, totp=wrong_totp) is BreakGlassOutcome.BAD_CREDENTIALS


def test_non_ascii_username_is_bad_credentials_not_a_raise(
    valid_config: BreakGlassConfig, valid_totp: str
) -> None:
    # Attacker-controlled username with non-ASCII must not raise (hmac.compare_digest quirk) —
    # it collapses to the same uniform BAD_CREDENTIALS outcome as any other wrong username.
    assert (
        _verify(valid_config, username="ownér-recovery", totp=valid_totp)
        is BreakGlassOutcome.BAD_CREDENTIALS
    )


def test_gate_off_honours_credentials_regardless_of_health(
    make_settings: Callable[..., Settings], valid_totp: str
) -> None:
    config = BreakGlassConfig.from_settings(make_settings(breakglass_require_idp_down=False))
    assert _verify(config, totp=valid_totp, idp_healthy=True) is BreakGlassOutcome.OK


def test_disabled_path_burns_a_decoy_verify(
    make_settings: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The disabled path must do equivalent Argon2 work so timing can't reveal break-glass exists.
    calls = _spy(monkeypatch, "hex.breakglass.password.decoy_verify")
    config = BreakGlassConfig.from_settings(make_settings(breakglass_enabled=False))
    _verify(config, totp="000000")
    assert calls.count == 1


def test_condition_not_met_path_burns_a_decoy_verify(
    valid_config: BreakGlassConfig, valid_totp: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spy(monkeypatch, "hex.breakglass.password.decoy_verify")
    _verify(valid_config, totp=valid_totp, idp_healthy=True)
    assert calls.count == 1


def test_all_factors_evaluated_when_username_wrong(
    valid_config: BreakGlassConfig, valid_totp: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No short-circuit on the username: a wrong username must still run the password AND TOTP
    # checks, or the early return becomes a timing oracle for "which factor was wrong".
    pw_calls = _spy(monkeypatch, "hex.breakglass.verifier.password.verify_password", returns=False)
    totp_calls = _spy(monkeypatch, "hex.breakglass.verifier.verify_totp", returns=False)
    _verify(valid_config, username="someone-else", totp=valid_totp)
    assert pw_calls.count == 1
    assert totp_calls.count == 1
