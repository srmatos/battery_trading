"""Battery technical and financial specification, loaded from Attachment 1.

The spreadsheet lists one parameter per row (label in column A, value in column B). This
module maps those row labels onto a typed, immutable ``BatterySpec`` so the rest of the
package never has to deal with spreadsheet layout or label strings.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Attribute name on BatterySpec -> row label used in the source spreadsheet.
_FIELD_LABELS = {
    "max_charge_mw": "Max charging rate",
    "max_discharge_mw": "Max discharging rate",
    "max_storage_mwh": "Max storage volume",
    "charge_efficiency_loss": "Battery charging efficiency",
    "discharge_efficiency_loss": "Battery discharging efficiency",
    "lifetime_years": "Lifetime (1)",
    "lifetime_cycles": "Lifetime (2)",
    "degradation_pct_per_cycle": "Storage volume degradation rate",
    "capex_gbp": "Capex",
    "fixed_opex_gbp_per_year": "Fixed Operational Costs",
}


@dataclass(frozen=True)
class BatterySpec:
    """Immutable technical/financial parameters of the battery asset.

    Rates are in MW, storage in MWh, money in £. ``charge_efficiency_loss`` and
    ``discharge_efficiency_loss`` are fractions (0.05 = 5%) of energy lost on the way into
    and out of storage respectively. Lifetime, degradation, capex and opex are carried for
    reporting only; they do not influence dispatch decisions.
    """

    max_charge_mw: float
    max_discharge_mw: float
    max_storage_mwh: float
    charge_efficiency_loss: float
    discharge_efficiency_loss: float
    lifetime_years: float
    lifetime_cycles: float
    degradation_pct_per_cycle: float
    capex_gbp: float
    fixed_opex_gbp_per_year: float

    @classmethod
    def from_excel(cls, path: str, sheet_name: str = "Data") -> "BatterySpec":
        """Build a spec from the Attachment 1 workbook (label/value rows on ``sheet_name``)."""
        df = pd.read_excel(path, sheet_name=sheet_name, header=0, index_col=0)
        values = df["Values"]
        return cls(**{attr: float(values[label]) for attr, label in _FIELD_LABELS.items()})
