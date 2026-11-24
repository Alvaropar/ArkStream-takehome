# Phase 3 cost sensitivities

**The combined base-case mean turns positive at +0.039%, compared with −0.528% under the original linear impact rule.** Across the four development tests, 34 of 68 measurable gate-passing address-windows earned a positive funded copy return under the combined variant. Giving each origin equal weight gives +0.027% combined and −0.549% original. The combined variant clears the requested profitability screen for considering Phase 4.

The combined base book earned 265.56 USDC on 6,210,182 USDC of filled turnover across the four tests. Holding those fills fixed, an additional 0.43 bps per side would absorb the aggregate profit. Each of the original and combined variants had 34 positive address-windows.

Each test starts flat with 10,000 USDC per address. All nine windows use the original calendar, population, gates, funding and delay conventions. The 3 December 2025 origin contains training only. An address appearing at two origins contributes two observations. Means use funded returns with a complete daily chain. The gate-passer count includes inactive addresses.

Square-root impact uses six completed Hyperliquid four-hour bars of volume and 42 four-hour log returns (seven days) for daily volatility. Y = 1 is a PLACEHOLDER. Stress triples estimated impact. Both optimistic impact variants have zero impact, so their results share the corresponding optimistic ledgers. The cap uses a single factor across the address’s target basket, measured at each decision against 15,000 USDC. A pending reduction frees headroom when acknowledged. [Impact decision](adr/0033-square-root-impact.md) · [Exposure decision and order fields](adr/0034-address-gross-exposure-cap.md)

## Positive funded copy returns

Cells show positive copies / gate-passers and the arithmetic mean of measurable copy returns. The returns file also gives measurable counts and unpriced intents. [Returns by origin, scenario and variant](../research/replay/sensitivity_returns.csv)

| Test origin | Scenario | Original | Square-root | Cap | Combined |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | optimistic | 7/17 · +2.54% | 7/17 · +2.54% | 7/17 · +1.05% | 7/17 · +1.05% |
| 2025-10-08 | base | 6/17 · −0.19% | 6/17 · +1.50% | 6/17 · −1.22% | 6/17 · +0.43% |
| 2025-10-08 | stress | 8/17 · −5.36% | 7/17 · −5.21% | 7/17 · −3.45% | 7/17 · −3.54% |
| 2025-10-22 | optimistic | 10/16 · −0.77% | 10/16 · −0.77% | 10/16 · −0.73% | 10/16 · −0.73% |
| 2025-10-22 | base | 7/16 · −3.00% | 9/16 · −1.42% | 8/16 · −2.06% | 9/16 · −1.01% |
| 2025-10-22 | stress | 7/16 · −4.14% | 9/16 · −0.72% | 7/16 · −3.91% | 8/16 · −1.59% |
| 2025-11-05 | optimistic | 11/18 · −1.02% | 11/18 · −1.02% | 11/18 · +0.01% | 11/18 · +0.01% |
| 2025-11-05 | base | 10/18 · −1.59% | 10/18 · −1.30% | 10/18 · −0.37% | 10/18 · −0.22% |
| 2025-11-05 | stress | 9/18 · −2.86% | 8/18 · −2.50% | 8/18 · −1.33% | 8/18 · −1.22% |
| 2025-11-19 | optimistic | 11/17 · +3.02% | 11/17 · +3.02% | 9/17 · +1.01% | 9/17 · +1.01% |
| 2025-11-19 | base | 11/17 · +2.59% | 11/17 · +2.92% | 9/17 · +0.58% | 9/17 · +0.91% |
| 2025-11-19 | stress | 6/17 · +0.71% | 7/17 · +1.01% | 4/17 · −0.79% | 4/17 · −0.49% |
| All four tests | base | 34/68 · −0.528% | 36/68 · +0.427% | 33/68 · −0.743% | 34/68 · +0.039% |

## Cost per filled side

Each cell gives **fee / half-spread / impact / drift** in bps for gate-passing addresses, weighted by absolute executed notional. Positive drift is adverse to the follower. The signed anchor-to-mid adjustment is a separate column in the data. The full file also reports the A/B universe and separate BTC/ETH and other-coin panels. [Cost decomposition](../research/replay/sensitivity_costs.csv)

| Test origin | Scenario | Original | Square-root | Cap | Combined |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | optimistic | 4.5 / 1.3 / 0.0 / −0.8 | 4.5 / 1.3 / 0.0 / −0.8 | 4.5 / 1.6 / 0.0 / −1.1 | 4.5 / 1.6 / 0.0 / −1.1 |
| 2025-10-08 | base | 4.5 / 3.1 / 10.9 / −0.5 | 4.5 / 3.2 / 2.7 / −0.5 | 4.5 / 4.1 / 13.8 / −1.5 | 4.5 / 4.1 / 3.2 / −1.5 |
| 2025-10-08 | stress | 4.5 / 7.0 / 4.2 / −6.1 | 4.5 / 7.0 / 3.0 / −6.1 | 4.5 / 10.3 / 1.0 / −12.4 | 4.5 / 10.3 / 2.5 / −12.4 |
| 2025-10-22 | optimistic | 4.5 / 4.4 / 0.0 / −0.3 | 4.5 / 4.4 / 0.0 / −0.3 | 4.5 / 4.3 / 0.0 / −0.3 | 4.5 / 4.3 / 0.0 / −0.3 |
| 2025-10-22 | base | 4.5 / 5.7 / 19.8 / −0.6 | 4.5 / 5.7 / 3.4 / −0.6 | 4.5 / 5.6 / 15.3 / −0.4 | 4.5 / 5.6 / 3.0 / −0.4 |
| 2025-10-22 | stress | 4.5 / 11.6 / 45.3 / −2.8 | 4.5 / 11.6 / 8.1 / −2.9 | 4.5 / 11.6 / 37.7 / 2.2 | 4.5 / 11.6 / 7.2 / 2.5 |
| 2025-11-05 | optimistic | 4.5 / 3.1 / 0.0 / −0.4 | 4.5 / 3.1 / 0.0 / −0.4 | 4.5 / 3.3 / 0.0 / −0.1 | 4.5 / 3.3 / 0.0 / −0.1 |
| 2025-11-05 | base | 4.5 / 4.4 / 7.1 / −0.5 | 4.5 / 4.4 / 4.0 / −0.5 | 4.5 / 4.7 / 5.4 / −0.2 | 4.5 / 4.7 / 3.7 / −0.2 |
| 2025-11-05 | stress | 4.5 / 9.5 / 12.7 / 7.7 | 4.5 / 9.5 / 8.3 / 7.7 | 4.5 / 9.9 / 8.7 / 5.8 | 4.5 / 9.9 / 7.3 / 5.9 |
| 2025-11-19 | optimistic | 4.5 / 5.2 / 0.0 / −0.3 | 4.5 / 5.2 / 0.0 / −0.3 | 4.5 / 5.9 / 0.0 / 0.1 | 4.5 / 5.9 / 0.0 / 0.1 |
| 2025-11-19 | base | 4.5 / 5.8 / 5.7 / −0.4 | 4.5 / 5.8 / 2.3 / −0.4 | 4.5 / 6.6 / 6.4 / −0.4 | 4.5 / 6.6 / 2.3 / −0.4 |
| 2025-11-19 | stress | 4.5 / 9.8 / 9.0 / 16.9 | 4.5 / 9.8 / 5.8 / 16.9 | 4.5 / 10.8 / 9.6 / 15.9 | 4.5 / 10.8 / 5.7 / 15.9 |

Pooling all four tests by executed notional gives the following base-scenario impact in bps per side. The panels use each variant’s own fills.

| Universe | Coins | Original | Square-root | Cap | Combined |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gate-passers | All | 10.7 | 3.0 | 10.4 | 3.1 |
| Gate-passers | BTC and ETH | 0.8 | 0.6 | 0.1 | 0.3 |
| Gate-passers | Other coins | 19.1 | 5.1 | 16.2 | 4.7 |
| All A/B | All | 22.3 | 4.7 | 20.4 | 4.2 |
| All A/B | BTC and ETH | 1.2 | 1.0 | 0.2 | 0.4 |
| All A/B | Other coins | 56.0 | 10.6 | 38.7 | 7.6 |

## Holding-band break-even

The table covers all A/B addresses and gives mean net bps per completed follower round trip under base scenario costs. Positive values clear break-even. Each trip has equal weight and uses peak notional as its denominator. Bands refer to the leader at the origin. The full table gives all scenario and variant combinations, completed trips, address counts, gross return, cost, funding and net return. A dash means there were no measurable completed trips. [All holding-band tables](../research/replay/sensitivity_bands.csv)

| Test origin | Leader holding band | Original | Square-root | Cap | Combined |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | <1m | 136.8 | 132.7 | 117.5 | 114.0 |
| 2025-10-08 | 1-15m | 34.2 | 39.1 | 40.1 | 45.1 |
| 2025-10-08 | 15m-1h | 23.0 | 26.4 | 13.5 | 16.1 |
| 2025-10-08 | 1-6h | 92.8 | 102.6 | 90.9 | 99.3 |
| 2025-10-08 | 6-24h | 51.6 | 56.9 | 63.2 | 64.8 |
| 2025-10-08 | 1-7d | 471.3 | 502.9 | 408.8 | 438.0 |
| 2025-10-08 | >7d | 58.4 | 66.0 | 8.2 | 14.2 |
| 2025-10-08 | No closed trip | 119.4 | 203.8 | 142.2 | 226.5 |
| 2025-10-22 | <1m | −83.7 | −10.9 | −57.5 | −15.0 |
| 2025-10-22 | 1-15m | −6.1 | −5.5 | −8.4 | −8.3 |
| 2025-10-22 | 15m-1h | −3.6 | 1.6 | −10.4 | −7.3 |
| 2025-10-22 | 1-6h | 40.3 | 42.5 | 39.8 | 40.9 |
| 2025-10-22 | 6-24h | 64.9 | 73.2 | 74.0 | 77.3 |
| 2025-10-22 | 1-7d | −45.3 | −8.5 | −30.4 | −2.7 |
| 2025-10-22 | >7d | −159.0 | −72.4 | −129.5 | −51.0 |
| 2025-10-22 | No closed trip | 20.5 | 30.6 | 29.6 | 32.2 |
| 2025-11-05 | <1m | 11.0 | 36.5 | 12.8 | 33.8 |
| 2025-11-05 | 1-15m | −12.1 | −4.6 | −6.3 | −3.3 |
| 2025-11-05 | 15m-1h | −5.4 | −0.2 | −1.6 | 3.4 |
| 2025-11-05 | 1-6h | 15.5 | 27.0 | 31.7 | 35.8 |
| 2025-11-05 | 6-24h | 47.3 | 66.7 | 62.3 | 68.4 |
| 2025-11-05 | 1-7d | −60.0 | −20.5 | −60.6 | −28.4 |
| 2025-11-05 | >7d | −441.4 | −424.4 | −445.0 | −435.6 |
| 2025-11-05 | No closed trip | 51.9 | 49.6 | −23.8 | −26.2 |
| 2025-11-19 | <1m | −35.7 | 52.5 | −40.1 | 45.8 |
| 2025-11-19 | 1-15m | −6.2 | 2.4 | −5.0 | 1.5 |
| 2025-11-19 | 15m-1h | 27.6 | 35.6 | 23.8 | 31.1 |
| 2025-11-19 | 1-6h | −5.3 | 86.3 | 31.1 | 94.1 |
| 2025-11-19 | 6-24h | 22.9 | 70.1 | 48.8 | 76.3 |
| 2025-11-19 | 1-7d | −88.3 | −48.2 | −98.0 | −60.0 |
| 2025-11-19 | >7d | −241.7 | −223.8 | −250.7 | −236.5 |
| 2025-11-19 | No closed trip | 5.8 | 4.4 | 5.8 | 4.4 |

Holding bands with a positive mean net return per trip in every base test were 6-24h under the original variant and 1-6h, 6-24h under the combined variant.

## Delay break-even

Read the four gate-passer counts in each cell as **nonpositive at 1 s / observed crossing / positive through 300 s / unmeasured**. A crossing brackets the first change from positive to nonpositive on the 1, 10, 60 and 300 s grid. Address-level delay grids and crossing bounds are alongside each order ledger. [Counts by origin](../research/replay/sensitivity_delays.csv)

| Test origin | Scenario | Original | Square-root | Cap | Combined |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | optimistic | 10 / 1 / 6 / 0 | 10 / 1 / 6 / 0 | 10 / 1 / 6 / 0 | 10 / 1 / 6 / 0 |
| 2025-10-08 | base | 10 / 1 / 6 / 0 | 10 / 1 / 6 / 0 | 10 / 1 / 6 / 0 | 10 / 1 / 6 / 0 |
| 2025-10-08 | stress | 9 / 1 / 6 / 1 | 9 / 1 / 6 / 1 | 9 / 2 / 5 / 1 | 9 / 2 / 5 / 1 |
| 2025-10-22 | optimistic | 6 / 1 / 9 / 0 | 6 / 1 / 9 / 0 | 6 / 1 / 9 / 0 | 6 / 1 / 9 / 0 |
| 2025-10-22 | base | 8 / 1 / 7 / 0 | 6 / 1 / 9 / 0 | 9 / 0 / 7 / 0 | 7 / 1 / 8 / 0 |
| 2025-10-22 | stress | 11 / 0 / 5 / 0 | 10 / 0 / 6 / 0 | 11 / 0 / 5 / 0 | 10 / 0 / 6 / 0 |
| 2025-11-05 | optimistic | 6 / 1 / 10 / 1 | 6 / 1 / 10 / 1 | 6 / 1 / 10 / 1 | 6 / 1 / 10 / 1 |
| 2025-11-05 | base | 7 / 1 / 9 / 1 | 7 / 1 / 9 / 1 | 7 / 1 / 9 / 1 | 7 / 1 / 9 / 1 |
| 2025-11-05 | stress | 8 / 0 / 9 / 1 | 8 / 1 / 8 / 1 | 9 / 0 / 8 / 1 | 8 / 1 / 8 / 1 |
| 2025-11-19 | optimistic | 4 / 1 / 10 / 2 | 4 / 1 / 10 / 2 | 6 / 1 / 8 / 2 | 6 / 1 / 8 / 2 |
| 2025-11-19 | base | 4 / 1 / 10 / 2 | 4 / 1 / 10 / 2 | 6 / 1 / 8 / 2 | 6 / 1 / 8 / 2 |
| 2025-11-19 | stress | 8 / 1 / 6 / 2 | 7 / 2 / 6 / 2 | 11 / 1 / 3 / 2 | 10 / 2 / 3 / 2 |
| All four tests | base | 29 / 4 / 32 / 3 | 27 / 4 / 34 / 3 | 32 / 3 / 30 / 3 | 30 / 4 / 31 / 3 |

## Cap execution and coverage

Counts below are for gate-passing addresses under the combined base variant. One signal may resize several coins. Small orders include minimum-size skips at decision and acknowledgement. A headroom deferral means the proposed order could exceed the cap before pending reductions finish. The address summary’s broad unpriced count includes these deferrals. Prices can also lift existing holdings above the limit between decisions. The order audit checks that a submission cannot increase such a breach.

| Test origin | Intents | Filled | Minimum-size skips | Headroom deferrals | Missing square-root inputs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | 12257 | 2787 | 8604 | 762 | 0 |
| 2025-10-22 | 20747 | 3096 | 16773 | 834 | 0 |
| 2025-11-05 | 1895 | 1663 | 110 | 86 | 1 |
| 2025-11-19 | 1453 | 1296 | 65 | 58 | 0 |

The 8 October stress test had no earlier crash sample for parameterised drift. Missing execution inputs can leave cash idle or leave an existing position open. Across scenarios, parameterised orders receive mean shortfall, which understates copy-series volatility for those coins and can distort Sharpe.

Run the sensitivity replay with `uv run python -m arkstream replay --sensitivities`. The two verification runs used `POLARS_MAX_THREADS=8`. All 383 published sensitivity files matched the independent nine-window rerun byte for byte. A fresh control replay also reproduced all 264 archived original files. [Sensitivity hashes](../provenance/PHASE3_SENSITIVITY_OUTPUT_CHECKSUMS.txt) · [Original replay hashes](../provenance/PHASE3_OUTPUT_CHECKSUMS.txt)

## Sizing limits and leader impact (ADRs 0035, 0036)

Added 2026-11-20. Three cumulative variants on top of the combined one (square-root impact + 1.5x cap):
**+ participation** caps each order at 0.5% of the latest completed Hyperliquid 4h volume (PLACEHOLDER);
**+ no scale-up** never copies a leader above their own size (multiplier ≤ 1, order ≤ the triggering leader batch's
notional); **+ leader sweep** anchors native taker copies at the leader batch's VWAP in base and its deepest fill in
stress (first fill in optimistic). Same nine windows, holdout never computed. The size-dependent drift term
(ADR-0036 item 2) did not qualify at any origin or horizon, so none is applied.
[Participation](adr/0035-participation.md) · No scale-up ·
[Leader sweep and size study](adr/0036-leader-sweeps.md)

**With all limits and leader impact included, the mean funded base return across gate-passers is +0.558%,
positive in all four tests.** It earned 3,797 USDC on 5.01M USDC of filled turnover; an additional 7.58 bps per
filled side would absorb it (0.43 bps for the combined variant). Stress stays negative in all four tests.

Positive copies / gate-passers and mean funded return, base scenario:

| Test origin | Combined | + participation | + no scale-up | + leader sweep (full) |
| --- | ---: | ---: | ---: | ---: |
| 2025-10-08 | 6/17 · +0.43% | 6/17 · +0.28% | 7/17 · +1.60% | 7/17 · +1.37% |
| 2025-10-22 | 9/16 · −1.01% | 9/16 · −0.95% | 10/16 · +0.06% | 10/16 · +0.04% |
| 2025-11-05 | 10/18 · −0.22% | 10/18 · +0.00% | 9/18 · +0.20% | 9/18 · +0.17% |
| 2025-11-19 | 9/17 · +0.91% | 8/17 · +0.45% | 10/17 · +0.66% | 10/17 · +0.64% |
| All four tests | 34/68 · +0.039% | 33/68 · −0.048% | 36/68 · +0.629% | 36/68 · +0.558% |
| Profit / extra cost per side to absorb it | 266 USDC / 0.43 bps | −321 USDC / −0.52 bps | 4,277 USDC / 8.54 bps | 3,797 USDC / 7.58 bps |

Full variant under the other scenarios: optimistic +1.98%, +0.08%, +0.39%, +0.76%; stress −2.64%, −0.70%,
−0.60%, −0.46%. [Returns by origin, scenario and variant](../research/replay/sensitivity_returns.csv)

**Cost per filled side**, base, notional-weighted, test windows:

| Universe | Variant | Filled notional | Fee | Half-spread | Impact | Drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| All A/B | Combined | 91.3M | 4.50 | 4.13 | 4.20 | −0.07 |
| All A/B | Full | 73.2M | 4.50 | 4.01 | 2.60 | −0.01 |
| Gate-passers | Combined | 6.21M | 4.50 | 5.12 | 3.09 | −0.68 |
| Gate-passers | Full | 5.01M | 4.50 | 5.20 | 2.63 | −0.94 |

**What each limit did** (base, all A/B, test windows):
- **Participation** clipped 2,631 orders and cut impact from 4.20 to 3.08 bps per side, but on its own it slightly
  lowered the mean (−0.048% against +0.039%): the smaller orders gave up more trading PnL than they saved in impact.
- **No scale-up** is what moves the result: 20,988 orders clipped, filled notional down from 89.2M to 73.2M, and the
  mean up to +0.629%. Copying small leaders at several times their own size was the costly part.
- **Leader sweep** shifted the anchor by 0.75 bps per filled side on average (1.75 bps on coins other than BTC, ETH,
  HYPE and SOL; 24,852 of 91,462 fills re-anchored) and cost 0.07 percentage points of mean return. Copied orders
  are mostly small, so the sweeps they inherit are small.

**Holding bands** (base, completed follower round trips, net bps per trip after costs and funding, full variant):
1-6h +116, +39, +41, +101 and 6-24h +75, +95, +99, +55 across the four tests; both bands clear costs in every test,
as in the combined variant. 1-7d and >7d are negative in three of four. **Delay break-even** (gate-passing
address-windows): 28 nonpositive at 1 s, 3 crossing within the grid, 34 positive through 300 s, 3 unmeasured.

**Size study** (`research/replay/leader_size/`): no qualifying term. The high-share arm (orders ≥0.5% of a 4h bar)
has 4-25 orders per coin, below the 30 required. On notional alone, HYPE's large orders (≥100k) drift +4.0 to
+7.3 bps over 1-300 s against −0.5 to +0.3 for small ones; this is disclosed, not applied.

Caveats: impact Y = 1, the 0.5% participation and the 1.5x cap are placeholders; parameterised orders receive the
mean shortfall, which understates copy-series volatility; under no scale-up part of the allocation stays idle for
small leaders and returns are still measured on the full 10,000 USDC.
