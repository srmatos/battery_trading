"""Turns strategy intents into a feasible dispatch and computes the resulting cash flows.

This is the single place where every hard constraint is enforced:

  - the battery never charges and discharges at the same time;
  - a market commitment is held constant for that market's whole settlement period;
  - combined power across both markets never exceeds the charge/discharge rate limit;
  - the battery never goes above max storage or below empty.

Markets are aligned by position (see ``market.load_markets``): Market 2 hour ``j`` contains
Market 1 half-hours ``2*j`` and ``2*j+1``. Market 2's commitment spans the whole hour, so it
is fixed first, capped to what is feasible for the full hour. Market 1 may then only use
the rate and storage headroom that Market 2 leaves, in time order across the two halves.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .battery import Battery
from .market import Market
from .strategy import BaseStrategy, Intent
from .types import Direction

_EPS = 1e-9

# Cash-flow sign per direction: selling (discharge) earns money, buying (charge) costs it.
_CASH_SIGN = {Direction.DISCHARGE: 1.0, Direction.CHARGE: -1.0, Direction.IDLE: 0.0}

# (direction, realised power MW, state of charge MWh after the half-hour)
_HalfHourOutcome = tuple[Direction, float, float]


@dataclass
class Diagnostics:
    """Counters of notable events in a run, surfaced in the summary for transparency."""

    m1_conflicts_with_active_m2: int = 0
    m1_budget_exhausted_events: int = 0


@dataclass
class SimulationResult:
    """Output of a run.

    ``m1`` / ``m2`` hold one row per settlement period of each market with columns
    ``direction``, ``power_mw``, ``price`` and ``cashflow_gbp`` (positive = revenue).
    ``soc_trajectory`` is the state of charge at the end of each half-hour.
    """

    m1: pd.DataFrame
    m2: pd.DataFrame
    soc_trajectory: pd.Series
    final_battery: Battery
    diagnostics: Diagnostics

    @property
    def net_profit_gbp(self) -> float:
        """Total trading revenue minus total charging cost across both markets."""
        return float(self.m1.cashflow_gbp.sum() + self.m2.cashflow_gbp.sum())


def _dispatch_frame(
    prices: pd.Series, directions: list[Direction], powers: np.ndarray, duration_h: float
) -> pd.DataFrame:
    """Build a per-period dispatch table, computing cash flows vectorised in one pass."""
    price_values = prices.to_numpy()
    signs = np.array([_CASH_SIGN[d] for d in directions])
    frame = pd.DataFrame(
        {
            "direction": [d.value for d in directions],
            "power_mw": powers,
            "price": price_values,
            "cashflow_gbp": signs * powers * duration_h * price_values,
        },
        index=prices.index,
    )
    frame.index.name = "timestamp"
    return frame


class Simulator:
    """Runs one strategy per market against a battery over the full price history."""

    def __init__(
        self,
        battery: Battery,
        markets: dict[str, Market],
        strategies: dict[str, BaseStrategy],
    ) -> None:
        """``markets`` and ``strategies`` are keyed ``"m1"`` (half-hourly) and ``"m2"`` (hourly)."""
        self.battery = battery
        self.m1 = markets["m1"]
        self.m2 = markets["m2"]
        self.strategy_m1 = strategies["m1"]
        self.strategy_m2 = strategies["m2"]

        if len(self.m1.prices) != 2 * len(self.m2.prices):
            raise ValueError("Market 1 must have exactly twice the periods of Market 2.")
        if not np.isclose(self.m2.interval_hours, 2 * self.m1.interval_hours):
            raise ValueError("Market 2's period must be exactly twice Market 1's.")

    def run(self) -> SimulationResult:
        """Simulate every hour in order and return the dispatch, SoC and diagnostics."""
        battery = self.battery
        # Plain lists: per-element access is far cheaper than pandas .iloc inside the loop.
        m1_intents: list[Intent] = self.strategy_m1.decide(self.m1, battery.spec).tolist()
        m2_intents: list[Intent] = self.strategy_m2.decide(self.m2, battery.spec).tolist()
        d1, d2 = self.m1.interval_hours, self.m2.interval_hours

        n_hours = len(m2_intents)
        m1_dirs = [Direction.IDLE] * (2 * n_hours)
        m1_powers = np.zeros(2 * n_hours)
        m2_dirs = [Direction.IDLE] * n_hours
        m2_powers = np.zeros(n_hours)
        soc = np.zeros(2 * n_hours)
        diag = Diagnostics()

        for j, m2_intent in enumerate(m2_intents):
            halves = m1_intents[2 * j : 2 * j + 2]
            m2_dir = m2_intent.direction
            # Capped over the FULL hour, so the commitment can be honoured in both halves.
            m2_power = min(m2_intent.power_mw, battery.max_power(m2_dir, d2))

            if m2_power > _EPS:
                m2_dirs[j] = m2_dir
                m2_powers[j] = m2_power
                outcomes = self._m2_active_hour(m2_dir, m2_power, halves, d1, d2, diag)
            else:
                # Includes the case where Market 2 wanted to trade but nothing is feasible
                # (e.g. discharge with an empty battery): Market 1 is then unconstrained.
                outcomes = self._m2_idle_hour(halves, d1)

            for k, (direction, power, soc_after) in enumerate(outcomes):
                i = 2 * j + k
                m1_dirs[i] = direction
                m1_powers[i] = power
                soc[i] = soc_after

        return SimulationResult(
            m1=_dispatch_frame(self.m1.prices, m1_dirs, m1_powers, d1),
            m2=_dispatch_frame(self.m2.prices, m2_dirs, m2_powers, d2),
            soc_trajectory=pd.Series(soc, index=self.m1.prices.index, name="soc_mwh"),
            final_battery=battery,
            diagnostics=diag,
        )

    def _m2_idle_hour(self, halves: list[Intent], d1: float) -> list[_HalfHourOutcome]:
        """Market 2 is not trading this hour: Market 1 acts freely in each half-hour (it may
        even charge in one half and discharge in the other), limited only by physics."""
        outcomes = []
        for intent in halves:
            power = self.battery.apply(intent.direction, intent.power_mw, d1)
            direction = intent.direction if power > _EPS else Direction.IDLE
            outcomes.append((direction, power, self.battery.soc_mwh))
        return outcomes

    def _m2_active_hour(
        self,
        m2_dir: Direction,
        m2_power: float,
        halves: list[Intent],
        d1: float,
        d2: float,
        diag: Diagnostics,
    ) -> list[_HalfHourOutcome]:
        """Market 2 holds ``m2_power`` in ``m2_dir`` for the whole hour. Market 1 may add
        power in the same direction only, limited by:

          - rate headroom: ``max_rate - m2_power`` in each half-hour;
          - a storage budget shared by both halves: the extra energy that can move on top
            of Market 2's full-hour effect without overfilling or emptying the battery, so
            Market 2's commitment is guaranteed to be deliverable in the second half too.
        """
        battery = self.battery
        spec = battery.spec
        charging = m2_dir is Direction.CHARGE

        max_rate = spec.max_charge_mw if charging else spec.max_discharge_mw
        rate_headroom = max(max_rate - m2_power, 0.0)
        soc_end_m2_only = battery.project_soc(m2_dir, m2_power, d2)
        budget_mwh = max(spec.max_storage_mwh - soc_end_m2_only if charging else soc_end_m2_only, 0.0)

        outcomes = []
        for intent in halves:
            m1_power = 0.0
            if intent.direction is m2_dir and intent.power_mw > _EPS and rate_headroom > _EPS:
                m1_power = min(intent.power_mw, rate_headroom)
                energy = (
                    battery.energy_stored_for_charge(m1_power, d1)
                    if charging
                    else battery.energy_withdrawn_for_discharge(m1_power, d1)
                )
                if energy > budget_mwh + _EPS:
                    diag.m1_budget_exhausted_events += 1
                    m1_power = (
                        battery.charge_power_for_stored_energy(budget_mwh, d1)
                        if charging
                        else battery.discharge_power_for_withdrawn_energy(budget_mwh, d1)
                    )
                    energy = budget_mwh
                budget_mwh = max(budget_mwh - energy, 0.0)
            elif intent.direction not in (Direction.IDLE, m2_dir):
                # Opposite direction to an active Market 2 commitment: not allowed.
                diag.m1_conflicts_with_active_m2 += 1

            realised = battery.apply(m2_dir, m2_power + m1_power, d1)
            # By construction nothing is clipped here; if float noise ever clips, Market 2
            # keeps priority and Market 1 absorbs the shortfall.
            m1_power = min(m1_power, max(realised - m2_power, 0.0))
            direction = m2_dir if m1_power > _EPS else Direction.IDLE
            outcomes.append((direction, m1_power, battery.soc_mwh))
        return outcomes
