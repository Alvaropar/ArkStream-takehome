# Phase 5: the two-sleeve paper scheme, its tests, the holdout and the deployment decision

Written 2026-11-23. **Revision 3.** It replaces revision 2, which designed allocation across a basket that the
Phase 4 v2 evidence does not support. Its ADRs are **0086-0095**, the next free numbers after the renumbering
(ADR-0085). The section 1 figures and the IC thresholds were corrected on 2026-11-23 to the published run, in which
α excludes funding (ADR-0084).

**Revision 4, the same day: the user's three decisions.**
1. **Live money on an E1 address needs its own ADR.** ADR-0072 makes E1 shadow-only. Gray is therefore defined by
   ADR-0090 as an **execution measurement paid as a research cost**, not an allocation (section 10.2).
2. **Limits scale whole sleeves, never single legs.** Each sleeve stays a scaled copy of its leader's tradable book
   (ADR-0073). The unconstrained copy is reported alongside (sections 3-4).
3. **D2 is also judged on the book that would hold capital:** the hand-off alone under the gray rules and the
   750 USDC loss cap, called G\* (sections 2, 6, 8-9).

**Status: accepted.** Written up as ADRs 0086-0095, which the user approved on 2026-11-24 before any Phase 5 result,
and ADR-0096, the engine details pinned before any P5-4 or P5-5 result. ADR-0097 pins the freeze mechanism, ADR-0098
(accepted by the user on 2026-11-24) adds the holdout cost runs B and C, ADR-0099 pins their details and the v2
holdout entry point before they were computed, and ADR-0100 pins the cutoff selection and the cutoff deliverables.

**Note of 2026-11-24, at the joint freeze (P5-7).** This text now agrees with the accepted ADRs 0086-0100 and with
the development results in [phase-5-results.md](phase-5-results.md). No rule changed in this edit.
- The user's choices of 2026-11-24 are written in as decided (section 15): P5 in the budget form with no waiver
  (sections 4 and 4.1), and option C for G\* with the stress cap on the remaining budget (section 10.2).
- The gray size is 2,500 USDC (section 10.2), and both risk-rule variants were rejected (section 6.2).
- `λ ≈ 0.15` is marked as the pre-run estimate, with the measured values beside it (sections 4.1 and 7).
- L1 is measured out of sample on the population (section 6.1).
- Runs B and C, the v2 holdout entry point and the cutoff selection are described in sections 8 and 10.3 (ADRs
  0098-0100); their development runs are in the results, section 9.
- Revision 2 was deleted, and this file took its name.

Scope and discipline come from ADR-0065:
- designed on development data only;
- every variant goes in the trial log;
- the decision rules are written before results;
- frozen together with the Phase 4 v2 specification in one hash;
- the holdout is opened once.

## 0. Where Phase 5 starts

- **Phase 4 v2 found no capital-grade evidence of skill** ([phase-4-v2-results.md](phase-4-v2-results.md)):
  - no E2 address at 3 Dec under any of the six specifications run (published, entry-day beta ×2, loosened evidence
    gates, gate 7b without flow intervals, funding removed);
  - ranking IC averages -0.030 and is positive at 1 of 4 origins;
  - the categories are not ordered;
  - the copy keeps about 16% of a leader's edge after costs and delay.
- **A direct GO is therefore rejected.** The plan's GO needs research validity, which is not met.
- **This phase decides between CONDITIONAL GO and NO-GO,** and that decision chooses the deployment protocol:
  **gray** (live micro-capital beside paper) or **paper** (no capital).

```
Phase 5 on development data (training + test windows)
   → joint freeze
   → holdout opened once: the chosen two-sleeve scheme
   → CONDITIONAL GO or NO-GO (section 9)
   → cutoff selection with the frozen rules
   → deployment protocol: gray or paper (section 10)
```

## 1. The two sleeves

| | 0x2cd9 | 0x971f |
| --- | --- | --- |
| Role | **formal hand-off** (the frozen Phase 4 rule's only 3 Dec hand-off) | **observation sleeve** (declared here, outside the hand-off) |
| Category at 3 Dec | E1 | E1 |
| α ± s, bps per day of gross (excluding funding) | 26.7 ± 61.9 (23.7 including funding) | 75.7 ± 44.9 (74.7 including funding) |
| Posterior P(α > 0) | 0.00: τ² is robustly 0 at 3 Dec, so every posterior is the point mass at μ0 = 0 | 0.00 (the same) |
| α without its best week | -8.7: **not robust** | 56.5: **robust** |
| Static / timing split | -2.6 / 29.3 | -20.3 / 96.1 |
| Exposed days | 47 | 79 |
| Book | about 91% of gross in HYPE, long only | BNB about 62%, BTC about 38%, long only |
| S2 (Phase 2) | pass | **fail: gate 7b only** |
| S3 (copyability) | pass | pass |

Sources: Phase 4 v2 results, 3 Dec table (`decision/phase-4-v2-3dec-e1-e2.csv`); books from the v1 audit `basket_concentration_2025-12-03.csv`.

**Why 0x971f is run.** This is a Phase 5 design choice. Phase 2 and Phase 4 are not changed.
1. **0x2cd9 alone is one HYPE bet.** At about 91% HYPE it could never meet a rule that no coin exceeds 40% of
   portfolio stress loss, the share form of P5 this design started from. A one-sleeve scheme would therefore test a
   "portfolio" that cannot exist inside our own limits. P5 is now the budget form (section 4), which a one-coin book
   can meet, but the point stands: one sleeve exercises none of the limits that bind across sleeves. 0x971f is the
   only robust E1 address at 3 Dec that is not in HYPE.
2. **It tests a multi-address strategy.** The things that only exist with two or more sleeves:
   - adding sleeve targets per coin and netting them (both books can hold BTC);
   - per-coin and portfolio limits that bind across sleeves;
   - participation shared within a 4h bar;
   - a risk state in one sleeve (pause, flatten) alongside a normal one.

**What 0x971f's status is, and is not.**
- **Why it is outside the hand-off.** It fails gate 7b by a hair: the gap-rate lower bound is 5.46 against 5.0
  bps/day. The whole gap is two intervals with recorded withdrawals (ADR-0069):
  - src_row 75841, 12 Oct, -420 USDC;
  - src_row 75852, 23 Oct, -728 USDC.

  In each, the residual equals the withdrawal. Without them the gap is -0.04 bps/day, against a rank agreement of
  0.995, a slope of 1.006 and tracking of 0.011.
- **Gate 7 is not changed.** 0x971f runs as an observation sleeve:
  - same engine, sleeve size and limits as 0x2cd9;
  - zero capital in every protocol;
  - **no path to capital unless it re-qualifies under the frozen rules** at the cutoff selection or a later review.
- **Adding it does not make the share form of P5 attainable.** When 0x2cd9 holds HYPE and 0x971f is flat, HYPE is
  all of the stress loss, and scaling 0x2cd9 as a whole cannot change that share. That is one reason P5 is the budget
  form (section 4.1). How often P5 binds, and how far the limits scale 0x2cd9 down, are **findings** of section 7,
  not assumptions.
- **Selection is in-sample on the development windows.** Both addresses were chosen with data up to 3 Dec, which
  covers every development test window. Development results for the pair therefore test the **machinery and the risk
  rules, not skill**. The holdout is the only out-of-sample test of this scheme.

## 2. The chosen strategy (what is frozen and tested)

**S\***: a paper copy of 0x2cd9 and 0x971f.
- **Sizing:** one sleeve of **10,000 USDC notional** each, the provisional Phase 4 size, so Phase 4 v2's P4-9 recompute
  is not triggered. Equal weight.
  - Frozen reference equity sizing (ADR-0052), copy multiplier `k_i = min(A_i / E_ref,i, 1)`, no scale-up.
  - 0x971f's equity (about 7.5k) is below its sleeve, so its sleeve is partly idle. That is reported as utilisation.
- **Coins:** each wallet's tradable universe (ADR-0073), with the 1.5x cap solved on the full book.
- **Rules:** execution as in section 3, limits as in section 4, risk states and triggers as in section 5.
- **No weighting variants.** With two sleeves there is nothing to optimise.
- **Two risk-rule variants** were settled at P5-4 (section 6.2). Both were rejected, so the current rules stay:
  - the cap denominator: the fixed allocation (kept) vs sleeve NAV;
  - `E_ref` at reviews: reset (kept) vs high-water mark.

Every test runs three configurations side by side, on the same leader events and the same costs:

| Configuration | What it is | Why |
| --- | --- | --- |
| **S\*** (the scheme) | both sleeves, 10k each, every limit and risk state | the strategy under test |
| **U\*** (unconstrained twin) | both sleeves, 10k each, only the sleeve gross cap S1 and the execution rules O1-O3 | the leader-shaped copy; S\* minus U\* is the effect and cost of the limits **[decision 2]** |
| **G\*** (the capital book) | the hand-off alone (0x2cd9) at the gray size, under the gray rules of section 10.2 and the 750 USDC loss cap | the book that would hold money; judged by D2b **[decision 3]** |

## 3. Execution model (simulated in the replay; the live engine is out of scope, ADR-0064)

1. **Leader state.** Fills update a virtual book per leader, using the measured 392 ms receive delay. Snapshots
   update equity, the `E_ref` review and resync.
2. **Sleeve target** per coin: `T_{i,c} = s_i · k_i · q_{i,c}`.
   - `q` is the leader's net position.
   - `s_i` is the risk state scalar (section 5).
   - Non-tradable coins have target 0.
3. **Aggregate target** per coin: `T_c = Σ_i λ_i · T_{i,c}`. `λ_i ∈ [0, 1]` is the sleeve's **limit scale**, set
   by section 4.1 so that every limit holds. **A limit never cuts a single leg:** when one binds, the sleeves that
   cause it are scaled as wholes, so each stays a scaled copy of its leader's tradable book (ADR-0073). Netting
   between sleeves happens only in the physical order; virtual attribution stays per sleeve.
4. **Order:** `Δ_c = T_c − held_c − pending_c`.
   - Deadband: `max(10 USDC, 2% of |T_c|)`.
   - After a 250 ms debounce, plus a 15-minute sweep.
   - Bounded-price IOC with a deterministic client id.
   - A partial fill, rejection or timeout recomputes `Δ` from state. The original size is never resent.
5. **Participation:** at most 0.5% of the latest completed 4h volume **per coin per bar, summed over both sleeves**.
6. **Flatten sweep:** when a leader is flat and its sleeve is not, close the residual reduce-only at the next sweep
   (pre-holdout Check 5).
7. **Stale signals:** older than 30 s at decision (PLACEHOLDER) → not executed; resync at the next decision.
8. **Funding** is booked as cash in the copy's PnL. It is reported separately from α.
9. **Where the copy may still differ from the leader's shape, and how that is shown.** Each difference is logged and
   reported as tracking error against the scaled target:
   - temporary, leg-level execution effects: participation clips (O1), sub-minimum skips and the deadband (O3), stale
     signals (item 7);
   - one risk state: REDUCE_ONLY does not open legs the leader opens during the state (section 5).

   No limit changes the book's shape.

## 4. Risk limits (ADR-0088)

**In the paper scheme every limit runs exactly as it would with capital**, on the paper book, and every time a limit
binds is logged. The percentages apply to the scheme's notional `D` = 20,000 (two 10k sleeves).

| # | Metric | Limit (PLACEHOLDER) | Checked | Action |
| --- | --- | --- | --- | --- |
| O1 | Participation per coin per 4h bar, both sleeves | ≤ 0.5% | every order | clip; remainder next bar (execution, leg-level) |
| O2 | Limit price vs decision mark | ≤ the stress-scenario p99 shortfall for the coin's liquidity bucket | every order | IOC at the bound (execution) |
| O3 | Minimum size, deadband | 10 USDC; 2% of target | every order | skip (execution) |
| O4 | Post-trade projection | no limit below breached | every target update | recompute `λ_i` (section 4.1) before any order |
| S1 | Sleeve gross | ≤ 1.5 × cap denominator (section 6.2) | every target update | scale the sleeve as a whole (ADR-0034) |
| S2 | Sleeve stressed loss | ≤ 25% of sleeve NAV | hourly and every target update | scale the sleeve as a whole |
| S3 | Sleeve drawdown from its high-water mark | -10% reduce-only; -15% flatten and pause | hourly | state machine |
| P1 | Portfolio gross | ≤ 1.5 × `D` | every target update | scale the contributing sleeves as wholes |
| P2 | Net per coin | BTC, ETH ≤ 25% of `D`; any other coin ≤ 10% per sleeve holding it and ≤ 20% in total | every target update | per-sleeve part: scale that sleeve; total part: scale the contributing sleeves (wholes) |
| P3 | Net BTC-equivalent beta (holdings-based) | ≤ 0.5 × `D` | every target update | scale the contributing sleeves as wholes |
| P4 | Portfolio stressed loss, plus exit cost | ≤ 15% of `D` | hourly and every target update | scale the contributing sleeves as wholes; a passive breach → reduce-only until below 90% |
| P5 | One coin's stress loss, summed over sleeves | ≤ 40% of the P4 budget: 40% × 15% × `D` = 1,200 USDC | hourly and every target update | scale the contributing sleeves as wholes; no waiver (section 4.1) |
| P6 | Drawdown ladder on the scheme's high-water mark | -5% halve new risk; -10% reduce-only; -15% flatten all, stop | hourly | state machine |

### 4.1 How a binding limit sets each sleeve's scale `λ_i` [decision 2]

1. **Start** from `λ_i = 1` for both sleeves at each leader-driven target update. The hourly checks can only lower
   `λ_i` (ADR-0096 item 2).
2. **Per-sleeve limits first** (S1, S2, the per-sleeve part of P2): each sleeve's `λ_i` is the largest value at or
   below its current one that satisfies them. Every leg is multiplied by the same `λ_i`, as ADR-0034 already does for
   the gross cap.
3. **Portfolio limits** (P1, the total part of P2, P3, P4), in that order:
   - the contributing sleeves are those whose positions add to the limited quantity in the breaching direction;
   - they are multiplied by **one common factor**, the largest that restores the limit;
   - sleeves that do not contribute are not touched.
4. **P5, the budget form (ADR-0088 item 6):** one coin's stress loss, summed over sleeves, is at most 1,200 USDC.
   It is solved last, like the other portfolio limits: one common factor on the sleeves whose positions in the coin
   add to its stress loss. There is no waiver.
   - The share form first written here (at most 40% of current P4 usage, waived when scaling cannot change the share)
     was not adopted. It jumps at the waiver, and with two coins it can leave no non-zero book that meets it.
5. **Repeat until nothing changes, deterministically.** The ordered pass repeats until no `λ_i` changes by more than
   1e-12 relative, at most 50 passes. A solve that does not converge sets the contributing sleeves to `λ = 0` and
   logs an engine fault. The order of the steps is fixed, and ties are broken by address order.
6. **Logged at every update:** each `λ_i`, which limit set it, and any P5 binding. The time-weighted and the
   exposure-weighted mean `λ_i` per sleeve are reported (ADR-0096 item 11).

**What this implied for 0x2cd9, before any run (the pre-run estimate).** The per-sleeve part of P2 allows at most
10% of `D` = 2,000 USDC in any coin other than BTC and ETH. At the full 1.5x gross, about 91% HYPE is roughly
13,650 USDC of HYPE. So whenever 0x2cd9 is near its full gross, `λ ≈ 2,000 / 13,650 ≈ 0.15`, and its **whole** sleeve
runs at about one-seventh. The HYPE leg is never cut alone. U\* shows the leader-shaped copy beside it.

**Measured at P5-5** ([phase-5-results.md](phase-5-results.md) section 7). 0x2cd9's leader runs at about 0.1x
leverage, so its 10k copy holds 5-14% of the sleeve on average (51% in the 8 Oct crash window). P2 binds only in the
hours when HYPE exceeds 2,000 USDC. Weighted by exposure, `λ` was 0.19 in the 8 Oct window and 0.34-0.81 in the
others. P5 never bound on the pair.

**Stress shock:** the largest adverse 24h move per coin since 1 Jul 2025, applied to every position at once (point in
time, ADR-0017), plus the exit cost at stress costs. The shock is fitted **once per origin**, on the history from
1 Jul 2025 to the origin. The coin covariance and betas are fitted on the 90 days before it (ADR-0088; Phase 4 v2
A5).

## 5. Risk states and triggers (ADR-0089)

**State machine** per sleeve: `NORMAL → HALVED → REDUCE_ONLY → FLATTEN → PAUSED → (review) → NORMAL or EXITED`. The
scheme-level state (P6) caps both sleeves; the more restrictive state wins.
- **Reduce-only** keeps the sleeve in the leader's shape on the legs it already holds. Their common scale may only
  fall: the largest value at which no held leg grows or flips sign. Legs the leader opens during the state are not
  opened. That is the one deliberate departure from the leader's shape; it is logged as tracking error.
- **HALVED** multiplies the whole sleeve by 0.5.
- **Flatten** sends reduce-only IOC slices within O1, or a TWAP of at most 60 minutes for coins under 1M USDC of 4h
  volume, at stress costs.

| # | Trigger | Threshold (PLACEHOLDER) | Action |
| ---: | --- | --- | --- |
| L1 | Leader drawdown beyond its own history | > 1.5 × its point-in-time max drawdown | REDUCE_ONLY |
| L2 | Leader leverage out of character | > 2 × its p95 | REDUCE_ONLY |
| L3 | Leader equity collapse | < 0.7 × `E_ref` | REDUCE_ONLY until review |
| L4 | Large withdrawal | > 50% of equity in 24h | REDUCE_ONLY |
| L5 | Leader liquidation or auto-deleveraging | any | FLATTEN, PAUSED |
| L6 | Leader drifts to non-tradable coins | > 10% of notional, trailing 7 days | REDUCE_ONLY; exit at review if it persists |
| L7 | Leader inactive | > 14 days | release at review |
| C1 | Copy execution degrades | rolling 14-day shortfall per side > the stress scenario's | REDUCE_ONLY |
| C2 | Copy drawdown | S3 | REDUCE_ONLY / FLATTEN |
| C3 | Feed stale or position mismatch | > 60 s while holding, or any unexplained difference | freeze increases; resync |

- **How the replay measures them** (ADR-0096 items 3-7):
  - a firing is a trigger's condition turning on, counted whatever the sleeve's state;
  - C1 compares the realised cost of each fill with the stress model's cost for the same order, model against model;
  - L6 is measured only once the run holds 7 full days of the leader book;
  - L7 uses a pre-window last fill only when it is known at the window start;
  - C3 has no data in the replay, so it is tested by fault injection.
- **Exit at a 14-day review:** a binding gate fails on data to the review, the category falls to E- or E0, the sleeve
  was paused through the whole period, or L7 applies.
- **Resume:** only at a review, after the trigger clears, and with a human decision. The replay models that decision
  as yes, and labels it so (ADR-0096 item 6).

## 6. Testing on development data (training and test windows)

### 6.1 Calibration on the training windows, on the population rather than the pair

Trigger firing rates are calibrated on **every A/B single-sleeve copy** (each copy is a basket of one) over the
training windows. That is the natural test set for sleeve-level rules, and it keeps the two chosen addresses out of
the calibration.

Reported per trigger:
- the firing rate per sleeve-month;
- the copy's 14-day return and drawdown after firing against matched days without firing (descriptive);
- the false-alarm share (firings followed by a non-negative 14-day return).

A threshold changes only if it fires more than once per sleeve-month (operational noise), never to improve return.

**Result (P5-4; [phase-5-results.md](phase-5-results.md) section 4):** F4 passes, and no threshold changed.
- On the training windows the highest rate is L6's, 0.48 firings per sleeve-month.
- L1 cannot fire on a training window, because its threshold comes from the same history.
- L1 was therefore **measured out of sample on the population**, over the four test windows (1,330 copy-windows),
  where its threshold is out of sample. It fires 0.37 times per sleeve-month, and at most 0.49 in any window.
  - The firings cluster: 25 of 157 came on 10-11 Oct.
  - 31 firings come from leaders with no drawdown before the origin, whose threshold is therefore 0. This is
    reported, not changed.

### 6.2 Risk-rule variants, chosen on the population

| Item | Current | Variant |
| --- | --- | --- |
| Cap denominator | 1.5 × fixed allocation | 1.5 × min(`A_i`, sleeve NAV) |
| `E_ref` at reviews | reset to the latest equity | high-water reference `max(E_ref,prev, E_latest)` |

- **Decided on all A/B single-sleeve copies** over the four development test windows, never on the pair.
- **Criterion:** keep the current rule unless the variant lowers the 95% expected shortfall of window returns by at
  least 20% at a mean cost of no more than 0.25 pp per window.
- **Result (P5-4): both rejected,** so the current rules stay. The cap denominator min(A, NAV) cut the ES95 by 1.3%,
  and the high-water `E_ref` by 1.6%.

### 6.3 The pair on the four development test windows

- **Run S\*, U\* and G\*** with the exact engine (one event loop over the sleeves) in four scenarios: optimistic, base,
  stress, and severe (60 s / 300 s).
- **Report, for each configuration:**
  - raw return, α (excluding funding, ADR-0084) and funding;
  - max drawdown, worst day, 95% expected shortfall;
  - time in each risk state and every trigger firing;
  - **each sleeve's `λ_i` over time, its time-weighted and exposure-weighted means, and which limit set it**,
    especially the per-sleeve P2 on HYPE;
  - P5 binding;
  - netting between sleeves (shared BTC);
  - participation clips, flatten-sweep closures;
  - utilisation, and the cost split (half-spread, fee, impact, drift).
- **S\* against U\*:** the return, drawdown and tracking error that the limits cost or save, per sleeve.
- **G\*:** the stress loss before each trade against the remaining budget (750 USDC minus the loss to date), the gray
  scale `λ`, and the loss path against the cap.
- **Context, not a test:** 200 random pairs of A/B copies per window through the same engine. This shows whether the
  pair's drawdowns and limit binding are typical.
- **Label in every table:** "selection in-sample on these windows; machinery test, not skill".

### 6.4 Stress tests

1. **Historical:** the 10-11 Oct path inside the 8 Oct window, in base and severe, for S\*, U\* and G\*. Report the
   state changes, the loss against the ladder (S\*) and against the 750 USDC cap (G\*), and the exit costs.
2. **At the limits:** S\* with both sleeves and the scheme at their maximum permitted exposure, and G\* at the largest
   exposure its stress cap allows, with the section 4 joint shock, severe delays and stress costs.

### 6.5 Pass criteria before the freeze (written before any Phase 5 run; PLACEHOLDERS)

| # | Criterion | Pass |
| ---: | --- | --- |
| F1 | Fault tests: every ladder and state transition both ways; reduce-only never increases \|position\|; flatten completes within O1 with its cost booked; resume refused outside a review; participation shared within a bar; stale signal dropped and resynced; flatten sweep closes a residual; the `E_ref` invariant | all pass |
| F2a | Stress at the limits, S\* (6.4.2) | loss ≤ 16.5% of `D` (the flatten step plus overshoot) |
| F2b | Stress at the limits, G\* (6.4.2) | loss including exit ≤ `L_gray` = 750 USDC |
| F3 | Historical stress (6.4.1) | the ladder and the G\* cap act as designed; no limit breached without its action |
| F6 | Shape | in S\* and G\*, every sleeve's targets equal `λ_i` × the U\* targets on every leg, apart from the logged execution effects and the REDUCE_ONLY rule (section 3, item 9) |
| F4 | Trigger noise (6.1) | each leader trigger ≤ 1 firing per sleeve-month on the population |
| F5 | Determinism | two runs byte-identical |

If a criterion fails, the rules are fixed on development data and logged, then retested. The criteria are not relaxed.

**Result:** F1-F6 all pass on development data ([phase-5-results.md](phase-5-results.md) section 6).

## 7. Development findings feed the memo

The development run was to show three things the memo needs. What it showed is in
[phase-5-results.md](phase-5-results.md) section 7.
1. **Whether a two-sleeve scheme of these books can live inside the limits:** 0x2cd9's `λ`, how often P5 binds, and
   S\* against U\*.
   - **The pre-run expectation:** `λ` for 0x2cd9 near 0.15 most of the time. The finding would then read "our
     per-coin limits let us hold a single-coin leader at about one-seventh of a sleeve; capital needs more
     independent sleeves". That would be a result, not a failure.
   - **Measured:** the leader's low leverage keeps the copy small, so P2 binds only when HYPE exceeds 2,000 USDC.
     The exposure-weighted `λ` was 0.19 in the crash window and 0.34-0.81 otherwise, and P5 never bound.
2. **What the risk machinery costs:** the trading cost of the risk actions, and their effect on drawdown in the crash
   window.
3. **Whether the costs match the model on these books:** the cost split, and participation clips on HYPE and BNB.

## 8. The holdout: opened once (ADR-0092)

**Joint freeze first** (ADR-0091). One hash covers:
- the Phase 4 v2 specification as decided in the freeze-decision trial-log entry, including the funding treatment;
- this document's rules, including the observation-sleeve declaration, ADRs 0086-0100, and the development results;
- `risk.yaml`, `execution.yaml`, `instruments.yaml`;
- every source the holdout path imports;
- the data, replay and selection manifests (pre-holdout Check 3), and the environment block;
- the window-report module, already run on all four development windows (Check 4);
- the cost rebuild, run C's refit, the v2 holdout entry point and the cutoff selection, run on development data
  (ADR-0098 item 8, ADR-0100);
- the pre-registered tests below.

The user sends the hash to the reviewers. No `HOLDOUT_FREEZE.txt` exists before the freeze writes it. The mechanism
details are pinned in ADR-0097.

**Run:** 3 Dec 2025 00:00 → 4 Jan 2026 00:00, 32 calendar rows. Selection at 3 Dec uses the frozen rules on data
before it, so the hand-off is 0x2cd9, with 0x971f as the observation sleeve. S\*, U\* and G\* run in all four
scenarios.

**If the cutoff hand-off differs** (section 10.3), that address's G\* is run on the same holdout window with the
frozen rules before any gray start, and it must pass D2b as well. This step is declared here, so it is part of the
single opening.

**Three runs in the one opening, one frozen strategy** (ADR-0098; details in ADR-0099):

| Run | Costs charged on fills | Cost model in the risk rules | Books | Role |
| --- | --- | --- | --- | --- |
| A | the frozen model, in the four scenarios | frozen | S\*, U\*, G\* | decides D1-D5 |
| B | the cost rebuild | frozen | S\*, U\*, G\* | reported; D3 and C1 are also read on B |
| C | the cost rebuild | refitted daily at 00:00 UTC on data before it | S\*, G\* | reported; a variant that decides nothing |

- **The cost rebuild** prices each order from the market at its own time. It is "rebuilt real conditions", not real
  fills:
  - a delay drawn per order from the measured per-draw distribution;
  - the Binance tape over that delay, on BTC, ETH, HYPE, SOL, BNB, AAVE and EIGEN;
  - the same day's Hyperliquid spread estimate, without the floor;
  - impact `y` fitted on the same day's taker orders;
  - no fill above the frozen O2 bound of the order's liquidity bucket.

  Each part falls back to the frozen value, flagged, when its data are short.
- **In C,** the spread and impact `y` are refitted on the trailing 14 days and the drift table at daily vintages. The
  refit feeds the stress limits (S2, P4, P5, `L_gray`) and the gray loss cap. C1 and O2 keep the frozen benchmark in
  every run; C logs a shadow C1 and a shadow O2 on its own model and never acts on them.
- **Order:** A runs first, and its outputs and D1-D5 entry are written before B or C starts. B and C never change the
  verdict. If B fails a condition that A passes, the memo's summary says so.
- **The entry points** (`phase5 holdout`, `src/arkstream/holdout.py`; `phase5 cutoff`, `src/arkstream/cutoff.py`)
  are refused by the freeze guard until the freeze holds. They enforce the P5-8 order (ADR-0100 item 5):
  1. run A (`--stage a`): the window's trees, marks and trigger series, then S\*, U\* and G\* and the H5 outcomes;
  2. the cutoff selection (`phase5 cutoff`, section 10.3), which waits for run A;
  3. D5 from it, the G\* rerun for a differing hand-off, the report and the D1-D5 decision entry
     (`--stage decision`), which wait for the cutoff selection;
  4. runs B and C (`--stage bc`), which wait for the decision entry.

  Both entry points were run on development data and compared with the development outputs (results, sections 9.6
  and 9.8).

**Pre-registered outputs:**

| # | Output | Role |
| ---: | --- | --- |
| H1 | Engine validity: the run completes; every state and limit event traceable; paper fills reconcile with the replay | decides (D1) |
| H2 | Risk behaviour: max drawdown, worst day, ladder and state events; S\* losses against the flatten step, G\* losses against the 750 USDC cap; `λ_i` paths and P5 binding | decides (D2a, D2b) |
| H3 | Cost model out of sample: median shortfall per side (base) by coin against the development distribution | decides (D3) |
| H4 | Returns of S\*, U\* and G\*: raw, α, funding, per sleeve and combined, with and without the 0x971f sleeve | **reported, not decisive**: 32 days × 2 sleeves cannot measure skill (MinTRL ≈ 1,600 days) |
| H5 | Cross-section, all measured addresses at 3 Dec: IC of the frozen statistic with holdout α; category ordering; the robustness and break-even hypotheses (pass vs fail, next α); carry books vs trading books | D4 uses the IC; the rest is reported and feeds the protocol's promotion test |
| H6 | Limit binding on the pair (P2, P5) out of sample | reported; feeds the memo |

## 9. Decision rule (pre-registered, ADR-0093)

**GO: rejected** (section 0).

**CONDITIONAL GO → gray protocol** if **all** of:

| # | Condition | Measure |
| ---: | --- | --- |
| D1 | The engine works out of sample | H1 clean; F1 fault tests pass on the frozen code |
| D2a | The risk design holds on the scheme | S\*, under base and stress: no loss beyond 16.5% of `D`; no limit breached without its designed action |
| D2b | The risk design holds on the book that would hold capital **[decision 3]** | G\* (the hand-off alone, gray size and rules), under base and stress: realised loss including exit ≤ `L_gray` = 750 USDC; its stress cap never breached without its action |
| D3 | The cost model holds | holdout median shortfall per side (base) ≤ the development p90 for the same coins |
| D4 | No contrary selection evidence | holdout IC of the frozen statistic `m` > -0.20 (two development window-sds below zero; the sd of the `m` IC is 0.101). When `m` is constant at the origin (as at 3 Dec), the IC of the own-data α instead, > -0.14 (sd 0.071; ADR-0093 item 4) |
| D5 | Something to trade live | the cutoff selection (frozen rules, data to 4 Jan) has a non-empty hand-off |

**NO-GO → paper protocol** if any condition fails.

The holdout's returns (H4) are reported in full, but they decide nothing beyond D2a and D2b. **CONDITIONAL GO here is not a
claim of skill.** It says the scheme behaves as designed out of sample, so a small, capped, live execution
measurement is worth its cost.

## 10. Deployment protocols (outlines; written in full after the holdout)

The final text, `decision/deployment-protocol.md`, is written after the holdout and the cutoff selection. It fills in
the findings (cost re-estimates, limit binding, the cutoff hand-off). **Its parameters are fixed here.**

### 10.1 Paper (NO-GO)

- **Capital:** none. The 100k stays in reserve as off-exchange USDC.
- **Run:** the frozen engine in paper on the cutoff hand-off plus the observation sleeve, with the unconstrained twin
  (U\*) beside it. Record:
  - signal times, intended orders and would-be fills against the live book at signal time;
  - slippage against the model, tracking, and every state and limit event.
- **Cross-sectional panel:** every 14 days, replay all A/B addresses, then compute the frozen statistic's IC and the
  category ordering.
- **Reviews:** every 14 days, with a summary every 8 weeks.
- **Revisit (move to gray or capital)** only if all of:
  - the pooled IC over at least 6 windows (holdout plus paper) is significant at one-sided 95%, using the development
    window-sd of 0.101. After 6 windows that means a mean of about 0.068 or more. When the pool uses the own-data α
    (`m` constant at any of its windows), the sd is 0.0706 and the bar about 0.047 (ADR-0094);
  - at least one E2 **trading** book (not carry) passes every stage;
  - the engine is clean.
- **Stop rule:** close the project after 6 months (PLACEHOLDER; kept by the user on 2026-11-24) if the revisit
  conditions are not met.

### 10.2 Gray (CONDITIONAL GO): an execution measurement, not an allocation (ADR-0090) [decision 1]

**Why it needs its own ADR.** ADR-0072 makes E1 shadow-only, and the hand-off is E1. Live money on it would
contradict ADR-0072 unless that money is something other than an allocation.

**ADR-0090** defines gray money as an **execution measurement paid as a research cost**:
- **Purpose:** measure real fills, not earn returns. The paper engine cannot observe delay, slippage, fees, partial
  fills and rejections as they really happen; this measures them for each live order against its paper twin.
- **Not an allocation:**
  - it is not counted as deployed capital and makes no skill claim;
  - it does not change any address's category;
  - its returns are never evidence for promotion.
- **Budget, fixed in advance:**
  - **`L_gray` = 750 USDC** (0.75% of the 100k), booked as a research expense;
  - at most **5,000 USDC** live;
  - it ends after at least 4 weeks and at least 200 live orders, or when the cap is hit, whichever comes first;
  - it cannot be extended or enlarged without a new ADR.
- **What ADR-0072 now says for E1:** its consequence reads "shadow-only; may serve as the signal source of an
  ADR-0090 execution measurement".
- **Fallback if ADR-0090 is not adopted:** gray stays paper. Then the two outcomes must mean different things, or the
  decision changes nothing:
  - CONDITIONAL GO → the paper protocol with its revisit path;
  - NO-GO → close the project.

**Mechanics:**
- **Live book = G\*:** the cutoff hand-off only.
  - The observation sleeve stays paper unless it re-qualifies under the frozen rules.
  - Live sleeve size: **2,500 USDC**. The rule was 5,000 if more than 10% of G\*'s intents fall under the 10 USDC
    minimum after `λ` (ADR-0090 item 6). At P5-5 none of 193 did; P5-1's unscaled share was 1.6%.
- **The live book's stress loss must stay within the remaining budget, `L_gray` minus the loss to date, at every
  target update and hourly** (ADR-0090 item 6). The cap is enforced by scaling the whole sleeve (section 4.1), never
  a single leg.
- **G\*'s limits are option C** (ADR-0088 item 7): the stress cap replaces S2 and P2-P5. O1-O4, S1 and S3 stay, and
  so does the P6 ladder. S3 and P6 run on the live book's own high-water mark. The absolute cap bounds the HYPE
  exposure in USDC directly.
- **Duration:** at least 4 weeks and at least 200 live orders. Daily reconciliation. Every resume needs a human
  decision.
- **Revert to paper when** the loss cap is hit (flatten), or when live shortfall exceeds the stress scenario for two
  consecutive reviews.
- **Escalation to a capital stage (15k):** only through the paper revisit conditions in 10.1, never on PnL.

### 10.3 The cutoff selection and the cutoff deliverables (both protocols; ADR-0100)

- **The cutoff selection** runs the frozen Phase 4 v2 pipeline at the cutoff origin, 4 Jan 00:00 UTC. That is the
  last midnight before the cutoff and the last origin the frozen replay admits, so the 4 Jan partial day is not used.
  - The pipeline builds, by the frozen functions: the drift tables, the Phase 2 tables, the all-priced tree's shared
    inputs, the cutoff training window of both trees, and the selection at that origin.
  - Its hand-off decides D5 and, if it differs from 3 Dec, the G\* rerun (section 8).
- **`trader_decisions.csv`:** every address in the package, with its grade, its category, the first gate it fails
  (S1, S2, S3 in order, the category, the duplicate screen) and its role (hand-off, observation, none).
- **`target_allocations.csv`:**
  - deployed 0 (paper), or the live sleeves (gray): at 2,500 each, at most two, ordered by category and then by D4's
    statistic;
  - the observation sleeve marked zero-capital;
  - the reserve.

## 11. Deferred until at least 3-4 capital-eligible candidates exist

These parts of revision 2 have nothing to act on with two sleeves:
- subset search and effective-number-of-bets selection;
- the three weighting rules (capped equal weight, inverse stress, equal risk contribution) and the risk-model blend;
- capacity grids beyond the gray sizing;
- 1,000-scheme evaluation and the pilot-horizon bootstrap;
- the account-structure (one account vs sub-accounts) and margin-contagion tests.

They come back with the first capital stage.

## 12. Where each operating question is answered

| Question in the written test | Answer |
| --- | --- |
| How decisions update on new history or trades | Fills update targets at once (section 3). Snapshots update `E_ref` at reviews, the triggers and the risk marks. The hand-off changes only at the 14-day review. |
| When instructions are generated | After the 250 ms debounce, plus the 15-minute sweep and the flatten sweep, through the deadband |
| Several sources on one contract | Sleeve targets are summed after each sleeve's limit scale `λ_i` is applied. A binding limit scales whole sleeves, never single legs; netting happens only in the physical order, and attribution stays virtual (sections 3 and 4.1) |
| Fills that differ from target | Recompute from state; never resend; reconciliation freeze after 3 cycles |
| When capital may increase and when risk must fall | Only through the revisit and escalation conditions (10.1-10.2); risk falls through the ladder, limits and triggers (sections 4-5) |
| When a human steps in | Every resume, every protocol change, L3-L5, the ladder at -10% and below |
| Set by hand or reviewed periodically | Loss caps and protocol (at each decision); limits and triggers (monthly); cost and delay scenarios against live or paper fills (monthly); the hand-off (14-day review) |

## 13. Development plan

| Step | Work | Output | Checks |
| --- | --- | --- | --- |
| **P5-0** | Write ADRs 0086-0095 from this document, including **ADR-0090** (gray as an execution measurement, with the ADR-0072 wording change) and whole-sleeve scaling in ADR-0088; trial-log entry; `risk.yaml` v3 with PLACEHOLDER labels; the decision rule (section 9) and holdout outputs (section 8) written in | ADRs, config | review only |
| **P5-1** | Replays: the two sleeves at 2,500 and 5,000 USDC, for gray sizing and the sub-minimum share (10k exists) | `research/replay_gray/` | byte-identical rerun |
| **P5-2** | Stress shocks and coin covariance, fitted once per origin | `risk_model/origin=<date>/` | leak test |
| **P5-3** | Engine: merged loop; the `λ_i` solver of section 4.1 (whole-sleeve scaling, P5 in the budget form); state machine; flatten sweep; stale-signal rule; shared participation; the U\* and G\* configurations from the same leader events; fault tests (F1) and the shape test (F6) | `portfolio_replay.py`, tests | F1, F6 |
| **P5-4** | Trigger calibration and risk-rule variants on all A/B single-sleeve copies (6.1-6.2); L1 out of sample on the test windows | `triggers_calibration.csv`, `l1_test_windows.csv`, variant table | F4; criterion as written |
| **P5-5** | S\*, U\* and G\* on the four test windows, 200 random pairs as context, stress tests (6.3-6.4) | `decision/phase-5-results.md` | F2a, F2b, F3, F5 |
| **P5-6** | Window-report module and the H5 cross-sectional tests, run on all four development windows; schema fixed | `holdout_report.py` | identical schema across windows |
| **P5-7** | Joint freeze (ADR-0091, details in ADR-0097); `verify_holdout_inputs.py`; the user sends the hash | `HOLDOUT_FREEZE.txt` | `freeze.guard` |
| **P5-8** | Holdout run once; report; decision by section 9 (ADRs 0092-0093) | holdout report, decision entry | report schema = development |
| **P5-9** | Cutoff selection with the frozen rules; `trader_decisions.csv`, `target_allocations.csv`; `deployment-protocol.md` (paper or gray, ADR-0094); memo | deliverables | the protocol parameters match section 10 |

**Order:** P5-0 → P5-1 and P5-2 → P5-3 → P5-4 → P5-5 → P5-6 → P5-7 → P5-8 → P5-9.

P5-0 also needed the Phase 4 freeze-decision entry (which variants are adopted), so the frozen Phase 4
specification is known. It was made on 2026-11-23.

**Status on 2026-11-24:** P5-0 to P5-6 are done on development data ([phase-5-results.md](phase-5-results.md)).
The user gave the go for P5-7. P5-8 and P5-9 each need their own go.

## 14. Assumptions the tests cannot settle (stated in the memo)

- **Live delays and fills.** Paper and the holdout measure the model, not real fills. Only the gray protocol measures
  real ones.
- **Order-book depth at arrival.** There is no historical book; impact is a square-root assumption.
- **Venue details:** Hyperliquid tiered margin, and auto-deleveraging of our own account.
- **Activity we cannot see:** isolated or spot positions of the leaders. Gate 7 screens for it but cannot rule it out.
- **Change after the cutoff:** the venue and API (A11), and re-qualification on current data at any live start (A12).

## 15. Decisions for the user (decided on 2026-11-24)

The user approved ADRs 0086-0095 on 2026-11-24, with the recommended option on every open item.
1. **ADR-0090 is adopted** (gray as an execution measurement paid as a research cost). The gray envelope is
   2,500 USDC per live sleeve, at most 5,000 live, and `L_gray` = 750 USDC.
2. **D4 and the stop rule.** D4 uses -0.20 on `m`, or -0.14 on the own-data α when `m` is constant at the origin
   (ADR-0093 item 4). The paper stop rule stays at 6 months.
3. **P5 is the budget form**, at 1,200 USDC with no waiver (ADR-0088 item 6). The waiver and the strict share form
   were both set aside.
4. **The observation sleeve gets no capital** unless it re-qualifies under the frozen rules.
5. **The Phase 4 freeze-decision entry** was made on 2026-11-23 (ADR-0091 item 1).
6. **Also decided on 2026-11-24:**
   - G\* uses option C (ADR-0088 item 7);
   - the gray stress cap uses the remaining budget (ADR-0090 item 6);
   - the sub-minimum test is measured on G\* after `λ` (ADR-0090 item 6), which set the size at 2,500 USDC at P5-5;
   - the small pinned details are accepted as written.
