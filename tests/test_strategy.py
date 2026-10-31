"""Unit tests for ThresholdStrategy: classification, warm-up and no look-ahead."""
import pytest

from battery_trading.strategy import ThresholdStrategy
from battery_trading.types import Direction
from tests.factories import make_market, make_spec


def test_idle_until_enough_history():
    """With fewer than min_periods past prices the strategy never acts."""
    market = make_market([50.0] * 10)
    intents = ThresholdStrategy(lookback_periods=20, min_periods=15).decide(market, make_spec())
    assert all(i.direction is Direction.IDLE for i in intents)


def test_charges_on_cheap_price_and_discharges_on_expensive_price():
    """After a flat baseline, a price dip triggers charge and a spike triggers discharge."""
    market = make_market([50.0] * 50 + [1.0, 99.0])
    intents = ThresholdStrategy(lookback_periods=50, min_periods=20).decide(market, make_spec())
    assert intents.iloc[-2].direction is Direction.CHARGE
    assert intents.iloc[-2].power_mw == 2.0
    assert intents.iloc[-1].direction is Direction.DISCHARGE
    assert intents.iloc[-1].power_mw == 2.0


def test_never_uses_future_prices():
    """The first period has no history at all, so it must be idle even if it's the cheapest."""
    market = make_market([1.0] + [50.0] * 50)
    intents = ThresholdStrategy(lookback_periods=50, min_periods=5).decide(market, make_spec())
    assert intents.iloc[0].direction is Direction.IDLE


def test_rejects_invalid_quantiles():
    """The charge quantile must sit strictly below the discharge quantile."""
    with pytest.raises(ValueError):
        ThresholdStrategy(charge_quantile=0.8, discharge_quantile=0.2)
