# Alt-drift floor and receive delay: before and after (ADR-0061, ADR-0062), and copy capture (ADR-0063)

Written 2026-11-21. Brief: `decision/briefs/alt-floor-and-receive.md`, plus the user's addition (capture and
market-relative outputs). Frozen sizing only (ADR-0052); Phase 2 not rerun; the holdout test window
(2025-12-03..2026-01-04) never computed; no selection. Both rules were **decided after seeing results** (the
measured-latency rerun showed the ADR-0048 floor setting the base alt cost) and were fixed in their ADRs before any
replay result under them was computed. One variant each; no choice between variants was made (none was run).

Four replay runs of `replay --frozen` (POLARS_MAX_THREADS=8), all nine windows, every scenario:

| Run | Alt floor below 300 s (base) | `receive_ms` | Where |
| --- | --- | --- | --- |
| before | ADR-0048: max(proxy, own 300 s, 0) | 250 | the published state after ADRs 0058-0060 (saved before this rerun) |
| floor only | ADR-0061 | 250 | scratch |
| receive only | ADR-0048 | 392 | scratch |
| **both (published)** | ADR-0061 | 392 | `research/replay_frozen/` |

The published run and an independent second run are byte-identical: 266 of 266 replay files, and the three capture
tables (269 files in all).

## 1. The evidence: point-in-time split-order estimates (ADR-0061)

Later child orders of leaders' split trades on parameterised coins (taker, forced fills excluded, coins passing
the price check at the vintage, both orders before the vintage, 10-11 Oct left out). Mean move of the child's best
fill vs the first order's VWAP, bps, positive = worse for the copier. Cells exist with at least 30 observations;
"pooled" unless every liquidity bucket reaches 30.

| Vintage | (0, 1] s | (1, 2] s (base 1.2 s) | (2, 5] s (5 s) | (5, 10] s (10 s) |
| --- | --- | --- | --- | --- |
| 2025-10-08 | 11 obs: none | 11 obs: none | pooled 91: -0.02 | pooled 177: +0.72 |
| 2025-10-22 | 12: none | 19: none | pooled 117: -0.41 | pooled 254: +0.33 |
| 2025-11-05 | 18: none | 27: none | pooled 177: -0.43 | by bucket: <250k -0.06 (35), 250k-1M +1.61 (56), 1M-5M -1.49 (82), >=5M +1.10 (185) |
| 2025-11-19 | 20: none | **pooled 43: +0.25** | pooled 270: -0.58 | by bucket: -0.16 (42), +0.53 (71), +5.01 (105), +1.28 (260) |
| 2025-12-03 (training only) | 27: none | pooled 51: -0.58 | pooled 340: +2.32 | by bucket: +2.20 (62), -4.69 (91), +3.33 (135), +9.42 (298) |

- The (0, 1] bin never reaches 30. Most sub-second children are at the same millisecond as the first order (elapsed
  0, excluded: a copy is never at 0 ms).
- At the base delay of 1.2 s an estimate exists only from 19 Nov. At the 8 Oct, 22 Oct and 5 Nov test windows, base at
  1.2 s keeps the ADR-0048 floor.
- The 5 s and 10 s bins have estimates at every origin (from 17 and 15 Sep).
- 60 s has no bin and falls back to ADR-0048.

## 2. Before and after, 56 gate-passing test address-windows

| Scenario | before | floor only | receive only | **both** |
| --- | --- | --- | --- | --- |
| Optimistic mean (positive / 56) | +1.090% (29) | +1.090% (29) | +1.098% (29) | **+1.098% (29)** |
| Optimistic headroom, bps/side | 14.42 | 14.42 | 14.61 | **14.61** |
| **Base** mean (positive) | +0.544% (28) | +0.542% (28) | +0.571% (28) | **+0.569% (28)** |
| Base profit / headroom | 3,046 USDC / 7.20 bps | 3,034 / 7.17 | 3,197 / 7.57 | **3,185 / 7.53** |
| Stress mean (positive / 55 measured) | -1.534% (22) | -1.534% (22) | -1.535% (22) | **-1.535% (22)** |
| Stress headroom | -20.06 | -20.06 | -20.07 | **-20.07** |
| Severe mean (positive / 55) | -1.403% (21) | -1.403% (21) | -1.403% (21) | **-1.403% (21)** |
| Stress check: pass / fail on loss / fail unmeasured (stress) | 44 / 11 / 1 | 44 / 11 / 1 | 44 / 11 / 1 | **44 / 11 / 1** |
| Same, severe | 46 / 9 / 1 | 46 / 9 / 1 | 46 / 9 / 1 | **46 / 9 / 1** |
| Stress worst-imputed mean | -2.33% | -2.33% | -2.33% | **-2.33%** |
| Cost-surface lower bound, at (y 2, part 0.25%, cap 1.0x) | -0.010% (-0.15 bps) | -0.029% (-0.42 bps) | +0.019% (+0.28 bps) | **-0.007% (-0.10 bps)** |
| Cost-surface centre | +0.544% | +0.542% | +0.571% | **+0.569%** |

Base mean per test window (both): 8 Oct +1.31%, 22 Oct +0.85%, 5 Nov -0.45%, 19 Nov +0.57% (before: +1.21, +0.86, -0.44,
+0.58).

**Parameterised-coin drift per side**, base, filled orders of gate-passers, notional-weighted. This is the old floor
beside the new one:

| | before (ADR-0048) | floor only | receive only | **both** |
| --- | --- | --- | --- | --- |
| all tests | 3.72 bps (1.54 M USDC) | 3.73 (1.55 M) | 3.72 (1.55 M) | **3.73 (1.55 M)** |
| 8 Oct / 22 Oct / 5 Nov | 3.99 / 4.28 / 5.34 | 3.99 / 4.28 / 5.34 | 3.99 / 4.28 / 5.32 | **3.99 / 4.28 / 5.32** |
| 19 Nov | 0.13 | 0.25 | 0.13 | **0.25** |
| methods (both) | | | | ADR-0048 floor: 2,440 orders, 1.29 M, 4.42 bps; split-order estimate: 331 orders, 0.26 M, 0.25 bps |

Optimistic (-0.29 bps), stress (+55.0 bps) and severe (+50.8 bps) parameterised drift is unchanged by either rule.

**Base delay grid**, gate-passers' mean copy return. This is where the floor rule moves base most, because the 5 s and 10 s bins have
estimates everywhere:

| Delay | 1 s | 1.2 s | 5 s | 10 s | 60 s | 300 s |
| --- | --- | --- | --- | --- | --- | --- |
| before | +0.488% | +0.544% | +0.580% | +0.466% | +0.526% | +1.001% |
| floor only | +0.488% | +0.542% | **+0.902%** | **+0.827%** | +0.526% | +1.001% |
| receive only | +0.516% | +0.571% | +0.580% | +0.480% | +0.526% | +1.001% |
| both | +0.516% | +0.569% | **+0.900%** | **+0.841%** | +0.526% | +1.001% |

Break-even status counts (gate-passers: non-positive at the shortest, crossing, positive through the grid,
unmeasured): base 25 / 0 / 28 / 3 in all four runs; stress and severe 31 / 2 / 18 / 5 before, 30 / 2 / 17 / 7 with
receive 392.

**Holding bands** (base, net bps per completed trip, positive tests of 4):

| Band | before | floor | receive | both |
| --- | --- | --- | --- | --- |
| <1m | +4.5 (3) | +21.3 (3) | +5.1 (3) | +22.1 (3) |
| 1-15m | +0.1 (1) | +0.3 (1) | +0.0 (1) | +0.2 (1) |
| 15m-1h | +6.7 (1) | +6.7 (1) | +7.7 (1) | +7.7 (1) |
| 1-6h | +60.5 (4) | +61.7 (4) | +60.9 (4) | +62.2 (4) |
| 6-24h | +71.0 (4) | +71.2 (4) | +71.9 (4) | +72.1 (4) |
| 1-7d | +115.1 (1) | +114.1 (1) | +115.1 (1) | +114.1 (1) |
| >7d | -153.0 (0) | -152.6 (0) | -168.4 (0) | -167.9 (0) |

### How much each change moved the result

- **Floor (ADR-0061): almost nothing at the base delay, and in the costly direction.** At 1.2 s the split-order
  evidence is too thin before 19 Nov, so three of four test windows keep the ADR-0048 floor. At 19 Nov the estimate
  (+0.25 bps) is **above** what ADR-0048 gave there (+0.13 bps on average: most coins' own 300 s cells are at or
  below zero at that origin and floor at zero), so base falls slightly (-0.002 pp; cost-surface lower bound -0.010%
  to -0.029%). The rule changes base materially only at 5 s and 10 s on the delay grid (+0.32 and +0.36 pp), where
  the venue's own short-delay prices are well below the coins' five-minute drift.
- **Receive 392 ms (ADR-0062): +0.027 pp on base, +0.008 pp on optimistic, stress and severe flat.** It lifts the
  cost-surface lower bound above zero on its own (+0.019%), but with the floor change the bound is -0.007%, still
  not positive.
- **Together**: base +0.544% -> +0.569% (28 positive both), headroom 7.20 -> 7.53 bps per side; the stress check,
  stress and severe are unchanged.

## 3. Receive delay: what changed in the copy decisions (ADR-0062)

Base scenario, all nine windows, before vs receive only, keyed on the leader fills (trader, order id, source rows),
not on the plan's row ids:

- **Copy decisions:** 612,744. **None changes grouping**: the same leader fills form each batch, as ADR-0062 item 2
  predicts.
- **Decision time:** every decision moves by exactly +142 ms.
- **Changed inputs.** Of 2,249,586 decision legs, 2,247,415 match one to one.
  - 3,164 have a different capped target. The cap's view of other coins and the minute marks are read at a later
    time.
  - 90,940 have a different requested quantity. More earlier orders are acknowledged by the later decision, so the
    netting against holdings and pending orders changes.
  - 25,633 have a different status.
  - 15 read another 4h bar.

Over all four scenarios: 2,450,976 decisions, none regrouped; 12,626 / 256,481 / 68,541 legs with a changed target /
requested quantity / status. Equity snapshots and frozen-review rows are unchanged (frozen sizing reads the review,
not the decision time).

## 4. Copy capture and market-relative returns (ADR-0063)

For each address, window and scenario, the follower PnL is compared with a benchmark. The benchmark uses the same
frozen sizing, cap and leader budget, at the leader's own prices, with zero delay and zero cost, on every coin. The
gap is split into parts that sum to it exactly (largest |closure| 6e-6 USDC over 11,936 rows). The ratio is "not
meaningful" when |benchmark PnL| < 100 USDC (1% of the allocation): 729 of 2,984 address-windows per scenario,
because many A/B addresses barely trade. 91-101 more are incomplete because of a missing mark or funding rate.
Outputs: `research/replay_frozen/capture_summary.parquet`, `capture_daily.parquet` and `market_relative.parquet`.

**Test windows, gate-passers (56).** Capture is the median ratio where meaningful, and aggregate = sum of follower PnL
/ sum of benchmark PnL. Alpha is the median daily alpha, from one regression on BTC and ETH daily returns, in bps per
day. Leader return is the median of the leader's own raw return, shown beside the ratio and never divided into it.

| Window | n (meaningful) | Leader return | BTC / ETH buy-and-hold | Optimistic capture (aggregate) | **Base capture (aggregate)** | Stress capture (aggregate) | Severe capture | Base alpha | Base beta BTC / ETH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 Oct | 16 (16) | -5.19% | -10.8% / -13.0% | 0.95 (0.79) | **0.87 (0.41)** | 0.80 (-0.07) | 0.90 | +13.1 | 0.05 / 0.02 |
| 22 Oct | 12 (9) | +3.21% | -6.3% / -15.1% | 0.86 (0.75) | **0.72 (0.55)** | 0.53 (-0.64) | 0.47 | -3.1 | 0.09 / -0.07 |
| 5 Nov | 15 (10) | 0.00% | -8.4% / -4.9% | 0.97 (0.12) | **0.89 (-0.93)** | 0.72 (-6.07) | 0.75 | +0.2 | 0.00 / 0.06 |
| 19 Nov | 13 (8) | +1.29% | -1.9% / -4.2% | 0.89 (0.42) | **0.93 (0.51)** | 0.32 (-1.72) | 0.47 | +7.6 | 0.04 / 0.00 |
| **all tests** | 56 (43) | +0.66% | | 0.93 (0.67) | **0.89 (0.35)** | 0.69 (-0.92) | 0.75 | **+1.0** | 0.04 / 0.00 |

The median alpha is +1.85 bps/day under optimistic, -0.04 under stress, 0.0 under severe, and +1.6 for the benchmark.
In base, 15 of 56 alphas have a 95% interval that excludes zero, in either direction.

**Gap breakdown, gate-passers, all four tests, USDC** (benchmark PnL 9,197; positive = cost to the follower):

| Part | Optimistic | **Base** | Stress | Severe |
| --- | ---: | ---: | ---: | ---: |
| Follower PnL | 6,149 | **3,185** | -8,490 | -7,764 |
| **Gap** | 3,048 | **6,012** | 17,687 | 16,961 |
| Delay drift | -256 | 293 | 8,103 | 5,812 |
| Sweep anchor | 0 | 298 | 457 | 510 |
| Half-spread | 880 | 1,338 | 3,219 | 3,173 |
| Impact | 0 | 1,076 | 3,215 | 3,186 |
| Fees | 1,894 | 1,902 | 1,893 | 1,868 |
| Funding difference | 9 | 6 | 3 | 7 |
| Not executed: below minimum | -24 | -61 | 108 | 57 |
| Not executed: cap deferral | -124 | 261 | 521 | 1,415 |
| Not executed: uncopyable coin | -231 | -231 | -231 | -231 |
| Not executed: pricing failure | 510 | 991 | 271 | 616 |
| Not executed: participation clip | 392 | 165 | 144 | 563 |
| Not executed: other | -2 | -27 | -15 | -15 |

The same breakdown per test window and for all A/B is in `capture_summary.parquet`. For all A/B in base, the
benchmark PnL is 243,399 USDC, the follower PnL 132,265, the median capture 0.97 and the aggregate 0.54. That gap
is 110,576 USDC: fees 33,024, half-spread 24,578, pricing failures 22,184, impact 18,781, sweep anchor 4,798,
uncopyable coins 4,042, delay drift 3,492.

Reading:
- In base, gate-passers keep about a third of the same-sizing benchmark's PnL in aggregate. The typical address keeps
  about 0.9, so the shortfall is concentrated in a few addresses, mostly at 5 Nov.
- Of the 6,012 USDC base gap, 72% is fees, half-spread and impact (4,316 USDC). The delay drift is small (293 USDC)
  at the measured 1.2 s.
- Under stress, drift becomes the largest part (8,103 USDC).
- "Uncopyable coin" is negative: the benchmark lost money on the coins the follower cannot trade.
- The category split of the not-executed parts is an allocation by missed notional, not a counterfactual run (see
  ADR-0063 item 2). The total is exact.
- Copy betas to BTC and ETH are near zero (median 0.04 / 0.00). The copy returns are not a leveraged market position,
  while BTC and ETH fell 2-15% in every test window.

## 5. Verification

- **Determinism.** Two independent `replay --frozen` runs give 266 of 266 identical files. `replay --capture` on both
  trees gives identical capture tables, also on repeated runs. The capture step at the end of the first runs stopped
  on a missing mark: the Hyperliquid daily marks start on 28 Jul and training windows open on 1 Jul. Buy-and-hold now
  starts at the first boundary with a mark (`buy_hold_from`). The first capture outputs differed in the last bits of
  the allocated parts (unordered group-by sums), and every aggregation now sorts first. Both fixes are post-processing
  only, so the replay was not run again. `replay --frozen` now runs the capture step at its end.
- **Gates.** ruff and mypy clean; pytest 243 passed, none skipped; audit 31/31; the checksum record
  (`provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt`, 396 files) verifies; two package builds are identical (3,563 files)
  and a clean extract passes its manifest. New tests are in `tests/test_alt_floor_receive.py`:
  - per-vintage estimate: seeded leak, bins, minimum, buckets, coins;
  - floor rule: estimate, fallback, zero floor; stress, severe and optimistic unchanged;
  - receive: grouping unchanged, decision time;
  - capture: exact closure, regression, published outputs.
- **Scope.** The latency session's files are untouched. Phase 2 was not rerun. The holdout test window is absent from
  every output (the 3 Dec origin has a training window only).
