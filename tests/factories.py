"""Shared test builders, so every test file constructs specs and markets the same way."""
from __future__ import annotations

import pandas as pd

from battery_trading.market import Market
from battery_trading.spec import BatterySpec


def make_spec(**overrides) -> BatterySpec:
    """A 2 MW / 4 MWh lossless battery by default; override any field per test."""
    defaults = dict(
        max_charge_mw=2.0,
        max_discharge_mw=2.0,
        max_storage_mwh=4.0,
        charge_efficiency_loss=0.0,
        discharge_efficiency_loss=0.0,
        lifetime_years=10.0,
        lifetime_cycles=5000.0,
        degradation_pct_per_cycle=0.001,
        capex_gbp=500_000.0,
        fixed_opex_gbp_per_year=5_000.0,
    )
    defaults.update(overrides)
    return BatterySpec(**defaults)


def make_market(prices: list[float], interval_hours: float = 0.5, start: str = "2024-01-01") -> Market:
    """A single market with regularly spaced periods starting at ``start``."""
    index = pd.date_range(start, periods=len(prices), freq=pd.Timedelta(hours=interval_hours))
    return Market(name=f"{interval_hours}h market", interval_hours=interval_hours, prices=pd.Series(prices, index=index))


def make_markets(m1_prices: list[float], m2_prices: list[float]) -> dict[str, Market]:
    """A half-hourly Market 1 and an hourly Market 2 covering the same period."""
    return {"m1": make_market(m1_prices, 0.5), "m2": make_market(m2_prices, 1.0)}
