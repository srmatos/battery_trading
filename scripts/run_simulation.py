#!/usr/bin/env python3
"""Command-line entry point: run the battery dispatch simulation on the provided data.

Loads the battery spec and market prices, runs a ThresholdStrategy on each market,
prints a profit summary and optionally saves a chart and per-period CSVs.

Example:
    python scripts/run_simulation.py --plot output/simulation.png --export-csv output
"""
from __future__ import annotations

import argparse
import os
import sys

# Lets the script run from a checkout without `pip install -e .`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from battery_trading import Battery, BatterySpec, Simulator, ThresholdStrategy, load_markets
from battery_trading.reporting import plot_results, summarise


def parse_args() -> argparse.Namespace:
    """Define and parse the CLI options."""
    parser = argparse.ArgumentParser(description="Simulate battery trading across two markets.")
    parser.add_argument("--spec", default="Attachment 1.xlsx", help="Battery spec workbook")
    parser.add_argument("--prices", default="Attachment 2.xlsx", help="Market price workbook")
    parser.add_argument("--lookback-days", type=float, default=7.0,
                        help="Rolling window (days) used to set cheap/expensive thresholds")
    parser.add_argument("--charge-quantile", type=float, default=0.25,
                        help="Charge when price <= this quantile of the window")
    parser.add_argument("--discharge-quantile", type=float, default=0.75,
                        help="Discharge when price >= this quantile of the window")
    parser.add_argument("--initial-soc", type=float, default=0.0, help="Starting energy (MWh)")
    parser.add_argument("--plot", help="Save a PNG chart to this path")
    parser.add_argument("--export-csv", help="Save per-period dispatch CSVs into this directory")
    return parser.parse_args()


def main() -> None:
    """Wire spec, markets, strategies and simulator together, then report the results."""
    args = parse_args()

    spec = BatterySpec.from_excel(args.spec)
    markets = load_markets(args.prices)

    # The window is given in days but each strategy works in its own market's periods.
    strategies = {
        key: ThresholdStrategy(
            lookback_periods=round(args.lookback_days * 24 / market.interval_hours),
            charge_quantile=args.charge_quantile,
            discharge_quantile=args.discharge_quantile,
        )
        for key, market in markets.items()
    }

    simulator = Simulator(Battery(spec=spec, soc_mwh=args.initial_soc), markets, strategies)
    result = simulator.run()
    print(summarise(result))

    if args.export_csv:
        os.makedirs(args.export_csv, exist_ok=True)
        result.m1.to_csv(os.path.join(args.export_csv, "market1_dispatch.csv"))
        result.m2.to_csv(os.path.join(args.export_csv, "market2_dispatch.csv"))
        result.soc_trajectory.to_csv(os.path.join(args.export_csv, "soc_trajectory.csv"))
        print(f"\nCSV results written to {args.export_csv}/")

    if args.plot:
        os.makedirs(os.path.dirname(args.plot) or ".", exist_ok=True)
        plot_results(result, args.plot)
        print(f"Chart written to {args.plot}")


if __name__ == "__main__":
    main()
