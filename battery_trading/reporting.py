"""Presentation of a simulation run: a text summary and an optional PNG chart."""
from __future__ import annotations

import pandas as pd

from .simulator import SimulationResult


def _revenue_and_cost(dispatch: pd.DataFrame) -> tuple[float, float]:
    """Split a market's cash flows into revenue (discharge) and cost (charge), both >= 0."""
    cash = dispatch.cashflow_gbp
    return float(cash[cash > 0].sum()), float(-cash[cash < 0].sum())


def summarise(result: SimulationResult) -> str:
    """Return a multi-line summary of profit, energy, cycling and diagnostics."""
    battery = result.final_battery
    spec = battery.spec
    diag = result.diagnostics

    m1_revenue, m1_cost = _revenue_and_cost(result.m1)
    m2_revenue, m2_cost = _revenue_and_cost(result.m2)
    years = len(result.m2) / (365.25 * 24)
    cycles = battery.equivalent_full_cycles

    rows = [
        ("Market 1 revenue (discharge)", f"£{m1_revenue:,.2f}"),
        ("Market 1 cost (charge)", f"£{m1_cost:,.2f}"),
        ("Market 2 revenue (discharge)", f"£{m2_revenue:,.2f}"),
        ("Market 2 cost (charge)", f"£{m2_cost:,.2f}"),
        None,
        ("Total trading revenue", f"£{m1_revenue + m2_revenue:,.2f}"),
        ("Total trading cost", f"£{m1_cost + m2_cost:,.2f}"),
        ("Net trading profit", f"£{result.net_profit_gbp:,.2f}"),
        ("Fixed opex over period (info)", f"£{spec.fixed_opex_gbp_per_year * years:,.2f}"
         f" (capex £{spec.capex_gbp:,.0f} not included)"),
        None,
        ("Energy imported from grid", f"{battery.cumulative_charge_energy_mwh:,.1f} MWh"),
        ("Final state of charge", f"{battery.soc_mwh:.3f} / {spec.max_storage_mwh:.1f} MWh"),
        ("Equivalent full cycles used", f"{cycles:,.1f} / {spec.lifetime_cycles:,.0f}"
         f" ({100 * cycles / spec.lifetime_cycles:.1f}% of rated life)"),
        None,
        ("M1 blocked by opposite M2 commitment", f"{diag.m1_conflicts_with_active_m2} half-hours"),
        ("M1 capped by shared storage budget", f"{diag.m1_budget_exhausted_events} half-hours"),
    ]
    width = max(len(r[0]) for r in rows if r)
    lines = [
        "=== Battery dispatch simulation summary ===",
        f"Period: {result.m1.index[0]} -> {result.m1.index[-1]} ({years:.2f} years)",
        "",
    ]
    lines += ["" if r is None else f"{r[0]:<{width}} : {r[1]}" for r in rows]
    return "\n".join(lines)


def plot_results(result: SimulationResult, output_path: str) -> None:
    """Save a 3-panel PNG (prices, state of charge, cumulative profit) to ``output_path``.

    Matplotlib is imported lazily so it stays an optional dependency of the package.
    """
    import matplotlib

    matplotlib.use("Agg")  # headless backend: works without a display (CI, SSH, etc.)
    import matplotlib.pyplot as plt

    # Market 1 timestamps follow UK clock changes and are not strictly monotonic, so pair
    # its cash flows with Market 2's hours positionally instead of using resample().
    m1_per_hour = result.m1.cashflow_gbp.to_numpy().reshape(-1, 2).sum(axis=1)
    cum_profit = (m1_per_hour + result.m2.cashflow_gbp.to_numpy()).cumsum()

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    axes[0].plot(result.m1.index, result.m1.price, label="Market 1 (£/MWh)", linewidth=0.7)
    axes[0].plot(result.m2.index, result.m2.price, label="Market 2 (£/MWh)", linewidth=0.7)
    axes[0].set_ylabel("Price (£/MWh)")
    axes[0].legend(loc="upper right")
    axes[0].set_title("Market prices")

    axes[1].plot(result.soc_trajectory.index, result.soc_trajectory.to_numpy(), color="green")
    axes[1].set_ylabel("SoC (MWh)")
    axes[1].set_title("Battery state of charge")

    axes[2].plot(result.m2.index, cum_profit, color="black")
    axes[2].set_ylabel("Cumulative profit (£)")
    axes[2].set_title("Cumulative net profit")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
