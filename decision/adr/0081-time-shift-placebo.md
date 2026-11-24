# ADR-0081: The time-shift placebo for E2 copies: a holdings-level circular shift of the copy's exposure path, same coins, sizes and costs

- Status: Accepted; written before any placebo value was computed
- Date: 2026-11-23
- Phase: Phase 4 v2, P4-5 (ADR-0075 item 4)
- Pins the mechanics ADR-0075 item 4 leaves open, and corrects the trigger used in the first runs. Protocol of
  ADR-0070

## Context
ADR-0075 item 4: "only if τ² is not robustly 0 and E2 addresses exist: replay each E2 copy with the leader's fill
times shifted by a random 1-7 days (same coins, sizes and costs; seed [20251203, address prefix, origin], 20 shifts).
If the real copy's α does not beat the shifted copies' median, the leader adds nothing beyond exposure and costs."

After ADR-0080, τ² > 0 at all five origins and category E2 holds 6 / 3 / 8 / 8 / 8 A/B addresses. The first
implementation tested for E2 only among the hand-off rows (none), which is narrower than ADR-0075's "E2 addresses
exist". That is corrected here: the category is assigned to every A/B address, so the placebo runs for every E2
address. Two details are open: how a copy is "replayed" with shifted times while keeping "the same costs", and
where shifted exposure lands when it would cross the origin (which would read data after it).

## Decision
1. **Who:** every address in category E2 at an origin where τ² is not robustly 0 (ADR-0072), whatever its S1-S3
   status.
2. **Holdings-level shift (same coins, sizes and costs).** On the common training window (ADR-0070) and the copy's
   valid exposed days (ADRs 0077, 0080), split the residual PnL into
   - the holding part `H_t = Σ_c e_{c,t} ρ_{c,t}`, with `ρ_{c,t} = r_{c,t} - Σ_f β_{c,f} r_{f,t}` (the coin's
     residual return under the origin's betas), and
   - the rest `O_t = U_t - H_t`: execution costs, fees, funding and intraday trading.

   A shift of d days moves the start-of-day exposure path `e_{c,t}` to day `t + d`, **circularly inside the
   window's D calendar days**, so nothing after the origin is read and total exposure is unchanged. `G_t` and `O_t`
   stay on their own days. A coin-day whose shifted exposure meets a missing return contributes 0 and is counted.
   `α^(d) = (Σ_t Σ_c e^(d)_{c,t} ρ_{c,t} + Σ_t O_t) / Σ_t G_t`.
   - This keeps the copy's coins, sizes and costs exactly, as ADR-0075 requires; it does not re-simulate execution at
     the shifted times (a full replay would change the costs, which ADR-0075 holds fixed).
3. **Draws:** 20 shifts, d uniform on {1, ..., 7},
   `numpy.random.default_rng([20251203, int(address[2:10], 16), origin ordinal])`.
4. **Result, reported (not binding):** the real α, the median and the 20th / 80th percentiles of α^(d), the share of
   shifts below the real α, and `placebo_pass = α > median α^(d)`. ADR-0075 does not make the placebo a gate, so
   the category is unchanged; the report says which E2 copies "add nothing beyond exposure and costs".
5. **Output:** `research/selection_v2/placebo.csv`.
6. **Tests:** a copy whose exposure is constant gets α^(d) = α for every d; the draw is reproducible from the seed.
