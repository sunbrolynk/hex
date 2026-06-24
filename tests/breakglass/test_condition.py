"""Condition gate: a healthy reachable IdP closes the break-glass path."""

from collections.abc import Callable

from hex.breakglass import BreakGlassConfig
from hex.breakglass.condition import condition_met
from hex.config import Settings


def test_gate_on_permits_only_when_idp_down(valid_config: BreakGlassConfig) -> None:
    assert valid_config.require_idp_down is True
    assert condition_met(valid_config, idp_healthy=False) is True
    assert condition_met(valid_config, idp_healthy=True) is False


def test_gate_off_always_permits(make_settings: Callable[..., Settings]) -> None:
    config = BreakGlassConfig.from_settings(make_settings(breakglass_require_idp_down=False))
    assert condition_met(config, idp_healthy=True) is True
    assert condition_met(config, idp_healthy=False) is True
