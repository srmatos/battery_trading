"""Unit tests for the Simulator: market rules, rate limits and Market 2 priority."""
import pandas as pd
import pytest

from battery_trading.battery import Battery
from battery_trading.simulator import Simulator
from battery_trading.strategy import BaseStrategy, Intent
from battery_trading.types import Direction
from tests.factories import make_markets, make_spec


class FixedStrategy(BaseStrategy):
    """Requests the same direction and power in every period, for deterministic tests."""

    def __init__(self, direction: Direction, power_mw: float = 0.0):
        self.intent = Intent(direction, power_mw)

    def decide(self, market, spec):
        """Repeat the fixed intent for every period of the market."""
        return pd.Series([self.intent] * len(market.prices), index=market.prices.index)


def run_one_hour(spec, soc, m1: FixedStrategy, m2: FixedStrategy, price=50.0):
    """Simulate a single hour (two Market 1 half-hours, one Market 2 hour) at a flat price."""
    battery = Battery(spec=spec, soc_mwh=soc)
    markets = make_markets([price, price], [price])
    result = Simulator(battery, markets, {"m1": m1, "m2": m2}).run()
    return battery, result


def test_brief_example_splitting_across_markets_in_same_direction():
    """2 MW to Market 1 + 3 MW to Market 2 = 5 MW at the limit, emptying a 5 MWh battery."""
    battery, result = run_one_hour(
        make_spec(max_discharge_mw=5.0, max_storage_mwh=5.0), 5.0,
        FixedStrategy(Direction.DISCHARGE, 2.0), FixedStrategy(Direction.DISCHARGE, 3.0),
    )
    assert result.m1.power_mw.tolist() == pytest.approx([2.0, 2.0])
    assert result.m2.power_mw.tolist() == pytest.approx([3.0])
    assert battery.soc_mwh == pytest.approx(0.0)
    # (2 * 0.5 + 2 * 0.5) * 50 + 3 * 1.0 * 50
    assert result.net_profit_gbp == pytest.approx(250.0)


def test_combined_power_never_exceeds_rate_limit():
    """When both markets ask for the full rate, the total is still capped at the rate."""
    _, result = run_one_hour(
        make_spec(max_discharge_mw=5.0, max_storage_mwh=100.0), 100.0,
        FixedStrategy(Direction.DISCHARGE, 5.0), FixedStrategy(Direction.DISCHARGE, 5.0),
    )
    combined = result.m1.power_mw.to_numpy() + result.m2.power_mw.iloc[0]
    assert (combined <= 5.0 + 1e-9).all()


def test_m1_blocked_when_opposite_to_active_m2():
    """Market 1 cannot discharge while Market 2 is charging the same battery."""
    _, result = run_one_hour(
        make_spec(), 2.0,
        FixedStrategy(Direction.DISCHARGE, 2.0), FixedStrategy(Direction.CHARGE, 2.0),
    )
    assert (result.m1.direction == "idle").all()
    assert result.diagnostics.m1_conflicts_with_active_m2 == 2


def test_m1_free_when_m2_has_nothing_feasible():
    """Market 2 wants to discharge an empty battery (0 MW feasible), so Market 1 may charge."""
    battery, result = run_one_hour(
        make_spec(), 0.0,
        FixedStrategy(Direction.CHARGE, 2.0), FixedStrategy(Direction.DISCHARGE, 2.0),
    )
    assert result.m2.direction.iloc[0] == "idle"
    assert result.m1.power_mw.tolist() == pytest.approx([2.0, 2.0])
    assert battery.soc_mwh == pytest.approx(2.0)


def test_m2_commitment_is_never_clipped_mid_hour_by_m1():
    """Market 2 needs the whole capacity for its hour; Market 1 must not eat into it."""
    battery, result = run_one_hour(
        make_spec(max_charge_mw=10.0), 0.0,
        FixedStrategy(Direction.CHARGE, 10.0), FixedStrategy(Direction.CHARGE, 4.0), price=10.0,
    )
    assert result.m2.power_mw.iloc[0] == pytest.approx(4.0)
    assert (result.m1.power_mw == 0.0).all()
    assert battery.soc_mwh == pytest.approx(4.0)


def test_both_idle_has_no_cashflow_and_no_soc_change():
    """Doing nothing earns nothing and leaves the battery untouched."""
    battery, result = run_one_hour(
        make_spec(), 1.5, FixedStrategy(Direction.IDLE), FixedStrategy(Direction.IDLE)
    )
    assert result.net_profit_gbp == 0.0
    assert battery.soc_mwh == pytest.approx(1.5)
