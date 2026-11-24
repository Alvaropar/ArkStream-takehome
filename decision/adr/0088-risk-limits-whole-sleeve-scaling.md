# ADR-0088: Risk limits, and the whole-sleeve limit scale `λ_i` that enforces them

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24); every limit PLACEHOLDER. Whole-sleeve scaling
  (items 2-3) is the user's decision 2 of 2026-11-23. The form of P5 (item 6: option b, the budget form) and the
  limits of G\* (item 7: option C) are the user's choices of 2026-11-24. The hourly-check detail is pinned in
  ADR-0096.
- Date: 2026-11-23
- Phase: Phase 5 (revision 4)
- Builds on: ADR-0017 (the stress shock), ADR-0034 (the gross cap scales the whole address), ADR-0071 and ADR-0077
  (coin betas), ADR-0079 (the coin covariance)
- Source: `decision/phase-5-methodology.md` section 4 and 4.1 (revision 4)

## Context
Each sleeve must stay a scaled copy of its leader's tradable book (ADR-0073). A limit that cut one leg would change the
book's shape, so the copy would no longer be the leader's. ADR-0034 already scales every leg of an address by one
factor for the gross cap. The user extended that to every limit (decision 2).

## Decision
1. **The limits.** In the paper scheme every limit runs exactly as it would with capital, on the paper book, and
   every time a limit binds is logged. Percentages are of `D` = 20,000 (two 10k sleeves) unless stated.

   | # | Metric | Limit (PLACEHOLDER) | Checked | Action |
   | --- | --- | --- | --- | --- |
   | O1 | Participation per coin per 4h bar, both sleeves | ≤ 0.5% | every order | clip; remainder next bar (ADR-0087) |
   | O2 | Limit price vs decision mark | ≤ the stress scenario's p99 shortfall for the coin's liquidity bucket (ADR-0053 buckets) | every order | IOC at the bound |
   | O3 | Minimum size; deadband | 10 USDC; 2% of target | every order | skip |
   | O4 | Post-trade projection | no limit below breached | every target update | solve `λ_i` (item 3) before any order |
   | S1 | Sleeve gross | ≤ 1.5 × cap denominator (ADR-0095 item 2) | every target update | scale the sleeve |
   | S2 | Sleeve stressed loss | ≤ 25% of sleeve NAV | hourly and every target update | scale the sleeve |
   | S3 | Sleeve drawdown from its high-water mark | -10% reduce-only; -15% flatten and pause | hourly | state machine (ADR-0089) |
   | P1 | Portfolio gross | ≤ 1.5 × `D` | every target update | scale the contributing sleeves |
   | P2 | Net per coin | BTC, ETH each ≤ 25% of `D`; any other coin ≤ 10% per sleeve holding it and ≤ 20% in total | every target update | per-sleeve part: that sleeve; total part: the contributing sleeves |
   | P3 | Net BTC-equivalent beta | ≤ 0.5 × `D` | every target update | scale the contributing sleeves |
   | P4 | Portfolio stressed loss plus exit cost | ≤ 15% of `D` | hourly and every target update | scale the contributing sleeves; a passive breach → reduce-only until below 90% (item 4) |
   | P5 | One coin's stress loss, summed over sleeves (item 6) | ≤ 40% of the P4 budget: 40% × 15% × `D` = 1,200 USDC | hourly and every target update | scale the contributing sleeves |
   | P6 | Drawdown ladder on the scheme's high-water mark | -5% halve new risk; -10% reduce-only; -15% flatten all, stop | hourly | state machine (ADR-0089) |

2. **Quantities** (pinned here):
   - **Gross** is `Σ_c |position_c| × mark_c`. **Net per coin** is the signed sum over the sleeves.
   - **Stress loss** applies the stress shock to every position at once:
     - the fall to longs and the rise to shorts (ADR-0017);
     - on the netted book for P4 and P5, and on the sleeve's virtual book for S2;
     - plus the exit cost: the stress scenario's modelled shortfall per side (ADR-0060) for closing each position in
       one order against the latest completed 4h volume.
   - **The stress shock** per coin is the largest adverse 24 h move on hour marks over the history **expanding from
     1 Jul 2025 to the origin** (ADR-0017, `leader.price_history_start`). It is fitted once per origin and held fixed
     through that window, including the 32-day holdout from the 3 Dec origin. A tradable coin with less than 24 h of
     history takes the largest shock in its ADR-0053 liquidity bucket.
   - **The coin covariance** (Ledoit-Wolf, as ADR-0079) and **the coin betas** are fitted on the **90 days before the
     origin**, point in time. The covariance is used only for reporting (the ex-ante volatility of the book and the
     sleeves' risk correlation). No limit uses it.
   - **P3's BTC-equivalent beta** is `|Σ_c net_c · β_c|`, where `β_c` is the single-factor beta of the coin's daily
     Hyperliquid return on BTC's, with the ADR-0077 fit rules (at least 10 days, shrink weight n / (n + 30) toward the
     cross-coin median, BTC = 1).
   - **Sleeve NAV** is the sleeve allocation plus the sleeve's virtual PnL, including funding and costs.
3. **The solver** (methodology 4.1; the user's decision 2). At each target update:
   1. Start from `λ_i = 1` for every sleeve.
   2. **Per-sleeve limits** (S1, S2, then the per-sleeve part of P2). Each sleeve's `λ_i` is the largest value at or
      below its current one that satisfies them. Every leg is multiplied by the same `λ_i`, as ADR-0034 does.
   3. **Portfolio limits** (P1, the total part of P2, P3, P4), in that order:
      - the contributing sleeves are those whose positions add to the limited quantity in the breaching direction;
      - they are multiplied by **one common factor**, the largest that restores the limit;
      - sleeves that do not contribute are not touched.
   4. **P5**, in the budget form of item 6: one common factor on the sleeves whose positions in the coin add to its
      stress loss, as for the other portfolio limits. There is no waiver.
   5. **Repeat until nothing changes** (pinned here). A later step can break an earlier limit, for example when a
      scaled sleeve was offsetting another sleeve in the same coin. The ordered pass is therefore repeated until no
      `λ_i` changes by more than 1e-12 relative, at most 50 passes.
      - Each pass only lowers `λ`, and a flat book satisfies every limit.
      - If the passes do not converge, the sleeves contributing to any limit still breached go to `λ = 0`. This is
        logged as an engine fault and tested in F1.
   6. **Determinism:** the order of the steps is fixed, and ties are broken by address order.
   7. **Logged at every update:** each `λ_i`, the limit that set it, the pass count and any P5 binding. The
      time-weighted mean `λ_i` per sleeve is reported, with the exposure-weighted mean beside it (ADR-0096 item 11).
4. **Hourly checks and passive breaches.**
   - Each hour mark reruns the checks on the current targets at the current marks.
   - An S2 or P5 breach scales, as at a target update.
   - A P4 breach caused by marks alone does not force a sale. It puts the scheme in the P4 reduce-only state, in which
     orders that increase exposure are blocked, until P4 usage is below 90% of the limit. The next leader-driven
     target update solves P4 as usual.
5. **What this implied for 0x2cd9, before any run: the pre-run estimate** (methodology 4.1). The per-sleeve part of P2 allows 10% of `D` =
   2,000 USDC in any coin other than BTC and ETH. Near full gross, 91% HYPE is about 13,650 USDC of HYPE, so
   `λ ≈ 2,000 / 13,650 ≈ 0.15`, and the **whole** sleeve runs at about one-seventh. The HYPE leg is never cut alone.
   U\* shows the leader-shaped copy beside it.
   - **Measured at P5-5** (`decision/phase-5-results.md` section 7): the leader runs at about 0.1x leverage, so P2
     binds only in the hours when HYPE exceeds 2,000 USDC. The exposure-weighted `λ` was 0.19 in the 8 Oct window and
     0.34-0.81 in the others, and P5 never bound on the pair.
6. **The form of P5: (b), the budget form** (the user's choice, 2026-11-24; section 15 item 3). The options as put to
   the user are kept below.

   The arithmetic below uses the 3 Dec shocks from the existing Phase 2 table
   (`research/leader/origin=2025-12-03/stress_shocks.parquet`): HYPE 17.3%, ETH 14.6%, BNB 13.5%, BTC 10.5%.

   - **(a) As written: the share of current P4 usage, with the waiver.** P5 is waived and logged when scaling cannot
     change the share (one sleeve carries all the stress). Its problems:
     - **It is discontinuous at the waiver.** Say 0x971f holds a small position with stress loss `b`. Meeting 40%
       then forces 0x2cd9's HYPE stress to at most (2/3)·`b`, so `λ → 0` as `b → 0`. At `b = 0` the waiver applies
       and `λ` jumps back to the P2 level, about 0.15. A 50 USDC BTC position in 0x971f can zero out 0x2cd9.
     - **It can be infeasible.** If that small position is the only other stress (BTC alone, say), BTC's share is
       then about 60%. No non-zero book meets 40% for both coins, and the waiver does not apply because scaling
       does change the shares. So the solver drives both sleeves toward zero.
     - **The feasible band is narrow** with the full books: roughly 0x971f's stress between 1.25 and 1.45 times
       0x2cd9's.
   - **(b) Chosen: against the P4 budget.** A coin's stress loss, summed over sleeves, is at most 40% × 15% ×
     `D` = **1,200 USDC**.
     - It is an absolute, continuous limit with no waiver. It is solved like the other portfolio limits (step 3, last).
     - At the 3 Dec shocks it does not bind on either book: P2 binds first unless a coin's shock exceeds 60% (one
       sleeve holds it), 30% (both do) or 24% (BTC, ETH). It constrains only high-shock coins.
     - **What it gives up:** concentration is limited only when the book is near its P4 budget. A small book may sit
       in one coin.

   `risk.yaml` carries `P5_basis: budget` and `P5_coin_stress_max_usdc: 1200`. The waiver of methodology 4.1 item 4
   is not used.
7. **The limits of G\*: option C** (the user's choice, 2026-11-24). The options as put to the user are kept below.

   G\* (ADR-0086) is 0x2cd9 alone at a live sleeve of 2,500 USDC (set at P5-5 under ADR-0090; the rule allowed 5,000). The arithmetic below assumes
   full 1.5x gross at 91% HYPE and ignores the minor coins and the exit cost, except where stated.

   | Option | P2 cap per non-BTC/ETH coin | `λ` at 2.5k | `λ` at 5k | What it means |
   | --- | --- | --- | --- | --- |
   | **A** Section 4 as written, percentages of `D` = 20,000 | 2,000 USDC | ≈ 0.59 | ≈ 0.29 | P4 (3,000) is slack against `L_gray`; P5 is already replaced by `L_gray` |
   | **B** Percentages of the live sleeve | 250 / 500 USDC | ≈ 0.07 | ≈ 0.07 | most HYPE orders fall under the 10 USDC minimum, so the execution measurement measures little |
   | **C (chosen)** The `L_gray` stress cap replaces P2-P5; O1-O4, S1, S3 and the P6 ladder stay | none (the 750 USDC stress cap binds instead) | ≈ 1 | ≈ 0.55-0.6 | the HYPE leg alone stresses to about 590 USDC at 2.5k (about 650-700 with the minor coins and exit), under 750; about 1,180 at 5k |

   With C, two details follow (accepted with it):
   - **S2 is also replaced by `L_gray`.** Otherwise S2 (25% × 2,500 = 625 USDC) binds before `L_gray` at 2.5k.
   - **For one sleeve, P1 equals S1.** S3 and P6 are measured on the live book's own high-water mark, so they flatten
     at -375 USDC at 2.5k (-750 at 5k).

   So G\* runs O1-O4, S1 (equal to P1 for one sleeve), the `L_gray` stress cap on the remaining budget (item 2's
   stress loss; ADR-0090 item 6), and S3 and P6 on the live book's own high-water mark. `risk.yaml` carries
   `gray.limits: C`.

## Consequences
- **Code:** `portfolio_replay.py` (P5-3); the stress shocks, betas and covariance in `risk_model/origin=<date>/`
  (P5-2, leak test).
- **Tests:**
  - F1: every limit binds and is restored by whole-sleeve scaling; non-convergence goes to `λ = 0`; a passive P4
    breach blocks increases without selling;
  - F6: shape.
- **Findings, not assumptions:** how often each limit binds, the time-weighted `λ_i` and the P5 behaviour
  (methodology section 7).
- **The two former open items are settled** (items 6 and 7), so P5-3 codes the budget form of P5 and the option C
  configuration of G\*.
