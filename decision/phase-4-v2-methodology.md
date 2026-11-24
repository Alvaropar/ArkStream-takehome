# Phase 4 v2: selection methodology and development plan

Written 2026-11-23. **Revision 2, the same day:** includes the PM's amendments A1-A5 (section 15). **Status:
accepted, 2026-11-23,** as ADR-0069 (gate 7) and ADRs 0070-0075 (Phase 4 v2); a new ADR (the joint freeze) comes with
Phase 5. The ADRs are binding where they pin details this document leaves open. Until the code lands step by step
(P4-1 onward), ADRs A0130-A0141 and 0066-0068 describe what runs.

Inputs:
- [full_selection_criteria.md](full_selection_criteria.md) and [pre-holdout-checks.md](pre-holdout-checks.md);
- the Phase 4 review of 2026-11-23;
- the external Phase 4 review of 2026-11-23, adopted where marked **[ext]**;
- the PM's amendments, marked **[A1]**-**[A5]**.

The Phase 5 counterpart is [phase-5-methodology.md](phase-5-methodology.md), revision 4 (the two-sleeve scheme).
Revision 2, its counterpart when this document was written, was deleted on 2026-11-24.

**Decided after seeing results.** Every change below was decided after the development windows had been seen, like
ADRs 0066-0068. The protocol therefore applies:
- each change is written down before it is computed;
- it is applied at all five origins;
- it is logged in `provenance/trial_log.md`;
- it is never reverted because of the address or the return it produces.

---

## 0. Why Phase 4 changes

| # | Finding | Evidence (development data only) | Consequence |
| ---: | --- | --- | --- |
| 1 | Ranking on past copy returns does not predict | Spearman of the trip key with the next window: -0.16 / -0.07 / +0.07 / +0.17. NAV key (ADR-A0051): -0.01 / +0.27 / +0.31 / -0.19 (`diagnostics/persistence.csv`, `audit/mtm_key_persistence.csv`). Top quintile at 8 Oct underperformed in every later window (`decay.csv`). | Ranking must earn its place (section 7). |
| 2 | The spread of mean copy returns across addresses is as large as noise alone would make it | 312 A/B copies at 3 Dec with at least 20 days and 4 weeks: variance of the mean daily copy return 1.44e-5, mean squared week-clustered standard error 1.48e-5, so the method-of-moments signal share is about 0. Against a common factor (equal-weight copy index) the alpha signal share is 0.24. Unfiltered frozen tree, `research/copy_daily_twr_training.csv`; illustrative. | Market-adjust, shrink, and compute τ² before anything else (sections 5-6, 12). |
| 3 | The top-ranked address rests on one day | 0xd2f0, rank 1 at every origin since 22 Oct: copy +26.4% on 10 Oct; cumulative copy return since 8 Sep +12.1%, **-13.0% without 10-11 Oct** (leader +35.8%, or +4.1% without). Best week = 174% of its summed weekly returns. `single_event` was only a flag. | Robustness becomes binding, on the address's own data (section 6.3). |
| 4 | The score is not market-relative and mixes skill with how much of the sleeve is used | All three sleeves held only long positions, in HYPE, BNB and TAO; a BTC/ETH regression misses HYPE. The NAV return on a fixed 10k sleeve under no scale-up dilutes leaders smaller than the sleeve (0x971f: median equity 7.5k). | Holdings-based market adjustment, **per unit of gross exposure-time** (section 5) **[A1]**. |
| 5 | The rule variants were compared on something other than selection | `rule_a` and `rule_b_coin_filter` select **the same addresses at every origin** (`walk_forward.csv`). The rule_b gain is the coin filter's effect on the same sleeves: 8 Oct -11.9% → -2.3% (the crash window), 5 Nov -2.2% → +1.3%. | Judge the coin policy as an execution policy, not as a selection result (sections 4 and 10). |
| 6 | The coin filter selects on leaders' past profit per coin, not on copy cost | 3 Dec: 45 of the 125 dropped coins were dropped because the zero-cost benchmark lost money, and 50 because it made under 500 USDC. Capture is not execution leakage: at 8 Oct BTC -0.08, ETH 0.11, HYPE 0.08 (kept by fiat); at 3 Dec 10 kept coins have capture > 1. Near-threshold flicker: ZEC kept at 19 Nov (0.537) and dropped at 3 Dec (0.494) with 42k benchmark PnL. | Replace with ex-ante, direction-neutral coin eligibility (section 4). |
| 7 | The coin filter changes the leader's book | Excluded legs are removed and the 1.5x cap is re-solved on kept coins only (ADR-A0140), so kept legs grow and hedges can disappear. Not measured anywhere. | Cap on the full book; exclude leaders with material excluded exposure (section 4). |
| 8 | The pairwise walk measures diversification badly | Correlation counts flat days (Check 2). On days both copies hold positions, two pairs sit at 0.50-0.51, mostly from 10 Oct: without 10-11 Oct, 0x2cd9/0x971f is 0.10-0.13. Overlap is a cosine over identical (day, coin), so long BNB and long HYPE score 0. HYPE is 91% of 0x2cd9 and 78% of 0xd2f0. Effective independent bets: 1 to 2.2. | Phase 4 keeps only a duplicate screen. Diversification moves to Phase 5 (section 8). |
| 9 | `sel_hold_band` judges an address by its band's pooled average | Gate audit: passing address-windows +0.3% vs failing +1.6%. | Demote to a diagnostic (section 4.3). |
| 10 | The evidence cannot support a skill claim on volatile copies | Detecting 10 bps/day at one-sided 80% confidence and 80% power needs about 3,400 days at 3.5% daily volatility (0x2cd9, 0xd2f0) and about 110 days at 0.63% (0x971f) **[ext formula]**. MinTRL ≈ 1,610 days. | Evidence categories, not a forced positive label (section 6). |

## 1. Principles

1. **Phase 4 answers "who is individually qualified, and how strong is the evidence?"** Phase 5 answers "how do the
   qualified addresses combine into a scheme?". Choosing the basket and its weights moves to Phase 5. ADR-0065
   freezes both phases together, so the holdout still tests one fully mechanical rule.
2. **Copyability and safety are yes/no conditions. Skill is a graded, shrunk estimate.**
3. **Skill is measured per unit of exposure [A1].** The primary statistic is market-adjusted return per unit of
   gross exposure-time. It does not change when a leader is smaller than the sleeve, or when a copy sits idle.
   Utilisation and capacity are measured here but decided in Phase 5.
4. **No credit for missing evidence** (ADR-0068). Short records are not given hard minimum lengths chosen after seeing
   results. They get wide uncertainty and are shrunk toward the prior.
5. **Coins are judged by measured cost, never by whether leaders made money on them.**
6. **Ranking is used only if it is shown to predict** on development data, by a criterion written down before it is
   measured.
7. **Do not force an inconclusive address into a positive category [ext].** "No address shows evidence of skill" is
   a valid Phase 4 result. It leads to a shadow-only or CONDITIONAL GO decision, not to a looser rule.
8. **One provisional sleeve size [A3].** Phase 4 is computed at a 10,000 USDC sleeve, the size every existing
   replay uses. If Phase 5 chooses other sizes, Phase 4 is recomputed once at those sizes before the joint freeze
   (section 9.1).

## 2. The pipeline at a glance

| Stage | Question | Binding? | Output |
| --- | --- | --- | --- |
| S1 Data integrity | Can the records be turned into returns we trust? | yes | grade A/B (ADR-0066), unchanged |
| S2 Leader evidence | Enough evidence, and no severe leader risk? | yes | Phase 2 binding gates (ADR-0067), with **gate 7 v2** (section 3) |
| S3 Copyability | Can we trade this leader at the provisional sleeve size and our delay? | yes | equity band, **leader tradable share**, break-even delay, copier screen |
| S4 Copy economics | What did the copy earn per unit of exposure, net and market-adjusted? | no (measurement) | statistic set (section 5) |
| S5 Evidence | Is there measurable skill dispersion at all, and is this address positive and not one event? | yes (category) | DerSimonian-Laird τ², shrunk α, P(α > 0), own-data robustness, **evidence category** |
| S6 Ranking validation | Does the statistic predict the next window? | decides whether ordering is used | pooled IC and decision (section 7) |
| S7 Duplicates and co-movement | Is any pair the same bet? | duplicates only | near-duplicate screen; co-movement matrices for Phase 5 |

## 3. S1-S2: gate 7 v2 (ADR-0069)

### 3.1 Why change it

Gate 7 (`gate_book_account`) asks whether the book rebuilt from fills explains the account's returns. It compares
account and book returns on timestamp-matched snapshot intervals (`leader_book.intervals`), and passes when the
one-sided 80% Fisher-z lower bound of their **Pearson** correlation is at least 0.5 and the tracking std is at most
0.02.

Two problems:
1. **Pearson correlation is decided by a few large intervals.** Gate 6 (`gate_rebuild_fit`) already judges how often
   the book misses materially, with a Clopper-Pearson bound on the share of intervals within 1% of equity. Gate 7 then
   lets the same handful of large misses also decide "agreement". In a quiet account they dominate the correlation.
   - The cross-check values the book at Binance 1m marks while the account is marked on Hyperliquid.
   - Venue dislocations (10 Oct) are a plausible source of such intervals. This is a hypothesis, to be checked in step P4-1.
2. **Correlation cannot see bias.** A book that misses a steady PnL source (a hedge, an isolated position, activity
   outside the fills) passes as long as the variations line up. The gate fails the wrong addresses and misses the
   failure that matters for copying.

The case that raised it: 0x971f fails gate 7 at 5 Nov, 19 Nov and 3 Dec, with correlation 0.538 on 118 intervals,
a lower bound of 0.480 and nRMSE 0.85. Its slope is 1.07 [0.76, 1.37] and it passes gate 6. Its card shows grade A,
the PnL identity exact on every snapshot, rebuilt realized PnL within 0.10 USDC of `closed_pnl` (1,706 USDC), and
100% core-perp notional.

**The rule below is set on principle, not to pass 0x971f.** Whether 0x971f passes is unknown until the rerun, and the
result stands either way. At 3 Dec gate 7 is 220 pass / 7 fail / 131 unmeasured. The change can move at most those 7
to pass, and it can fail some of the 220 through the new gap and slope checks.

### 3.2 The rule

Over the usable fit intervals (unchanged: at least `min_intervals` = 10; otherwise unmeasured, which never passes):

| Check | Statistic | Pass if | Status |
| --- | --- | --- | --- |
| 7a Agreement on ordinary intervals | **Spearman** ρ of account return `r_start` vs book return `book_r`; one-sided 80% lower bound via Fisher z with the Bonett-Wright variance `(1 + ρ²/2) / (n - 3)` | lower bound ≥ 0.5 | replaces the Pearson bound |
| 7b No steady gap **[A2]** | gap **rate** `ḡ = Σ (r_start - book_r) / Σ interval days` (bps/day); week-clustered standard error; one-sided 80% lower bound of `|ḡ|`, i.e. `|ḡ| - z₀.₈ · se` | lower bound ≤ 5 bps/day (≈ 18% a year unexplained) | new |
| 7c One-for-one | Theil-Sen slope of account on book | in [2/3, 3/2] (at most a third of the book's moves hidden or unexplained) | new |
| 7d Tracking | std(r_start - book_r) | ≤ 0.02 | unchanged |

- **Why a rate [A2].** A summed gap grows with the number of intervals, so the same leak would pass at 8 Oct (about
  30 intervals) and fail at 3 Dec (about 120). ADR-0066's 10% is a level relative to equity, not a sum of returns
  over time. A per-day rate with its uncertainty is comparable at every origin.
- **What 7b can and cannot detect.** It fails an address only when the gap is **confidently** above 5 bps/day. A noisy
  residual therefore gets the benefit of the doubt:
  - with 0.5% daily residual noise, a steady +20 bps/day gap fails at both 30 and 120 intervals (lower bounds 12.3
    and 16.2 bps/day);
  - a +8 bps/day gap passes at both (0.3 and 4.2 bps/day).

  This departs from the "no credit for imprecision" stance of gates 6 and 7a. It is accepted because an equivalence
  version (requiring the upper bound to be ≤ 5 bps/day) would fail almost every account for lack of precision, and
  because 7a and 7d already require precise agreement and cap the dispersion. Both lower bounds are reported.
- **Reported, not binding:** the Pearson correlation and its bound, the OLS slope and intercept with 95% CIs, nRMSE,
  the number of intervals with miss > 1% (the gate 6 link), the lag-1 autocorrelation of the residual, and the three
  largest residual intervals with their `src_row` (traceable to `traders.csv`).
- **Thresholds:** the 0.5 bound and the 80% level are unchanged; 5 bps/day and [2/3, 3/2] are new (PLACEHOLDER). None
  was chosen by looking at any address's value.
- **Code:** `leader_book.agreement_regression` adds `xc_spearman`, `xc_spearman_lower`, `xc_gap_rate`,
  `xc_gap_rate_lower` and `xc_ts_slope`. `intervals` sets `xc_flag` from 7a-7d (`disagree_rank`, `disagree_gap`,
  `disagree_slope`, `disagree_tracking`). Config:
  `leader.book.{agreement: spearman, max_gap_bps_per_day: 5, gap_lower_conf: 0.80, slope_band: [0.667, 1.5]}`.
- **Tests:**
  - outliers in 3 of 100 intervals fail Pearson and pass Spearman;
  - a steady +20 bps/day gap with 0.5% daily noise fails 7b at 30 and at 120 intervals;
  - a zero-mean residual passes 7b at any length;
  - multi-day intervals are weighted by their days;
  - a hidden 50% hedge fails 7c;
  - fewer than 10 intervals is unmeasured.
- **Rerun:** Phase 2 at all five origins for every A/B address (`make leader`), then
  `scripts/audit_gate_change.py`. Publish every address that moves, in either direction, with its reasons
  (`research/audit/gate_change_addresses.csv`, as for ADR-0067).
- **Longer-term fix (not in scope):** value the cross-check book at Hyperliquid prices. The repo has only daily and
  4h Hyperliquid marks, not 1m, so this is recorded as a limitation.

## 4. S3: copyability

### 4.1 Coin eligibility (replaces the ADR-A0136/A0140 coin filter)

There are two universes **[ext 9.4]**:
- the **research benchmark universe** (BTC, ETH, HYPE, SOL), used for comparisons and factors;
- the **tradable universe**, the coins the copy may trade.

Being on the benchmark list gives a coin no trading exemption. The tradable universe is computed at each origin from
data before it:

| # | Condition | Measure | Threshold (PLACEHOLDER) |
| ---: | --- | --- | --- |
| T1 | Priced | passes the point-in-time price check (ADR-0044) and has a drift source (aggTrades or the ADR-0061 split-order floor) | pass |
| T2 | Valued **[ext 9.3]** | share of training notional-hours (all A/B) with a closing mark and known funding | ≥ 95% |
| T3 | Liquid at our size | share of training orders (all A/B, at the **provisional 10,000 USDC sleeve [A3]**) that fit under the 0.5% participation limit without clipping | ≥ 95% |
| T4 | Affordable | base-scenario implementation shortfall per side (half-spread + impact + delay drift + fee), bps of traded notional, from the training replay, pooled over wallets, **leave-one-wallet-out** when used to evaluate a wallet **[ext 9.2]** | median ≤ 25 bps per side |
| T5 | Enough wallets | effective number of wallets in the coin's training notional (1 / HHI) | ≥ 5 (fewer: not tradable; no credit for missing evidence) |

- **No PnL or capture condition.** Capture stays a reported diagnostic per coin, with per-wallet medians **[ext 9.1]**.
- A coin-PnL momentum filter is a separate hypothesis. If wanted, it is tested as such, not as copyability.
- Every published coin set carries its coverage columns (pre-holdout Check 1).

### 4.2 Applying it to a leader (fixes finding 7)

- **`sel_tradable_share`** (replaces `sel_copyable_notional`): the share of the leader's training notional-hours in
  non-tradable coins must be ≤ 10%. Otherwise the **leader** is ineligible. We do not copy part of a book.
- For eligible leaders, the excluded legs get target 0. **The 1.5x cap scale is solved on the leader's full book**,
  so the kept legs stay exactly proportional.
  - Code: `replay_cap.cap_legs` computes the scale over every coin, then zeroes the excluded legs.
  - Status: `not_tradable`, joining the excluded statuses.
- Reported per leader: the holdings-based net beta of the copied book against the full book (section 5.2). An
  eligible leader with `|Δβ| > 0.25` (PLACEHOLDER) is ineligible: removing its legs changes its direction.

### 4.3 Other S3 gates

| Gate | Treatment |
| --- | --- |
| `sel_equity_band` [5k, 2M] | unchanged (ADR-A0130); judged against the provisional 10k sleeve **[A3]** |
| `sel_break_even` | unchanged: it separates outcomes best (+1.0% passing vs -0.6% failing) |
| `sel_copier` | unchanged; "weaker member" = lower evidence category, then lower posterior α (section 6) |
| `sel_hold_band` | **diagnostic only.** The address's own simulated copy already decides copyability; the band's pooled average is reported beside it |

## 5. S4: copy economics

### 5.1 Series, window and measurability

- **Series:** the copy's daily mark-to-market ledger, base scenario, from the tradable-universe replay at the
  provisional sleeve. Each day gives residual PnL `U_{i,t}` (section 5.2) and gross exposure `G_{i,t}` (notional at
  the start-of-day mark).
- **Common window [ext 6.2]:** every address is measured over the same calendar days, from
  `max(8 Sep 2025, origin - 12 weeks)` to the day before the origin. 8 Sep is the first day a copy can be priced
  (`export_twr_matrices.py`). This makes addresses comparable on regimes, including whether the 10-11 Oct crash is
  inside.
- **Flat days carry no information about skill [A1].** A day with `G = 0` contributes nothing to the numerator or the
  denominator of the primary statistic. So the window start no longer matters for its value. This is consistent with
  ADR-A0051, which starts at the first exposure.
- **Measurability:** at least **20 exposed days** (`G > 0`) in at least **4 calendar weeks with exposure**.
  - This keeps ADR-A0051's 20 days and 4 weeks, but counts exposed days. Under a per-exposure statistic, flat days are
    not evidence.
  - Stated before the rerun: this can make sparse copies unmeasured. 0x4c6e has about 16 days with a non-zero copy
    return in the unfiltered 3 Dec training series.

### 5.2 Market adjustment: holdings-based, with betas fixed per origin [A5]

- Regressing about 60-90 sleeve days on several factors is noisy **[ext 8.4]**. Instead, the market component comes
  from **positions**, which are known exactly, and **coin betas**, estimated from long price histories:
  - `e_{i,c,t}` = the copy's signed notional in coin c at the start of day t;
  - `β_{c,f}` = coin c's beta to factor f, **estimated once at each origin** from Hyperliquid daily marks over the
    **90 days before it**, shrunk toward the cross-coin median. It is not re-estimated within a window. This keeps
    the leak test simple: every beta used at an origin has one fit date, before that origin;
  - factors: **BTC**, **ETH** and **ALT**, the equal-weight daily return of tradable coins other than BTC and ETH,
    with membership fixed at the origin;
  - residual PnL `U_{i,t} = PnL_{i,t} - Σ_c e_{i,c,t} Σ_f β_{c,f} r_{f,t}`, after costs and funding.
- **Primary statistic [A1]: alpha per unit of gross exposure-time.**

  ```
  α_i = Σ_t U_{i,t} / Σ_t G_{i,t}     (bps per day of 1 USDC gross)
  ```

  This is the residual version of the CT measure. Scaling every position by a constant scales both sums by it, so
  `α_i` is unchanged by the sleeve size, the no-scale-up multiplier and idle days.
  - Caveat: per unit of gross, a hedged book (long BTC, short ETH) looks less efficient than a directional one with
    the same residual PnL.
  - The information ratio (mean residual return over residual volatility) is therefore reported beside it.
- **Mandatory decomposition: static replica [A5].** Over 12 weeks a holdings-based α is dominated by a few coin moves
  (for example HYPE). Every address reports:
  - the **static replica**: on each exposed day, the copy's gross `G_{i,t}` allocated across coins in the window's
    average signed mix (in-window weights, descriptive only);
  - `α_static` = the replica's residual PnL per unit gross: **coin selection**;
  - `α_timing = α - α_static`: **when** the leader is in each coin;
  - the share of residual PnL from the three largest coin-days.

  Coin selection counts as skill. The decomposition shows the reader how much of α is one coin's run.
- The BTC/ETH return regression (`market_relative`) stays as a cross-check.

### 5.3 The statistic set (reported for every address) [ext 6.4, 11 Stage 3]

| Statistic | Role |
| --- | --- |
| `α_i` per unit of gross exposure-time, with its standard error | **primary** (shrunk in section 6) |
| `α_static`, `α_timing`, top-3 coin-day share | mandatory decomposition [A5] |
| Information ratio of the residual | reported (risk-normalised alternative; fairer to hedged books) |
| Utilisation `ū_i = mean_t G_{i,t} / A` and its p50 / p95 | reported; **handed to Phase 5** for capacity and expected sleeve return [A1] |
| Residual return on sleeve NAV (`Σ U / (A · days)`), raw NAV return, geometric return, volatility, max drawdown, 95% expected shortfall | reported |
| Trip expectancy `EV`, PnL / peak notional `EP`, CT (total, not residual) | diagnostics |
| Capture vs the zero-cost benchmark, gap decomposition (ADR-0063) | diagnostics |
| Training stress and optimistic returns, break-even delay | reported (gates use them) |

## 6. S5: evidence, shrinkage and categories

### 6.1 Uncertainty

- `s_i` is the standard error of the ratio `α_i`, by the delta method with residuals `U_{i,t} - α_i G_{i,t}`,
  clustered by calendar week, with a small-sample t (df = weeks with exposure - 1) converted to a normal-equivalent by
  scaling.
- **Bootstrap check [ext 6.2]:** a synchronized moving-block bootstrap with **one block length (7 days)**, the same
  calendar blocks for every address. The 5- and 10-day lengths are run only if τ² > 0 at that origin (section 6.2)
  **[A4]**.
- About 12 weeks is the binding limit on information, and the report says so.

### 6.2 Is there skill dispersion? DerSimonian-Laird first [A4]

At each origin, across every A/B address with a measured `α_i`, with `w_i = 1 / s_i²`:

```
ᾱ_FE = Σ w_i α_i / Σ w_i
Q    = Σ w_i (α_i - ᾱ_FE)²
τ²   = max(0, (Q - (k - 1)) / (Σ w_i - Σ w_i² / Σ w_i))      (DerSimonian-Laird)
```

- DerSimonian-Laird weights each address by its own precision. The standard errors here differ by an order of
  magnitude across addresses, which the plain method-of-moments difference ignores.
- **τ² is "robustly about 0"** at an origin when `τ² = 0` and Cochran's Q does not reject homogeneity at p = 0.20.
  Then:
  - the report says plainly that the data shows no measurable differences in skill;
  - **nobody can reach E2**;
  - the placebo (section 7) and the extra bootstrap block lengths are skipped.
- **Prior:** `α ~ N(μ0, τ²)`, with `μ0 = min(0, ᾱ_RE)`, the random-effects mean (weights `1 / (s_i² + τ²)`). The prior
  never assumes skill.
- **Posterior:** `w*_i = τ² / (τ² + s_i²)`, mean `m_i = w*_i α_i + (1 - w*_i) μ0`, sd `v_i = √w*_i · s_i`.
- **Scale [A1]:** because `α_i` is per unit of gross, pooling no longer mixes copies at different utilisation. A
  half-idle copy and a fully deployed one are compared on the same footing.
- Behaviour clusters (ADR-A0132) may serve as prior groups (a per-cluster μ0 and τ²) if each has at least 30
  addresses and τ² > 0; otherwise there is one pool **[ext 8.5]**.

### 6.3 Robustness, on the address's own data [A4] [ext 6.5]

Shrunk quantities cannot test robustness. When τ² ≈ 0 every posterior equals μ0, and a check on the posterior would
pass for everyone when μ0 = 0. Robustness is therefore judged on the unshrunk record:

| Measure | Binding? |
| --- | --- |
| **`α_i` without its best calendar week** (the week with the largest residual PnL; both sums recomputed) | **yes: must be > 0** |
| Own-data `P(α > 0)` without the best week, `Φ(α_i,ex / s_i,ex)` | reported (the stricter alternative; not adopted, so that confidence is not demanded twice on about 12 weeks) |
| Without 10-11 Oct; without the best 1 and 3 weeks; without the best trip | reported |
| Best week's share of summed weekly residual PnL; top-5 trips' share of positive trip profit | reported |

### 6.4 Evidence categories [ext 6.3, 11 Stage 6]

| Category | Condition | Consequence |
| --- | --- | --- |
| E0 Insufficient | unmeasured (under 20 exposed days or 4 weeks with exposure) | no claim; not passed to Phase 5 |
| E- No evidence | measured, own `α_i ≤ 0` | not passed to Phase 5 |
| E1 Weak | own `α_i > 0`, but posterior `P(α > 0) = Φ(m_i / v_i) < 0.8`, or the robustness check fails | shadow-only candidate; passed to Phase 5 for a shadow scheme |
| E2 Positive | posterior `P(α > 0) ≥ 0.8`, τ² not robustly 0, and the robustness check holds | eligible for the Phase 5 capital scheme |
| E3 Persistent | E2, and a positive `α` in later out-of-sample windows (holdout, then live shadow) | eligible to scale; not reachable inside Phase 4 |

When τ² is robustly 0, nobody reaches E2. Addresses with a positive own `α_i` are still E1, so a shadow scheme can be
built and the operating machinery tested. The 0.8 level is the one already used by gates 6 and 7 and the former key.

## 7. S6: does ranking predict? (decides whether ordering is used)

- **Test:** at each development origin, the Spearman IC between the posterior mean `m_i` and the next 14-day `α`
  (same definition, per unit of gross). The outcome comes from the **flat-start** test replays (no carried
  positions), across all A/B addresses with both values.
- **Pre-declared rule:** Phase 5 may use `m_i` to order or tilt the eligible set only if the mean IC over the four
  origins is ≥ 0.05 **and** it is positive at 3 or more origins.
  - Otherwise every eligible address gets the same expected `α` in Phase 5, and the categories still gate.
  - If τ² is robustly 0 at an origin, `m_i = μ0` for everyone there, the IC is undefined, and ordering is not used.
- **Reported beside it:** the IC of the unshrunk `α_i`, the former keys, the information ratio and the t-statistic,
  and top-quintile hit rates.
- **Prior note:** a rough check on the continuous training replay gave a mean IC of +0.25 for alpha against a common
  factor (positive at all four origins) and +0.18 for the raw mean. The continuous replay carries positions across
  origins, which inflates persistence, so this is a hypothesis only.
- **Placebo, only if τ² is not robustly 0 and E2 addresses exist [A4] [ext 11 Stage 4]:** replay each E2 copy with
  the leader's fill times shifted by a random 1-7 days (same coins, sizes and costs). If the real copy does not beat
  the shifted copies' median, the leader adds nothing beyond exposure and costs.

## 8. S7: duplicates in Phase 4, diversification in Phase 5

**Phase 4 removes only duplicates.** A hard pairwise correlation filter on these sample sizes is unreliable. A 0.50
correlation on 20 days has a 95% interval of 0.07-0.77 **[ext 8.2]**. At 3 Dec such a filter would remove 0x971f, the
only sleeve not in HYPE, on what is mostly one crash day.

- **Copier screen:** unchanged (`copiers.py`).
- **Near-duplicate:** a pair is a near-duplicate when all three hold:
  - same-coin position overlap ≥ 0.7;
  - the 95% lower bound of their correlation on days both copies hold exposure, **without 10-11 Oct**, is ≥ 0.5;
  - there are at least 20 such days.

  The weaker member (lower category, then lower `m_i`) is removed, and the pair is named.
- **Co-movement measured and handed to Phase 5 [ext 8.1]**, for every eligible pair:
  - correlation on the full calendar, on both-exposed days, and on both-exposed days without the crash, with Fisher
    95% intervals;
  - downside correlation (days the ALT factor is in its bottom 20%);
  - joint large-loss frequency (both below their own 10th percentile);
  - same-coin overlap and its direction share;
  - **exposure-based risk correlation** `ρ_ij = e_i'Σe_j / √(e_i'Σe_i · e_j'Σe_j)`, with Σ a shrunk coin covariance
    estimated once at the origin from the 90 days before it **[A5]**. It counts long BNB and long HYPE as related
    bets.
- **An unmeasured pair gets no diversification credit** (ADR-0068, kept). Phase 5 treats it at correlation 1 for
  risk.
- **Retired:** the walk order (within-cluster round robin), the pairwise 0.5 thresholds and fixed K = 5. Basket size
  and weights belong to Phase 5.

## 9. What Phase 4 hands to Phase 5

Per origin, `research/selection_v2/origin=<date>/eligible.parquet`, one row per address in E1 or E2 that passed
S1-S3 and the duplicate screen. Each row carries:
- category, `α_i`, `s_i`, `m_i`, `v_i`, `P(α > 0)`, τ² and its "robustly 0" flag;
- the robustness columns and the static-replica decomposition;
- utilisation `ū_i` (p50 / p95), so Phase 5 can turn a per-gross `m_i` into an expected sleeve return
  `m_i · ū_i · A`;
- capacity inputs: median equity, `E_ref`, the order-size profile, the tradable share;
- exposure profile: mean signed exposure by coin, holdings-based factor betas;
- training stress loss and drawdown;
- evidence keys: `snapshot_src_row`, `last_fill_src_row`, `tid`, `oid`.

Also `comovement.parquet` (section 8), `coins.parquet` (section 4.1, with coverage) and `ranking_validation.csv`
(section 7).

### 9.1 The sleeve-size loop with Phase 5 [A3]

Phase 4 is computed at the provisional 10,000 USDC sleeve. Phase 5 chooses sleeve sizes from that hand-off. To avoid
an endless loop:
1. Phase 5 chooses sizes from the 10k-based eligible set.
2. **If any chosen size differs from 10k,** Phase 4 is recomputed **once** on the replay trees at the chosen sizes
   (Phase 5 builds them in P5-1): T3, the statistics, τ², categories and duplicates.
3. Phase 5's construction is rerun **once** on the recomputed eligible set, with the sizes held fixed.
4. That result is what the joint freeze covers.

At stage 1 every sleeve is at most 10k (Phase 5, section 3.2), so T3 and the equity band computed at 10k are
conservative. The recompute mainly updates the statistics for size-dependent costs: impact, sub-minimum skips and
participation clips.

## 10. Development evaluation (Phase 4's own tests)

Phase 4 no longer forms a basket, so its tests ask whether the **qualification** adds value:
- **The E2 set at equal weight, and the E1 ∪ E2 set at equal weight,** against all-A/B random draws of the same size
  (exact enumeration where the pool allows **[ext 7.2]**, else 1,000 seeded draws). Measured on `α` and on raw base
  returns, with and without 10-11 Oct, per window and pooled.
- **Category calibration:** the mean next-window `α` by category (E-, E1, E2). Categories must be ordered, or the
  report says they are not.
- **Gate audit** (ADR-A0135) on the new gates, kept.
- **Coin policy as an execution policy:** for the same addresses, compare the copy on the tradable universe with the
  copy on all priced coins. This is reported, not used for selection.
- **Kept, descriptive only:** Clopper-Pearson on win counts. Deflated Sharpe, White's Reality Check and PBO are not
  computed: four windows and pools of this size cannot support them **[ext 7]**. The trial log carries the trial
  count.

## 11. What is kept, changed and dropped

| Item | Was (ADR) | Now |
| --- | --- | --- |
| Grades | ADR-0066 | kept |
| Phase 2 gates | ADR-0067 | kept; **gate 7 → v2**: Spearman, gap rate, slope (ADR-0069) |
| Missing measurements | ADR-0068 | kept |
| Key | p20 bootstrap of the daily NAV return (ADR-A0051) | holdings-adjusted α **per unit of gross exposure-time**, DerSimonian-Laird shrinkage, categories (ADRs 0070-0072) |
| Measurability | 20 days / 4 weeks from the first exposure | 20 **exposed** days / 4 weeks with exposure (ADR-0070) |
| `single_event` | flag | own-data α without the best week > 0, binding (ADR-0072) |
| Coin filter | PnL ≥ 500 and capture ≥ 0.5; majors exempt; cap on kept coins (ADRs A0136, A0140) | ex-ante tradable universe; cap on full book; leader-level exclusion (ADR-0073) |
| `sel_hold_band` | gate (ADR-A0130) | diagnostic (ADR-0073) |
| Walk, K = 5, equal weights | ADR-A0132 | duplicate screen only; basket → Phase 5 (ADR-0074) |
| Variant choice | matched random-k wins (ADR-A0137) | pre-declared IC rule and qualification tests (ADR-0075) |
| Sleeve size | 10k (replay default) | provisional 10k with a one-pass recompute (ADR-0070) |
| Freeze | ADR-A0141 (void) | joint Phase 4 + 5 freeze (a new ADR, with Phase 5) |

## 12. Development plan

Each step lists what it produces and how it is checked. Nothing reads the holdout. Every step writes its definitions
(ADR) **before** computing, and its result goes into the trial log.

**Order [A4]:** τ² is computed as early as possible (P4-3 and P4-4). If it is robustly 0, the optional extras are
skipped.

| Step | Work | Output | Checks |
| --- | --- | --- | --- |
| **P4-0** | Write ADR-0069 and ADRs 0070-0075 from this document; trial-log entry "Phase 4 v2 decided after seeing results"; config keys with PLACEHOLDER labels | ADRs, `decision_context.yaml` v2 | review only |
| **P4-1** | Gate 7 v2 in `leader_book`; rerun Phase 2 at all five origins for all A/B addresses (`make leader`); `scripts/audit_gate_change.py` | gate counts by origin; every mover with reasons; 0x971f's 7a-7d values and top residual intervals | unit tests (section 3.2); audit counts pinned in `expected_counts.yaml` |
| **P4-2** | Coin eligibility T1-T5 at the 10k sleeve (`selection_coins` → `coin_eligibility`); `cap_legs` on the full book; status `not_tradable`; rerun the replay for all A/B over nine windows as `research/replay_tradable/` (about 17 min); `sel_tradable_share`, `Δβ` | coin sets with coverage; replay tree; leader tradable shares | excluded coin never traded; cap scale equals the unfiltered scale; leave-one-out reproducible; byte-identical rerun |
| **P4-3** | Factor series (BTC, ETH, ALT) and coin betas fit **once per origin** on the 90 days before it; residual PnL; `α_i` per unit gross with its clustered standard error; static-replica decomposition; utilisation; the rest of the statistic set | `statistics.parquet` per origin | leak test: a planted post-origin day changes nothing, and every beta has one fit date before the origin; a synthetic one-coin book reproduces `α` exactly; `α` is unchanged when all positions are scaled by 0.5 |
| **P4-4** | **DerSimonian-Laird τ² and Q first;** then shrinkage, own-data robustness and categories; 7-day bootstrap check | `evidence.parquet` per origin; τ² and Q table by origin | synthetic: equal true α gives τ² ≈ 0 and no E2; a one-week record fails robustness; seeds fixed |
| **P4-5** | Ranking validation on the flat-start test windows; apply the pre-declared rule. Only if τ² is not robustly 0 and E2 exists: the placebo and the 5- and 10-day bootstrap lengths | `ranking_validation.csv`; ordering used: yes/no | — |
| **P4-6** | Duplicate screen; co-movement matrices; exposure-based risk correlation (Σ fit once per origin) | `comovement.parquet`, duplicate decisions | unmeasured pair = no credit; crash days excluded where stated |
| **P4-7** | Development evaluation (section 10); update `full_selection_criteria.md` (funnel rows filled) | `walk_forward_v2.csv`, report `decision/phase-4-v2-results.md` | determinism: two runs byte-identical |
| **P4-8** | Hand-off to Phase 5 (section 9) | `eligible.parquet` per origin | schema test |
| **P4-9** | **After Phase 5 chooses sleeve sizes:** if any differs from 10k, recompute P4-2 (T3 only) and P4-3 to P4-6 once on the chosen-size trees (section 9.1) | recomputed `eligible.parquet`; a diff of categories against the 10k pass | diff published; no further iteration |

Order matters:
- P4-1 changes the A/B universes' gate passes, so it comes before every replay and statistic.
- P4-9 comes before the joint freeze.

## 13. Expected consequences, stated before the rerun

- **The 3 Dec candidate set will change.**
  - 0xd2f0 will very likely fail the own-data robustness check, because its copy is negative without the crash week.
    That makes it E1 at best: shadow only.
  - 0x971f depends on gate 7 v2 (unknown). If eligible, its per-gross `α` no longer suffers from its small size, but
    its capacity (about 7.5k) stays a Phase 5 limit.
  - 0x4c6e may become unmeasured: about 16 exposed days in the unfiltered series.
  - 0x2cd9 is likely E1 or E2. Its static-replica decomposition will show how much of its α is HYPE's own move. In
    Phase 5 its 91% HYPE concentration becomes a weight question, not a reason to drop it.
  - The rerun pool will be larger: 19-25 Phase 2 passes per origin under ADR-0067 (22 / 19 / 25 / 25 / 23).
- **Finding 2 makes a τ² that is robustly 0 the single most likely outcome.** Then nobody reaches E2, and the decision
  path is a shadow scheme or a CONDITIONAL GO, never loosened thresholds.
- **Risk of forking paths:** this is the fourth post-hoc change in two days (ADRs 0066-0068, then this). The defence
  is order and transparency: definitions are written before any number is computed under them, and they are applied
  everywhere and logged. A reviewer should be able to see every address that moved and why.

## 14. Decisions for the user

1. Accept gate 7 v2 as specified, including 7b (5 bps/day) and 7c, which can also fail addresses that pass today.
2. The T4 cost ceiling (25 bps per side) and the `|Δβ|` limit (0.25): placeholders, to be set on principle before P4-2.
3. Exposed-day counting for measurability: it follows from A1, and may make sparse copies (0x4c6e) unmeasured.

## 15. Amendment log (PM review, 2026-11-23)

| # | Amendment | Adopted? | Where | Note |
| --- | --- | --- | --- | --- |
| A1 | Primary statistic per unit of gross exposure-time; shrink that; utilisation and capacity to Phase 5 | yes | sections 1.3, 5.1-5.3, 6.2, 9 | Flat days drop out of the statistic, which also settles the window-start conflict with ADR-A0051. Measurability now counts exposed days. The information ratio is reported because per-gross α penalises hedged books. |
| A2 | Gate 7b as a gap rate with a week-clustered one-sided 80% lower bound, threshold per day | yes | section 3.2 | Multi-day intervals are weighted by days. The test gives noisy residuals the benefit of the doubt (+8 bps/day passes at 0.5% noise); accepted because an equivalence version is infeasible and 7a/7d already require precision. |
| A3 | Provisional 10k sleeve; recompute Phase 4 if Phase 5 changes it | yes | sections 1.8, 4.1, 9.1, 12 (P4-9) | Exactly one recompute and one Phase 5 rerun, sizes then held fixed, so the loop ends. |
| A4 | Robustness on own data; DerSimonian-Laird τ²; compute τ² first and skip extras if it is robustly 0 | yes | sections 6.1-6.4, 7, 12 | Binding form: own α without the best week > 0. The own-data P ≥ 0.8 form is reported, not binding. "Robustly 0" = τ² = 0 and Q not significant at p = 0.20. |
| A5 | Coin betas once per origin from the 90 days before it; static-replica decomposition mandatory | yes | sections 5.2, 5.3, 8 | The same one-fit-per-origin rule applies to the coin covariance used for co-movement and in Phase 5. |
