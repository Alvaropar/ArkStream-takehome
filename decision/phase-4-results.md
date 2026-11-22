# Phase 4: selection rule, development walk-forward and the freeze (items 1-7)

Written 2026-11-22. Brief: [`briefs/phase-4-selection.md`](briefs/phase-4-selection.md).

- **Decisions:** ADRs [0130](adr/0130-selection-gates.md)-[0141](adr/0141-holdout-freeze-executable.md).
- **Inputs:** frozen `E_ref` sizing only (ADR-0119); measured delays (ADR-0150: base 1.2 s, stress 5 s).
- **The rule in force:** `rule_b_coin_filter`, with its coin filter **executed inside the frozen replay**
  (ADR-0140, `research/replay_coinfilter/`). It replaces ADR-0136's attribution scoring.
- **The holdout (3 Dec 2025 - 4 Jan 2026) has not been opened.** Items 8-9 wait for the reviewers to receive the
  freeze hash and for "open the holdout".

## Freeze hash

```
freeze_hash: cbb44708d6569d55c809cff5daed3fc63004a97c2b3a3e409db79b84b00a2e8b
```

`provenance/HOLDOUT_FREEZE.txt` (ADR-0141) records the SHA-256 of `config/decision_context.yaml` (`frozen: true`,
rule `rule_b_coin_filter` on `research/replay_coinfilter`), the other three config files, the selection, replay
(including the coin-filter replay and the holdout path), drift, price and leader sources, and the 3 Dec shortlist. The
earlier hash in ADR-0139 was never sent and is void.

**The repository has no git**, so the hash proves only that the holdout ran on the frozen rules, not when. Please
send it to the reviewers before the holdout run; that message is the dated record of the order of events.

## The rule

At each origin, from data up to it only:

1. **Gates** (ADR-0130). Grade A/B and all 18 Phase 2 gates, then:
   - at least 90 snapshot days and 60 usable return days;
   - median equity in **[5k, 2M]** (your choice, from the capital; the plan had 20k);
   - at least 90% copyable notional;
   - a holding band that the training-window break-even study finds copyable;
   - training break-even delay above 1.2 s;
   - not the weaker member of a confirmed copier cluster.
2. **Key** (ADR-0131). The 20th percentile of 2,000 entry-week block-bootstrap means of the follower's net return per
   completed training-window round trip (base, after costs and funding). It needs at least 10 trips and 4 blocks, and
   **key > 0** to be selectable.
3. **Clusters and walk** (ADR-0132). Ward behaviour clusters (6, no outcome features). The walk takes addresses by
   within-cluster rank and adds one only while its daily copy-return correlation and position overlap with every
   chosen address stay below 0.5, up to K = 5. Sleeves are equal.
4. **Coin filter**, executed (ADR-0136 definition, ADR-0140 execution).
   - **Kept coins:** BTC, ETH, HYPE, SOL and the coins where the unfiltered training-window copy kept at least half
     of a benchmark win of at least 500 USDC.
   - **Every other coin is never traded:** passing coins get `coin_filter_excluded`; failing ones keep their
     price-check status.
   - **The 1.5x address cap and resize legs** are solved on the kept coins only.
   - **The ADR-0162 benchmark** trades the kept coins only.
   - **Every copy-series input** of the rule (key, band table, break-even gate, co-movement, outcomes, random-k
     pools, equal weight, capture) comes from the filtered replay.

## Executable filter vs the attribution scoring (ADR-0140 item 7)

Same four development windows, base 1.2 s, funded, 10,000 USDC per sleeve, 1,000 seeded random-k draws.
**The rule selects the same addresses in every window either way**, and the 3 Dec shortlist is unchanged.

| | Attribution (ADR-0136, the basis of the ADR-0137 choice) | **Executable (ADR-0140, in force)** |
| --- | ---: | ---: |
| Mean basket return, base (median) | +0.72% (-0.02%) | **+0.71% (-0.02%)** |
| Per window: 8 Oct / 22 Oct / 5 Nov / 19 Nov | -2.27% / +5.18% / +1.31% / -1.35% | **-2.32% / +5.18% / +1.31% / -1.35%** |
| Wins vs matched random-k | 3 of 4 | **2 of 4** (8 Oct: the basket is the median of its 3-address pool) |
| Wins vs all-A/B random-k | 2 of 4 | **2 of 4** |
| Beats equal weight | 3 of 4 | **3 of 4** |
| Optimistic / stress mean | +0.84% / -0.87% | **+0.83% / -0.87%** |
| Basket stress check | pass in 4 of 4 | **pass in 4 of 4** (worst basket drawdown -7.8%; one 19 Nov sleeve fails alone) |
| Capture, base, four windows (follower / benchmark PnL) | 0.16 (148 / 916 USDC), gap not decomposed | **0.157 (143 / 916 USDC)**; 0.187 against the leader-fee benchmark |
| Base gap decomposition | not available | **773 USDC**: half-spread 379 (49%), fees 211 (27%), impact 113 (15%), pricing failures 52, delay drift 20, sweep anchor 16, cap deferrals 6, uncopyable coins 0 |

The executable result is slightly worse on the ranking test: 2 of 4 matched wins instead of 3. Under ADR-0140 that
does not reopen the choice of rule. In the 8 Oct window the filter now also applies to the other two pool members'
cap: their filtered returns rise (pool median -8.1% to -2.3%), and the basket's single sleeve becomes the median.

## Pool sizes: what the matched random-k test can judge

| Origin | A/B | Phase 2 all-gate | Eligible pool | Selected k | Possible matched picks |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 Oct | 300 | 16 | 3 | 1 | 3 |
| 22 Oct | 327 | 12 | 2 | 1 | 2 |
| 5 Nov | 330 | 15 | 3 | 2 | 3 |
| 19 Nov | 358 | 13 | 5 | 3 | 10 |
| 3 Dec (shortlist) | 354 | 11 | 4 | 3 | (holdout) |

**With eligible pools of 2-5, the matched random-k test can barely judge the ranking.** Each "win" is a choice among
2-10 possible baskets. Selection rests mostly on the gates and the coin filter, and the **all-A/B random-k baseline
is the main test of whether the gates add value**: 2 of 4.

## Development walk-forward, executable rule (`walk_forward.csv`, `baselines.csv`)

| Window | Pool / k / picks | Basket base | Matched median, basket percentile | All-A/B median, percentile | Equal weight | Optimistic | Stress (basket check) |
| --- | --- | ---: | --- | --- | ---: | ---: | --- |
| 8 Oct | 3 / 1 / 3 | **-2.32%** | -2.32%, 0.52 | 0.00%, 0.21 | -14.57% | -2.24% | -1.74% (pass, dd -7.8%) |
| 22 Oct | 2 / 1 / 2 | **+5.18%** | +1.68%, 0.75 (win) | 0.00%, 0.82 (win) | +3.43% | +5.55% | +3.75% (pass) |
| 5 Nov | 3 / 2 / 3 | **+1.31%** | +0.59%, 0.84 (win) | 0.00%, 0.71 (win) | +0.68% | +1.55% | -2.10% (pass) |
| 19 Nov | 5 / 3 / 10 | **-1.35%** | +0.01%, 0.25 | +0.20%, 0.21 | +0.60% | -1.53% | -3.39% (pass; 1 of 3 sleeves fails on loss) |
| **Mean** | | **+0.71%** | -0.01% | +0.05% | -2.47% | +0.83% | -0.87% |

- **Without 10-11 Oct** (only the 8 Oct window contains them), the 8 Oct basket earns +6.12%, against a matched
  median of +1.62%: a win, so 3 of 4 matched wins without the crash.
- **Exact intervals (Clopper-Pearson, 95% two-sided):**
  - matched random-k 2 of 4: 0.07-0.93;
  - all-A/B random-k 2 of 4: 0.07-0.93;
  - beating equal weight 3 of 4: 0.19-0.99;
  - matched random-k without the crash, 3 of 4: 0.19-0.99.
  None excludes 0.5, and the windows were used to choose the rule.
- **MinTRL** (basket daily base, 56 development days, in-sample): daily Sharpe 0.041 (0.79 annualised), kurtosis 16;
  about **1,610 daily observations** at that Sharpe and about 6,410 at half of it. This is far beyond any pilot
  horizon. The holdout MinTRL comes at item 8.
- **Economic reading:**
  - mean base return positive (+0.71%), median about zero;
  - stress negative on average (-0.87%);
  - the basket stress check passes in all four windows;
  - the plan's research-validity gate ("beats matched random-k in most windows without trailing equal weight") is
    **not met** on development data: 2 of 4 is not most.

## Market-relative (5a, `market_relative.csv`)

BTC fell in every development window (-10.8%, -6.3%, -8.4%, -1.9%). The basket returned +8.5, +11.4, +9.7 and
+0.5 pp over BTC (base). Its daily alpha was +43, +34, +7 and -8 bps per day; the 95% interval excludes zero in the
first three windows (14 days each). Its BTC beta was 0.31 at 8 Oct (R^2 0.94; one sleeve) and -0.06 to 0.10
afterwards.

Over cash the basket returns +0.71% on average. Its return over BTC is mostly BTC's own fall: with betas near zero,
the basket did not earn its market exposure. Sleeve, equal-weight and random-k rows are in the file.

## Copy capture (5b, `capture.csv`, `capture_medians.csv`, `capture_daily.csv`)

Benchmark: the same filtered plan at leader prices with zero delay and cost, on the kept coins (ADR-0140 item 4).
Summed over the four windows:

| Series | Scenario | Follower PnL | Benchmark PnL | Aggregate capture | Against the leader-fee benchmark |
| --- | --- | ---: | ---: | ---: | ---: |
| Basket | base | +143 | +916 | **0.157** | 0.187 |
| Basket | optimistic | +182 | +916 | 0.199 | 0.237 |
| Basket | stress | -1,237 | +916 | -1.35 | -1.61 |
| Equal-weight pool | base | -3,183 | -2,188 | 1.45 (lost more than the benchmark) | 1.25 |

- **Per selected sleeve,** base:
  - where the benchmark won, the median ratio is 0.74, 0.71 and 0.77 by window (n = 1, 2, 2);
  - where it lost, the ratio is 1.56 at 8 Oct and 1.59 at 19 Nov: the copy lost more than the benchmark.
  - The 19 Nov basket benchmark (-12 USDC) is not meaningful.
- **The aggregate is low** because costs trim each winning window (the copy keeps about 0.7) and enlarge each losing
  one, and the net of wins and losses is small.
- **The gap** (773 USDC, base) is half-spread 49%, fees 27% and impact 15%. Delay drift is only 20 USDC at the
  measured 1.2 s; under stress it becomes 953 USDC.

## Diagnostics (5c, `research/selection/diagnostics/`, pre-registered in ADR-0135; filtered tree)

- **Persistence: ranking on past copy results does not predict.** Spearman of the key with the next window's
  return, all A/B with a measured key, is -0.16, -0.07, +0.07 and +0.17 (n = 33-138). The top-quintile hit rate is
  0.14-0.61. Raw training copy return: -0.03, +0.30, +0.25, -0.13.
- **Feature screen:** no feature keeps one sign in all four windows; every mean rho is within ±0.13. Leader beta to
  BTC is the most negative (-0.13; positive in 1 of 4), and leader alpha is the most positive (+0.07; 3 of 4).
- **Gate audit:** the gates screen risk, not return.
  - Eligible address-windows (13) averaged -2.4% base, against +0.5% for the rest; all-gate passers -0.6% vs +0.5%.
  - The break-even gate separates best: +1.0% passing vs -0.6% failing.
  - The holding-band gate passes the worse group: +0.3% vs +1.6%.
- **Attribution** (all A/B, completed test trips, base, filtered):
  - 42k of 78k USDC trip PnL closed on 10-11 Oct;
  - short trips carry 76k;
  - BTC/ETH/HYPE/SOL carry 60k against 18k for the other kept coins.
- **Crowding:** the effective number of independent bets is 2.2 / 1.4 / 1.7 / 3.5 in the eligible pool and 1 / 1 /
  1.4 / 2.2 in the basket.
- **Alpha vs beta:** the median R^2 of A/B copies on BTC and ETH is 0.35-0.42.
- **Decay:** the top quintile by key at 8 Oct underperformed in every later window (mean -6.0% to -0.7%).
- **Capture drivers and tail:** in `capture_drivers.csv` and `tail.csv`.

## 3 Dec shortlist (item 7; the rule at the 3 Dec origin, training data to 3 Dec, filtered replay)

Every eligible address (`research/selection/shortlist_2025-12-03.csv`; source keys `snapshot_src_row`,
`last_fill_src_row`, `tid`, `oid`):

| Address | Decision | Reason | Key (p20, bps/trip) | Trips / weeks | Median equity | Training copy return (filtered) |
| --- | --- | --- | ---: | --- | ---: | ---: |
| 0x2cd9f4645b14bf968212c7c108213eaeb193946e | **selected** | positive key; diversification check passed | +114 | 33 / 7 | 21,308 | +38.2% |
| 0x971fc0c9becffd708c52a195b8a87c27359e77fa | **selected** | positive key; diversification check passed | +136 | 19 / 9 | 7,489 | +5.0% |
| 0xd2f03635901956b950737bbf02463dfad9f2e9e1 | **selected** | positive key; diversification check passed | +205 | 52 / 12 | 70,202 | +26.2% |
| 0x4c6eacc86bd4cee8f41cf257f054ca53b2cef8b3 | rejected | key unmeasured: 8 completed trips, below the 10 minimum | n/a | 8 / 4 | 8,165 | +12.5% |

The other 350 A/B addresses at 3 Dec are not eligible. Each one's failed gates are in
`origin=2025-12-03/variant=rule_b_coin_filter/candidates.parquet`. The 3 Dec coin set (37 coins) is in
`research/replay_coinfilter/coin_sets.csv`.

## Holdout path (built, frozen, not run)

`python -m arkstream replay --coin-filter --holdout` (`replay_coinfilter.run_holdout`) replays origin 3 Dec, from
3 Dec 2025 00:00 to 4 Jan 2026 00:00 UTC (32 daily returns), with the 3 Dec coin set. Inputs are frozen at the 3 Dec
vintage: drift cells, spreads, the price check, holding bands and E_ref reviews from 3 Dec. Data runs to that
boundary; the last 24 hours before the cutoff have no closing mark and are not scored.

- It runs only through `freeze.guard`.
- It goes through the same single-window branch that reproduces the 19 Nov development window byte for byte (a
  test, no holdout data read).
- After the freeze, item 8 adds only a reporting module outside the hashed set (`holdout_report.py`).

## Verification

- **Checks:** `ruff` and `mypy` clean; full `pytest` 276 passed; audit 31/31.
- **Tests added:**
  - `tests/test_coin_filter.py`:
    - status classes;
    - the cap and resize legs on kept coins only;
    - an excluded leg never reserved or filled;
    - the published tree never filling an excluded coin (follower or benchmark);
    - the single-window branch reproducing the 19 Nov window;
    - the holdout path refused without the freeze.
  - `tests/test_selection.py`:
    - bootstrap and key;
    - clusters and walk;
    - random-k;
    - Clopper-Pearson and MinTRL;
    - capture aggregation;
    - the freeze guard: edited threshold, moved cutoff, edited shortlist, tampered file;
    - the seeded leak;
    - the published shortlist recomputed from the filtered tree.
- **Determinism:** two filtered replays give 266 of 266 files byte-identical; two `select --evaluate` runs give 189
  of 189.
- **First filtered run:** the benchmark still traded price-check-failing coins outside the set. This was found by the
  data test, fixed before any outcome was read, and the tree was rerun (trial log).
- **Scope:** the latency session's files were not touched. The holdout window was not read.
