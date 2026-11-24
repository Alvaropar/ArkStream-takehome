# ADR-0082: Gross exposure-time is the larger of the start-of-day and end-of-day gross; a day is exposed when it is at least 10 USDC

- Status: Accepted (the user's decision, 2026-11-23); written before any rerun under it
- Date: 2026-11-23
- Phase: Phase 4 v2, P4-3 to P4-5 (and everything downstream that reads the categories: P4-6 to P4-8)
- Amends: ADR-0070 items 3-5 and ADR-0071 item 1 (`G_t` = notional at the start-of-day mark), ADR-0077 items 1 and 3
  (the flat-day consequence), ADR-0080 item 1 (the 10 USDC threshold now applies to this `G_t`)
- **Decided after seeing results**, as a definitional fix: the protocol of ADR-0070 applies (written before
  computing, applied at all five origins, logged, never reverted on the address or return it produces). The user
  accepted in advance that it may move 0x2cd9's α and robustness either way.

## Context
Under ADR-0070/0071, `G_t` is the gross at the start-of-day mark, and a day with `G_t` below the threshold enters
neither sum of α (ADR-0077 item 3, ADR-0080). A day that opens a position from flat therefore drops its whole PnL,
including the entry's spread, impact and fee, while a day that starts exposed keeps its exit costs. The statistic is
asymmetric in costs, which favours copies that often enter from flat. ADR-0077 reported this as `pnl_flat_days`; the
user decided to fix it.

## Decision
1. **Gross exposure-time:** `G_t = max(G^start_t, G^end_t)`, with `G^start_t = Σ_c |e_{c,t}|` (positions held through
   boundary t at mark(t), as before) and `G^end_t = Σ_c |H_{c,t}|` (positions held through boundary t + 1 at
   mark(t + 1)).
2. **Exposed day:** a valid day (ADR-0077 item 2) with `G_t ≥ 10 USDC` (ADR-0080's threshold, unchanged). So a day
   that opens from flat and ends with a position counts, with its entry costs; a day that starts exposed counts, with
   its exit costs; a day below 10 USDC at both ends stays flat (dust, ADR-0080).
3. **Everything that uses `G_t` or "exposed" uses this definition:** measurability (20 exposed days in 4 weeks), α and
   its standard error, robustness, the bootstrap, the static replica (it allocates `G_t`), utilisation `ū = mean G_t
   / A` (so Phase 5's `m · ū · A` matches α's denominator), the copy betas' denominator, "both exposed" in
   co-movement, the placebo, and the outcome α of the test windows.
4. **Unchanged:** the residual `U_t = PnL_t - Σ_c e_{c,t} Σ_f β_{c,f} r_{f,t}` still removes the market component
   of the **start-of-day** positions. Stated consequence: on a day that opens from flat, the market move between the
   fill and the day's close stays in `U_t`; an intraday position's market move was never removed under ADR-0071
   either.
5. **Not rerun:** the replays and P4-2 (coin sets, leader shares) do not depend on `G_t`. P4-3 to P4-5 are recomputed,
   and P4-6 to P4-8 with them because they read the categories.
6. **Tests:** a day that opens from flat and ends at 1,000 USDC is exposed and carries its entry costs; a day below
   10 USDC at both ends is not; `G_t` is the larger of the two grosses.
