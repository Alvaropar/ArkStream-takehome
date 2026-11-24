# Phase 5 development results (P5-1 to P5-6)

Written 2026-11-24. **Development data only: the holdout is closed.** Every number below comes from the four
development test windows (8 Oct, 22 Oct, 5 Nov and 19 Nov 2025, 14 days each) or from the training windows. The rules
are ADRs 0086-0096, approved by the user on 2026-11-24, with `config/risk.yaml` v3. Section 9 adds the development
runs of the holdout cost runs B and C (ADR-0098, accepted by the user on 2026-11-24, with the details pinned in
ADR-0099 before anything was computed).

> **Selection in-sample on these windows; machinery test, not skill.** Both sleeves were chosen with data up to
> 3 Dec, which covers every development window (ADR-0086 item 3). These runs test the engine and the risk rules.
> They say nothing about whether 0x2cd9 or 0x971f have an edge. The holdout is the only out-of-sample test.

## 1. What ran

| Step | Command | Output | Check | Result |
| --- | --- | --- | --- | --- |
| P5-1 | `replay --gray` | `research/replay_gray/` (2,500 and 5,000 USDC trees, `gray_sizing.csv`) | byte-identical rerun | 479/479 files identical. The two-address run at 10k reproduces the published 10k tree (45/45 order tables) |
| P5-2 | `phase5 risk-model` | `research/risk_model/origin=<date>/` | leak test | passes (a planted post-origin move changes nothing) |
| P5-3 | engine code | `portfolio_engine.py`, `portfolio_replay.py`, `tests/test_phase5_engine.py` | F1, F6 | 24 tests pass; no engine fault in any run |
| P5-4 | `phase5 population`, `phase5 l1-oos` | `research/phase5_population/` | F4; variant criterion as written | F4 passes, L1 measured out of sample on the test windows; both variants rejected |
| P5-5 | `phase5 pair` | `research/portfolio_replay/` | F2a, F2b, F3, F5 | all pass (section 6) |
| P5-6 | `phase5 report` | `src/arkstream/holdout_report.py`, `research/window_report/` | identical schema across windows | identical; H5 reproduces the published Phase 4 ranking ICs exactly |
| B, C | `phase5 cost-runs` | `research/cost_runs/` | run A unchanged; C's drift table at the origins | 384/384 files of A byte-identical; the daily table equals the frozen cells at all four origins (section 9) |
| Entry point | `phase5 holdout --check` | `src/arkstream/holdout.py`, `research/holdout_check/` | reproduces the development outputs on 19 Nov | pass: every output reproduced (section 9.6) |
| Cutoff selection | `phase5 cutoff --check`, `phase5 cutoff --check --deliverables` | `src/arkstream/cutoff.py`, `research/cutoff_check/` | reproduces the 3 Dec selection | pass: `eligible.parquet` and every selection table byte-identical (section 9.8) |

The details pinned while building the engine are in ADR-0096. Every run is logged in `provenance/trial_log.md`.

## 2. Gray size (ADR-0090 items 4 and 6)

The rule: G\* trades 5,000 instead of 2,500 if more than 10% of its intents fall under the 10 USDC minimum. The share
is measured on G\* after `λ`, over the four test windows pooled, base scenario.

| Measure | 2,500 | 5,000 |
| --- | --- | --- |
| G\* trigger-leg intents after `λ` | 193 | 192 |
| of which under 10 USDC | 0 (0%) | 0 (0%) |
| Unscaled single-sleeve share (P5-1, for comparison) | 1.6% | 1.2% |
| G\* filled orders per week | 24.3 | 24.6 |

**Chosen: 2,500 USDC** (`gray.sleeve_usdc` in `risk.yaml`). At about 24 orders a week, 200 live orders take about
8 weeks, inside the 12-week maximum.

## 3. Risk model (P5-2)

Stress shocks at 3 Dec (largest adverse 24 h move since 1 Jul 2025): HYPE 17.3%, ETH 14.6%, BNB 13.5%, BTC 10.5%.
Every tradable coin has its own shock, so the bucket fallback was never needed.

| Origin | HYPE beta to BTC | ETH | BNB | Covariance coins (complete days, shrinkage) |
| --- | --- | --- | --- | --- |
| 8 Oct | 1.94 | 1.82 | 1.35 | 20 (72, 0.27) |
| 3 Dec | 1.68 | 1.54 | 1.38 | 28 (74, 0.19) |

Betas are fitted on the 90 days before each origin. The covariance is used for reporting only.

## 4. Trigger calibration and risk-rule variants (P5-4, population)

All A/B addresses were copied as one-sleeve 10k baskets with S1, S3, the states and the triggers (ADR-0096 item 9).
The training windows give 4,367 sleeve-months. They overlap, because each starts on 27 Jul.

| Trigger | Firings | Per sleeve-month | Sleeves above 1 per month | U-twin forward 14d return after firing | Forward 14d drawdown | False-alarm share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| L1 leader drawdown | 0 | 0.00 | 0% | n/a | n/a | n/a (measured out of sample below) |
| L2 leverage | 359 | 0.08 | 2.8% | +5.4% | -4.5% | 75% |
| L3 equity collapse | 1,524 | 0.35 | 10.9% | +7.2% | -6.0% | 74% |
| L4 withdrawal | 566 | 0.13 | 4.5% | +0.5% | -6.8% | 64% |
| L5 forced fill | 1,277 | 0.29 | 8.5% | -0.3% | -3.8% | 52% |
| L6 non-tradable drift | 2,104 | 0.48 | 16.6% | +1.8% | -3.8% | 61% |
| L7 inactive | 1,164 | 0.27 | 5.1% | +1.8% | -3.8% | 63% |
| C1 execution | 99 | 0.02 | 0.4% | +2.8% | -6.0% | 58% |
| S3 copy drawdown | 1,066 | 0.24 | 8.5% | +7.4% | -7.0% | 67% |
| Matched hours without a firing | | | | +1.5% | -3.5% | |

- **F4 passes.** Every trigger fires at most once per sleeve-month on the population, so no threshold changes.
- **L1 cannot fire on a training window.** Its threshold comes from the same history, so it cannot be exceeded there.
  It is therefore measured out of sample on the four test windows, in the next table.
- **Descriptive only:** after a firing, the forward drawdown is deeper than on matched hours. Except for L5, the
  forward return is higher too. The triggers mark volatile spells, not losing ones. No threshold was tuned on this.

**L1 measured out of sample on the population** (`phase5 l1-oos`, written in the trial log before it ran). The same
copies and current rules as the variant test, on the four test windows (1,330 copy-windows), where L1's threshold
(1.5 × the leader's maximum drawdown before the origin) is out of sample. Descriptive. The threshold changes only if
F4 fails, and F4 passes. Outputs: `l1_test_windows.csv`, `l1_test_firings.csv` (one row per firing),
`l1_test_by_date.csv` and `l1_test_summary.json`.

| Test window | Firings | Sleeve-months | Per sleeve-month | Sleeves above 1 per month | U-twin forward return to window end | Forward drawdown | False-alarm share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 Oct | 51 | 110.5 | 0.46 | 13.6% | +2.2% | -6.2% | 55% |
| 22 Oct | 49 | 100.3 | 0.49 | 11.0% | +4.0% | -2.4% | 80% |
| 5 Nov | 36 | 105.6 | 0.34 | 8.4% | +1.8% | -2.0% | 73% |
| 19 Nov | 21 | 109.5 | 0.19 | 6.5% | +1.9% | -2.3% | 76% |
| **Pooled** | **157** | **425.9** | **0.37** | **9.9%** | **+2.6%** | **-3.6%** | **69%** |
| Matched hours without a firing | | | | | +0.3% | -3.0% | |

- **F4 passes for L1: 0.37 firings per sleeve-month, and at most 0.49 in any window.** No threshold changes.
- **The firings are clustered, not independent.**
  - 114 of the 1,330 copy-windows fired, across 97 addresses.
  - 25 of the 157 firings came on 10-11 Oct, 21 of them on 10 Oct. 51 came in the 8 Oct window.
  - 138 came at 23:00 UTC, when the daily leader snapshot lands.
- **Forward horizons are short.** A test window lasts 14 days, so the U twin's forward horizon is cut at the window
  end: the median is 8 days, and no firing has the full 14 days. 14 firings fell in a window's last hour.
  - The same rule applies to the 18,064 matched hours.
  - The leader's own forward 14-day index return, from the 3 Dec origin's Phase 2 table, has a median of +10.1% and
    a median drawdown of -1.2%. 127 horizons are complete, 21 were cut at 3 Dec 00:00 and 9 had no index.
  - Nothing at or after 3 Dec 00:00 was read.
- **What reduce-only did.**
  - It lasted to the window end in all 157 firings, a median of 191 hours, because a 14-day window's only review is
    at its start.
  - L1 moved the copy out of NORMAL in 80 firings. In the other 77 the copy was already reduce-only or stricter.
  - Against the U twin over the spell, the copies lost 26,399 USDC in total. Where L1 moved the state, they lost
    20,083 USDC: 17 firings saved money, 34 cost money and 29 made no difference, a mean of -2.6 pp of the sleeve.
  - As in training, L1 marks volatile spells, not losing ones. Its false-alarm share is 69%.
- **The two sleeves.**
  - 0x2cd9 fired once, at 10 Oct 23:00: -8.5% against a threshold of -6.5%. By the window end it was 2,747 USDC below
    its twin. The same event drives the S\* against U\* gap in section 6.
  - 0x971f fired once, at 10 Oct 23:00: -3.0% against -2.1%, and ended 153 USDC below its twin.
- **Finding, not changed (F4 passes): L1 fires on any drawdown when the history has none.** 31 firings (16
  addresses) have a threshold of 0, because the leader had no drawdown before the origin. Changing that would be a
  rule change made after the results, so it is reported for the memo instead.
- **Consistency:** the rerun's window returns equal `variants.csv` (current) on all 1,330 rows.

**Variants** (four test windows, 1,330 address-windows, base). The criterion was written before the runs: adopt only
if the variant cuts the 95% ES of window returns by at least 20% at a mean cost of at most 0.25 pp per window.

| Item | ES95 current | ES95 variant | Reduction | Mean cost per window | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Cap denominator: min(A, sleeve NAV) | -14.39% | -14.21% | 1.3% | 0.09 pp | rejected, keep the fixed allocation |
| `E_ref` at reviews: high-water | -14.39% | -14.15% | 1.6% | 0.14 pp | rejected, keep the reset |

## 5. The pair on the four test windows (P5-5)

*Selection in-sample on these windows; machinery test, not skill.*

Columns:
- S\* is the scheme, U\* the unconstrained twin, G\* the capital book (the hand-off alone at 2,500).
- α excludes funding and is in bps per day of gross.
- Funding is the USDC paid (-) or received (+).
- Max DD is the largest drawdown from the high-water mark, hourly, in USDC.
- `λ` tw is the time-weighted mean of `λ`; `λ` exp is weighted by the U\* exposure.
- Util is the mean gross over the allocation.

**Base scenario, per window:**

| Config | Sleeve | Window | Raw return | α ex funding | Funding | Max DD | Worst day | `λ` tw | `λ` exp | Util | Fills |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| G2500 | 0x2cd9 | 2025-10-08 | -4.11% | 465.9 | +1.6 | 243 | -7.86% | 0.99 | 0.97 | 9.2% | 15 |
| G2500 | 0x2cd9 | 2025-10-22 | -3.37% | -568.4 | -0.1 | 162 | -4.19% | 1.00 | 0.92 | 4.8% | 13 |
| G2500 | 0x2cd9 | 2025-11-05 | +11.69% | 116.2 | -1.7 | 55 | -1.67% | 1.00 | 1.0 | 13.6% | 111 |
| G2500 | 0x2cd9 | 2025-11-19 | +1.21% | 187.2 | -0.6 | 98 | -0.30% | 1.00 | 1.0 | 6.0% | 55 |
| S | 0x2cd9 | 2025-10-08 | -0.10% | 220.1 | +4.5 | 322 | -2.30% | 0.58 | 0.19 | 4.8% | 24 |
| S | 0x2cd9 | 2025-10-22 | -0.84% | -217.9 | -0.3 | 219 | -1.08% | 0.97 | 0.34 | 2.0% | 21 |
| S | 0x2cd9 | 2025-11-05 | +3.68% | 78.9 | -3.7 | 70 | -0.51% | 0.88 | 0.48 | 6.5% | 84 |
| S | 0x2cd9 | 2025-11-19 | -0.04% | 83.5 | -1.8 | 264 | -0.30% | 0.98 | 0.81 | 4.6% | 53 |
| S | 0x971f | 2025-10-08 | -0.49% | 151.1 | -0.3 | 90 | -0.84% | 0.93 | 0.53 | 0.9% | 60 |
| S | 0x971f | 2025-10-22 | -0.19% | 31.5 | -0.8 | 109 | -0.52% | 0.98 | 0.89 | 5.1% | 86 |
| S | 0x971f | 2025-11-05 | -0.30% | 132.3 | -1.1 | 130 | -0.21% | 0.96 | 0.63 | 4.4% | 27 |
| S | 0x971f | 2025-11-19 | +0.21% | 74.6 | -1.2 | 95 | -0.31% | 0.99 | 0.88 | 6.1% | 93 |
| S | scheme | 2025-10-08 | -0.30% | 212.2 | +4.2 | 407 | -1.57% | 0.76 | 0.26 | 2.8% | 84 |
| S | scheme | 2025-10-22 | -0.51% | -69.9 | -1.1 | 292 | -0.62% | 0.97 | 0.62 | 3.6% | 107 |
| S | scheme | 2025-11-05 | +1.69% | 101.3 | -4.8 | 189 | -0.31% | 0.92 | 0.55 | 5.4% | 111 |
| S | scheme | 2025-11-19 | +0.09% | 78.8 | -3.1 | 306 | -0.22% | 0.99 | 0.84 | 5.3% | 146 |
| U | 0x2cd9 | 2025-10-08 | +23.40% | 371.5 | +13.3 | 1571 | -10.76% | 0.97 | 0.97 | 51.3% | 74 |
| U | 0x2cd9 | 2025-10-22 | -1.47% | -153.6 | -0.5 | 671 | -2.28% | 1.00 | 0.92 | 5.5% | 17 |
| U | 0x2cd9 | 2025-11-05 | +11.51% | 112.0 | -6.7 | 222 | -1.68% | 0.99 | 1.0 | 13.6% | 111 |
| U | 0x2cd9 | 2025-11-19 | +1.47% | 19.4 | -2.9 | 390 | -0.30% | 1.00 | 1.0 | 7.3% | 60 |
| U | 0x971f | 2025-10-08 | -0.67% | -18.1 | -0.5 | 657 | -2.49% | 1.00 | 1.0 | 13.0% | 123 |
| U | 0x971f | 2025-10-22 | +1.70% | 290.3 | -0.3 | 134 | -0.09% | 0.99 | 1.0 | 5.8% | 65 |
| U | 0x971f | 2025-11-05 | +1.20% | 209.0 | -3.4 | 237 | -0.15% | 1.00 | 0.99 | 10.9% | 38 |
| U | 0x971f | 2025-11-19 | +1.91% | 271.3 | -1.4 | 102 | -0.15% | 1.00 | 1.0 | 6.8% | 78 |
| U | scheme | 2025-10-08 | +11.36% | 263.6 | +12.8 | 1839 | -6.63% | 0.98 | 0.98 | 32.2% | 197 |
| U | scheme | 2025-10-22 | +0.11% | -8.5 | -0.8 | 709 | -0.76% | 1.00 | 0.96 | 5.6% | 82 |
| U | scheme | 2025-11-05 | +6.35% | 137.1 | -10.1 | 235 | -0.91% | 0.99 | 1.0 | 12.2% | 149 |
| U | scheme | 2025-11-19 | +1.69% | 125.3 | -4.3 | 323 | -0.22% | 1.00 | 1.0 | 7.0% | 138 |

**Four scenarios pooled over the windows** (combined book; ES95 is of daily returns over the 56 days):

| Config | Scenario | Mean window return | Worst window | Max DD (USDC) | Worst day | ES95 daily | Fills |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S\* | optimistic | +0.32% | -0.47% | 384 | -1.44% | -0.79% | 446 |
| S\* | base | +0.24% | -0.51% | 407 | -1.57% | -0.84% | 448 |
| S\* | stress | -0.05% | -0.59% | 370 | -1.39% | -0.77% | 332 |
| S\* | severe | +0.07% | -0.32% | 338 | -1.23% | -0.68% | 331 |
| U\* | optimistic | +5.15% | +0.24% | 1,833 | -6.60% | -2.89% | 564 |
| U\* | base | +4.88% | +0.11% | 1,839 | -6.63% | -2.91% | 566 |
| U\* | stress | +3.08% | -1.43% | 1,970 | -7.27% | -3.24% | 566 |
| U\* | severe | +3.06% | -1.49% | 2,041 | -7.50% | -3.32% | 565 |
| G\* 2,500 | optimistic | +1.48% | -4.04% | 242 | -7.82% | -4.55% | 192 |
| G\* 2,500 | base | +1.36% | -4.11% | 243 | -7.86% | -4.57% | 194 |
| G\* 2,500 | stress | +0.83% | -4.32% | 244 | -8.03% | -4.15% | 192 |
| G\* 2,500 | severe | +0.99% | -4.23% | 243 | -7.91% | -4.01% | 192 |

### 5.1 What the limits do: S\* against U\*

- **Tracking error of S\* against U\*** (sd of daily return differences): 0x2cd9 182 bps a day, 0x971f 53 bps a day
  (base).
- **Return given up:** 8.1 pp a window for 0x2cd9 and 1.2 pp for 0x971f (base). Almost all of 0x2cd9's comes from
  the 8 Oct window: U\* +23.4%, S\* -0.1%.
  - In that window L1 fired in the 10-11 Oct crash and held the sleeve in reduce-only through the rebound.
  - P2-sleeve set `λ` in half of the window's hours.
- **Drawdown saved:** the scheme's worst drawdown was 407 USDC (2.0% of `D`), against U\*'s 1,839 USDC.
- **Netting:** no internal cross occurred. The two books never held opposite deltas in the same coin at the same
  decision.
- **Participation clips:** 2 clips in U\* (19 Nov window), none in S\* or G\*.

**What set `λ`** (share of hours, S\*, base): see `pair_summary.csv` (`lambda_set_by`) and H6 in
`research/window_report/`.
- 0x2cd9: P2-sleeve 50% of hours in the 8 Oct window, 17% in the 5 Nov window, under 1% otherwise. P3 1-4% and
  P2-total 2% of hours (19 Nov).
- 0x971f: P2-sleeve 13% (8 Oct) and 7% (5 Nov). P3 1-4%.
- **P5, the budget form, never bound on the pair.** It bound in 0-3.5% of the random pairs.

### 5.2 The capital book G\*

- **Largest loss:** 185 USDC including exit costs (8 Oct, base), against the 750 USDC cap. 190 in stress.
- **The stress cap:** never breached at a target update in any scenario. The highest ratio of target stress to
  remaining budget was 0.87 (5 Nov). The loss cap was never hit.
- **States:** P6 halved the book at -5% in the 8 Oct and 22 Oct windows. L1 (8 Oct) and L6 (19 Nov) put it in
  reduce-only.
- **Shape:** G\* follows U\* exactly while NORMAL (exposure-weighted `λ` 0.92-1.0). With 0x2cd9's low leverage, the cap
  rarely binds at 2,500.

### 5.3 Context, not a test: 200 random pairs per window

The same engine with S\* rules, base, two distinct A/B addresses per pair, seed [20251203, origin ordinal].

| Window | Pairs | Faults | Median max DD | 5th pct max DD | Scheme max DD | Pairs with a worse DD | Median `λ` | Scheme `λ` | Pairs with a ladder event | Pairs with P5 binding |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 Oct | 200 | 0 | -1.17% | -5.03% | -2.03% | 38% | 0.72 | 0.76 | 6% | 0% |
| 22 Oct | 200 | 0 | -1.69% | -4.27% | -1.46% | 55% | 0.66 | 0.97 | 3% | 3.5% |
| 5 Nov | 200 | 0 | -1.59% | -4.34% | -0.94% | 68% | 0.71 | 0.92 | 1% | 3% |
| 19 Nov | 200 | 0 | -2.03% | -4.13% | -1.53% | 61% | 0.68 | 0.99 | 1% | 1.5% |

The pair's drawdowns are typical of random pairs. Its `λ` is higher: random pairs carry larger, more concentrated
books, and P2 sets their `λ` in a median 21-32% of hours.

## 6. Stress tests and the pass criteria (written before the runs)

**Historical: 10-11 Oct inside the 8 Oct window (F3).**

| Config | Scenario | Max drawdown on 10-11 Oct | Max loss incl. exit | State events | Ladder consistent | G\* cap breaches |
| --- | --- | ---: | ---: | --- | --- | ---: |
| S\* | base | 2.0% (407 USDC) | 313 | REDUCE_ONLY: C1, L1 | yes | |
| S\* | severe | 1.7% (338) | 253 | REDUCE_ONLY: C1 | yes | |
| U\* | base | 9.2% (1,839) | 1,613 | none (no states by design) | | |
| U\* | severe | 10.2% (2,041) | 1,827 | none | | |
| G\* | base | 9.7% (243) | 185 | HALVED: P6; REDUCE_ONLY: L1 | yes | 0 |
| G\* | severe | 9.7% (243) | 187 | HALVED: P6; REDUCE_ONLY: L1 | yes | 0 |

**At the limits (F2a, F2b; ADR-0095 item 6, pinned).** Each sleeve's book at its hour of largest stress in the base
runs is scaled up until the first limit binds. Then every coin takes its shock at once, and the book exits in one
order at stress costs and severe delays.

| Window | S\* gross at the limit | First limit | S\* loss | % of `D` | G\* gross | First limit | G\* loss |
| --- | ---: | --- | ---: | ---: | ---: | --- | ---: |
| 8 Oct | 4,800 | P2-sleeve | 464 | 2.3% | 3,750 | S1 | 517 |
| 22 Oct | 6,862 | P3 | 811 | 4.1% | 3,750 | S1 | 553 |
| 5 Nov | 6,294 | P3 | 837 | 4.2% | 3,750 | S1 | 651 |
| 19 Nov | 6,182 | P3 | 861 | 4.3% | 3,750 | S1 | 554 |

| # | Criterion | Pass rule | Result |
| ---: | --- | --- | --- |
| F1 | Fault tests | all pass | **pass**: 24 tests, including every limit restored by whole-sleeve scaling, non-convergence to `λ = 0`, passive P4, reduce-only, sign flip, ladder both ways at a review, flatten at stress costs, C3 by fault injection, L5, participation shared, stale signal, flatten sweep, internal cross, the `E_ref` invariant |
| F2a | Stress at the limits, S\* | loss ≤ 16.5% of `D` (3,300) | **pass**: at most 861 USDC (4.3%) |
| F2b | Stress at the limits, G\* | loss incl. exit ≤ 750 | **pass**: at most 651 USDC |
| F3 | Historical stress | the ladder and the cap act as designed | **pass**: every hour past a ladder step was in that state or stricter; no cap breach |
| F4 | Trigger noise | ≤ 1 firing per sleeve-month | **pass**: highest on training L6, 0.48; L1, measured out of sample on the four test windows, 0.37 (at most 0.49 per window; section 4) |
| F5 | Determinism | two runs byte-identical | **pass**: the full P5-5 run twice, 389/389 files byte-identical (P5-1: 479/479) |
| F6 | Shape | targets = one scalar × U\* targets on every leg | **pass**: checked at every target update of every run, 0 violations |

## 7. Findings for the memo (methodology section 7)

1. **Can the two books live inside the limits?** Yes, but not in the way revision 4 expected.
   - The `λ ≈ 0.15` arithmetic assumed 0x2cd9 near its full 1.5x gross. Its leader runs at about 0.1x leverage, so
     the 10k copy holds 5-14% of its sleeve on average (51% in the crash window).
   - P2 binds only on the few hours when HYPE exceeds 2,000 USDC. Weighted by exposure, 0x2cd9's `λ` was 0.19 in the
     8 Oct window and 0.34-0.81 in the others.
   - P5 in the budget form never bound on the pair.
   - So the per-coin limit is binding when it matters (the crash window), and slack otherwise.
2. **What the risk machinery costs:**
   - Against U\*, S\* gave up 8 pp a window on 0x2cd9, almost all of it in the 8 Oct rebound after L1 fired. It cut
     the worst drawdown from 1,839 to 407 USDC.
   - The trading cost of the risk actions is small: no flatten was needed, and resizes are mostly inside the deadband.
3. **Do the costs match the model?** Model against model only.
   - Cost per side on S\*'s fills: half-spread 1.1-5.0 bps, impact 0.3-1.0, fee 4.5, drift -3.8 to +2.1.
   - D3's development p90 per coin (from the four windows): BNB 11.5, ETH 8.2, BTC 7.4 and HYPE 14.0 bps per side.
   - Too few coins reach 30 orders in one window: 1-3 coins per window are measured.
4. **G\* behaves as designed.**
   - It is sized at 2,500 with no sub-minimum orders, and never comes near its cap.
   - It fills about 24 orders a week, so the 200-order measurement takes about 8 weeks.

## 8. Window report (P5-6)

`holdout_report.py` writes H1-H6 and the D1-D5 evaluation for any (origin, window), with the schema fixed in
`SCHEMA`. On the development windows:
- **H1:** clean (no fault, every state event carries its reason).
- **H2:** S\* and G\* within their limits in base and stress.
- **H3:** 1-3 coins measured per window, all within the development p90.
- **H5:** the IC of `m` with the next window's α is +0.098 / -0.029 / -0.038 / -0.150, identical to
  `research/selection_v2/ranking_validation.csv`. At these origins `m` is not constant, so D4 uses `m` with -0.20.
  At 3 Dec it will use own α with -0.14 (ADR-0093 item 4).
- **The development "decision"** reads NO-GO only because D5 (the cutoff hand-off) is not defined before the cutoff.
  It is labelled "development: not a decision".

**F5 (determinism):** the full P5-5 step run twice gives 389/389 byte-identical files. The first rerun found
one difference, the JSON key order in `pair_summary.csv`; the keys are now sorted and the step was rerun.

## 9. Runs B and C on the development windows (ADRs 0098-0099)

> **Rebuilt real conditions, development: not real fills.** Descriptive only: no strategy parameter changed on these
> results (trial log, "Phase 5 cost runs B and C, development"). The selection is in-sample on these windows, as in
> section 5. The rebuild is a reconstruction from prints and the Binance tape, not an order book.

**What ran** (`phase5 cost-runs`, `research/cost_runs/`): B on S\*, U\* and G\* (2,500) and C on S\* and G\*, on
the four test windows, with the base tree inputs and the P5-5 configurations. A is the P5-5 base run.

### 9.1 Checks before the comparison
- **Run A is unchanged.** The P5-5 runs, rerun with the engine that now carries the B and C hooks, match
  `research/portfolio_replay` byte for byte on 384/384 files (four windows, four scenarios, S\*, U\*, G\*), and the
  128 summary rows are equal (`scripts/check_run_a_unchanged.py`, `research/audit/run_a_unchanged.md`). A never reads
  the BNB, AAVE or EIGEN tape (`replay_market.DIRECT` is unchanged), so BNB's development D3 p90 is unchanged too.
- **C's daily drift table equals the frozen cells on every origin day:** 1,560, 3,000, 3,149 and 3,258 cells, with no
  value or count different (`drift_daily_origin_check.csv`).

### 9.2 A against B

Pooled over the four windows, whole book:

| Book | Run | P&L (USDC) | Worst max drawdown (USDC) | Worst loss incl. exit (USDC) | Physical fills | Cost per side, notional-weighted, with fee (bp) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| S\* | A | +193.7 | 406.5 | 312.7 | 448 | 8.10 |
| S\* | B | +259.5 | 379.7 | 295.3 | 448 | 6.60 |
| U\* | A | +3,904.0 | 1,839.5 | 1,612.5 | 566 | 10.06 |
| U\* | B | +4,103.4 | 1,851.2 | 1,628.9 | 566 | 7.86 |
| G\* | A | +135.8 | 242.7 | 184.8 | 194 | 9.09 |
| G\* | B | +147.5 | 246.4 | 189.7 | 194 | 7.98 |

- **B ends above A in 11 of 12 book-windows,** by 1.6 to 103 USDC. The exception is G\* on 8 Oct, 4.6 USDC lower:
  its same-day HYPE spread, notional-weighted, was 12.0 bp against the 5.0 bp A charges (the window holds the
  10-11 Oct crash).
- **The same orders.** Every order A prices, B prices, and no order was rejected (section 9.5). The fill counts are
  equal. The traded notional differs by at most 0.07%, except S\* on 8 Oct (+7.2%, the C1 difference below).
- **Firings** are the same except S\* on 8 Oct. In A, C1 fires on 0x971f (10 Oct 22:00) and L1 then finds the sleeve
  already reduce-only; in B, C1 does not fire and L1 sets the state on both sleeves an hour later.

### 9.3 B against C
- **Identical fills, P&L, drawdown and firings in every window.** C's refit changes only the logged stress estimates
  (the worst loss including exit differs by at most 6.2 USDC).
- **The reason:** no stress limit (S2, P4, P5, `L_gray`) set `λ` in B or in C. `λ` was set by S1, P2, P3 or nothing,
  and the highest stress usage at an update was 87% of the G\* budget (5 Nov) and 31% of S\*'s.
- So B against C measures nothing in these windows: C's refit can matter only where a stress limit binds.

### 9.4 Accuracy per part

S\*, filled orders, model minus rebuild, bp per side without the fee, all four windows. S\* made 448 orders, all on
tape coins (BNB 139, BTC 127, HYPE 108, ETH 74); the rows cover the 437 whose drift came from the tape:

| Part | Frozen model | Rebuild | Frozen minus rebuild: mean, median, mean absolute | C's model | C minus rebuild: mean, mean absolute |
| --- | ---: | ---: | --- | ---: | --- |
| Delay (ms) | 1,200 | 1,450 | -250, -23, 361 | 1,200 | -250, 361 |
| Drift | -0.05 | -0.86 | +0.81, 0.00, 4.28 | -0.10 | +0.77, 4.24 |
| Half-spread | 3.16 | 3.48 | -0.32, 0.00, 1.27 | 3.19 | -0.29, 1.30 |
| Impact | 0.54 | 0.43 | +0.11, +0.05, 0.29 | 0.02 | -0.41, 0.44 |
| Total | 3.65 | 3.04 | +0.60, +0.90, 4.70 | 3.11 | +0.07, 4.60 |

The 11 orders whose drift fell back have the frozen drift by construction.

- **The frozen model overstates the cost on average:** by 0.6 bp per order, and by 1.5 bp per side notional-weighted
  (8.10 against 6.60, section 9.2). Per order the two differ by about 4.7 bp, mostly the drift over a delay that
  differs from the fixed 1,200 ms.
- **By coin:** the frozen model overstates BTC (0.0 against -0.6 bp), ETH (1.7 against -0.2) and BNB (6.2 against
  5.3; A's approximate drift, the rebuild's new tape).
- **HYPE's same-day spread is unmeasured, not shown to be higher.** Its rebuilt total (7.0 against 6.4 bp) rests on
  32 measured orders of 108; the other 70% fell back to the frozen 5 bp. The 32 have a median half-spread of 0.27 bp
  and a mean of 11.7 bp: 14 of them, on 10 Oct (the crash), measured 26.6 bp. Raw Corwin-Schultz on one volatile day
  inflates the mean. (Corrected on 2026-11-24; the first text said HYPE's same-day spread averaged 7.0 bp against the
  floor.)
- **C's model is close on average (+0.07 bp) but no better per order** (4.6 against 4.7). Its trailing 14-day impact
  `y` has a median of 0 (mean 0.06); the same-day fits have a median of 0.19.

**Fallbacks** (share of the orders the rebuild priced):

| Book | Orders | Drift (no print within 1 s) | Spread (fewer than 20 pairs that day) | Impact (fewer than 30 taker orders) |
| --- | ---: | ---: | ---: | ---: |
| S\* | 448 | 2.5% | 51% | 25% |
| U\* | 566 | 2.3% | 60% | 26% |
| G\* | 194 | 2.1% | 56% | 0% |

The spread falls back on every BNB order and on 70% of HYPE's (ADR-0099, Context). Each fallback is the frozen
value, so the fallbacks pull the rebuild toward A.

### 9.5 O2, D3, C1 and the shadow logs
- **O2 never bound.** The frozen bounds are 408-2,682 bp per side (`o2_bounds.csv`); the development stress p99
  includes the 10-11 Oct crash. No order in B or C came near them.
- **D3 on B passes in all four windows,** as on A (1, 2, 1 and 3 coins measured, all within the development p90).
- **C1 on B fires 0 times,** against once on A (S\*, 8 Oct).
- **Shadow C1 (C) fires once:** on 0x2cd9 at 10 Oct 21:00, where C's frozen C1 does not. C's own stress estimate,
  with its lower `y`, is below the rebuilt cost there, so here letting C1 adapt would have added a firing, not
  removed one.
- **Shadow O2 (C) would have rejected 41 orders** (S\* 34, G\* 7) that the frozen bound passed. The updated model's
  stress shortfall for an order is a much tighter bound than the development p99.

### 9.6 The v2 holdout entry point, check mode

`phase5 holdout --check` runs the entry point's code on the last development window (19 Nov → 3 Dec, trigger
series at 3 Dec) into `research/holdout_check/` and reads nothing at or after 3 Dec 00:00 (`check.md`):

| Output | Compared with | Result |
| --- | --- | --- |
| 10k tradable tree (the single-window path) | `research/replay_tradable`, 19 Nov test window | 26/26 files byte-identical |
| 2,500 gray tree | `research/replay_gray/sleeve=2500`, 19 Nov | 26/26 |
| Run A: S\*, U\*, G\* in the four scenarios | `research/portfolio_replay`, 19 Nov | 84/84 |
| Runs B and C | `research/cost_runs`, 19 Nov | 40/40 |
| Window report H1-H6 (`holdout_report.report`, unchanged) | `research/window_report`, 19 Nov | 6/6 tables identical |
| Trigger series the engine reads (`daily_twr`, `book_hourly`) | `research/leader/origin=2025-12-03` | byte-identical |
| The other 20 Phase 2 tables there | the same | 18 byte-identical; 2 equal to 3.5e-16 relative |
| Valuation marks; H5 outcomes | the development outputs | equal |

- **The two near-identical tables** (`evidence`, `trip_summary`) differ only in the last bits of three float
  columns. The entry point bounds its inputs at the window end, so the frames are smaller and polars sums in a
  different order.
- **Two code fixes on the way,** logged in the trial log; neither changes a development output.
  - The tradable tree now carries the window's marks, which the outcome α reads.
  - The trigger series are built with the panels `leader.run` shares over the origins (`leader.shared_panels`).
    Built alone, `leader.compute` makes narrower panels, which changed 4 of the 22 tables.
- **Past the last configured origin:** with the origins cut to 8 Oct-5 Nov, the same code builds the 19 Nov tables
  past the last origin (`beyond_last_origin.md`). `daily_twr` and `book_hourly` are byte-identical to the published
  ones, as are 17 of the other 20 tables; 2 are equal to 1e-12. `daily_marks` differs because the shared price grid
  then covers the coin lists of three origins instead of five (ADR-0044).
- **Not exercised before the freeze:** the branch of `run_sensitivities` past 3 Dec, and `leader.compute` on its
  holdout bound. Both run only behind `freeze.guard`, and the tests cover the refusals.

### 9.7 For the memo
- In development the rebuild finds the frozen cost model conservative by about 1.5 bp per side (notional-weighted).
  HYPE's same-day spread is unmeasured (32 of 108 orders measured, median 0.27 bp, the mean inflated by 10 Oct).
- Neither O2 nor the stress limits bound, so B against C carries no information yet. Both comparisons are labelled
  rebuilt real conditions, not real fills; only the gray protocol measures our own orders (ADR-0090).

### 9.8 The cutoff selection's entry point, check mode (ADR-0100)

`phase5 cutoff --check` runs the cutoff selection's code at the 3 Dec origin with the real configuration into
`research/cutoff_check/`. It reads nothing at or after 3 Dec 00:00 (`check.md`).

| Output | Compared with | Result |
| --- | --- | --- |
| Drift tables (the builder, on inputs bounded at 3 Dec) | `research/drift` | 3/3 files byte-identical |
| Phase 2 tables at 3 Dec (the builder) | `research/leader/origin=2025-12-03` | 20/22 byte-identical; 2 equal to 3.5e-16 relative (section 9.6) |
| The all-priced prepare step: shared inputs; every window's universe and leader series | `research/replay_allpriced` | 4/4 and 18/18 byte-identical |
| The 3 Dec training window, all-priced (`run_sensitivities(training=)`) and its capture rows | the same | 28/28 files; 3/3 tables |
| The 3 Dec tradable sets; the tradable training window and its capture rows | `research/replay_tradable` | identical; 28/28; 3/3 |
| The selection at 3 Dec (`selection_v2.run(only=)`), `eligible.parquet` included | `research/selection_v2/origin=2025-12-03` | 12/12 byte-identical |

- **The hand-off** at 3 Dec is 0x2cd9, as published, so D5 is true (`cutoff_handoff.json`).
- **The holdout check, rerun with the cutoff check's hand-off as D5,** still reproduces every development output.
  Its 19 Nov decision entry now reads CONDITIONAL GO, labelled "development: not a decision".
- **The deliverables at 3 Dec** pass their consistency check (`deliverables/check.md`).
  - `trader_decisions.csv` covers 1,313 addresses: every address with a snapshot before 3 Dec. They are 182 A, 176 B
    and 955 C.
  - Of the 358 A/B addresses, 335 first fail S2, 21 fail S3 and 1 fails on its category; 1 (0x2cd9) fails no gate.
    The counts match `funnel_v2.csv`.
  - `target_allocations.csv` was written for both protocols. NO-GO: everything in paper, reserve 100,000. CONDITIONAL
    GO: 0x2cd9 live at 2,500, the observation sleeve zero-capital, reserve 97,500.
- **A differing cutoff hand-off:**
  - An address that cannot be replayed from 3 Dec gets D2b unmeasured and a NO-GO (tests).
  - The G\* rerun path ran on development data with a synthetic hand-off that adds 0x971f: its own 2,500 gray tree was built from the origin's inputs, G\* ran in the four scenarios (worst loss 21.6 USDC against the 750 cap, no cap breach) and D2b was read over both G\* books (true)
    (`g_rerun_check.md`).
- **Unchanged:** run A, 384/384 files byte-identical; the development selection rerun at every origin, 72/72 files
  byte-identical (`research/audit/selection_unchanged.md`).
- **One code fix on the way,** logged in the trial log: a single training window has no delay-grid rows, so
  `run_sensitivities` no longer writes an empty summary CSV. The full run always has those rows, so its output does
  not change.
- **An earlier development origin was not checked.** Its selection needs its test window's outcomes, which this path
  does not build (ADR-0100 item 7).

## 10. What is next

- **P5-7, the joint freeze (ADR-0091).** The user gave the go on 2026-11-24. This document is part of the frozen set.
  - `risk.yaml` holds no `OPEN` choice: the variants were settled at P5-4 and the gray size at P5-5.
  - L1 was measured out of sample before the freeze (section 4).
  - The freeze-mechanism changes listed in ADR-0091 are pinned in ADR-0097: the v2 shortlist, the manifests, the
    environment block and `verify_holdout_inputs.py`.
  - Runs B and C, run C's refit, the v2 holdout entry point and the cutoff selection are built and run on
    development data (section 9), and the frozen set holds them (ADR-0098 item 8, ADRs 0099-0100). One hash covers
    everything.
  - The user sends the hash to the reviewers.
- **The cutoff selection and the cutoff deliverables** are built and checked at 3 Dec (section 9.8; ADR-0100). The
  P5-8 order is enforced by the entry points: run A, the cutoff selection, the decision entry, then runs B and C.
- **P5-8, the holdout, and P5-9, the cutoff deliverables,** each need their own go.
