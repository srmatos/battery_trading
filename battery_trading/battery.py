"""Physical battery model: state of charge, efficiency losses and feasibility limits.

All power values are measured at the grid connection, i.e. the power traded in the
markets. Efficiency losses sit between the grid and the storage:

  - charging ``P`` MW for ``t`` h imports ``P*t`` MWh but stores only
    ``P*t*(1 - charge_efficiency_loss)`` MWh;
  - discharging ``P`` MW for ``t`` h exports ``P*t`` MWh but withdraws
    ``P*t / (1 - discharge_efficiency_loss)`` MWh from storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .spec import BatterySpec
from .types import Direction

# Powers/energies below this are treated as zero, to absorb floating-point noise.
_EPS = 1e-9


@dataclass
class Battery:
    """Mutable battery state plus the conversions and limits that depend on it.

    ``apply`` is the only method that changes state; every other method is a pure
    calculation the simulator uses to plan feasible commitments before applying them.
    """

    spec: BatterySpec
    soc_mwh: float = 0.0
    cumulative_charge_energy_mwh: float = field(default=0.0, init=False)
    cumulative_discharge_throughput_mwh: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Clamp the initial state of charge into the physically valid range."""
        self.soc_mwh = min(max(self.soc_mwh, 0.0), self.spec.max_storage_mwh)

    # --- pure energy/power conversions -------------------------------------------------
    def energy_stored_for_charge(self, power_mw: float, duration_h: float) -> float:
        """MWh that ends up in storage when importing ``power_mw`` for ``duration_h``."""
        return power_mw * duration_h * (1 - self.spec.charge_efficiency_loss)

    def charge_power_for_stored_energy(self, energy_mwh: float, duration_h: float) -> float:
        """Import power needed to store ``energy_mwh`` over ``duration_h`` (inverse of above)."""
        if duration_h <= 0:
            return 0.0
        return energy_mwh / (duration_h * (1 - self.spec.charge_efficiency_loss))

    def energy_withdrawn_for_discharge(self, power_mw: float, duration_h: float) -> float:
        """MWh taken out of storage when exporting ``power_mw`` for ``duration_h``."""
        return power_mw * duration_h / (1 - self.spec.discharge_efficiency_loss)

    def discharge_power_for_withdrawn_energy(self, energy_mwh: float, duration_h: float) -> float:
        """Export power deliverable by withdrawing ``energy_mwh`` over ``duration_h``."""
        if duration_h <= 0:
            return 0.0
        return energy_mwh * (1 - self.spec.discharge_efficiency_loss) / duration_h

    def project_soc(self, direction: Direction, power_mw: float, duration_h: float) -> float:
        """State of charge the action would lead to, without changing the battery."""
        if direction is Direction.CHARGE:
            return self.soc_mwh + self.energy_stored_for_charge(power_mw, duration_h)
        if direction is Direction.DISCHARGE:
            return self.soc_mwh - self.energy_withdrawn_for_discharge(power_mw, duration_h)
        return self.soc_mwh

    # --- feasibility at the current state of charge --------------------------------------
    def max_power(self, direction: Direction, duration_h: float) -> float:
        """Largest power sustainable in ``direction`` for ``duration_h`` from the current SoC,
        bounded by both the rate limit and the storage headroom/energy available."""
        if duration_h <= 0 or direction is Direction.IDLE:
            return 0.0
        if direction is Direction.CHARGE:
            headroom = max(self.spec.max_storage_mwh - self.soc_mwh, 0.0)
            by_soc = self.charge_power_for_stored_energy(headroom, duration_h)
            return min(self.spec.max_charge_mw, by_soc)
        by_soc = self.discharge_power_for_withdrawn_energy(max(self.soc_mwh, 0.0), duration_h)
        return min(self.spec.max_discharge_mw, by_soc)

    # --- state mutation ------------------------------------------------------------------
    def apply(self, direction: Direction, power_mw: float, duration_h: float) -> float:
        """Execute an action, clipped to what is physically feasible, and update the SoC.

        Returns the power actually realised at the grid (<= ``power_mw``); callers must use
        this value, not the requested one, for any cash-flow calculation.
        """
        if direction is Direction.IDLE or power_mw <= _EPS or duration_h <= 0:
            return 0.0

        realised = min(power_mw, self.max_power(direction, duration_h))
        if realised <= _EPS:
            return 0.0

        if direction is Direction.CHARGE:
            stored = self.energy_stored_for_charge(realised, duration_h)
            self.soc_mwh = min(self.spec.max_storage_mwh, self.soc_mwh + stored)
            self.cumulative_charge_energy_mwh += realised * duration_h
        else:
            withdrawn = self.energy_withdrawn_for_discharge(realised, duration_h)
            self.soc_mwh = max(0.0, self.soc_mwh - withdrawn)
            self.cumulative_discharge_throughput_mwh += withdrawn
        return realised

    @property
    def equivalent_full_cycles(self) -> float:
        """Cycles used so far: storage energy discharged divided by max storage volume, so
        partial cycles count proportionally (matches the spec's definition of a cycle)."""
        if self.spec.max_storage_mwh <= 0:
            return 0.0
        return self.cumulative_discharge_throughput_mwh / self.spec.max_storage_mwh
