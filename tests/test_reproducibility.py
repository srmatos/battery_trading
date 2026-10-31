"""End-to-end regression test: the default run on the provided data must reproduce the
headline results published in the README. The model is fully deterministic (no randomness),
so any change in these numbers means the model's behaviour changed."""
from pathlib import Path

import pytest

from battery_trading import Battery, BatterySpec, Simulator, ThresholdStrategy, load_markets

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "Attachment 1.xlsx"
PRICES_PATH = ROOT / "Attachment 2.xlsx"


@pytest.mark.skipif(
    not (SPEC_PATH.exists() and PRICES_PATH.exists()), reason="input workbooks not present"
)
def test_default_run_reproduces_published_results():
    """Same configuration as `scripts/run_simulation.py` with default arguments."""
    spec = BatterySpec.from_excel(str(SPEC_PATH))
    markets = load_markets(str(PRICES_PATH))
    strategies = {"m1": ThresholdStrategy(lookback_periods=336), "m2": ThresholdStrategy(lookback_periods=168)}
    result = Simulator(Battery(spec=spec, soc_mwh=0.0), markets, strategies).run()

    assert result.net_profit_gbp == pytest.approx(78_280.15, abs=0.01)
    assert result.m1.cashflow_gbp.sum() == pytest.approx(-3_452.75, abs=0.01)
    assert result.m2.cashflow_gbp.sum() == pytest.approx(81_732.90, abs=0.01)
    assert result.final_battery.equivalent_full_cycles == pytest.approx(1_124.4, abs=0.1)
