# ADR-0084: Funding is a separate source of return, not skill: alpha excludes the copy's funding PnL

- Status: Accepted; fixed before the rerun under it
- Date: 2026-11-23
- Phase: Phase 4 v2, stage S4 (measurement), binding through S5 (evidence and categories)
- Amends: ADR-0071 item 1 (the residual) and ADR-0083 (funding was reported beside α, never binding)
- **Decided after seeing results** (the user's decision, 2026-11-23). It follows a diagnostic run that moved funding
  out of the residual (trial log, "Funding removed from alpha"). Like every post-hoc change, it is applied at all
  five origins, logged, and not reverted on the address or return it produces.

## Context
Under ADR-0071 the residual `U = PnL - market` keeps the copy's funding payments. Copies that sat short BTC or ETH and
collected funding therefore showed a steady positive α. The static replica holds no funding, so all of it appeared
as "timing".

ADR-0083 measured this, beside α only:
- carry books were 5 of the 6 E2 addresses at 3 Dec;
- they dominated the DerSimonian-Laird τ² from 5 Nov onward.

Funding carry is a market premium that any account can earn by holding a perpetual position. It is not evidence that
the leader chooses or times positions well, which is what Phase 4 grades. The diagnostic, with funding taken out of
the residual, found:
- E2 15 / 11 / 6 / 8 / 6 → 11 / 8 / 0 / 0 / 0;
- τ² at 3 Dec robustly 0 (Q p = 0.69);
- hand-offs unchanged at every origin.

## Decision
1. **Residual:** `U_{i,t} = PnL_{i,t} - Σ_c e_{i,c,t} Σ_f β_{c,f} r_{f,t} - F_{i,t}`, where `F_{i,t}` is the copy's
   funding posted on day t. Config: `selection_v2.market.funding_in_alpha: false`.
2. **Everything built on `U` follows:**
   - α and its standard error;
   - the DerSimonian-Laird τ², the shrinkage and the categories;
   - the own-data robustness checks;
   - the static replica and the timing part;
   - the top-3 coin-day share;
   - the test-window outcome α used by the ranking validation and the calibration;
   - the placebo.
3. **Funding stays visible, never dropped:**
   - `alpha_funding = Σ F / Σ G`;
   - `alpha_incl_funding` with `s_incl_funding`, the former definition, reported;
   - `alpha_ex_funding` equals α.
4. **`carry_book`** is now measured on the total: `alpha_incl_funding > 0` and `alpha_funding ≥ alpha_incl_funding / 2`.
   It remains a description, not a gate.
5. **The copy's economics are unchanged.** NAV returns, drawdowns, stress, capture and the Phase 5 inputs still
   include funding, because the copy really pays and receives it. Only the *skill* statistic excludes it.

## Consequences
- **Rerun:** Phase 4 v2 at all five origins (P4-3 to P4-8; no replay rerun). `decision/phase-4-v2-results.md`, the
  3 Dec E1/E2 table and the funnel in `full_selection_criteria.md` are updated.
- **Tests:**
  - funding is excluded from U and α when the flag is off and included when it is on;
  - the carry label uses the total;
  - the hand-off schema gains `alpha_incl_funding` and `s_incl_funding`.
- **The expected outcome is "no measurable skill at 3 Dec".** That is stated, not corrected.
