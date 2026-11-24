# Pre-holdout checks (2026-11-22)

Four checks raised in review before any further decision. All read development data only (training windows ending
3 Dec 2025 and earlier); no holdout window was computed. No hashed file was changed: the freeze `cbb44708…`
still matches. Scripts are in `scripts/` (outside the hashed set); outputs in `research/audit/`.

## Check 1: unvalued observations in the coin filter

**The route exists.** `selection_coins.coin_pnl` sets an (address, coin) PnL to null when a funding payment is unknown
or a held coin has no closing mark, and `coin_set` keeps a coin on the summed benchmark PnL and capture of the valued
rows. It counts the unvalued rows but imposes no coverage condition on them.

**It did not matter here.** `scripts/audit_coin_filter_coverage.py` →
`research/audit/coin_filter_coverage_2025-12-03.csv` (all 162 coins traded in the 3 Dec training window; the 37 kept are
listed first). The script reproduces the module's nulls and capture exactly (asserted).

| | Follower | Benchmark |
| --- | ---: | ---: |
| Valued (address, coin) observations, all coins | 2,377 | 3,209 |
| Unvalued, all coins | 6 | 19 |
| of which funding unknown / mark unavailable | 6 / 0 | 16 / 3 |
| Kept coins with any unvalued observation | 1 (MELANIA) | 1 (MELANIA) |

- **MELANIA:** 3 follower and 2 benchmark observations unvalued, all funding unknown. That is 1.6% and 5.6% of the
  coin's traded notional. Capture is 0.610, and it is the same 0.610 on the addresses valued on both sides (threshold
  0.5). Benchmark PnL is 865 USDC (threshold 500).
- **Robustness:** I recomputed every coin's decision on only the addresses valued on both sides. A side with no row
  never traded the coin, so its PnL is exactly zero, not missing. **No kept/dropped decision changes** at 3 Dec or at
  any development origin (8 Oct, 22 Oct, 5 Nov, 19 Nov: 0, 0, 1 and 0 kept coins with any unvalued row).

**Verdict:** coverage is effectively complete; the frozen filter is reliable at every origin.

**Proposed hardening, a no-op now:** keep a coin only if the decision also holds on the both-valued subset, and
publish the coverage columns with every coin set. This protects the cutoff selection (item 9), where coverage has not
been checked. It changes a hashed file, so it can only go in with the next freeze, which ADR-0065 requires anyway.

## Check 2: measured diversification of the 3 Dec basket

`scripts/audit_basket_pairs.py` → `research/audit/basket_pairs_2025-12-03.csv` and
`basket_concentration_2025-12-03.csv`. The inputs are the walk's own: the coin-filter tree, 3 Dec training window, base
scenario.

**All three pairs were measured.** None was admitted through the "unmeasured does not block" route: each pair has
129 common days, and both correlation and overlap are measured.

**The measured numbers overstate diversification:**

| Pair | Walk corr (129 days) | Days both hold exposure | Corr on those days | Corr without 10-11 Oct | Spearman (from 8 Sep) | Overlap | Shared coin-days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0x2cd9 / 0x971f | 0.31 | 31 | **0.51** | 0.10 | 0.19 | 0.00 | none |
| 0x2cd9 / 0xd2f0 | -0.19 | 25 | **0.50** | 0.39 | 0.34 | 0.37 | 17 (HYPE, all same direction) |
| 0x971f / 0xd2f0 | -0.62 | 62 | -0.17 | -0.14 | 0.18 | 0.00 | none |

1. **The walk counts flat days as common days.** The copies hold exposure on only 31 (0x2cd9), 79 (0x971f) and
   68 (0xd2f0) of the 129 days. The remaining days are 0.0 returns, including every day before 8 Sep, when nothing is
   executable. Those zeros pull the correlation toward zero.
   - On the days both copies actually carry risk, two pairs are at the 0.5 threshold.
   - `min_common_days: 20` is met by calendar days, not by days with risk on both sides.
2. **The strongest negative correlation (-0.62) comes from the 10-11 Oct crash.** It is -0.14 without those two days,
   and the rank correlation is +0.18.
3. **Concentration:**
   - Every sleeve is 100% long in every coin it held.
   - HYPE is 91% of 0x2cd9's gross exposure and 78% of 0xd2f0's.
   - 0x971f holds BNB (62%) and BTC (38%).
   - Zero overlap here means different coins, not opposite risk: three long crypto books.

**Verdict:** the basket is not shown to be diversified. The memo should say the diversification benefit is unverified,
and that the basket is long-only crypto with a HYPE concentration.

**If the rule is corrected** (development data only, logged as decided after seeing results, new freeze):
- measure correlation on days both copies hold exposure, with `min_common_days` counted on those days;
- make an unmeasured pair block the candidate instead of passing it;
- rerun the walk at all five origins.

At 3 Dec this would likely reject a pair partner of 0x2cd9, so it changes the basket. That is the reason to decide the
definition on its merits and apply it at every origin, not only where it bites.

## Check 3: the holdout's data dependency chain

`scripts/verify_holdout_inputs.py` → `research/audit/holdout_inputs_verification.md`, run with POLARS_MAX_THREADS=8.

| Item | Result |
| --- | --- |
| Current freeze (45 files) | recomputed hash equals `cbb44708…` |
| Raw inputs + reference prices (`provenance/CHECKSUMS.txt`, 14) | all match |
| Reference price manifest (7) | all match |
| Binance aggTrades MANIFEST (476) | all match |
| Hyperliquid funding / 4h candles / user funding (1,491 / 195 / 12) | all match |
| Pre-Phase 4 outputs (`PRE_PHASE4_OUTPUT_CHECKSUMS.txt`, 396) | all match |
| Binance kline zips (`data/reference/binance/CHECKSUMS.txt`, 1,326) | 1,270 match. 56 entries point to `data/lake/_raw/.../aggTrades/` zips (BTC, ETH, HYPE, SOL, 8-21 Oct) that are no longer there. Each one's hash is in the aggTrades MANIFEST, which verifies, so the content is intact; the entry is stale. |
| Shared inputs copied into the coin-filter tree (marks, spreads, drift cells, bands) | identical byte for byte to the frozen tree |

**The gap:** 454 files the holdout path reads are covered by no manifest: 266 under `research/replay_coinfilter` and
188 under `research/selection`. Only the 3 Dec shortlist is in the freeze. They are now hashed in
`research/audit/unmanifested_inputs.txt`.

**Environment:**
- Python 3.12.15 on Windows 11;
- polars 2.1.0, numpy 2.5.5, pyarrow 26.0.1;
- `uv.lock` hash `ad8e6154…`;
- POLARS_MAX_THREADS=8.

**Proposed for the next freeze:**
1. Add the manifest file hashes and the coin-filter/selection output manifest to `HOLDOUT_FREEZE.txt`, so the freeze
   pins data as well as code.
2. Record the environment block.
3. Drop or annotate the 56 stale kline-manifest entries.
4. Run `verify_holdout_inputs.py` immediately before the holdout run and keep its output.

## Check 4: lock the holdout report before reading the holdout

**Current plan:** ADR-A0140/A0141 let `holdout_report.py` be written after the freeze, outside the hashed set. The
review is right that its aggregation choices are discretion: missing returns, the dates included, the benchmark
comparison and the stress summary.

**Proposed:**
- Write the report module now as a window report that takes any (origin, window).
- Run it on all four development test windows, not only 19 Nov, so the holdout is reported in exactly the form the
  development windows were.
- Freeze its output schema.
- Add its SHA-256 to the next freeze.
- It reads only frozen outputs and decides nothing.

**Day counts to report separately:**

| Measure | Holdout value |
| --- | --- |
| Calendar span scored | 3 Dec 2025 00:00 → 4 Jan 2026 00:00 UTC: 32 days (3 Dec … 3 Jan) |
| Data to the cutoff, not scored | 4 Jan 00:00 → 23:59:42 UTC (no closing daily mark) |
| Output rows per address | 32 |
| Valid daily returns per address | counted, not assumed. A day with a held coin lacking a mark, or unknown funding, is null and is reported as such. |

ADR-A0140 and the Phase 4 results describe the window as "32 daily returns". The report will say 32 calendar rows and
state the number of valid returns separately.

## Check 5: residual exposure after the leader exits (added after the copy-trading review)

**Question:** does the copy keep a position after the leader is flat? This is the fragmented-exit failure described in
an external copy-trading account.

`scripts/audit_residual_exposure.py` → `research/audit/residual_exposure.csv`. Inputs: the coin-filter replay, base,
the four development test windows and the 3 Dec training window.

| Window | Leader-flat events | Leaving a residual | Median residual | Residual share of exposure-time | Residual PnL (priced) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 Oct test, all A/B | 2,874 | 9.9% | 1.09 USDC | 1.8% | -1,319 USDC |
| 22 Oct test, all A/B | 2,522 | 14.0% | 1.25 USDC | 1.7% | -379 USDC |
| 5 Nov test, all A/B | 2,445 | 16.0% | 0.27 USDC | 1.4% | +60 USDC |
| 19 Nov test, all A/B | 2,066 | 19.8% | 0.53 USDC | 1.5% | +914 USDC |
| 3 Dec training, all A/B | 17,601 | 12.6% | 0.64 USDC | 2.4% | +1,470 USDC |
| Selected baskets, four test windows | 114 | 16 events | | ≤ 0.9% | -46 USDC in total |

**Mechanism:**
- The replay targets the leader's net position, so a partial leader exit is never read as a full one.
- A residual arises when the flattening order is shrunk by the no-scale-up leader-batch budget or the 0.5%
  participation cap (most cases, usually cents to a few USDC). It also arises when the order cannot be priced
  (`no_eligible_aggtrade`) or falls under the 10 USDC minimum.
- Nothing retries until the leader trades that coin again, or a cap resize leg touches it.

**It is immaterial for the result.** Across the four development test windows (all A/B, base), the capture gap is
48,857 USDC:
- fees 59%, half-spread 34%, impact 20% (shares of the gap; some components are negative, so they do not sum to
  100%);
- delay drift -1.2%;
- orders skipped under the minimum -0.1%;
- participation clips 1.5%.

The basket gap (773 USDC) has delay drift of 20 USDC.

**For the operating answers:** a live engine needs a flatten sweep. When the leader is flat and the copy is not,
close the remainder (reduce-only), independently of leader events.

## Check 6: end-to-end fragmented-position test (passes; no defect)

`tests/test_fragmented_lifecycle.py`, 10 tests. A synthetic leader runs through the frozen replay's own path:
`batches` → `reference_equity` → `cap_legs` (no scale-up) → `order_inputs` (1.2 s) → `quotes` (base, sweep anchor) →
`execute` (square-root impact, participation, leader-batch budget, 1.5x cap, pending reservations).

The leader's lifecycle:
- an entry, with two fills of one order in the same millisecond;
- a scale-in on two orders in the same millisecond;
- a partial close that becomes visible only after the scale-in decision, while those orders are still pending;
- a partial close split across two fills inside the debounce;
- a full close, then a new short;
- a short-to-long flip in one fill, then a close.

It runs unconstrained, and with the 0.5% participation budget clipping every order to 30 units.

All five invariants from the review hold in both runs:
1. The target is the frozen multiplier times the latest *visible* net position.
2. A partial reduction never sets a flat or opposite target.
3. Each request is target - (held + pending): no double counting.
4. No fill exceeds or reverses its request, and the copy never holds more than its largest target or the cap,
   through the flip included.
5. Closes set a zero target and are always submitted. Unconstrained, the copy ends exactly flat.

What the clipped run shows (documented behaviour, not a defect):
- **A residual after a leader close.** When the leader closes, the copy is still long 15 units because the close was
  clipped. It is netted out at the leader's next order in the coin, as in Check 5. A live engine needs the flatten
  sweep noted there.
- **The participation budget is per order.** Two leader orders in the same millisecond each get 0.5% of the bar, so
  the copy can take 1% of a bar at once (ADR-0035 as written). This is slightly optimistic for bursts of orders.

## What these checks change

- **Check 1 and Check 3:** documentation and hardening only. The frozen rule and the data are intact.
- **Check 2:** a substantive finding about the basket.
- **Check 4:** a process change.

ADR-0065 already requires a new freeze after Phase 5. Any change adopted from these checks should go into that one
freeze, decided on development data only, never on the holdout.
