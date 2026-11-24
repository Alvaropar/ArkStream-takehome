# Measured copy delay: results before and after

Brief: [`briefs/measured-latency-rerun.md`](briefs/measured-latency-rerun.md). Decisions:
[ADR-0058](adr/0058-measured-copy-delay-scenarios.md) (the scenarios, chosen by the user from the measurement before
any Phase 4 result), [ADR-0059](adr/0059-millisecond-delays-and-horizons.md) (milliseconds end to end, horizons and
delay grid), [ADR-0060](adr/0060-severe-scenario.md) (severe). Frozen `E_ref` sizing only (ADR-0052); Phase 2 not
rerun (it does not depend on the copy delay); the holdout test window (2025-12-03..2026-01-04) was not computed;
selection has not started.

"Before" is the published frozen replay under ADR-0055 (`decision/pre-phase-4-results.md` section 11), saved before
any rerun in `provenance/measured_latency_before/` (summary CSVs, the gate-passer address summaries and the previous
checksum list). "After" is `research/replay_frozen/` and `research/drift/` from this rerun. Every figure below is over
the **56 gate-passing development test address-windows** (16 / 12 / 15 / 13 at 8 Oct, 22 Oct, 5 Nov, 19 Nov),
funded, on 10,000 USDC per address-window.

| Scenario | Before | After | Basis (ADR-0056 total) |
| --- | --- | --- | --- |
| optimistic | 1 s | 1 s | about the measured 10th percentile |
| base | 10 s (assumed) | **1.2 s** | the measured median |
| stress | 60 s; 300 s for thin coins (assumed) | **5 s, every coin** | the measured 99th percentile, rounded up |
| severe | (did not exist) | 60 s; 300 s for thin coins, stress costs | labelled sensitivity: disconnects of 2-17 s |

## How much did the measured delay change the result?

**Very little.** Base moves from +0.47% to **+0.54%** (+0.07 pp; 28 positive both times; headroom 6.2 to 7.2 bps
per filled side). Optimistic is unchanged to the byte. Stress at 5 s is slightly *worse* than the old 60 s / 300 s
stress: −1.40% to **−1.53%**, and 2 more windows fail the stress check (44 pass, 11 fail on loss, 1 unmeasured;
46 / 9 / 1 before). The cost-surface lower bound goes from −0.06% to **−0.01%** (−0.8 to −0.15 bps per side):
still not positive. Severe reproduces the old stress result exactly (−1.40%).

The reason is that between 1 s and 60 s the result does not depend on the delay in this model:

- **Parameterised coins** (37% of the gate-passers' filled base notional) take a drift that, at any delay under
  300 s, is bounded below by the coin's own 300 s estimate (base: max(four-coin proxy, own 300 s, 0), ADR-0048;
  stress: max(stress proxy, own 300 s stress cell or the ADR-0053 fallback)). Their base drift is **+3.68 bps per
  side at 10 s and at 1.2 s**.
- **BTC, ETH, HYPE, SOL** are priced from Binance aggTrades at the exact acknowledgement time, and the drift there
  is small and slightly favourable at every horizon from 1 s to 60 s (development cells −1.8 to +1.6 bps; filled
  base orders −1.53 bps at 10 s, −1.04 bps at 1.2 s).
- On the delay grid, base is +0.49% / +0.54% / +0.58% / +0.47% / +0.53% at 1 / 1.2 / 5 / 10 / 60 s, and stress (on
  the 54 windows measured at every point) −2.23% / −2.21% / −2.11% / −2.17% / −2.21%. The jump at 300 s (base +1.00%,
  stress +0.89%) is a change of method, not of delay: from 300 s parameterised coins use their own 300 s cell
  without the proxy and zero bounds.

So the measured delay removes an assumption, not a cost: the 10 s base was conservative, but the 10 s delay was not
what limited the base result. What limits it is the spread, impact and fee placeholders and the parameterised-coin
drift bound (section 6).

## 1. Scenario results

| Scenario | Delay before → after | Mean funded return | Positive / measured | Profit (USDC) | Headroom per filled side |
| --- | --- | ---: | ---: | ---: | ---: |
| optimistic | 1 s → 1 s | +1.09% → +1.09% | 29 / 56 → 29 / 56 | 6,105 → 6,105 | 14.4 → 14.4 bps |
| **base** | 10 s → **1.2 s** | +0.47% → **+0.54%** | 28 / 56 → 28 / 56 | 2,611 → 3,046 | 6.2 → **7.2 bps** |
| **stress** | 60 / 300 s → **5 s** | −1.40% → **−1.53%** | 21 / 55 → 22 / 55 | −7,715 → −8,437 | −18.6 → −20.1 bps |
| severe (new) | 60 / 300 s | −1.40% | 21 / 55 | −7,715 | −18.6 bps |

Headroom = profit / filled turnover: the extra cost per filled side that would absorb the profit. Stress means are
over measured windows (ADR-0055: 55 of 56; the unmeasured one is the same 8 Oct window as before).

Per test origin (mean / positive of measured / headroom in bps):

| Scenario | 8 Oct | 22 Oct | 5 Nov | 19 Nov |
| --- | ---: | ---: | ---: | ---: |
| optimistic, before = after | +2.52% / 6 of 16 / 25.7 | +1.15% / 8 of 12 / 19.9 | −0.03% / 7 of 15 / −0.5 | +0.57% / 8 of 13 / 8.1 |
| base, before (10 s) | +1.05% / 6 of 16 / 11.0 | +0.91% / 8 of 12 / 15.8 | −0.42% / 7 of 15 / −5.8 | +0.36% / 7 of 13 / 5.1 |
| **base, after (1.2 s)** | **+1.21% / 6 of 16 / 12.5** | **+0.86% / 8 of 12 / 14.8** | **−0.44% / 7 of 15 / −6.2** | **+0.58% / 7 of 13 / 8.2** |
| stress, before (60 / 300 s) | −0.06% / 6 of 15 / −0.6 | −1.15% / 5 of 12 / −20.2 | −2.91% / 5 of 15 / −41.0 | −1.45% / 5 of 13 / −20.6 |
| **stress, after (5 s)** | **−0.20% / 6 of 15 / −1.9** | **−0.98% / 5 of 12 / −16.9** | **−2.97% / 6 of 15 / −42.1** | **−1.94% / 5 of 13 / −27.6** |
| severe (60 / 300 s) | −0.06% / 6 of 15 / −0.6 | −1.15% / 5 of 12 / −20.2 | −2.91% / 5 of 15 / −41.0 | −1.45% / 5 of 13 / −20.6 |

Base is still negative in one test (5 Nov) and positive in three. Training windows (gate-passers, base) move little:
−1.06 / +6.32 / +5.47 / +7.00 / +7.22% before, −1.05 / +6.36 / +5.21 / +6.62 / +7.00% after at the five origins.

## 2. Stress check and coverage (ADR-0055 measure)

The plan's stress check: measured, not exhausted, and stress maximum drawdown within the −10% `reduce_only` step;
an unmeasured window fails. It is read on `stress` (ADR-0058 item 5); severe is beside it.

| Test origin | Before, stress 60 / 300 s: pass / fail on loss / fail unmeasured | **After, stress 5 s** | After, severe 60 / 300 s |
| --- | ---: | ---: | ---: |
| 8 Oct (16) | 10 / 5 / 1 | 10 / 5 / 1 | 10 / 5 / 1 |
| 22 Oct (12) | 11 / 1 / 0 | 11 / 1 / 0 | 11 / 1 / 0 |
| 5 Nov (15) | 12 / 3 / 0 | 12 / 3 / 0 | 12 / 3 / 0 |
| 19 Nov (13) | 13 / 0 / 0 | **11 / 2 / 0** | 13 / 0 / 0 |
| all four (56) | 46 / 9 / 1 | **44 / 11 / 1** | 46 / 9 / 1 |

The two new failures are at 19 Nov and sat just inside the line before: 0xa7c6…707a (drawdown −9.3% → −11.9%,
return −9.3% → −11.9%; base −3.5%) and 0xd2f0…e9e1 (−8.0% → −10.4%, return −6.3% → −9.8%; base −7.8%). In both, the
5 s stress prices parameterised coins with max(stress proxy, own 300 s cell), where the old 300 s thin-coin path took
the own 300 s cell alone, which can be negative (section 6).

Coverage: windows measured 55 of 56 both times (the 8 Oct window with 2 of 8 intents unpriced). Pricing failures
rose from 534 of 16,829 intents to 1,984 of 16,256, almost all at 8 Oct (496 → 1,946 of 12,507): before the crash
sample, a parameterised coin without its own development 300 s estimate cannot be stress-priced at any delay
(ADR-0053's known residual), but with a 300 s acknowledgement the follower's pending orders stayed reserved longer,
so most of those intents fell below the 10 USDC minimum (a measured outcome: `below_minimum` 7,589 → 5,695); at
5 s they are large enough to need a price. No window's measurement changed. The worst-measured sensitivity (each
unmeasured window at its test's worst measured stress return) is −2.33% (−2.08% before). Under ADR-0049's broad
measure: 50 measured, 21 positive, −1.81% (49, 20, −1.64% before); check 42 / 8 / 6 (43 / 6 / 7).

## 3. Cost surface (ADR-0050), base at 1.2 s

| Point (Y, participation, cap) | Before (base 10 s): mean / positive / profit / headroom | **After (base 1.2 s)** |
| --- | ---: | ---: |
| centre (1, 0.5%, 1.5x) | +0.47% / 28 / 2,611 / 6.2 bps | **+0.54% / 28 / 3,046 / 7.2 bps** |
| Y 0.5 | +0.56% / 28 / 3,141 / 7.5 | +0.64% / 29 / 3,580 / 8.5 |
| Y 2 | +0.32% / 28 / 1,773 / 4.2 | +0.35% / 28 / 1,980 / 4.7 |
| participation 0.25% | +0.34% / 27 / 1,898 / 4.6 | +0.41% / 28 / 2,288 / 5.5 |
| participation 1% | +0.49% / 28 / 2,762 / 6.5 | +0.59% / 28 / 3,283 / 7.7 |
| participation none | +0.60% / 28 / 3,382 / 8.0 | +0.60% / 28 / 3,365 / 7.9 |
| cap 1.0x | +0.17% / 27 / 965 / 2.5 | +0.22% / 27 / 1,208 / 3.2 |
| cap 2.0x | +0.14% / 27 / 806 / 1.8 | +0.32% / 27 / 1,773 / 4.0 |
| most favourable | (0.5, none, 1.5x): +0.71% / 28 / 3,960 / 9.3 | (0.5, none, 1.5x): +0.70% / 29 / 3,945 / 9.2 |
| **least favourable (lower bound)** | **(2, 0.25%, 2.0x): −0.06% / 27 / −334 / −0.8** | **(2, 0.25%, 1.0x): −0.01% / 27 / −57 / −0.15** |

The least favourable corner changed its cap (1.0x is now the worse of the two one-at-a-time caps). At the lower
bound the tests are −0.12% / +0.31% / −0.48% / +0.37% (before −0.65% / +0.15% / −0.25% / +0.69%): two tests still
negative. The base result still does not clear costs across the whole surface.

## 4. Holding bands (base, frozen, all A/B addresses, four tests)

Net funded result per completed follower round trip (trip-weighted bps), with the number of tests in which the band
is positive:

| Leader's median hold | Completed trips, before → after | Net bps, before (10 s) | **Net bps, after (1.2 s)** | Positive tests, before → after |
| --- | ---: | ---: | ---: | ---: |
| <1m | 203 → 202 | −9.6 | **+4.5** | 0 → 3 of 4 |
| 1-15m | 1,005 → 1,057 | +0.4 | +0.1 | 1 → 1 |
| 15m-1h | 630 → 645 | +5.4 | +6.7 | 1 → 1 |
| 1-6h | 1,638 → 1,656 | +60.3 | +60.5 | **4 → 4** |
| 6-24h | 1,421 → 1,423 | +71.1 | +71.0 | **4 → 4** |
| 1-7d | 1,965 → 1,963 | +117.6 | +115.1 | 1 → 1 |
| >7d | 201 → 205 | −166.2 | −153.0 | 0 → 0 |

The bands clearing costs in every test are still 1-6h and 6-24h. The only band the delay moves is the shortest:
leaders holding under a minute gain 14 bps per trip at 1.2 s (positive in three tests, not four).
Per test (after): <1m +21.0 / +0.9 / −35.0 / +31.0; 1-6h +118.8 / +32.3 / +31.7 / +80.7; 6-24h +72.3 / +83.7 /
+67.1 / +59.3. Figure: `decision/figures/p4_holding_bands_frozen.png`.

## 5. Delay grid and break-even

The grid is now 1, 1.2, 5, 10, 60, 300 s (ADR-0059). Mean funded return of the gate-passers at each fixed delay:

| Scenario costs | 1 s | 1.2 s | 5 s | 10 s | 60 s | 300 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| optimistic | +1.09% | +1.14% | +1.24% | +1.19% | +1.12% | +1.32% |
| base | +0.49% | **+0.54%** | +0.58% | +0.47% | +0.53% | +1.00% |
| stress (54 windows measured at every point) | −2.23% | −2.21% | **−2.11%** | −2.17% | −2.21% | +0.89% |

The 1, 10, 60 and 300 s points are identical to the previous grid (the base value at 10 s equals the previous base
result exactly). Break-even statuses are unchanged (base: 25 non-positive at the shortest delay, 0 crossing inside
the grid, 28 positive through it, 3 unmeasured; stress and severe: 31 / 2 / 18 / 5). The break-even delay of the
copyable addresses is not inside the grid: those that lose, lose at 1 s already.

## 6. Why stress at 5 s is not better than at 60 s

Drift per filled side, gate-passers (stress costs):

| Price source | Stress 60 / 300 s (= severe) | Stress 5 s |
| --- | ---: | ---: |
| BTC, ETH, HYPE, SOL (aggTrades at acknowledgement) | −5.3 bps | −0.6 bps |
| parameterised coins | +49.0 bps | +53.5 bps |
| all | +14.5 bps | +19.3 bps |

At 60 s the four directly priced coins drifted in the follower's favour (the leader's sweep partly reverts within a
minute), which 5 s does not capture. On parameterised coins the old thin-coin path (300 s) took the coin's own 300 s
crash-sample cell alone; at 5 s every coin takes max(stress proxy, own 300 s cell or fallback), which is never
lower. Both are properties of the drift model and the data, not of the code change: severe, which keeps the old
delays, reproduces the old stress result byte for byte.

## 7. What else stayed the same

- **Drift** (`research/drift`): all 16,278 rows at 1, 10, 60 and 300 s equal the previous output; the hold bands and
  the coverage report are byte-identical. New: 358 development and 278 stress cells at 1.2 s and 5 s; the four
  aggTrades coins have an `ok` all-band cell at both horizons at all five origins (the four-coin proxy exists), and
  stress cells from 22 Oct on (none at 8 Oct, none borrowed).
- **Replay inputs**: the nine universes, hold bands, valuation marks and impact inputs are byte-identical;
  `spread_estimates` gains two `severe_*` columns equal to the stress ones; `drift_cells` gains the new horizons
  (33,031 → 35,667 rows).
- **Optimistic**: daily ledgers, funding and band tables byte-identical in all nine windows; orders differ only in the
  delay columns and in the horizon unit inside `parameter_cells` (60 → 60000).
- **Severe vs the old stress**: the same in all nine windows (ledgers byte-identical, orders as above).
- **Size study** (ADR-0036): byte-identical; it keeps its 1 / 10 / 60 / 300 s horizons and still finds no size
  term.

## 8. Verification

- `ruff`, `mypy`, the full `pytest` (229 tests, unit and data, none skipped; new: `tests/test_measured_latency.py`
  for millisecond delays, the 1.2 s print, the cell keys, the bracket, the scenario config, the delay plan, severe
  pricing as stress and its thin-coin rule, the new drift cells at every origin and the published delays) and the
  audit (31/31) pass.
- Two independent runs at `POLARS_MAX_THREADS=8` are byte-identical: `drift` 4 of 4 files (1 min 52 s and 1 min
  45 s), `replay --frozen` 230 of 230 files (16.5 and 15.8 min; 185 before, plus severe's 45).
- Against the saved before state: optimistic ledgers byte-identical in all nine windows, severe identical to the old
  stress, base at the 10 s grid point equal to the old base result, orders differing only in the delay units (all
  18 window-scenario pairs checked), size study and universes byte-identical.
- `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt` regenerated over the same scope: 357 files (the 123 Phase 2 and
  price-check files unchanged and verified, 4 drift, 230 frozen replay); `SIZING_ARCHIVE_CHECKSUMS.txt` still
  matches. `VERIFY.md`, figures (`make figures`) and the package updated.

## Open items carried

- The decision time inside the delay stays at event + 250 ms receive + 250 ms debounce (ADR-0030 placeholders); the
  measured receive median is 392 ms. It decides which fills are batched, not the acknowledgement time (ADR-0058).
- The delay figures carry ADR-0056's caveats: Binance Demo acknowledgement (Hyperliquid's cannot be measured without
  orders), one home laptop on Wi-Fi, a p99 resting on few messages. Severe covers an outage of a minute.
- The stress check on the selected basket, and whether severe should enter any gate, are Phase 4 questions; nothing
  was selected here.
