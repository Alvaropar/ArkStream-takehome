# Phase 5: capital allocation, risk management and execution — methodology and development plan

Written 2026-11-23. **Revision 2, the same day:** follows the PM's Phase 4 amendments:
- A1: skill is measured per unit of gross exposure, and utilisation is applied here;
- A3: a provisional 10k sleeve with a one-pass recompute;
- A5: the risk model is fitted once per origin.

It also fixes a conflict in revision 1: at a 15k stage, the 25% per-sleeve cap (3,750) sat below the 5,000 minimum
sleeve.

**Status: proposal.** It becomes binding when written up as ADRs 0076-0083 and before any Phase 5 result is computed.
Scope and discipline come from ADR-0065:
- designed on the four development windows only;
- every variant goes in the trial log;
- choice criteria are written before results;
- frozen together with [Phase 4 v2](phase-4-v2-methodology.md) in one hash;
- the holdout is opened once and tests the whole scheme.

Points adopted from the external Phase 4 review are marked **[ext]**.

---

## 0. What Phase 5 must deliver

The written test asks for:
- a launch decision;
- the address set and how it forms a portfolio;
- the capital arrangement and the number of addresses;
- how unallocated capital is handled;
- risk limits, pause and exit conditions;
- the operating arrangement (decision updates, instruction timing, multiple sources on one contract, fills vs
  targets, capital increases and risk cuts, manual intervention).

Phase 5 turns each of these into a **mechanical, simulated and tested rule**. Section 9 maps every question to where
it is answered.

**Inputs from Phase 4 v2** (`research/selection_v2/origin=<date>/`), per origin:
- the E1 and E2 addresses, each with:
  - posterior alpha `m_i` **per unit of gross exposure-time** (scale-free);
  - utilisation `ū_i` (p50 / p95 gross per unit of allocation);
  - capacity inputs and exposure profiles;
- the co-movement matrices, including exposure-based risk correlation;
- the tradable coin set;
- the ranking-validation flag, which says whether posterior alpha may order the eligible set;
- the τ² "robustly 0" flag. When it is set, there are no E2 addresses and only a shadow scheme is built.

Phase 4 is computed at a **provisional 10,000 USDC sleeve** (Phase 4 v2, section 9.1). An expected sleeve return is
always `m_i · ū_i · A_i`: skill times how much of the allocation the copy actually uses.

**What exists today:** each address is replayed separately (frozen `E_ref`, 1.5x cap, 0.5% participation, measured
delays, square-root impact). Portfolio-level netting, shared margin and portfolio limits were never simulated
(ADR-0064). The development figures today:
- capture 0.157;
- gap 49% half-spread, 27% fees, 15% impact;
- delay drift 20 USDC in base and 953 in stress;
- worst basket drawdown -7.8%.

## 1. Principles

1. **The pilot is a measurement experiment with a loss budget.** Its job is to measure slippage, tracking and capture
   at a bounded cost, not to maximise return. MinTRL is about 1,600 days, so returns cannot be the scaling signal.
2. **Every limit is derived from the budget.** Development data calibrates only how often a rule fires and what it
   costs, never which threshold gave the best return.
3. **Simplest rule wins** unless a more complex one beats it by a margin stated in advance.
4. **Diversification is decided here, on the combined book** (Phase 4 v2, section 8). It is a choice of which sleeves
   to hold and how much, not only a cap on positions.
5. **Everything is point in time and simulated before the freeze.** A rule the replay does not execute is not part of
   the scheme (ADR-0065).
6. **No credit for missing evidence.** An unmeasured pair counts as correlation 1. An unpriced position counts at its
   stress loss.

## 2. Account structure and execution model

### 2.1 Structure (ADR-0076)

| Option | For | Against |
| --- | --- | --- |
| **A. One trading account (cross margin), virtual sleeves** | One book for portfolio limits and the drawdown ladder; orders for one coin are netted across leaders (the plan's live model; answers "several sources, one contract" directly); one reconciliation | A sleeve's loss draws on shared margin |
| B. One sub-account per sleeve | Exact isolation; matches today's per-address replay | Portfolio limits need cross-account aggregation; no order netting; N reconciliations |

- **Default: A**, with the reserve in a separate account that the trading account cannot draw on.
- **Switch to B** only if the margin-contagion test (section 7.4) shows that a single sleeve's stressed loss at its
  limits can push the account's maintenance-margin ratio above 25%.
- Under the gross caps here (portfolio 1.5x), that is not expected.

### 2.2 Execution model (what the engine does, and what the replay simulates)

1. **Leader state.** Fills update a virtual book per leader (WebSocket `userFills`; the replay uses the measured
   392 ms receive delay). Snapshots (`clearinghouseState`) update equity, the `E_ref` review and resync.
2. **Sleeve target** per coin: `T_{i,c} = s_i · k_i · q_{i,c}`.
   - `q` is the leader's visible net position.
   - `k_i = min(A_i / E_ref,i, 1)` is the frozen copy multiplier (ADR-0052, no scale-up). It is not the posterior
     alpha `m_i`.
   - `s_i ∈ {1, 0.5, reduce-only, 0}` comes from the risk state machine (section 5).
   - The sleeve cap is projected on the leader's **full** book; non-tradable coins have target 0 (Phase 4 v2, section 4.2).
3. **Aggregate target** per coin: `T_c = Σ_i T_{i,c}`, projected onto the portfolio limits (section 4). When a limit
   binds, the risk-increasing sleeve contributions are cut pro rata. Each sleeve keeps its virtual attribution even
   when physical positions cancel.
4. **Order:** `Δ_c = T_c − held_c − pending_c`.
   - Sent only if `|Δ_c| > max(10 USDC, 2% of |T_c|)` (deadband).
   - After a 250 ms debounce, plus a sweep every 15 minutes.
   - Bounded-price IOC with a deterministic client order id.
   - A partial fill, rejection or timeout recomputes `Δ` from exchange state. The original size is never resent.
5. **Participation:** at most 0.5% of the coin's latest completed 4h volume **per coin per bar, summed over all
   orders**. This closes the per-order loophole in pre-holdout Check 6.
6. **Flatten sweep:** when a leader is flat and its sleeve is not (pre-holdout Check 5: 1.4-2.4% of exposure-time),
   close the remainder reduce-only at the next sweep, independently of leader events.
7. **Staleness:** a signal older than 30 s at decision (PLACEHOLDER; the stress delay is 5 s) is not executed late.
   The target is resynced from leader state at the next decision instead.
8. **Reconciliation:** exchange state is authoritative. A drift beyond tolerance for 3 cycles freezes that coin and
   alerts.

**What the replay will and will not simulate:**
- Items 2-7 are simulated (section 6).
- Order netting across sleeves (item 3's physical netting) is **not** credited in the base result. Sleeves are
  executed separately, which overstates cost slightly. The saving is measured separately as an upside.
- Item 8 is an operating rule (live engine out of scope, ADR-0064).

## 3. Capital allocation

### 3.1 The capital stack (ADR-0077)

| Layer | Stage 0 Shadow | Stage 1 | Stage 2 | Stage 3 cap |
| --- | ---: | ---: | ---: | ---: |
| Deployed `D` (trading account) | 0 | **15,000** (CONDITIONAL GO) or **30,000** (GO) | 60,000 | 80,000 |
| Reserve (separate account, USDC) | 100,000 | 85,000 / 70,000 | 40,000 | ≥ 20,000 |

- **Unallocated capital.** If total sleeve capacity is below the stage's `D`, the shortfall stays in the reserve. It
  is never parked in the trading account.
  - The reserve is held as USDC: not lent, not staked, not used as margin.
  - It **never tops up a losing sleeve**; there is no averaging down.
  - It moves into the trading account only at a stage gate.
- Inside the trading account, idle margin from a sleeve not using its full allocation counts toward deployed capital.
  It is reported as utilisation, the share of `D` actually at risk.
- Stage amounts are PLACEHOLDERS from the plan (`config/risk.yaml`). Stage 1 at 15k applies when the Phase 4
  evidence is "positive but underpowered".

### 3.2 Sleeve capacity (ADR-0078)

`cap_i = min(E_ref,i, A*_i)`, rounded down to the sleeve grid {2.5k, 5k, 7.5k, 10k, 15k}.
- **`E_ref,i`:** under no scale-up a leader cannot absorb more than its own equity (0x971f: about 7.5k).
- **`A*_i`:** the largest grid size at which the training-window copy has at most 2% of intended notional clipped by
  participation and capture no more than 10% below the 2.5k copy (PLACEHOLDERS).
- This comes from replaying all A/B addresses at each grid size. Sleeves are only ever sized on the grid, so every
  evaluated sleeve has an exact replay.
- **Minimum sleeve `A_min` = 5,000:** below it, more than about 5% of orders fall under the 10 USDC minimum (plan:
  4.7% at 5k). A leader whose capacity is under `A_min` cannot be held.
- **Number of sleeves:** `K ≤ floor(D / A_min)`, so 3 at 15k and 6 at 30k. It is also limited by how many eligible
  sleeves pass the constraints below. `K = 0` is valid.
- **Largest sleeve:** `max(25% of D, A_min)`. That is 5,000 at 15k (three sleeves at most), 7,500 at 30k and
  15,000 at 60k.
- **Sizes and the Phase 4 loop [A3]:**
  - At stage 1 no sleeve exceeds 10k, so Phase 4's 10k-based T3 and equity band are conservative. The 15k grid point
    is used only from stage 2.
  - If any chosen size differs from 10k, Phase 4 is recomputed **once** on the chosen-size trees (Phase 4 v2, P4-9).
    Construction (section 3.3) is then rerun **once** with the sizes held fixed. The loop stops there.

### 3.3 Inclusion and weights (ADR-0079): diversification lives here

**Eligible set:**
- the Phase 4 v2 E2 addresses for a capital stage;
- E1 ∪ E2 for the shadow stage (labelled shadow-only).

**Risk model, point in time [A5]:**
- `Σ`: coin covariance from Hyperliquid daily marks over the 90 days before the origin (EWMA, half-life 30 days),
  with Ledoit-Wolf shrinkage. It is fitted **once at each origin or review** and not re-estimated within a window.
  The coin betas are fitted the same way (Phase 4 v2, section 5.2).
- `e_i`: sleeve exposure profiles at p50 and p95 utilisation (Phase 4 v2 hand-off).
- Sleeve covariance: `C = E Σ E'`, conservatively blended: `ρ_ij = max(exposure-based ρ_ij, realised ρ_ij on
  both-exposed days)`.
- Unmeasured pairs are set to `ρ = 1` **[ext 8.3]**.

**Three weighting rules (the variants):**

| Rule | Weights |
| --- | --- |
| R1 Capped equal weight | `w_i = min(cap_i, D / K)` |
| R2 Inverse stress | `w_i ∝ 1 / SL_i`, where `SL_i` is the sleeve's stressed loss per unit of allocation at p95 utilisation (section 4.3 shock) |
| R3 Equal risk contribution | on `C`, with the same caps |

All three are subject to:
- capacity `cap_i`;
- the floor `A_min` (else 0);
- at most `max(25% of D, A_min)` per sleeve;
- the construction constraints below.

**Construction constraints**, checked at p95 utilisation:
- the portfolio stress loss (section 4.3) ≤ 15% of `D`;
- no coin above 40% of the stress loss;
- `|net BTC-equivalent beta|` ≤ 0.5 × `D`;
- the net per-coin limits of section 4.2 not binding at p50 utilisation.

**Subset choice:** enumerate every subset of the eligible set up to `K`. With 25 eligible and `K = 6` that is about
177k subsets, which is feasible.
- For each subset, apply the chosen weighting rule and discard it if any constraint fails.
- Among the feasible subsets, choose the one with the highest effective number of bets
  `ENB = (Σλ)² / Σλ²`, where λ are the eigenvalues of the weighted correlation.
- Ties go to the higher expected return `Σ w_i · m_i · ū_i` (per-gross skill times utilisation, **[A1]**), but
  **only if** Phase 4 v2's ranking validation passed. Otherwise ties go to fewer sleeves, then to address order.
- A HYPE-concentrated leader is not excluded by a pairwise threshold. It gets the weight the stress and coin-share
  constraints allow, possibly 0.

**Choice between R1-R3:** keep R1 unless R2 or R3 lowers the 95% expected shortfall of window returns across the
random schemes (section 7.2) by at least 20%, while lowering the mean by no more than 0.25 pp per window. Ties go to
the simpler rule.

### 3.4 Sizing mechanics to settle (ADR-0080; at most two variants each)

| Item | Today | Variant | Why |
| --- | --- | --- | --- |
| Cap denominator | 1.5 × fixed allocation | 1.5 × min(`A_i`, sleeve NAV) | After copy losses the copy's leverage on its own capital rises today |
| `E_ref` at reviews | reset to the latest usable equity | high-water reference `max(E_ref,prev, E_latest)` | 483 of 2,041 reviews in the 3 Dec training window raised the multiplier after the leader lost, which re-levers into losers |

Same criterion as R1-R3. Simplest wins.

### 3.5 Reviews and rebalancing

- Weights, inclusion, `E_ref` and capacity are recomputed only at the 14-day review, aligned with the `E_ref`
  schedule, from data up to the review.
- Between reviews only the risk state machine changes exposure.
- No rebalancing toward losers from the reserve.

## 4. Risk limits (ADR-0081)

### 4.1 The risk budget

- **Pilot loss budget `L` = 5% of the 100k = 5,000 USDC (PLACEHOLDER, sign-off item).** It is approved per stage: the
  USDC amount is re-signed at each stage gate, and the percentages below stay fixed.
- At `D` = 30k, the flatten step (-15% of `D`) is 4,500 USDC. The flatten cost and any overshoot must fit within the
  remaining 500 USDC, which the simulation checks (section 7.6).

### 4.2 The limit set

| Level | # | Metric | Limit (PLACEHOLDER) | Checked | Action |
| --- | --- | --- | --- | --- | --- |
| Order | O1 | Participation per coin per completed 4h bar, all orders | ≤ 0.5% | every order | clip; remainder next bar |
| Order | O2 | Limit price vs decision mark | ≤ stress-scenario p99 shortfall for the coin's liquidity bucket | every order | IOC at the bound; recompute |
| Order | O3 | Minimum size and deadband | 10 USDC; 2% of target | every order | skip |
| Order | O4 | Post-trade projection | no limit below breached | every risk-increasing order | block the increase |
| Sleeve | S1 | Gross exposure | ≤ 1.5 × cap denominator (section 3.4) | every order | scale all coins together (ADR-0034) |
| Sleeve | S2 | Stressed loss (section 4.3) | ≤ 25% of sleeve NAV | hourly mark and pre-trade | block increases |
| Sleeve | S3 | Drawdown from the sleeve's high-water mark | -10% reduce-only; -15% flatten and pause | hourly mark | state machine (section 5) |
| Portfolio | P1 | Gross exposure | ≤ 1.5 × deployed NAV | every order | pro-rata cut |
| Portfolio | P2 | Net per coin | BTC, ETH ≤ 25% of deployed NAV each; any other coin ≤ 10% per sleeve holding it and ≤ 20% in total | every order | pro-rata cut of risk-increasing contributions |
| Portfolio | P3 | Net beta, holdings-based BTC-equivalent | ≤ 0.5 × deployed NAV | every order | pro-rata cut |
| Portfolio | P4 | Stressed loss (section 4.3), plus exit cost | ≤ 15% of deployed NAV | hourly mark and pre-trade | block increases; a passive breach → reduce-only until below 90% of the limit |
| Portfolio | P5 | One coin's share of P4 | ≤ 40% | hourly mark | block increases in that coin |
| Portfolio | P6 | Drawdown ladder on deployed NAV's high-water mark | -5% halve new risk; -10% reduce-only; -15% flatten all, stop, human review | hourly mark | state machine |
| Account | P7 | Maintenance margin / account equity | ≤ 25% | hourly mark | reduce-only; alert |

**Why P4 = 15%:** a repeat of the worst observed 24h move in every coin at once, at full permitted exposure, lands
at the flatten step and stays inside the budget. Gradual losses are handled by the ladder. For alt-heavy books, P4
binds well before the 1.5x gross cap. That is intended: the gross cap is the backstop and the stress limit is the
real limit.

### 4.3 The stress shock

- Per coin: the largest adverse 24h move observed since 1 Jul 2025, point in time (the Phase 2 `stress_horizon_h`
  shocks, ADR-0017), applied to each position in its adverse direction **at the same time**. This is conservative for
  hedged books.
- Plus the exit cost at stress-scenario spreads and impact.
- An unpriced position counts at its stress loss with a 100% shock.

## 5. Pause, exit, resume and capital changes (ADR-0082)

### 5.1 Risk state machine

Per sleeve:
`NORMAL → HALVED → REDUCE_ONLY → FLATTEN → PAUSED → (review) → NORMAL or EXITED`

Portfolio: the same states, driven by P6. The portfolio state caps every sleeve's state; the more restrictive wins.

- **Reduce-only** copies the leader's reductions and blocks increases.
- **Flatten** sends reduce-only IOC slices within O1.
  - Thin coins (latest 4h volume under 1M USDC): TWAP over at most 60 minutes.
  - Costed at the stress scenario.

### 5.2 Triggers

| # | Trigger | Data | Threshold (PLACEHOLDER) | Action | Human? |
| ---: | --- | --- | --- | --- | --- |
| L1 | Leader drawdown beyond its own history | leader book, hourly | > 1.5 × its point-in-time max drawdown | sleeve REDUCE_ONLY | review |
| L2 | Leader leverage out of character | leader book, hourly | > 2 × its p95 | REDUCE_ONLY | review |
| L3 | Leader equity collapse | snapshots | < (1 − 0.3) × `E_ref` | REDUCE_ONLY until review | yes |
| L4 | Large withdrawal | `net_deposit` | > 50% of equity in 24h | REDUCE_ONLY | yes |
| L5 | Leader liquidation or auto-deleveraging | fills | any | FLATTEN, PAUSED | yes |
| L6 | Leader drifts to non-tradable coins | fills, trailing 7 days | > 10% of notional | REDUCE_ONLY; exit at review if it persists | review |
| L7 | Leader inactive | fills | > 14 days | release the allocation at review | no |
| C1 | Copy execution degrades | own fills, rolling 14 days | realised shortfall per side > the stress scenario's | REDUCE_ONLY | yes |
| C2 | Copy drawdown | sleeve NAV | S3 (-10% / -15%) | REDUCE_ONLY / FLATTEN | yes at -15% |
| C3 | Feed stale or position mismatch | WebSocket vs `clearinghouseState` | > 60 s while holding, or any unexplained position difference | freeze increases; resync | if not cleared in 10 min |
| P | Portfolio ladder, stress breach, margin | section 4 | P4, P6, P7 | as in section 4 | yes at -10% |
| O | Venue incident, oracle anomaly, reconciliation drift for 3 cycles, key incident | ops | any | REDUCE_ONLY all; freeze coin | yes |

### 5.3 Exit, resume and capital changes

- **Exit at a review** (the sleeve is removed and its capital released to the reserve) when:
  - the address fails a binding Phase 2 or S3 gate, rerun on data to the review;
  - its Phase 4 v2 category falls below E2 (or below E1 in shadow);
  - it was PAUSED through the whole period;
  - L7 applies.
- **Resume:** only at a review, only if the trigger has cleared and the address re-qualifies under the frozen
  Phase 4 v2 rules, and only with human sign-off. After a portfolio flatten (P6 at -15%), the scheme restarts from
  shadow.
- **Capital increases:** only at a stage gate, and **never because of PnL alone**. All of the following must hold:
  - at least 28 days at the stage;
  - at least 200 copy orders;
  - realised shortfall inside the base scenario's 80% band;
  - daily tracking error against the paper target ≤ 0.5% of `D` (PLACEHOLDER);
  - the ladder never went past -5%;
  - no open incident;
  - signed off.
- **Capital decreases** are automatic through the ladder and the exits.

### 5.4 How triggers are calibrated

- Use all A/B copies over the training windows (to calibrate) and the four development test windows (to evaluate).
- For each trigger, report:
  - how often it fires per sleeve-month;
  - the copy's return and drawdown in the 14 days after firing against matched days without firing (descriptive);
  - its false-alarm share (firings followed by a non-negative 14-day copy return).
- Thresholds come from the risk logic above. A threshold is changed only if the trigger fires more than once per
  sleeve-month (operational noise), never to improve return.

## 6. Simulation architecture (ADR-0083)

1. **Sleeve trees.** Replay all A/B addresses at each grid size (section 3.2) on the Phase 4 v2 tradable universe,
   with the flatten sweep and the per-bar participation of section 2.2. Five grid sizes × about 17 minutes ≈ 1.5
   hours.
2. **Exact portfolio engine** (`portfolio_replay.py`):
   - one event loop merging the chosen sleeves' decisions by time;
   - sleeve targets come from the existing replay functions (`batches`, `reference_equity`, `cap_legs`,
     `order_inputs`, `quotes`, `execute`);
   - the portfolio projection (section 4) and the state machine (section 5) run inside the loop. Reduce-only
     interacts with pending orders and netting, so it cannot be applied after the fact;
   - per-coin participation is shared across sleeves;
   - outputs: sleeve and portfolio ledgers, a state timeline, a limit-binding log, overlay cost, utilisation, and the
     netting saving measured on the side.
3. **Fast approximation for many random schemes.** Sum the sleeve ledgers, then apply the state machine as
   path-dependent scalars on each sleeve's PnL increments, with the scaling trades charged at stress cost. A flatten
   is exact (PnL stops, plus the exit cost); halve and reduce-only are approximate.
   - **Validated before use:** on the selected schemes and 20 random schemes per window, compared with the exact
     engine.
   - Pass: |window return difference| ≤ 0.25 pp and the same ladder events.
   - Otherwise the exact engine is used everywhere.
4. **Guarantees:** point in time, seeded and byte-identical on rerun, holdout refused without the freeze (`freeze.guard`).

## 7. Testing before the holdout

### 7.1 Unit and fault tests (each with an expected end state)

The plan's fault table, plus:
- the pro-rata projection cuts only risk-increasing contributions;
- every ladder and state transition, in both directions;
- reduce-only never increases `|position|`;
- flatten completes within O1 and its cost is booked;
- resume is refused outside a review;
- the reserve is never debited by trading;
- the `E_ref` invariant holds (a leader's equity change with fixed positions moves nothing);
- participation is shared across sleeves in one bar;
- a stale signal is dropped and resynced;
- the flatten sweep closes a residual;
- an unmeasured pair is treated as `ρ = 1` in construction.

### 7.2 Development evaluation

At each development origin:
- Phase 4 v2 eligible set → section 3 construction → the exact engine over the next 14 days.

Baselines on the same windows:
- 1,000 random schemes: random subsets of the eligible set with the same construction and the same risk rules;
- all-A/B random schemes;
- the eligible set at equal weight with no overlay;
- cash.

Scenarios: optimistic, base, stress and severe (60 s / 300 s).

Reported:
- raw and holdings-adjusted return;
- max drawdown, 95% expected shortfall (daily), worst day;
- time in each state and the number of trigger firings;
- overlay cost, turnover, capture, utilisation, netting saving;
- each window with and without 10-11 Oct.

### 7.3 Historical stress

The 8 Oct window contains 10-11 Oct. Report the full scheme's path through it: state changes, losses against the
budget, and exit costs. Repeat at severe delays.

### 7.4 Hypothetical stress at the limits

- Set every sleeve and the portfolio at their maximum permitted exposure at the same time.
- Apply the section 4.3 joint shock with severe delays and stress costs.
- Check: the loss is within `L`, and P7 is not breached (the margin-contagion test of section 2.1).

### 7.5 Pilot-horizon bootstrap

- Synchronized calendar-block bootstrap of the sleeves' daily returns **[ext 6.2]**: the same calendar blocks for
  every sleeve, so cross-sleeve dependence is kept.
- Data: from 8 Sep to 2 Dec; block lengths 5, 7 and 10 days; horizons 30 and 60 days; with the ladder and the sleeve
  rules applied to each path.
- Outputs:
  - the probability of hitting -5%, -10% and -15%;
  - the probability of exiting a sleeve whose later return was non-negative (a false exit);
  - the loss distribution against `L`.

### 7.6 Pass criteria (written before any Phase 5 run; PLACEHOLDERS)

| Criterion | Pass |
| --- | --- |
| Hypothetical stress at the limits (7.4) | loss ≤ `L`; margin ratio ≤ 25% |
| Bootstrap, 30 days (7.5) | P(-15%) ≤ 5%; P(-10%) ≤ 15% |
| Flatten overshoot (7.3-7.5) | the realised loss at flatten, including exit cost, ≤ 16.5% of `D` (inside `L` at 30k) |
| Overlay cost in base (7.2) | ≤ 15 bps of `D` per window on average |
| Trigger noise (5.4) | ≤ 1 firing per sleeve-month for each leader trigger |
| Fault tests (7.1) | all pass |

**If a criterion fails:** the scheme is redesigned on development data (logged), or the stage is lowered (shadow
only). The criteria are not relaxed.

### 7.7 Variant choices (all logged; criteria as in sections 3.3-3.4)

- the weighting rule (R1, R2, R3);
- the cap denominator (two options);
- the `E_ref` policy (two options);
- the account structure (A or B, by the 7.4 test).

At most three variants per item, chosen before the holdout. None is chosen by a holdout result.

## 8. Freeze and holdout (a new ADR)

**One joint freeze**, which replaces the void ADR-A0141 hash. It covers:
- `decision_context.yaml` v2 and `risk.yaml` v2;
- `execution.yaml` and `instruments.yaml`;
- every Phase 2, Phase 4 v2, replay and Phase 5 source;
- the data manifests and the replay and selection output manifests (pre-holdout Check 3), plus the environment block;
- the window-report module, already run on all four development windows (Check 4).

The hash is sent to the reviewers before the run.

**Holdout run, once:**
1. Phase 4 v2 at 3 Dec.
2. Phase 5 construction at 3 Dec.
3. The exact engine from 3 Dec 2025 00:00 to 4 Jan 2026 00:00: 32 calendar rows, with the count of valid returns
   stated.
4. The report uses the development-window schema.
5. The outcome goes into the plan's decision table (GO / CONDITIONAL GO / NO-GO) and the memo. No retuning.

**Selection at the cutoff:** the frozen rules applied once at 2026-01-04 23:59:42 UTC produce `trader_decisions.csv`
and `target_allocations.csv`. These are the configuration a launch would start from. Under A12, a live start still
needs re-qualification on current data.

## 9. Where each operating question is answered

| Question in the written test | Answer |
| --- | --- |
| How decisions update on new account history or trades | Fills update targets at once (section 2.2). Snapshots update `E_ref` at reviews, leader triggers and risk marks. Inclusion and weights change only at the 14-day review (section 3.5) or through the state machine. |
| When instructions are generated | After the 250 ms debounce, plus the 15-minute sweep and the flatten sweep, through the deadband and minimum size (section 2.2) |
| Several sources on one contract | The sleeve targets are summed, then projected onto the portfolio limits, with pro-rata cuts of risk-increasing contributions; virtual attribution is kept (section 2.2, items 3-4) |
| Fills that differ from target | Recompute `Δ` from exchange state; never resend; reconciliation freeze after 3 cycles (section 2.2, items 4 and 8) |
| When capital may increase and when risk must fall | Stage gates on operational evidence (section 5.3); the ladder, stress limit and triggers (sections 4-5) |
| When a human steps in | The "Human?" column in section 5.2; every resume, stage change and override |
| Set by hand or reviewed periodically | Risk budget and stages (each stage gate); limits and trigger thresholds (monthly); the spread, impact and delay scenarios against live fills (monthly); the tradable universe and capacity (each review); the eligible set and weights (14-day review) |

## 10. Development plan

| Step | Work | Output | Checks |
| --- | --- | --- | --- |
| **P5-0** | Write ADRs 0076-0083 from this document and `risk.yaml` v2 with PLACEHOLDER labels; write the pass criteria (7.6) and variant criteria; trial-log entry | ADRs, config | review only |
| **P5-1** | Sleeve trees at the grid sizes; capacity `cap_i` per address and origin | `research/replay_grid/`, `capacity.parquet` | byte-identical rerun; capacity non-increasing in clipping |
| **P5-2** | Risk model: EWMA and Ledoit-Wolf `Σ`, coin betas, point-in-time stress shocks; exposure profiles; sleeve covariance and blended ρ | `risk_model/origin=<date>/` | leak test; PSD check; unmeasured pairs → 1 |
| **P5-3** | Construction: R1-R3, constraints, subset enumeration, ENB choice | `construction/origin=<date>/` (weights, rejected subsets with the binding constraint) | determinism; a synthetic case with a known answer |
| **P5-3b** | **Sleeve-size loop [A3]:** if any chosen size differs from 10k, run Phase 4 P4-9 once on the chosen-size trees, then rerun P5-3 once with the sizes fixed | recomputed eligible sets; final construction; diff against the first pass | no further iteration; diff published |
| **P5-4** | Exact portfolio engine with the state machine, portfolio projection, shared participation, flatten sweep, staleness rule; fault tests (7.1) | `portfolio_replay.py`, tests | all fault tests pass |
| **P5-5** | Fast approximation, and its validation against the exact engine | validation table | 0.25 pp tolerance |
| **P5-6** | Trigger calibration study (5.4) | `triggers_calibration.csv` | firing-noise criterion |
| **P5-7** | Development evaluation (7.2) and variant choices (7.7) | `decision/phase-5-results.md` | criteria applied as written |
| **P5-8** | Historical and hypothetical stress, pilot-horizon bootstrap (7.3-7.5); pass criteria (7.6) | stress and bootstrap reports | pass or redesign, logged |
| **P5-9** | Window-report module run on all four development windows; output schema frozen | `holdout_report.py` (as a window report) | identical schema across windows |
| **P5-10** | Joint freeze (a new ADR); `verify_holdout_inputs.py`; send the hash; then the holdout run, report, cutoff selection, memo | `HOLDOUT_FREEZE.txt`, holdout report, CSVs, memo | `freeze.guard`; the report schema matches development |

**Order:** P5-0 → P5-1 → P5-2 → P5-3 → P5-3b → P5-4 → P5-5 → P5-6 → P5-7 → P5-8 → P5-9 → P5-10.

Dependencies on Phase 4 v2:
- P5-1 needs the tradable universe (P4-2);
- P5-3 needs the eligible sets (P4-8);
- P5-3b runs P4-9.

If τ² is robustly 0 at every origin, P5-3 builds only the shadow scheme (E1). The rest of Phase 5 still runs, because
the shadow stage needs the same machinery.

## 11. Assumptions the simulation cannot test (stated in the memo)

- Live receive and acknowledgement delays outside the measured sample (2-17 s disconnects are covered only by the
  severe scenario).
- Order-book depth at arrival: there is no historical book; impact is a square-root assumption (Y = 1).
- Hyperliquid tiered maintenance margin (a uniform 2.5% is assumed, ADR-0067); auto-deleveraging of our own account.
- Leaders' positions outside what we observe (isolated or spot activity). Gate 7 v2 screens for it but cannot rule
  it out.
- Venue and API changes after the cutoff (A11, A12).

## 12. Decisions for the user

1. The loss budget `L` (proposed 5,000 USDC, re-signed per stage) and the stage amounts.
2. Account structure A as the default (one trading account, virtual sleeves, separate reserve).
3. The O2 slippage bounds and the C1 execution trigger, to be set from the stress-scenario shortfall distribution
   before P5-6.
4. Whether shadow mode runs on E1 ∪ E2 when there are no E2 addresses (recommended: yes, so the machinery is
   validated even if no capital is deployed).
