# Brief: fixes before Phase 4 (from the external review)

Written 2026-11-20. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot, take-home).
ADR numbers reserved for this session: **0110-0129**. The main session will not edit the project while this runs.
A separate Hyperliquid latency session may run at the same time: do not touch `src/arkstream_fetch/hl_ws_latency.py`,
`src/arkstream/latency.py`, `data/reference/latency/` or `research/latency/`.

## Why

An external review of the repository (validated by the main session on 2026-11-20) found three real methodological
problems and several smaller ones that must be fixed before addresses are selected (Phase 4). Everything below has
been checked against the code and data; do not re-litigate the findings, fix them.

| Finding | Validated evidence |
| --- | --- |
| **Sizing denominator differs from the plan.** The plan (section "Sizing and portfolio construction") freezes each leader's reference equity `E_ref` between reviewed rebalances; the replay divides by the latest snapshot equity. | `src/arkstream/replay_orders.py:342`, `src/arkstream/replay_cap.py:136,144`, ADR-0081 |
| **Price-check look-ahead.** The pre-registered Binance-vs-Hyperliquid price check (ADR-0012/0013) is computed once over all bars to the cutoff and applied at every origin. Rerun with only bars known at each origin, 2-14 coins classify differently, worth 0.02-0.98% of the next window's notional. | `research/hyperliquid/price_check.csv` used by `replay_orders.order_inputs`, `replay_market.vintages`, `leader.py`, `leader_worstcase` |
| **One-cent source switch.** ADR-0065 moves an address's whole return series to the rebuilt book after a single snapshot with abs(pnl - (equity - net_deposit)) > 0.01 USDC. | `src/arkstream/leader_assets.py:28` |
| Cost headroom is thin and rests on placeholders (impact Y = 1, participation 0.5%, cap 1.5x). | `decision/phase-3-sensitivity-results.md` |
| Drift for the ~159 coins without aggTrades below 300 s is a pooled four-coin proxy (optimistic for thin coins). | ADR-0080 |
| The 8 Oct stress result is 65.3% unpriced (the crash sample did not exist yet) but is reported as a number. | `research/replay/economic_screen.csv` |
| ADL and liquidation fills are included in drift estimation and in the leader-sweep anchor. They are forced fills, not signals. (The replay correctly mirrors them as position reductions; keep that.) | `drift.leader_orders`, `replay_orders.sweep_anchor`, `replay_size` |
| A clean copy cannot reproduce the work: the kline lake was built by an external tool (qh_data), and large inputs and outputs are not shipped. | `data/lake`, `research/replay` (7.2 GB), `data/reference/binance/aggtrades` (7.2 GB) |

## Scope, in this order

**A. Inputs (no long runs yet)**

1. **Point-in-time price check.** For each origin, apply the unchanged ADR-0012 rule (`hlprices.price_check`,
   thresholds in `config/decision_context.yaml: funding.price_check`) to the bars in
   `research/hyperliquid/price_check_bars.parquet` whose close is at or before the origin. Write
   `research/hyperliquid/price_check_by_origin.csv` (origin, coin, outcome, stats). Every consumer uses the
   classification as of its origin: the replay's training window at origin o and its test window [o, next origin)
   use the origin-o classification; drift vintages use the classification as of each vintage; Phase 2 validation
   flags, intraday marks and the worst-case Binance check use the origin's list. `insufficient` (fewer than 30
   bars) counts as not passing (no intraday price, not copied). Report, per origin, which coins change status and
   the orders and notional that moves.
2. **Materiality rule for the return source (amends ADR-0065).** The rebuilt book becomes an address's primary
   series only when reconciliation breaches known by the origin are material and persistent. Default
   (PLACEHOLDER, fix it in the ADR before looking at any return or gate outcome): a breach is
   abs(pnl - (equity - net_deposit)) > max(10 USDC, 0.5% of equity); the book is primary when at least 5% of the
   address's snapshots known by the origin breach, or 3 consecutive snapshots do. Otherwise the snapshot series
   stays primary and breaching intervals are excluded with a reason. Keep reporting both series for every
   address. Report how many addresses switch at each origin under the old and new rule.
3. **Special events.** Exclude fills with `dir` in Auto-Deleveraging, Liquidated* and Settlement from drift
   estimation (`drift.leader_orders`), from the sweep anchor and from the leader-size study. Keep mirroring them as
   position reductions in the replay. Report the counts excluded.
4. **Excluded-coin exposure per address.** Add to the Phase 2 evidence table each address's share of notional (to
   the origin) in coins not passing the price check at that origin and in HIP-3. Report it; do not add a gate.

Then rerun, in order: `python -m arkstream drift`, `python -m arkstream leader`, and record the changes in counts
(A/B, gate-passers per origin, return sources) against the current outputs.

**B. Replay changes**

5. **Conservative alt drift.** For parameterised coins below 300 s, base uses max(four-coin proxy, the coin's own
   300 s estimate, 0); stress keeps its current rule; optimistic keeps the proxy. Report each address's share of
   copied notional on parameterised coins.
6. **Stress coverage.** A stress result whose priced share of intents is below 80% (PLACEHOLDER) is reported as
   `unmeasured`, not as a return, and is never counted as positive or negative.
7. **Frozen-equity sizing variant.** Implement `E_ref`: the leader's latest usable cross-margin snapshot equity at
   each review, with reviews at the start of every window and every 14 days after it (UTC midnight); fixed between
   reviews. Copy multiplier = min(allocation / E_ref, 1) (no scale-up, ADR-0043). An unusable equity at a review
   means reduce-only until the next usable review. Everything else is the current full stack (square-root impact,
   1.5x cap, 0.5% participation, no scale-up, leader-sweep anchor, the new alt drift, the point-in-time price check).
   Run frozen and dynamic side by side on the nine windows and compare, per address and pooled: target exposure,
   gross and leverage, turnover, orders and skips, copy return, drawdown, stress, and the cases where they differ
   most (large deposits or withdrawals, falling leader equity, small leaders).

**STOP after item 7.** Report the comparison with a recommendation (the main session recommends frozen `E_ref`,
the plan's policy) and wait for the user to choose. The chosen policy is used unchanged in selection, the portfolio
replay and operations; record it in an ADR.

**C. After the user chooses**

8. **Cost uncertainty surface** on the chosen policy, base scenario, test windows only, gate-passers (all gates,
   including the worst-case gate). One-at-a-time around the current values plus the two corners: impact Y in
   {0.5, 1, 2}, participation in {0.25%, 0.5%, 1%, none}, cap in {1.0x, 1.5x, 2.0x}, and the most and least
   favourable combination. Per point: mean funded return, positives, profit, extra cost per side that would absorb
   it. Report the lower bound (the least favourable point), not only the central value. Skip the delay grid and the
   training windows for this surface. Give a runtime estimate before launching anything expected to take more than
   an hour.
9. **Reproducibility from a clean copy.**
   - Python 3.12 is already pinned (`.python-version`, `requires-python`); make the README state it and the `uv
     sync` step.
   - Add a standalone Binance kline fetcher `src/arkstream_fetch/fetch_klines.py` (same rules as
     `fetch_aggtrades.py`: standard library, host allowlist, published checksums, resumable, manifest) and a path
     for `refprices` to build from its zips without the external lake, so the reference prices can be rebuilt from
     public data alone. Check that it reproduces `data/reference/prices/MANIFEST.yaml` byte for byte; report any
     difference.
   - `scripts/package_submission.py`: builds the submission zip with an explicit include list (code, config,
     tests, decision/, provenance/, the small verified inputs: `data/raw`, `data/reference/prices`,
     `data/reference/hyperliquid`, `data/reference/binance` without the aggTrades zips, `data/reference/latency`,
     and the small research summaries) and writes `MANIFEST.sha256` for everything inside. Large items (aggTrades,
     the kline lake, `research/replay`, `research/leader`) are regenerated by documented commands with expected
     checksums from `provenance/`.
   - A `VERIFY.md` with the exact commands, from a clean unzip, to: install, run the tests and audit, fetch
     public data, rebuild each phase, and compare checksums.
10. **Rerun and report.** Final reruns of drift, leader, replay (chosen policy, all scenarios, delay grid) and
    `make figures`; update `decision/phase-3-sensitivity-results.md` (or a new `decision/pre-phase-4-results.md`)
    with before/after tables for every item.

## Rules (project spec, verbatim where quoted)

- "Inputs (read-only; never modify)".
- "Point in time: every function that produces values takes an `asof` timestamp and uses only rows with
  timestamp <= asof". This batch exists to remove look-ahead: add a seeded-leak test for the price-check fix (an
  outcome computed with a bar after the origin must change the result and be caught).
- "Never invent missing inputs: no imputed prices, funding or quotes. Missing -> flag and exclude, with a reason".
- "Determinism: same inputs give byte-identical outputs": two reruns of each changed command must match.
- "Traceability: every derived row keeps the source keys (trader, tid, oid, timestamp)".
- "No code path that sends real orders, now or later, unless explicitly enabled." Network code only in
  `src/arkstream_fetch`.
- **Never compute the holdout test window (2025-12-03..2026-01-04).** `frozen` stays false; selection does not
  start in this batch.
- Every threshold is fixed in an ADR **before** looking at the outcome it affects, and marked PLACEHOLDER. Every
  trial goes in `provenance/trial_log.md`, including the ones that make results worse.
- Record decisions as ADRs in `decision/adr/` (numbers 0110-0129; update the index rows for yours; mark amended
  ADRs as amended).

## Done when

- Items 1-7 done and reported; the user's policy choice recorded; items 8-10 done.
- `uv run ruff check src tests scripts`, `uv run mypy src`, `uv run pytest -q` and `uv run python -m arkstream audit`
  pass; synthetic tests for each change (point-in-time price check with a seeded leak, the materiality rule,
  special-event exclusion, frozen `E_ref` with reviews and reduce-only, the alt drift bound, stress `unmeasured`).
- A results file with before/after tables for every item, the cost surface with its lower bound, and an honest
  statement of whether the base case still clears costs once look-ahead is removed.

---

## Prompt to start the session

> Read `decision/briefs/pre-phase-4-fixes.md` in `C:\Projects\quant-task-arkstream` and carry it out: the fixes an
> external review found before Phase 4 (point-in-time price check, a materiality rule for the return source,
> excluding forced fills from drift and the sweep anchor, conservative drift for alts, unmeasured stress at low
> coverage, a frozen-equity sizing variant compared with the current dynamic one, a cost uncertainty surface, and
> reproducibility from a clean copy). The findings are already validated; fix them, do not re-argue them. Before
> writing code, read `decision/adr/README.md` and ADRs 0012, 0013, 0043, 0045, 0065, 0080, 0081 and 0084-0088, the
> plan's sections "Sizing and portfolio construction" and "Follower replay" in
> `ArkStream Hyperliquid Pilot — Revised Research & Deployment Plan (v2).md`, `config/execution.yaml`,
> `config/decision_context.yaml`, and `src/arkstream/replay*.py`, `leader*.py`, `drift.py` and `hlprices.py`. Work
> in the brief's order and **stop after item 7** to report the frozen-versus-dynamic comparison so I can choose the
> sizing policy. Never compute the holdout test window (2025-12-03..2026-01-04) and do not start selection. Record
> decisions as ADRs numbered 0110-0129. Do not touch the latency session's files listed in the brief.
