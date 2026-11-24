# ADR-0080: An exposed day needs a gross of at least the replay's 10 USDC minimum order; dust residuals are not exposure

- Status: Accepted; kept by the user on 2026-11-23; item 1's `G` amended by ADR-0082. **Decided after seeing results** (the first P4-3/P4-4 run, trial log 2026-11-23); written before
  the rerun under it
- Date: 2026-11-23
- Phase: Phase 4 v2, P4-3 to P4-7 (amends ADR-0070 item 5 and ADR-0071's "a day with G = 0")
- Protocol of ADR-0070: applied at all five origins, logged, never reverted on the address or return it produces

## Context
ADR-0070 counts a day as exposed when the copy's start-of-day gross `G_t > 0`. The first run of P4-3/P4-4 under it
gave DerSimonian-Laird τ² of 7e-4 (a standard deviation of about 270 bps per day) and Q in the millions at 22 Oct -
3 Dec. The cause is a measurement defect, not a skill dispersion:

- **Dust residuals count as exposure.** When a close is clipped by the participation or leader-batch budget, the copy
  can keep a remainder below the replay's 10 USDC minimum order (`replay.min_notional_usdc`), which nothing trades
  until the leader's next order in the coin (pre-holdout Check 5). Example, 19 Nov: 0x9bc5cf holds -0.000076 LINK
  (about 0.002 USDC) for 63 days; its only real exposure is one BTC trade over 2 days. It is "measured" on 62 exposed
  days in 10 weeks.
- **A dust day carries a whole trade.** A day that starts with dust and opens a position counts the trade's PnL and
  costs against the dust gross: the smallest α in the run was -24,053 bps per day.
- **The clustered standard error collapses** when almost all gross sits in one week (`d_t = U_t - α G_t ≈ 0` in
  every week), so such a record gets a weight 20 times the next largest and decides τ².

Across origins, 31-91 measured addresses have at least one dust day, and 16-23 per origin are measured only through
dust days.

## Decision
1. **Exposed day:** a valid day with `G_t ≥ 10 USDC` (`selection_v2.min_exposure_usdc`, set equal to
   `replay.min_notional_usdc`: a position the copy could not trade is not a position it holds by choice). A day below
   it is treated as flat: it enters neither sum of α, does not count for measurability, and its PnL is reported in
   `pnl_flat_days`.
2. The same definition applies everywhere "exposed" is used: measurability, α and its standard error, robustness,
   the bootstrap, the static replica, utilisation is unchanged (it counts every valid day's gross), "both exposed"
   in co-movement, and the outcome α of the test windows.
3. The threshold is the replay's existing execution minimum. It was not chosen by looking at any address's α or
   category, and no other value was tried.
4. Nothing else changes: DerSimonian-Laird, the prior, the categories and every threshold stay as ADRs 0072 and
   0078 define them. If τ² is still dominated by a few very precise records after this, that is reported, not
   corrected.

## Consequences
- The first run's outputs are replaced; its τ² and Q are kept in the trial log.
- Tests: a dust-only record is unmeasured; a day starting with dust carries no weight in α.
