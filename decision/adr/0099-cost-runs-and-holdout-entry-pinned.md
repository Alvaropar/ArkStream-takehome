# ADR-0099: Holdout cost runs B and C and the v2 holdout entry point: details pinned before computing

- Status: Accepted (pinned on development data on 2026-11-24, before any run B or C was computed and before the
  entry point was run; recorded in `provenance/trial_log.md`, "Phase 5 cost runs B and C, development").
  Item 11's D5 input and stage order are refined by ADR-0100: the cutoff hand-off now comes from the cutoff
  selection's entry point, and the stages are run A, the cutoff selection, the decision entry, then B and C.
  ADR-0098's "S1 stress cap" was corrected by an erratum to item 9's reading.
- Date: 2026-11-24
- Phase: Phase 5 (revision 4), built before P5-7 (joint freeze), run at P5-8
- Refines: ADR-0098 items 2-6 and 11 (the cost rebuild, C's refit, the shadow logs), ADR-0092 (the holdout run),
  ADR-0097 (the v2 holdout entry point it found missing)
- Source: `src/arkstream/cost_rebuild.py`, `src/arkstream/cost_updated.py`, `src/arkstream/cost_runs.py`,
  `src/arkstream/holdout.py`, `src/arkstream/portfolio_engine.py`

## Context
ADR-0098 item 11 leaves five details to be pinned on development data before the freeze: the rebuild windows, the
spread estimator's bias handling, the delay seed, C's trailing windows and the minimum counts for each fallback.
Building the runs needed a few more: what "the S1 stress cap" reads, what the shadow O2 bound is, and how an order
the frozen model cannot price is treated. ADR-0097 also found that the code had no v2 holdout entry point. Every
item below was written before any run B or C was computed.

Two facts from the development data shaped the items (structure, not results):
- The frozen spread fit (8-22 Oct) has 492 one-minute pairs for BTC, 405 for HYPE, 248 for ETH, 123 for SOL, 39 for
  BNB and about 10 for AAVE and EIGEN. One day holds about a fourteenth of that, so the same-day spread (item 3) will
  often fall back to the frozen value.
- The tree's trigger legs are decided 642 ms after the leader fill (receive 392 ms plus debounce 250 ms) and
  acknowledged at 1,200 ms.

## Decision
1. **The delay draw.**
   - The quantile function runs through the four `per_draw` rows of `research/latency/total_delay.csv` (p10 994,
     p50 1,225, p90 1,844, p99 3,540 ms). It is linear between them and flat below p10 and above p99, the convention
     of `latency.ack_quantile`. Draws are rounded to whole milliseconds.
   - One uniform per order the rebuild prices, in submission order, from numpy
     `default_rng([20251203, origin ordinal, config code])`, with S\* 1, U\* 2 and G\* 3. B and C share the stream;
     their draws differ once their orders do.
   - A trigger leg is acknowledged at the leader fill plus the draw. Every other order is decided after the receive
     and debounce legs, so it is acknowledged at the decision plus max(draw - 392 - 250, 0) ms. No acknowledgement
     is earlier than its decision.

2. **Drift.**
   - **Tape coins:** BTC, ETH, HYPE and SOL (`drift.aggtrades_symbols`), and, for the rebuild only, BNB, AAVE and
     EIGEN (BNBUSDT, AAVEUSDT, EIGENUSDT, downloaded and verified on 2026-11-24, rows of the aggTrades
     `MANIFEST.csv`). Run A and the drift table never read the three added coins.
   - **Reference:** anchor × P(t1) / P(t0).
     - Trigger leg: t0 is the leader fill and the anchor is the tree's mid at the leader fill.
     - Every other order: t0 is the decision and the anchor is the decision mark.
     - t1 is item 1's acknowledgement.
     - P(t) is the price of the last aggTrade at or before t, at most 1 s old (`drift.max_staleness_s`), from
       checksum-verified files.
   - **The basis correction is the ratio.** The level basis between the venues cancels, as in the frozen tape
     factor b1 / b0.
   - **Fallback, flagged:** a coin without tape, or no print within 1 s at either end, takes the frozen model's
     drift for the same order (its tape factor, or its parameterised cell at the frozen delay).

3. **Spread.**
   - `replay_spreads.fit_spreads` (ADR-0031: one-minute bars of the package's deduplicated prints; pairs of
     consecutive minutes with at least 2 prints each) on the decision's UTC day, 00:00 to 24:00.
   - **No scenario floor.**
   - **Bias handling:** the raw Corwin-Schultz mean, uncorrected, as in the frozen fit, which applies no correction
     and only flags `downward_bias`. The Abdi-Ranaldo estimate and the simulated bias are recorded per coin-day and
     never applied.
   - **Fallback, flagged:** fewer than 20 pairs that day takes the frozen model's half-spread for the same order.

4. **Impact.**
   - **Fit sample, per coin and UTC day:** the package's taker orders. A taker order is one (trader, oid) whose every
     fill has `is_maker` false, among eligible core-perp trades, forced fills excluded, every address in the
     package.
   - **Per order:**
     - N = Σ |size| × price, the VWAP and the sign;
     - x = σ_daily × √(N / V_daily) × 10⁴, from the latest completed 4h bar (`impact_bars`, as the frozen model);
     - reference = P(first fill - 1 ms) × basis_day. basis_day is the median, over the day's deduplicated prints, of
       print / P(print), with P as in item 2;
     - z = sign × (VWAP / reference - 1) × 10⁴ - the day's rebuilt half-spread (item 3; the frozen base half-spread
       when it falls back).
   - **y_day = max(Σ xz / Σ x², 0)** over the orders with x > 0 and a reference.
   - **Fallback, flagged:** fewer than 30 such orders (the drift cell minimum), or a coin without tape, takes the
     frozen y = 1.0.
   - **Our order:** impact = y_day × σ_daily × √(|q| × reference / V_daily) × 10⁴. This is the base square-root
     form, without a multiple, and it applies to FLATTEN orders too.

5. **Fill completeness (O2).**
   - **The frozen bound** per ADR-0053 liquidity bucket (by the latest completed 4h bar at the decision) is the 99th
     percentile (linear) of sign × (fill / mid at the leader fill - 1) × 10⁴. That is the stress scenario's price
     shortfall, without the fee, over the filled trigger-leg orders of the 10k tradable tree on the four development
     test windows (every A/B address). It is written to `research/cost_runs/o2_bounds.csv` and frozen with it.
   - **Test:** the rebuilt order's shortfall without the fee, sign × (rebuilt price / anchor - 1) × 10⁴, above its
     bucket's bound makes the order `rejected_o2`.
   - **The engine's failure path:** the order counts as submitted and uses participation, holds its pending quantity
     until its acknowledgement, then fills nothing. The next update or sweep recomputes Δ from state.
   - An unknown bucket takes the largest bound. The test is binary: no depth data, so no partial fills.

6. **Which orders, and the fee.**
   - The rebuild prices only orders the frozen model prices. An order the frozen model cannot price (a tree pricing
     failure, no drift cell, no square-root inputs) keeps its frozen status. The rebuild changes costs, not the order
     set.
   - Fee 4.5 bps. Funding and marks are unchanged.

7. **Runs and windows.**
   - B and C each run once, on the base scenario's tree inputs (signals, legs, trigger-leg references). The frozen
     base model's cost is recorded beside the rebuilt one; for a FLATTEN order it is the stress cost, as A charges.
   - Books: B on S\*, U\* and G\*; C on S\* and G\*.
   - **The rebuild window** of an order is its decision's UTC day (items 3 and 4); its drift (item 2) uses data to
     its acknowledgement. C learns from its own fill from 00:00 UTC after that day.

8. **C's daily refit**, at 00:00 UTC of each day d, on data before d:
   - **Spread:** item 3's estimator on [d - 14 days, d), the scenario floor kept (the larger of the floor and the
     estimate). Fewer than 20 pairs takes the frozen estimate.
   - **Drift table:** `drift.estimate` at the daily vintages, on the expanding history from 2025-09-08: rules 4 and 5,
     10-11 Oct excluded from the development cells and used as the stress sample once known. With it the ADR-0053
     bucket cells, the ADR-0061 split-order cells on the same vintages, and each leader's hold band at d. Rule 4's
     tape coins stay BTC, ETH, HYPE and SOL. On an origin day the daily cells must equal the origin's frozen cells
     (checked).
   - **Impact y:** item 4's fit pooled over [d - 14 days, d), plus C's own filled orders decided before d (x from the
     order, z its rebuilt impact). Fewer than 30 orders takes the frozen y.
   - **Fixed:** the delays (1,200 ms base, 5,000 ms stress), the fee, the half-spread floors (1 / 5 bp base, 3 / 15 bp
     stress), the 3× stress impact multiple, and the C1 and O2 benchmarks.

9. **What reads the updated model in C.**
   - **ADR-0098 item 5's "S1 stress cap" means the limits that call `stress_loss`.** S1 is the gross cap and reads no
     cost model. For S\* they are S2, P4 (with its hourly passive check) and P5; for G\*, the `L_gray` stress cap.
     With them, the exit cost in the gray loss cap. The logged stress quantities follow the same model.
   - **C1 and O2 use the frozen model in every run.**
   - **Shadow C1:** C1 recomputed with the updated stress model for each fill, logged as `shadow_trigger_on`, never
     acted on.
   - **Shadow O2:** the bound is the updated model's stress shortfall without the fee for that order (`exit_bps` on
     the updated view, less the fee). It is order-level, because the updated model has no p99 distribution by
     bucket. Logged as `shadow_o2_reject` when the rebuilt shortfall exceeds it, never acted on.

10. **The per-order record** (`cost_records.parquet`, every order the rebuild prices in B and C):
    - for the frozen model, C's updated model (C only) and the rebuild: delay, drift, half-spread, impact and fee
      (bps), and the fill status;
    - the fallback flag of each rebuilt part, the bucket, the O2 bound, and in C the shadow bound.

    Accuracy is measured within one run: per part, model minus rebuild, over the filled orders.

11. **The v2 holdout entry point** (`phase5 holdout`, `src/arkstream/holdout.py`).
    - **Guard:** refused by `freeze.guard` at 4 Jan 00:00 unless the freeze holds. Nothing runs before the guard.
    - **Trees:** the 10k tradable tree and the 2,500 gray tree (both sleeves) for 3 Dec → 4 Jan, through
      `run_sensitivities(window=...)` with the 3 Dec tradable sets (the ADR-A0140 single-window path). Their shared
      inputs are copied from the development trees, which hold the 3 Dec vintages.
    - **Marks:** the Hyperliquid daily closes to 4 Jan, as `replay.run` writes them (`model_inputs_by_origin`).
    - **Trigger series:** the Phase 2 tables at the window end, 4 Jan 00:00, built as `leader.run` builds every
      origin's: the price, volume and candle panels shared over the configured origins and the window end
      (`leader.shared_panels`), then `leader.compute`. The inputs are bounded at the window end; each value is used
      from its own time on. An address not graded A or B there has no L1-L4 series, as at a development series
      origin.
    - **Run A:** S\*, U\* and G\* in all four scenarios with the P5-5 code and the 3 Dec risk model; the H5 outcomes
      from `selection_v2.test_outcomes` on the window; the report through `holdout_report.report` (not
      development); the decision entry `research/holdout/decision_A.json` with D1-D5.
    - **B and C** refuse to start until that entry exists, and record its sha256.
    - **The G\* rerun (ADR-0092 item 3):** for each cutoff hand-off address other than 0x2cd9, its own 2,500 gray
      tree from the 3 Dec inputs and G\* in all four scenarios. D2b is read over all of them. An address outside the
      3 Dec all-priced universe, or without a tradable set there, has D2b unmeasured.
    - **D5:** the cutoff selection (ADR-0094 item 3) is not part of the entry point; the cutoff hand-off is an input.
      Without it D5 is unmeasured, which fails (ADR-0068).
    - **Check mode:** the same code on the last development window (19 Nov → 3 Dec, series at 3 Dec) must reproduce
      the development outputs: the trees, the S\*, U\* and G\* summaries and the outcomes. `--resume` reuses the
      trees, marks and series of an earlier check run; it is refused outside check mode, so the holdout always runs
      from the start.

12. **Minimum counts.**

    | Part | Minimum | Otherwise |
    | --- | --- | --- |
    | Rebuilt drift | a print within 1 s at t0 and at t1 | the frozen drift |
    | Rebuilt spread | 20 one-minute pairs (2 prints each) that day | the frozen half-spread |
    | Rebuilt impact | 30 taker orders with x > 0 that day | y = 1.0 |
    | C's spread | 20 pairs in the trailing 14 days | the frozen estimate |
    | C's drift table | 30 measured orders per cell (rule 4) | the cell's fallbacks, as in every run |
    | C's impact | 30 orders in the trailing 14 days plus C's own | y = 1.0 |
    | O2 bound | per bucket, every filled development trigger leg | the largest bound for an unknown bucket |

## Consequences
- **The frozen set grows** by the four modules, ADRs 0098-0099 and the output tree `research/cost_runs` (it holds the
  frozen O2 bounds).
- **The same-day spread falls back often** (Context). The fallback rate is reported per part.
- **Two parts of the holdout path cannot run before the freeze:** the trees' branch past 3 Dec in
  `run_sensitivities`, and `leader.compute` past the last configured origin. Each is exercised on development data
  (check mode, and a run with the origins truncated), not on its holdout bound.
- **The cutoff selection has no entry point.** D5 and the G\* rerun take its hand-off as an input.
- **Tests:** `tests/test_cost_runs.py` (the draw, the tape lookup, the impact fit, O2, the engine hooks leaving run A
  unchanged, the guard on the entry point).
