# Phase 3 follower replay

**The 6–24 hour holding band passes the first delay break-even screen in all four development tests.** The broader economic gate remains open. Across the origin's gate-passing addresses, mean funded base return was negative in three tests. Individual stress drawdowns exceeded 10% in every test. The 3 December origin has a training series only.

## Positive funded copies among gate-passers

Each test starts with a flat book and 10,000 USDC per address. The denominator includes every address passing the suitability gates at that origin, including addresses that subsequently stopped trading. The last column uses daily closing equity.

| Test origin | Gate-passers | Optimistic positive | Base positive | Stress positive | Mean base return | Stress drawdown over 10% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 Oct 2025 | 17 | 7 | 6 | 8 | −0.19% | 5 |
| 22 Oct 2025 | 16 | 10 | 7 | 7 | −3.00% | 4 |
| 5 Nov 2025 | 18 | 11 | 10 | 9 | −1.59% | 3 |
| 19 Nov 2025 | 17 | 11 | 11 | 6 | +2.59% | 3 |

On 8 October the crash sample needed for parameterised stress orders was still in the future. Of 2,000 stress intents from gate-passers, 1,306 were unpriced (65.3%). Skipped orders left cash idle or existing positions exposed. This matters when comparing the eight positive stress copies with the six positive base copies. Training also includes signals before the trade archive begins on 8 September. [Window counts and pricing coverage](../research/replay/economic_screen.csv)

## Round trips and delay

The band study uses completed follower round trips across the A/B universe, grouped by the leader's holding band at the origin. For 6–24 hours the mean base result after execution costs and funding was approximately +52, +65, +47 and +23 bps per trip in the four tests. The other measured bands each missed break-even in at least one test. These estimates give each trip equal weight and use peak notional as the denominator. [Gross result, cost, funding and sample size by band](../research/replay/band_break_even.csv)

The delay study holds the scenario's cost rules fixed and replays 1, 10, 60 and 300 seconds. The order set can change when a quote becomes stale, a parameter is missing or an order falls below minimum size. The per-address tables give the first crossing bracket and the additional cost per unit of turnover that would absorb remaining funded PnL. [Return and break-even conventions](adr/0032-follower-returns-and-break-even.md)

With base costs, 29 of the 68 gate-passing address-windows were already nonpositive at 1 second. Four had an observed positive-to-nonpositive crossing, 32 stayed positive through the tested grid, and three had insufficient evidence. An address can appear at more than one origin.

## Execution coverage

The 32 coins without an approved intraday reference are excluded from follower execution. The paired, unattainable leader-price benchmarks quantify the omitted contribution in USDC, with coverage and funding reported separately. Actual delayed PnL on those legs is unknown. [Exclusion impact and per-origin summaries](../research/replay/summary.md)

The development calibration produced 22 coin spread estimates. From 22 October, Corwin–Schultz raised the configured half-spread for 12 coins under optimistic costs, seven under base costs and four under stress costs. The matched print-count simulation supported a downward-bias label for two coins. Impact uses completed Hyperliquid 4h volume. Parameterised orders receive mean shortfall, which understates copy-series volatility for those coins and can distort Sharpe. [Spread study](../research/replay/spread_estimates.parquet) · [Execution-price decision](adr/0029-follower-execution-price.md)

Reproduce the nine windows with `uv run python -m arkstream replay` or `make replay`. The final development test ends at 00:00 UTC on 3 December 2025. The holdout test and address selection remain unopened.
