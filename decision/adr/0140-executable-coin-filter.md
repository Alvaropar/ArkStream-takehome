# ADR-0140: The coin filter runs inside the frozen replay; the rule stays rule_b_coin_filter

- Status: Accepted. **Written before the filtered replay was run** (the user's instruction, 2026-11-22)
- Date: 2026-11-22
- Phase: Phase 4 (selection), before the holdout
- Amends: ADR-0136 (replaces its attribution approximation), ADR-0138 (the rule is unchanged; its numbers are
  rerun). Superseded freeze: ADR-0139 (a new freeze follows, ADR-0141)

## Context
ADR-0136 scored the coin filter by removing the dropped coins' PnL from the existing replay ledgers, so the 1.5x
address cap and its resize legs were still solved over every coin. The rule must be executable before the holdout.
Excluded coins must never be traded, and the cap must bind on the kept coins only.

## Decision
1. **The rule stays `rule_b_coin_filter`, whatever the rerun shows.** No new variant choice is made. rule_a and
   rule_c_p10 are not rerun, and the ADR-0137 comparison stays as recorded, on the attribution numbers it was made
   on.
2. **Coin set: unchanged definition (ADR-0136).** At each origin it is computed from the *unfiltered* frozen
   replay's training window ending at that origin (all A/B, base): BTC, ETH, HYPE, SOL, plus coins whose summed
   benchmark PnL is >= 500 USDC with follower capture >= 0.5. The filter has to be defined before the filtered copy
   exists, and it uses data up to the origin only. As with the price check (ADR-0110), the training window at an
   origin and the window starting at it use that origin's set.
3. **Executable filter** (`replay_coinfilter`, `replay_sensitivity.run_sensitivities(coin_sets=...)`):
   - In the window's price-check table, a coin that passes the price check but is not kept gets outcome
     `coin_filter`.
   - Every intent in it gets status `coin_filter_excluded`. It joins the excluded statuses: never submitted, never
     reserved, never filled.
   - The 1.5x address cap and the basket resize legs are solved over the leader's positions in kept coins only:
     `cap_legs` builds its book from the passing coins, which are now the kept ones.
   - ADR-0122 classes the status as a measured policy outcome. Capture (ADR-0162) counts it as `uncopyable_coin`.
   - The leader-side inputs (frozen-snapshot diagnosis, marks, funding, E_ref) keep the unfiltered price-check list:
     they describe the leader, not what we copy.
4. **Benchmark** (ADR-0162) under the filter: the same filtered plan at leader prices with zero delay and cost, on
   the kept coins only. Capture then measures how well we execute what the rule copies. The leader's PnL in
   excluded coins is outside both books.
5. **Every copy-series input of rule_b comes from the filtered tree** (`research/replay_coinfilter/`):
   - from the training windows: the key, the holding-band break-even table, the break-even-delay gate and
     co-movement;
   - from the development test windows: the outcomes, the random-k pools and equal weight (all A/B replayed under
     the filter), stress (ADR-0122 coverage and check), capture and market-relative.
   The Phase 2 gates and the other selection gates are unchanged.
6. **Holdout path, built now and frozen with the rule.** `replay_coinfilter.run(..., holdout=True)` replays one
   window: origin 3 Dec, from 3 Dec 2025 00:00 to 4 Jan 2026 00:00 UTC (32 daily returns; the plan's 32 days). It
   uses the same filter with the 3 Dec coin set. Inputs are frozen at the 3 Dec vintage: drift cells, spreads, the
   price check, holding bands and the 3 Dec E_ref review schedule. Data runs to that boundary; the last 24 hours
   before the cutoff have no closing daily mark and are not scored.
   - It runs only through `freeze.guard`.
   - It shares `run_sensitivities`'s single-window branch, which is checked by replaying the 19 Nov development test
     window through it and matching the full run byte for byte (no holdout data read).
   - After the freeze, item 8 may add only a reporting module outside the hashed set (`holdout_report.py`). It may
     read the holdout tree and call frozen functions; nothing that decides a trade or a return may change.
7. **Reporting.** The new numbers sit next to the ADR-0136 attribution ones: basket return, wins against both
   random-k baselines, stress check and capture.

## Consequences
The filtered replay is a full run of the frozen stack over all nine windows (about 17 minutes). The attribution
outputs stay as the record behind ADR-0137/0138. A new freeze (ADR-0141) hashes the filtered replay code, the
holdout path and the new 3 Dec shortlist. Tests: an excluded coin is never traded, the cap book contains only kept
coins, the benchmark respects the filter, and the single-window branch reproduces a development window.
