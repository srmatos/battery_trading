"""Decision logic: turns a market's price series into a desired action per period.

Strategies only see prices (never the battery's state of charge) and state what they
*want* to do. Feasibility (rate limits, energy in storage, no simultaneous charge and
discharge, fixed commitments per settlement period) is enforced by the simulator, so a
strategy can be swapped or made smarter without any risk of producing an invalid dispatch.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .market import Market
from .spec import BatterySpec
from .types import Direction


@dataclass(frozen=True)
class Intent:
    """What a strategy wants to do in one settlement period of one market."""

    direction: Direction
    power_mw: float


class BaseStrategy(ABC):
    """Interface every dispatch strategy implements; the simulator depends only on this."""

    @abstractmethod
    def decide(self, market: Market, spec: BatterySpec) -> pd.Series:
        """Return a Series of :class:`Intent` indexed exactly like ``market.prices``.

        ``spec`` lets the strategy size its desired power to the battery's rate limits; it
        must not depend on the battery's state of charge.
        """


class ThresholdStrategy(BaseStrategy):
    """Rolling-quantile rule: charge when cheap, discharge when expensive.

    For each period the price is compared with the ``charge_quantile`` and
    ``discharge_quantile`` of the previous ``lookback_periods`` prices of the same market.
    The window is shifted by one period so a decision never sees the current or any future
    price. Deliberately simple and myopic, as the exercise allows.
    """

    def __init__(
        self,
        lookback_periods: int = 336,
        charge_quantile: float = 0.25,
        discharge_quantile: float = 0.75,
        min_periods: int | None = None,
    ) -> None:
        """``lookback_periods`` is in the market's own periods (336 half-hours = 7 days);
        ``min_periods`` is how much history is needed before acting (default 10% of it)."""
        if lookback_periods <= 0:
            raise ValueError("lookback_periods must be positive")
        if not 0.0 <= charge_quantile < discharge_quantile <= 1.0:
            raise ValueError("Require 0 <= charge_quantile < discharge_quantile <= 1")
        self.lookback_periods = lookback_periods
        self.charge_quantile = charge_quantile
        self.discharge_quantile = discharge_quantile
        self.min_periods = min_periods if min_periods is not None else max(4, lookback_periods // 10)

    def decide(self, market: Market, spec: BatterySpec) -> pd.Series:
        """Classify every period as charge/discharge/idle and request full rated power."""
        prices = market.prices
        rolling = prices.shift(1).rolling(self.lookback_periods, min_periods=self.min_periods)
        low = rolling.quantile(self.charge_quantile).to_numpy()
        high = rolling.quantile(self.discharge_quantile).to_numpy()
        values = prices.to_numpy()

        # Integer codes index into `choices`; NaN thresholds (not enough history yet) compare
        # False, so those periods fall through to idle.
        codes = np.select([values <= low, values >= high], [0, 1], default=2)
        choices = (
            Intent(Direction.CHARGE, spec.max_charge_mw),
            Intent(Direction.DISCHARGE, spec.max_discharge_mw),
            Intent(Direction.IDLE, 0.0),
        )
        return pd.Series([choices[c] for c in codes], index=prices.index)
