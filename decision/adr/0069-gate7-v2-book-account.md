# ADR-0069: Gate 7 v2: rank agreement, a steady-gap rate and a one-for-one slope between account and rebuilt book

- Status: Accepted (placeholders); fixed before any rerun under it
- Date: 2026-11-23
- Phase: Phase 2 (leader evidence), data-integrity category (ADR-0067)
- Amends: ADR-0067 item 2 (gate 7 on the Pearson lower bound)
- Source: `decision/phase-4-v2-methodology.md` section 3 (revision 2, amendment A2)
- **Decided after seeing results.** 0x971f failed gate 7 at 5 Nov, 19 Nov and 3 Dec (Pearson 0.538 on 118
  intervals, lower bound 0.480). The rule is set on principle. Whether 0x971f passes is unknown until the rerun, and
  the result stands either way.

## Context
Gate 7 asks whether the book rebuilt from fills explains the account's returns, on timestamp-matched snapshot
intervals (`leader_book.intervals`). Under ADR-0067 it passes when the one-sided 80% Fisher-z lower bound of the
**Pearson** correlation of account return `r_start` and book return `book_r` is at least 0.5, and std(r_start - book_r)
≤ 0.02. That design has two flaws:
1. **A few large intervals decide Pearson.** Gate 6 already judges how often the book misses materially. Gate 7 lets
   the same large misses decide "agreement" again. The cross-check values the book at Binance 1m marks while the
   account is valued on Hyperliquid, so venue dislocations (10 Oct) are a plausible source of those intervals. That is
   checked in the rerun.
2. **Correlation cannot see bias.** A book that misses a steady PnL source (a hedge, an isolated position, activity
   outside the fills) passes as long as the variations line up.

## Decision
Over the usable fit intervals, with at least `leader.book.min_intervals` = 10 (otherwise unmeasured, which never
passes, ADR-0068), gate 7 passes only if all four checks hold:

| Check | Statistic | Pass if |
| --- | --- | --- |
| 7a Rank agreement | Spearman ρ of `r_start` vs `book_r`; one-sided 80% lower bound via Fisher z with the Bonett-Wright variance `(1 + ρ²/2) / (n - 3)` | lower bound ≥ 0.5 |
| 7b No steady gap | gap rate `ḡ = Σ (r_start - book_r) / Σ interval days` (multi-day intervals weighted by their days), with a standard error clustered by calendar week; one-sided 80% lower bound `|ḡ| - z₀.₈ · se` | lower bound ≤ **5 bps/day** |
| 7c One-for-one | Theil-Sen slope of `r_start` on `book_r` | in **[2/3, 3/2]** |
| 7d Tracking | std(r_start - book_r) | ≤ 0.02 (unchanged) |

1. **`xc_flag`** is the first failing check: `disagree_rank`, `disagree_gap`, `disagree_slope`, `disagree_tracking`.
   The existing `too_few_intervals` and `no_variation` stay.
2. **Why 7b is a rate.** A summed gap grows with the number of intervals, so a summed threshold would be stricter at
   later origins. 5 bps/day is about 18% a year unexplained.
   - The test fails an address only when the gap is *confidently* above the threshold. A +20 bps/day gap with 0.5%
     daily noise fails at both 30 and 120 intervals; +8 bps/day passes at both.
   - This gives noisy residuals the benefit of the doubt, a departure from gates 6 and 7a. It is accepted because an
     equivalence version (upper bound ≤ 5 bps/day) would fail almost every account for lack of precision, and because
     7a and 7d already require precise agreement.
3. **Reported, not binding:**
   - the Pearson correlation and its bound;
   - the OLS slope and intercept with 95% CIs, and nRMSE;
   - the number of intervals missing by more than 1%;
   - the lag-1 autocorrelation of the residual;
   - both 7b bounds;
   - the three largest residual intervals with their `src_row`.
4. **Config** (PLACEHOLDER): `leader.book.agreement: spearman`, `max_gap_bps_per_day: 5`, `gap_lower_conf: 0.80`,
   `slope_band: [0.667, 1.5]`. The 0.5 bound and the 80% level are unchanged. None of the thresholds was chosen by
   looking at any address's value.

## Result (P4-1, Phase 2 rerun at five origins, 2026-11-23)
`scripts/audit_gate_change.py phase2_before_adr0069 _adr0069` → `research/audit/gate_change*_adr0069.csv`.

| Origin | Gate 7 pass / fail / unmeasured, before → after | Pass → fail | Fail → pass | Failing checks after |
| --- | --- | ---: | ---: | --- |
| 8 Oct | 174 / 10 / 118 → 172 / 12 / 118 | 2 | 0 | gap 7, tracking 3, slope 2 |
| 22 Oct | 193 / 12 / 127 → 191 / 14 / 127 | 2 | 0 | gap 12, tracking 1, slope 1 |
| 5 Nov | 202 / 13 / 120 → 194 / 21 / 120 | 8 | 0 | gap 18, tracking 2, rank 1 |
| 19 Nov | 224 / 12 / 125 → 217 / 19 / 125 | 7 | 0 | gap 14, tracking 4, slope 1 |
| 3 Dec | 220 / 7 / 131 → 215 / 12 / 131 | 5 | 0 | gap 10, tracking 2 |

**All binding gates pass: unchanged at every origin** (22 / 19 / 25 / 25 / 23). Every new gate 7 failure also fails
another binding gate.

**0x971f.**
- Its rank agreement is close to perfect: Spearman 0.995, lower bound 0.994, against Pearson 0.538. That confirms the
  outlier hypothesis.
- The slope is 1.006 and the tracking std 0.011.
- It now fails **7b** from 5 Nov onward: a gap rate of +13.1 bps/day, standard error 9.1, lower bound **5.46** against
  a limit of 5.0. It passes at 8 Oct and 22 Oct.
- The whole gap is two intervals with recorded withdrawals: src_row 75852 (23 Oct, -728 USDC, residual +1,028 bps)
  and 75841 (12 Oct, -420 USDC, +582 bps). In each, the residual times equity equals the withdrawal: the flow is
  recorded in `net_deposit` without a matching equity fall inside the interval.
- Without them the rate is -0.04 bps/day, and the median residual is -0.03 bps.

7b, as written, uses the mean rate, which is sensitive to such intervals. Diagnostic only: without intervals with a
recorded flow, 0 / 1 / 3 / 2 / 2 of the 7 / 12 / 18 / 14 / 10 7b failures per origin would be within 5 bps/day. So most
7b failures are real. **The result stands as computed.** Any change to 7b's treatment of flow intervals would be
decided after seeing 0x971f's result, and is the user's decision.

## Consequences
- **Rerun:** Phase 2 at all five origins for every A/B address, then `scripts/audit_gate_change.py`. Every address that
  moves is published with its reasons. 0x971f's 7a-7d values and its largest residual intervals are reported.
- **Direction:** the change can pass some of the 7 that fail at 3 Dec, and can fail some of the 220 that pass through
  7b or 7c.
- **Tests:**
  - outliers in 3 of 100 intervals fail Pearson and pass Spearman;
  - a +20 bps/day gap with 0.5% noise fails 7b at 30 and 120 intervals;
  - a zero-mean residual passes 7b at any length;
  - multi-day intervals are weighted by days;
  - a hidden 50% hedge fails 7c;
  - fewer than 10 intervals is unmeasured.
- **Limitation:** valuing the cross-check book at Hyperliquid prices would remove the venue mismatch, but the repo
  has only daily and 4h Hyperliquid marks, not 1m.
