# ADR-0078: P4-4 and P4-5 details: the DerSimonian-Laird pool, the degenerate posterior, robustness variants, the bootstrap draw, the outcome α and the IC rule's arithmetic

- Status: Accepted (placeholders); written before any τ², posterior, category or IC was computed
- Date: 2026-11-23
- Phase: Phase 4 v2, steps P4-4 (stage S5) and P4-5 (stage S6)
- Pins details ADRs 0072 and 0075 leave open. Protocol of ADR-0070

## Decision
1. **The pool for τ² and Q:** every A/B address of the origin's universe that is measured (ADR-0070 item 5) with a
   positive standard error `s` (ADR-0077 item 7), whatever its S2/S3 status: ADR-0072 item 2 says "every A/B
   address with a measured α". Q's p-value is the χ² survival with k - 1 degrees of freedom. Since τ² = 0 implies
   Q ≤ k - 1, "robustly 0" coincides with τ² = 0 in practice; both conditions are still checked.
2. **Prior groups:** the ADR-0072 behaviour clusters at the origin (`selection.behaviour_clusters`), used only when
   τ² > 0 and every cluster has at least 30 measured addresses and no measured address is unclustered; each group
   then gets its own DerSimonian-Laird τ² and μ0. Otherwise one pool.
3. **Degenerate posterior.** With τ² = 0 the posterior is a point mass at μ0 ≤ 0 (w* = 0, v = 0): `P(α > 0)` is 1
   if m > 0 and 0 otherwise, so it is 0. Unmeasured addresses (E0) get no posterior.
4. **Robustness, on valid exposed days** (ADR-0077):
   - best week = the calendar week with the largest Σ U (the earliest on ties); "without" removes all its days
     from both sums; it needs a positive remaining Σ G, otherwise the check fails (a one-week record fails);
   - own-data `P(α > 0)` without the best week = Φ(α_ex / s_ex), with s_ex by ADR-0077 item 7 on the remaining
     weeks (null under 2 weeks);
   - without 10-11 Oct: those days removed from both sums; without the best 3 weeks: the three largest-Σ U weeks;
   - without the best trip: `(Σ U - PnL of the largest-PnL copy trip opened and closed inside the window) / Σ G`.
     The trip's market component is not separated (stated; reported only);
   - best-week share = best week's Σ U / Σ over weeks (when positive); top-5 trip share = the five largest positive
     trip PnLs / all positive trip PnL.
5. **Bootstrap check:** over the common window's D calendar days, each draw concatenates ⌈D/7⌉ blocks of 7
   consecutive days with starts uniform on [0, D - 7], truncated to D days; the same draw serves every address
   (non-exposed or invalid days carry U = G = 0). α* = Σ U* / Σ G*; a draw with Σ G* = 0 is dropped for that address
   and counted. Generator `numpy.random.default_rng([20251203, origin ordinal, block length])`, 2,000 draws.
   Reported: SE, 20th percentile, share of α* > 0, and SE / s. Blocks of 5 and 10 days only when τ² > 0.
6. **Categories** exactly as ADR-0072 item 5, at the 0.80 level of `selection_v2.evidence.category_conf`.
7. **Outcome α for the IC** (P4-5): the next 14-day test window of the tradable replay at each development origin
   (flat start), base scenario, the **origin's** betas and ALT membership, same definition (ADR-0077). An outcome is
   defined when Σ G > 0 over its valid exposed days; there is no minimum day count (14 days cannot meet 20).
8. **IC arithmetic:** Spearman on average ranks across every address with both values (m from evidence, next α
   defined). If m is constant (τ² = 0) the IC is **undefined**: it counts as **0 in the mean** and as not positive.
   Ordering is used only if the mean IC over the four development origins is ≥ 0.05 and the IC is positive at ≥ 3
   of them (ADR-0075).
9. **Reported beside it:** the same IC for the unshrunk α (measured addresses), the information ratio, the
   t-statistic, the former NAV key (`selection.nav_keys`, ADR-A0051 definition) and trip key
   (`selection.address_keys`, ADR-A0131), both recomputed on the tradable training window; and the top-quintile hit
   rate: the share of the top ⌈20%⌉ by the key (ties by address) whose next α exceeds the median next α of the same
   population.
   The two former keys, kept only for this comparison (their ADRs, A0051 and A0131, are archived):
   - **NAV key:** the 20th percentile of 2,000 bootstrap means of the copy's daily NAV return (base scenario, from
     the first exposed day to the day before the origin, flat days counted as 0), resampling whole calendar weeks;
     unmeasured below 20 valid days or 4 weeks.
   - **Trip key:** the 20th percentile of 2,000 bootstrap trip-weighted means of completed follower round-trip net
     returns, resampling the calendar weeks in which trips opened; unmeasured below 10 trips or 4 weeks.
   - Both use the seed `[20251008, address prefix, origin ordinal]`.
10. **Placebo and extra block lengths** only if τ² is not robustly 0 at the origin and E2 addresses exist there;
    otherwise they are recorded as skipped.
11. **Outputs:** `evidence.parquet` per origin; `research/selection_v2/tau2.csv`;
    `research/selection_v2/ranking_validation.csv` with the decision rows.
12. **Tests:** equal true α (synthetic, heterogeneous s) gives τ² ≈ 0 and no E2; a dispersed synthetic gives
    τ² > 0; a one-week record fails robustness; the bootstrap is reproducible with the fixed seed and the same draw
    for every address; the degenerate posterior gives P = 0; an undefined IC counts as 0.
