# ADR-0073: Copyability: an ex-ante tradable universe, leader-level exclusion, the cap on the full book; hold band as a diagnostic

- Status: Accepted (placeholders); fixed before any rerun under it
- Date: 2026-11-23
- Phase: Phase 4 v2, stage S3 (binding), and the replay (`replay_cap`)
- Supersedes: ADR-A0136 (the coin filter's definition) and ADR-A0140 (execution on kept coins with the cap re-solved on
  them); amends ADR-A0130 (`sel_copyable_notional` → `sel_tradable_share`; `sel_hold_band` demoted to a diagnostic)
- Source: `decision/phase-4-v2-methodology.md` section 4 (amendment A3)

## Context
**Finding 6: the coin filter selected on leaders' past profit per coin.** At 3 Dec:
- 45 of the 125 dropped coins were dropped because the zero-cost benchmark lost money, and 50 because it made under
  500 USDC;
- BTC, ETH and HYPE were kept by fiat with capture 0.08-0.11;
- ZEC flickered around the 0.5 threshold.

**Finding 5:** `rule_a` and `rule_b_coin_filter` select the same addresses at every origin. The rule_b "gain" was the
filter's effect on the same copies.

**Finding 7:** removing excluded legs and re-solving the 1.5x cap on the kept coins makes kept legs larger and can drop
hedges. The copied book is then not the leader's.

**Finding 9:** `sel_hold_band` judges an address by its band's pooled average. Passing address-windows averaged +0.3%
against +1.6% for failing ones.

## Decision
1. **Two universes:**
   - the research benchmark universe (BTC, ETH, HYPE, SOL), for comparisons and factors;
   - the **tradable universe**, the coins the copy may trade.

   Being on the benchmark list gives no trading exemption.
2. **Tradable universe**, computed at each origin from training data before it (all A/B), at the provisional 10k
   sleeve (ADR-0070):

   | # | Condition | Threshold (PLACEHOLDER) |
   | --- | --- | --- |
   | T1 Priced | passes the point-in-time price check (ADR-0044) and has a drift source (aggTrades or the ADR-0061 split-order floor) | pass |
   | T2 Valued | share of training notional-hours with a closing mark and known funding | ≥ 95% |
   | T3 Liquid at our size | share of training orders, at the 10k sleeve, that fit under the 0.5% participation limit without clipping | ≥ 95% |
   | T4 Affordable | base implementation shortfall per side (half-spread + impact + delay drift + fee), bps of traded notional, pooled over wallets; **leave-one-wallet-out** when used to evaluate a wallet | median ≤ 25 bps |
   | T5 Enough wallets | effective number of wallets in the coin's training notional, 1 / HHI | ≥ 5 |

   - **No PnL or capture condition.** Capture stays a reported diagnostic per coin, with per-wallet medians.
   - The inputs come from the unfiltered frozen replay's training window.
   - Every published coin set carries its coverage columns (pre-holdout Check 1).
3. **Applying it to a leader:**
   - **`sel_tradable_share`** (replaces `sel_copyable_notional`): the share of the leader's training notional-hours in
     non-tradable coins must be ≤ **10%**. Otherwise the leader is ineligible: we do not copy part of a book.
   - For eligible leaders, excluded legs get target 0 with status `not_tradable`. **The 1.5x cap scale is solved on
     the leader's full book**, so the kept legs stay exactly proportional. In code, `replay_cap.cap_legs` computes the
     scale over every coin, then zeroes the excluded legs.
   - **`sel_direction`:** the holdings-based net beta of the copied book against the full book (ADR-0071 betas). If
     `|Δβ| > 0.25` (PLACEHOLDER), the leader is ineligible.
4. **Other S3 gates:**
   - `sel_equity_band` [5k, 2M]: unchanged, against the 10k sleeve;
   - `sel_break_even`: unchanged;
   - `sel_copier`: unchanged, with "weaker member" = the lower evidence category, then the lower posterior mean
     (ADR-0072);
   - **`sel_hold_band`: a diagnostic only.** The band's pooled average is reported beside the address's own simulated
     copy, which decides.
5. **The coin policy is evaluated as an execution policy:** the same addresses' copies on the tradable universe
   against all priced coins. This is reported and never used for selection.

### Carried over from ADR-A0130 (archived): the S3 gates that stay unchanged
These definitions were first set in ADR-A0130, which is otherwise superseded. They remain in force exactly as below:
- **`sel_equity_band`:** the leader's median equity is in **[5,000, 2,000,000] USDC**. This is the user's choice
  (2026-11-22), made from the capital before any test outcome. Under no scale-up (ADR-0037) a leader can absorb capital
  only up to its own equity. The plan proposed 20k.
- **`sel_break_even`:** the training-window break-even delay exceeds the base delay (1.2 s). The status must be
  `positive_through_grid`, or `crossing_bracket` with the last positive delay at least 1,200 ms.
- **`sel_copier`:** the address is not the weaker member of a confirmed copier cluster in the copier screen as of the
  origin. "Weaker" is defined in item 4 above.
- `sel_copyable_notional` and `sel_hold_band` (ADR-A0130 items 3-4) are replaced by `sel_tradable_share` and demoted to
  a diagnostic respectively (items 3-4 above). `sel_history` moved to Phase 2 (`gate_history`, ADR-0067).

## Consequences
- **Replay:** the replay is rerun for all A/B over the nine windows as `research/replay_tradable/`.
- **Tests:**
  - an excluded coin is never traded;
  - the cap scale equals the unfiltered scale;
  - leave-one-wallet-out is reproducible;
  - two runs are byte-identical.
- **Niche-coin specialists** become ineligible through T5 and the 10% share. That is consistent with "no credit for
  missing evidence", and stated.
- **`|Δβ|`** will rarely bind once the excluded share is at most 10%. It stays as a guard.
