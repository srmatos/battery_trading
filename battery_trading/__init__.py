"""battery_trading: a price-taking battery trading across two wholesale electricity markets.

Modules:
  spec       BatterySpec, loaded from Attachment 1
  market     Market and load_markets, loaded from Attachment 2
  battery    Battery: state of charge, efficiency losses, feasibility limits
  strategy   BaseStrategy, ThresholdStrategy: price-only decision logic
  simulator  Simulator: enforces all constraints and computes cash flows
  reporting  summarise() and plot_results()
"""

from .battery import Battery
from .market import Market, load_markets
from .simulator import SimulationResult, Simulator
from .spec import BatterySpec
from .strategy import BaseStrategy, Intent, ThresholdStrategy
from .types import Direction

__all__ = [
    "Battery",
    "BatterySpec",
    "Market",
    "load_markets",
    "Simulator",
    "SimulationResult",
    "BaseStrategy",
    "Intent",
    "ThresholdStrategy",
    "Direction",
]
