# Phase 4 v2: development results (steps P4-2 to P4-8)

Written 2026-11-23. Revised the same day twice:
- after the user's review (ADRs 0082 and 0083);
- after the user adopted **funding out of alpha (ADR-0084)**.

**Every number below is under ADR-0084** unless marked "before ADR-0084".

- **Methodology:** [phase-4-v2-methodology.md](phase-4-v2-methodology.md) (revision 2).
- **Decisions:** ADRs [0070](adr/0070-phase4-v2-structure-series.md)-[0075](adr/0075-ranking-validation-evaluation.md).
  The open details were pinned before computing in ADRs [0076](adr/0076-p4-2-tradable-measurement.md)-[0079](adr/0079-p4-6-to-p4-8-comovement-evaluation-handoff.md)
  and [0081](adr/0081-time-shift-placebo.md).
- **Post-hoc changes:** [ADR-0080](adr/0080-exposure-materiality-dust.md) (dust is not exposure; kept by the user) and
  [ADR-0082](adr/0082-gross-max-start-end.md) (gross = the larger of the start-of-day and end-of-day gross; the user's
  flat-day fix).
- **Binding since the second revision:** [ADR-0084](adr/0084-funding-out-of-alpha.md), the user's decision after a
  diagnostic. The residual, and therefore α, excludes the copy's funding: funding carry is a premium, not leader skill.
  [ADR-0083](adr/0083-alpha-ex-funding-carry-books.md)'s columns remain: α including funding and the funding part are
  reported, and the carry label is measured on the total.
- **Gate 7b is unchanged** (the user's decision).

Scope and checks:
- **Development data only.** The holdout (3 Dec 2025 - 4 Jan 2026) was never computed: the 3 Dec origin reads only its
  training window, and the four test windows end at 3 Dec. The freeze is void and stays void; no
  `HOLDOUT_FREEZE.txt` was written.
- **S2 uses gate 7 v2.** The trial log has the "ADR-0069 gate 7 v2 rerun" entry (P4-1), so the hand-off was built.
- **Reproducible.** Both v2 replays and `select-v2` are byte-identical on a second independent run
  (POLARS_MAX_THREADS=8): 266/266 and 72/72 files.

## Headline

1. **At 3 Dec, τ² is robustly 0.** Without funding, the copies show no measurable differences in skill at the final
   origin.
   - τ² = 0, and Cochran's Q does not reject homogeneity (p = 0.69).
   - Under ADR-0072 nobody can reach E2. Every posterior equals the prior (μ0 = 0, posterior sd 0).
   - `p_post` therefore reads 0.0 for every address at 3 Dec. That is a degenerate value: P(α > 0) is undefined with
     zero posterior spread. It is not a new finding.
2. **τ² is small but not zero at the earlier origins.** The between-address sd of true α is 8.5 / 8.8 / 1.6 / 2.0 /
   0 bps per day of gross, against a median own standard error of 21-32 bps/day.
3. **E2 exists only at 8 Oct and 22 Oct (11 and 8 addresses), and none is a carry book.**
   - From 5 Nov there is **no E2 at any origin**.
   - Before ADR-0084, every E2 from 5 Nov onward was a carry book (short BTC/ETH copies collecting funding).
4. **One E2 reaches the hand-off: 0x971f at 8 Oct** (α 100.9 bps/day, s 18.1, P(α > 0) 0.99, robust; placebo
   passed). It is E1 at 22 Oct, and it fails gate 7 v2 (S2) from 5 Nov.
5. **The hand-off is 3 / 2 / 1 / 1 / 1 addresses, unchanged by ADR-0084.** Every row except 0x971f at 8 Oct is E1, a
   shadow-only candidate. **At 3 Dec it is 0x2cd9 alone, E1**:
   - α 26.7 bps/day (s 61.9); 23.7 including funding, because it *pays* funding;
   - it still fails the robustness check: -8.7 bps/day without its best week.
6. **Ordering is not used.** IC of the posterior mean with the next window: +0.098 / -0.029 / -0.038 / -0.150 (mean
   -0.030, positive at 1 of 4).
7. **Qualification does not show value on the development windows.**
   - The E1 ∪ E2 hand-off beats same-size random draws in 2 of 4 windows on α, and 1 of 4 on raw return.
   - The categories are not ordered by next-window α at any origin, or pooled.

**Result:** no address shows capital-grade evidence of skill that persists into the next window, and at 3 Dec there is
no measurable skill dispersion at all. The decision path is a shadow scheme (or a CONDITIONAL GO) in Phase 5, never
looser thresholds.

## ADR-0084: funding out of alpha (second revision) and what moved

- **What changed.** The residual is now `U = PnL - market - funding`. Everything built on `U` follows: α, its SE, τ²,
  the shrinkage, the categories, robustness, the static/timing split, the test-window outcome α and the placebo.
- **What did not change:** the NAV return, drawdowns, stress, capture and the Phase 5 inputs keep funding.
- **Replays and coin sets are unchanged.** Only P4-3 to P4-8 were rerun.
- **Determinism:** two independent runs were byte-identical (72/72 files). The pre-ADR-0084 outputs are kept in
  `research/audit/selection_v2_before_adr0084/`.

| | 8 Oct | 22 Oct | 5 Nov | 19 Nov | 3 Dec |
| --- | --- | --- | --- | --- | --- |
| τ² (sd, bps/day), before → after | 9.1 → 8.5 | 9.9 → 8.8 | 2.9 → 1.6 | 2.6 → 2.0 | 1.3 → **0** |
| Q p-value | 2e-28 → 1e-25 | 6e-7 → 7e-5 | 0.017 → 0.24 | 4e-4 → 0.012 | 0.15 → **0.69 (robustly 0)** |
| E2 | 15 → 11 | 11 → 8 | 6 → **0** | 8 → **0** | 6 → **0** |
| carry books among E2 | 3 → 0 | 1 → 0 | 5 → 0 | 6 → 0 | 5 → 0 |
| hand-off | 3 → 3 | 2 → 2 | 1 → 1 | 1 → 1 | 1 → 1 |

Category moves: 56 of 1,688 address-origins (mostly E2 → E1 and E1 → E-).

## The first revision (ADRs 0082, 0083), before ADR-0084

- **ADR-0082 (flat days).** `G_t = max(start-of-day gross, end-of-day gross)`, and a day is exposed when `G_t ≥ 10`
  USDC.
  - A day that opens from flat now counts with its entry costs, as a day that starts exposed always counted its exit
    costs.
  - The residual still removes the market component of start-of-day positions (ADR-0082 item 4).
  - P4-3 to P4-8 were recomputed; the replays and P4-2 are unchanged.
- **ADR-0083 (carry).** `alpha_ex_funding` and `alpha_funding` are reported beside α, and `carry_book` is set when a
  positive α is at least half funding. Nothing binding changed, and no carry factor was added.

Movement (previous run → the first revision, both before ADR-0084):

| | 8 Oct | 22 Oct | 5 Nov | 19 Nov | 3 Dec |
| --- | --- | --- | --- | --- | --- |
| measured | 126 → 141 | 192 → 202 | 218 → 225 | 239 → 251 | 247 → 259 |
| τ² (sd, bps/day) | 2.5 → 9.1 | 4.9 → 9.9 | 0.8 → 2.9 | 0.45 → 2.6 | 0.26 → 1.3 |
| E2 | 6 → 15 | 3 → 11 | 8 → 6 | 8 → 8 | 8 → 6 |
| hand-off | 3 → 3 (0x971f now E2) | 1 → 2 (+0xa536) | 1 → 1 | 1 → 1 | 1 → 1 |

Named addresses at 3 Dec, before ADR-0084 (α / s / α without the best week, bps/day):
- **0x2cd9:** 21.3 / 73.7 / -23.7 → **23.7 / 62.0 / -11.9**. Still E1 and still not robust; still the only hand-off.
- **0x971f:** 107.9 / 63.3 / 79.4 → 74.7 / 44.7 / 55.6. E1, robust, fails S2.
- **0xd2f0:** 121.4 / 219.9 / -81.2 → 105.3 / 179.9 / -58.6. E1, not robust, fails `sel_tradable_share`.
- **0x4c6e:** E0, 11 exposed days in 3 weeks.

## P4-2: the tradable universe and the replays (unchanged by the review)

- **Universes.** The v1 trees predate ADR-0066 (300 / 327 / 330 / 358 / 354 addresses), so the frozen stack was
  rerun on the current A/B universes as `research/replay_allpriced/` (14.8 min). Its shared inputs (drift cells,
  hold bands, spreads, marks) are byte-identical to `research/replay_frozen/`.
- **The tradable replay** `research/replay_tradable/` copies each wallet's tradable set (12.5 min).
  - The cap plan is the all-priced one: every joined leg has the same cap scale.
  - Legs outside a wallet's set are `not_tradable`. No follower or benchmark fill lies outside a wallet's set (data
    tests).

| Origin | coins seen | T1 priced | T2 valued | T3 liquid | T4 ≤ 25 bps | T5 ≥ 5 wallets | **tradable (pooled)** | wallets whose own set differs (leave-one-out T4) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 Oct | 195 | 76 | 73 | 55 | 63 | 21 | **20** | 0 |
| 22 Oct | 195 | 84 | 76 | 71 | 57 | 30 | **25** | 2 |
| 5 Nov | 195 | 90 | 82 | 75 | 60 | 33 | **26** | 1 |
| 19 Nov | 195 | 159 | 87 | 73 | 65 | 39 | **29** | 14 |
| 3 Dec | 195 | 164 | 119 | 80 | 85 | 37 | **27** | 5 |

- **T5 binds most.**
- **3 Dec set:** AAVE, ADA, APT, ARB, ASTER, AVAX, BCH, BNB, BTC, CAKE, DOGE, DOT, EIGEN, ENA, ETH, FARTCOIN, HYPE,
  LINK, LTC, PENGU, PUMP, SOL, SUI, TON, VIRTUAL, XRP, kPEPE.
- **Leave-one-out flips** come from coins just above the 25 bps median (e.g. SPX at 3 Dec).
- **Coverage:** `coins.parquet` carries per-coin coverage columns.

Leader-level gates, passing out of the A/B universe:

| Gate | 8 Oct | 22 Oct | 5 Nov | 19 Nov | 3 Dec |
| --- | ---: | ---: | ---: | ---: | ---: |
| `sel_tradable_share` (≤ 10% of notional-hours outside the set) | 149 / 302 | 173 / 332 | 182 / 335 | 205 / 361 | 203 / 358 |
| `sel_direction` (max per-factor \|Δβ\| ≤ 0.25) | 235 | 258 | 268 | 294 | 283 |
| `sel_equity_band` [5k, 2M] | 207 | 239 | 235 | 251 | 254 |
| `sel_break_even` | 139 | 190 | 194 | 203 | 208 |
| `sel_copier` | 301 | 332 | 335 | 361 | 356 |
| S2 (all binding Phase 2 gates, gate 7 v2) | 22 | 19 | 25 | 25 | 23 |
| **S1-S3 all pass** | **5** | **3** | **2** | **2** | **2** |

## P4-3 and P4-4: statistics, τ² and categories

- **Window:** the common window runs from `max(8 Sep, origin - 12 weeks)` to the day before the origin.
- **Measurability:** ≥ 20 exposed days in ≥ 4 weeks with exposure.
- **The bootstrap check agrees:** the median ratio of the 7-day block-bootstrap SE to s is 0.82 / 0.94 / 0.95 /
  0.97 / 0.98, so s is slightly conservative. τ² > 0 at every origin, so the 5- and 10-day blocks were also run.

| Origin | A/B | measured (k) | Q (df, p) | **τ²** (sd, bps/day) | robustly 0 | μ0 | E0 / E- / E1 / E2 | carry books (all) |
| --- | ---: | ---: | --- | --- | --- | ---: | --- | ---: |
| 8 Oct | 302 | 141 | 392.0 (140, 1.0e-25) | 7.3e-7 (8.5) | no | 0 | 161 / 65 / 65 / 11 | 9 |
| 22 Oct | 332 | 202 | 286.7 (201, 6.8e-5) | 7.8e-7 (8.8) | no | 0 | 130 / 77 / 117 / 8 | 7 |
| 5 Nov | 335 | 225 | 238.6 (224, 0.24) | 2.6e-8 (1.6) | no | 0 | 110 / 82 / 143 / 0 | 11 |
| 19 Nov | 361 | 251 | 303.2 (250, 0.012) | 4.0e-8 (2.0) | no | 0 | 110 / 93 / 158 / 0 | 16 |
| 3 Dec | 358 | 259 | 246.4 (258, 0.69) | 0 (0) | **yes** | 0 | 99 / 97 / 162 / 0 | 15 |

- **E1:** no E1 record reaches posterior P(α > 0) ≥ 0.8; that is why it is E1. At 3 Dec, 93 of the 162 E1 pass the
  own-data robustness check, and 5 are carry books on the total.
- **The bootstrap block lengths:** with τ² robustly 0 at 3 Dec, only the 7-day block was run there (ADR-0072). The 5-
  and 10-day blocks ran at the other origins.

### 3 Dec: the E2 addresses, the hand-off and the named addresses

The full table of all **162** E1/E2 addresses at 3 Dec is [phase-4-v2-3dec-e1-e2.csv](phase-4-v2-3dec-e1-e2.csv). It is
regenerated by `scripts/export_v2_e1e2_table.py` and holds:
- α (excluding funding), s, α including funding, the funding part and the carry label;
- the posterior and the robustness variants;
- the static/timing split, exposure, S2/S3 status, hand-off and placebo.

In summary:
- **0 are E2 and 162 are E1** (τ² robustly 0). Of the E1, 93 are robust and 86 have a positive static α.
- 10 E1 pass S2 and 60 pass S3; only 0x2cd9 passes both.
- The six addresses that were E2 before ADR-0084 are E1 now, with α excluding funding of 0.2-2.6 bps/day.

Units: bps per day per USDC of gross. "incl. fund." = the former α. "ex best wk" = own α without the best week
(binding). Static and timing are the replica split, now without funding. P is undefined at 3 Dec (τ² = 0).

| Address | Cat. | α | s | incl. fund. | funding | carry book | ex best wk | robust | static | timing | exposed days | S2 | S3 | hand-off |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| **0x2cd9** | E1 | 26.66 | 61.87 | 23.71 | -2.95 | no | -8.74 | **no** | -2.60 | 29.26 | 47 | pass | pass | **yes (only one)** |
| 0x971f | E1 | 75.74 | 44.88 | 74.69 | -1.06 | no | 56.51 | yes | -20.30 | 96.05 | 79 | fail (gate 7 v2) | pass | no |
| 0xd2f0 | E1 | 108.25 | 180.08 | 105.34 | -2.91 | no | -55.88 | no | -71.03 | 179.29 | 60 | pass | fail (tradable share) | no |
| 0xd670ced0 | E1 (was E2) | 2.64 | 2.30 | 5.05 | 2.41 | no | 0.69 | yes | 0.05 | 2.60 | 82 | fail | pass | no |
| 0xdd795907 | E1 (was E2) | 2.33 | 2.04 | 4.81 | 2.48 | yes | 0.48 | yes | 0.00 | 2.33 | 80 | fail | fail (equity band) | no |
| 0x077a25d1 | E1 (was E2) | 1.91 | 1.68 | 4.30 | 2.39 | yes | 0.51 | yes | 0.00 | 1.91 | 50 | fail | pass | no |
| 0x649156eb | E1 (was E2) | 0.70 | 1.78 | 3.05 | 2.36 | yes | -0.47 | no | -0.38 | 1.07 | 84 | fail | pass | no |
| 0x7f5698c3 | E1 (was E2) | 0.20 | 0.21 | 2.59 | 2.39 | yes | 0.00 | no | 0.00 | 0.20 | 51 | fail | pass | no |
| 0x4c6e | E0 | (119.8) | | | | | | | | | 11 | pass | fail (tradable share) | no |

The former E2 carry books held BTC/ETH, which carry identity betas, so their static α is 0. Without funding,
almost nothing is left (0.2-2.3 bps/day).

Hand-off by origin (α and s in bps/day):

| Origin | Addresses (category, α, s, α incl. funding; robust?) |
| --- | --- |
| 8 Oct | **0x971f (E2, 100.9, 18.1, 99.4; yes)**, 0xa536 (E1, 6.7, 24.3, 6.4; no), 0xaeb9 (E1, 79.2, 120.5, 74.1; no) |
| 22 Oct | 0x971f (E1, 11.3, 59.3, 10.5; no), 0xa536 (E1, 0.5, 25.0, 0.5; no) |
| 5 Nov | 0xa536 (E1, 1.9, 18.2, 1.5; no) |
| 19 Nov | 0x2cd9 (E1, 20.5, 62.9, 17.5; no) |
| 3 Dec | 0x2cd9 (E1, 26.7, 61.9, 23.7; no) |

## P4-5: ranking validation

Spearman IC with the next 14-day α (flat-start test windows, the origin's betas), all A/B with both values:

| Key | 8 Oct | 22 Oct | 5 Nov | 19 Nov |
| --- | ---: | ---: | ---: | ---: |
| **posterior mean m (the rule)** | +0.098 | -0.029 | -0.038 | -0.150 |
| own α | -0.043 | +0.053 | -0.085 | -0.107 |
| information ratio | -0.027 | +0.050 | -0.074 | -0.096 |
| t-statistic | +0.009 | +0.002 | -0.101 | -0.161 |
| former NAV key (ADR-A0051) | -0.010 | -0.098 | +0.095 | -0.099 |
| former trip key (ADR-A0131) | -0.133 | +0.024 | +0.085 | -0.022 |

**Decision (pre-declared, ADR-0075):** the mean IC of m is -0.030 < 0.05, and it is positive at 1 < 3 origins.
**Ordering is not used.**

**Placebo (ADR-0081).** It runs only where τ² is not robustly 0 and E2 exists, so at 8 Oct and 22 Oct.
- 19 E2 address-origins; **10 beat their time-shifted copies' median** (8 of 11 at 8 Oct, 2 of 8 at 22 Oct).
- 0x971f at 8 Oct is one of them.
- Before ADR-0084 it was 12 of 46. The difference is the carry books, whose α was funding the shift could not move.

## P4-6: duplicates and co-movement

- **No near-duplicate pair exists.** Pairs exist only at 8 Oct (0x971f, 0xa536, 0xaeb9) and at 22 Oct (0x971f,
  0xa536). Ex-crash both-exposed correlations are 0.10-0.40, overlaps 0.0-0.24 and exposure-based risk correlations
  0.70-0.86.
- **0x971f / 0xaeb9 at 8 Oct is unmeasured** (19 both-exposed days, under 20). It gets no diversification credit:
  `corr_for_phase5` = 1.
- **The risk Σ is fitted once per origin.** Inputs: the tradable coins with returns on ≥ 60 of the 90 days before
  the origin, complete-case days, Ledoit-Wolf constant-correlation shrinkage.

## P4-7: development evaluation

| Window | Set (k) | α, set vs random median (bps/day) | raw return, set vs random median | without 10-11 Oct (α; raw) |
| --- | --- | --- | --- | --- |
| 8 Oct | E2 (1: 0x971f) | -61.5 vs +11.0 (lose) | -2.03% vs 0.00% (lose) | +32.0 vs 0.0 (win); +1.62% (win) |
| 8 Oct | E1 ∪ E2 (3) | -93.3 vs +26.9 (lose) | -10.07% vs +1.13% (lose) | +3.1 vs -2.3 (win); +3.24% vs +0.28% (win) |
| 22 Oct | E1 ∪ E2 (2) | +21.1 vs +5.4 (win) | -1.22% vs 0.00% (lose) | same |
| 5 Nov | E1 ∪ E2 (1) | -3.6 vs -0.2 (lose) | -6.73% vs 0.00% (lose) | same |
| 19 Nov | E1 ∪ E2 (1) | +19.4 vs +1.2 (win) | +1.47% vs 0.00% (win) | same |

- **Random baseline:** exact enumeration when C(n, k) ≤ 10,000, else 1,000 seeded draws.
- **Wins for E1 ∪ E2:** 2 of 4 on α and 1 of 4 on raw return (Clopper-Pearson 95% for 2 of 4: 0.07-0.93).
- **Category calibration:** next-window α is **not ordered by category at any origin or pooled**.
  - Pooled medians: E- 3.8, E1 2.6, E2 10.4 bps/day.
  - Pooled Σ U / Σ G: E- 12.6, E1 5.8, E2 35.6.
  - E2 exists only at 8 Oct and 22 Oct, and E- is not below E1. The categories are not shown to be ordered.
- **Gate audit** (next raw return, pass vs fail, pooled address-windows):
  - break-even +1.39% vs -0.06%; equity band +1.01% vs +0.36%; tradable share +1.11% vs +0.50%;
  - robustness +1.54% vs +0.54%; S2 -1.26% vs +0.97% (the Phase 2 gates screen risk, not return).
  - Mean next α is dominated by small-gross outliers and is in `gate_audit_v2.csv`.
- **Coin policy as an execution policy** (never used to select). Mean test raw return, tradable vs all-priced copy:
  - all A/B: 2.81% vs 3.62% (8 Oct), 0.22% vs 0.65%, 0.11% vs 0.12%, 0.35% vs 0.20%;
  - hand-off sets: -10.07% vs -10.07%, -1.22% vs -4.37%, -6.73% vs -4.80%, +1.47% vs +2.49%.

## P4-8: the hand-off

`research/selection_v2/origin=<date>/eligible.parquet` has a fixed schema (data test). It holds ADR-0079 item 5, ADR-0083's
`alpha_funding`, `alpha_ex_funding`, `s_ex_funding` and `carry_book`, and ADR-0084's `alpha_incl_funding` and
`s_incl_funding`. Since ADR-0084, `alpha` equals `alpha_ex_funding`. It holds 3 / 2 / 1 / 1 / 1 rows. The same
folder also holds:
- `comovement.parquet`, `coins.parquet` (with coverage), `candidates.parquet` (S1-S3 and the category for every A/B
  address), `statistics.parquet`, `evidence.parquet`, `residual_daily.parquet` (with the start- and end-of-day
  grosses and funding);
- at the top level: `ranking_validation.csv` and `placebo.csv`.

## Limitations and open points

1. **Three post-hoc corrections are in force.** ADR-0080 (dust) and ADR-0084 (funding) were decided after seeing a
   result. ADR-0082 (flat days) is a definitional fix decided before its rerun. All are logged with the runs they
   replaced.
2. **Funding no longer counts as α (ADR-0084),** but the copy still earns or pays it: it is in the NAV, stress and
   Phase 5 inputs. A carry premium could be a deliberate Phase 5 choice; it is not evidence of leader skill.
3. **On a day that opens from flat, the market move between fill and close stays in the residual** (ADR-0082
   item 4).
4. **About 12 weeks is the binding limit on information.** The median own error is 21-32 bps/day, against a
   between-address dispersion of 1-10 bps/day.
5. **Next:** Phase 5 sizes. If any differs from 10k, P4-9 recomputes once.
