# ADR-0083: Report α excluding funding beside α, and label funding-carry books; no carry factor

- Status: Accepted (the user's decision, 2026-11-23); reporting only, written before it was computed; **amended by ADR-0084**: α now excludes funding (binding); α including funding is reported, and the carry label uses it
- Date: 2026-11-23
- Phase: Phase 4 v2, P4-3 (statistic set) and P4-8 (hand-off columns)
- Relates to: ADR-0071 (the residual has no funding or carry factor), ADR-0072 (categories, unchanged)

## Context
After ADR-0080 every E2 address is a short BTC/ETH copy whose α of about 1-3 bps per day is funding received. BTC and
ETH carry identity betas, so the residual of such a book is funding plus costs, with a standard error of a fraction
of a basis point. A carry factor in the residual would be one more post-hoc rule change; the user declined it while
it does not touch the hand-off (no E2 passes S2).

## Decision
1. **Funding PnL** `F_t` = the copy's funding payments posted on day t (already inside `PnL_t` and `U_t`).
2. **Reported beside α** (same valid exposed days and `G_t`, ADR-0082):
   - `alpha_funding = Σ F_t / Σ G_t`;
   - `alpha_ex_funding = Σ (U_t - F_t) / Σ G_t`, with its standard error by ADR-0077 item 7 (`s_ex_funding`).
3. **Carry book** (a description, not a gate): `carry_book = α > 0 and alpha_funding ≥ α / 2`, that is, at least half
   of a positive α is funding. The results describe such addresses as carry books.
4. **Nothing binding changes:** α, the posterior, robustness and the categories stay as ADRs 0071, 0072 define them.
   The new columns are in `statistics.parquet`, `evidence.parquet` and the hand-off (`eligible.parquet`).
