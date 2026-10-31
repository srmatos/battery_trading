# battery_trading

Models a price-taking battery (2 MW / 4 MWh) charging and discharging across two wholesale
electricity markets to maximise trading profit, using the battery spec in
`Attachment 1.xlsx` and the market prices in `Attachment 2.xlsx`.


## A brief summary of my approach to the challenge

I built a small Python package that keeps the decision logic separate from the physics and
the market rules. A *strategy* looks only at prices and states what it would like to do.
The current one is a deliberately simple rule: in each market, charge when the price is at
or below the 25th percentile of that market's previous 7 days of prices, and discharge when
it is at or above the 75th percentile. A *simulator* then turns those wishes into a dispatch
that is always feasible. It enforces the charge/discharge rate limits, the 4 MWh storage
limit and the 5% losses on both charging and discharging. It also stops the battery from
charging and discharging at the same time, and holds each commitment for the market's full
settlement period. Because the hourly Market 2 commitment spans both of Market 1's
half-hours, it is fixed first. Market 1 can then only use the leftover power and storage
headroom, and only in the same direction. Every decision uses past prices only, so there is
no look-ahead. The run is fully deterministic. Over 2018–2020 it earns about £78k of trading
profit, buying £174k of energy and selling it for £252k, while using 22.5% of the battery's
rated 5,000 cycles. The design leaves room for a better optimiser to replace the heuristic later,
for example a rolling linear program across both markets. That optimiser would only need to
implement the same `BaseStrategy` interface.


## Instructions on how to set up and run the battery dispatch model

Requirements: Python 3.11 or newer (tested on 3.13.1). Run these commands from this directory:

```bash
# 1. Create an isolated environment and install the pinned dependencies
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Run the model on the provided data
python scripts/run_simulation.py --plot output/simulation.png --export-csv output

# 3. Run the test suite (unit tests + an end-to-end check of the published results)
pytest
```

Step 2 prints a profit summary. `--plot` saves a chart of prices, state of charge and
cumulative profit. `--export-csv` writes the per-period dispatch for both markets and the
state-of-charge trajectory. Other options:

| Option | Default | Meaning |
|---|---|---|
| `--spec` | `Attachment 1.xlsx` | Battery spec workbook |
| `--prices` | `Attachment 2.xlsx` | Market price workbook |
| `--lookback-days` | `7` | Rolling window used to set the cheap/expensive thresholds |
| `--charge-quantile` | `0.25` | Charge when the price is at or below this quantile of the window |
| `--discharge-quantile` | `0.75` | Discharge when the price is at or above this quantile of the window |
| `--initial-soc` | `0` | Energy stored at the start (MWh) |

The package can also be installed with `pip install -e ".[plot,dev]"` and used from Python:

```python
from battery_trading import Battery, BatterySpec, Simulator, ThresholdStrategy, load_markets

spec = BatterySpec.from_excel("Attachment 1.xlsx")
markets = load_markets("Attachment 2.xlsx")
strategies = {"m1": ThresholdStrategy(lookback_periods=336),   # 7 days of half-hours
              "m2": ThresholdStrategy(lookback_periods=168)}   # 7 days of hours
result = Simulator(Battery(spec), markets, strategies).run()
print(result.net_profit_gbp)
```


## Reproducible results from the model

The model has no randomness, so the same inputs always produce the same output. A run with
the default settings on the provided data (1 Jan 2018 – 31 Dec 2020) gives:

| Metric | Market 1 (half-hourly) | Market 2 (hourly) | Total |
|---|---:|---:|---:|
| Revenue from discharging | £46,397.92 | £205,961.49 | £252,359.41 |
| Cost of charging | £49,850.67 | £124,228.59 | £174,079.26 |
| **Net trading profit** | **−£3,452.75** | **£81,732.90** | **£78,280.15** |

| Battery metric | Value |
|---|---:|
| Energy imported from the grid | 4,734.4 MWh |
| Equivalent full cycles | 1,124.4 of 5,000 (22.5%) |
| Final state of charge | 0.000 MWh |
| Fixed opex over the period (for information only, not deducted) | £15,003.42 |

Capex (£500,000) and opex are not part of the trading result. Market 1 shows a loss on its
own because energy bought there is often sold in Market 2. All 1,330.5 MWh that Market 1
charges are bought in hours when Market 2 is idle. Market 1 then sells only 906.2 MWh,
because once Market 2 commits in an hour it usually takes all of the power and storage
headroom. Market 2 also has the wider average spread: it buys at £36.49/MWh and sells at
£61.17/MWh, against £37.47 and £51.20 in Market 1. The per-market split therefore shows
where cash flowed, not what each market would earn on its own.

How to check these numbers:

- `output/summary.txt`, `output/simulation.png` and `output/*.csv` are the outputs of this
  exact run.
- `tests/test_reproducibility.py` re-runs the full model and asserts the figures above to
  the penny, so `pytest` fails if the results ever drift.
- A fresh virtual environment built from `requirements.txt` produced the same CSVs, byte
  for byte.


## Package layout

```
battery_trading/
  spec.py        BatterySpec: loads Attachment 1 (rates, capacity, efficiencies, ...)
  market.py      Market, load_markets: loads Attachment 2 (the two price series)
  battery.py     Battery: state of charge, efficiency losses, feasibility limits
  strategy.py    Intent, BaseStrategy, ThresholdStrategy: price-only decision logic
  simulator.py   Simulator: enforces every constraint and computes cash flows
  reporting.py   summarise(), plot_results()
scripts/run_simulation.py    Command-line entry point
tests/                       Unit tests, shared test builders, end-to-end reproducibility test
output/                      Results of the default run
```


## Modelling details

**Battery.** Power is measured at the grid connection, which is what gets traded. Charging
at `P` MW for `t` hours imports `P*t` MWh but stores only 95% of it. Discharging `P*t` MWh
to the grid withdraws `P*t / 0.95` MWh from storage. `Battery.apply` is the only method
that changes the battery's state, and it always clips a request to what is physically
feasible.

**Market alignment.** Market 1 rows `2j` and `2j+1` are paired with Market 2 row `j` by
position. The half-hourly timestamps follow UK clock changes, with 46 or 50 periods on the
two clock-change days each year, while the hourly ones don't. Joining on timestamps would
therefore misalign a few periods each year. Both series start at the same instant, and
Market 1 has exactly twice as many rows, which the loader checks.

**Each hour `j`, the simulator:**
1. Caps Market 2's desired power to what is feasible for the *whole* hour, then holds it
   fixed for both half-hours.
2. Gives Market 1 the remaining rate headroom (`max rate − Market 2 power`) and a storage
   budget shared by the two half-hours. The budget is the energy that can still move after
   Market 2's full-hour effect, so Market 2's commitment can always be delivered.
3. Lets Market 1 add power only in the same direction as an active Market 2 commitment. If
   Market 1 wants the opposite direction, it stays idle and the conflict is counted.
4. Lets Market 1 trade freely in each half-hour when Market 2 is idle or has nothing
   feasible to do, including charging in one half and discharging in the other.

The exercise's own worked example is reproduced exactly in
`tests/test_simulator.py::test_brief_example_splitting_across_markets_in_same_direction`:
2 MW into Market 1 for both half-hours plus 3 MW into Market 2 for the hour.

## Simplifications

- **The decision rule is a heuristic, not an optimum.** It does not plan ahead or optimise
  the two markets together. A rolling linear program over both markets would very likely
  earn more. It is the natural next step and plugs into the same interface.
- **Lifetime, degradation, capex and opex are reported, not optimised.** The cycle count is
  tracked so that a lifetime constraint could be added later.
- **Clock changes are not modelled** (see Market alignment). This affects a few periods per
  year out of about 52,600.
- **No price impact.** The battery is a price taker, as the exercise specifies.
