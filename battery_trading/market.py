"""Wholesale market price series, loaded from Attachment 2.

Each market is a fixed settlement-period length plus a price series. The loader also
validates that the two markets can be aligned positionally (see ``load_markets``).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Market:
    """One wholesale market.

    ``interval_hours`` is the settlement-period length (0.5 for Market 1, 1.0 for Market 2)
    and is used by the simulator to turn committed power (MW) into traded energy (MWh).
    ``prices`` is in £/MWh, indexed by the start timestamp of each settlement period.
    """

    name: str
    interval_hours: float
    prices: pd.Series


def load_markets(path: str) -> dict[str, Market]:
    """Load Market 1 (half-hourly) and Market 2 (hourly) from the Attachment 2 workbook.

    Returns ``{"m1": Market, "m2": Market}``.

    The two series are aligned by row position, not by timestamp: Market 1 rows
    ``2*i`` and ``2*i+1`` belong to Market 2 row ``i``. The half-hourly timestamps follow UK
    clock changes (46 or 50 periods on DST days) while the hourly ones do not, so joining on
    timestamps would misalign a few periods twice a year. Both series start at the same
    instant and Market 1 has exactly twice as many rows, which this function enforces.
    """
    # dropna() removes the empty trailing rows the hourly sheet carries in the workbook.
    m1_df = pd.read_excel(path, sheet_name="Half-hourly data", header=0, index_col=0).dropna()
    m2_df = pd.read_excel(path, sheet_name="Hourly data", header=0, index_col=0).dropna()

    if len(m1_df) != 2 * len(m2_df):
        raise ValueError(
            f"Expected Market 1 to have exactly 2x the rows of Market 2 for positional "
            f"alignment, got {len(m1_df)} vs {len(m2_df)}."
        )

    return {
        "m1": Market("Market 1", 0.5, m1_df.iloc[:, 0].rename("price")),
        "m2": Market("Market 2", 1.0, m2_df.iloc[:, 0].rename("price")),
    }
