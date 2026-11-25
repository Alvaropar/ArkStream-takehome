# Decision memo: the 100,000 USDC Hyperliquid copy pilot, as of the cutoff

Written at P5-9 on 2026-11-24, after the holdout was opened once (P5-8). The decision time is the data cutoff,
2026-01-04T23:59:42.020Z. The last origin the frozen pipeline admits is 4 Jan 2026 00:00 UTC, so the 4 Jan partial day
is not used anywhere (ADR-0100 item 1; the user's choice, "Keep 00:00").

Every number below comes from a file named beside it. When this memo and a file disagree, the file is right.
The protocol in full is [deployment-protocol.md](deployment-protocol.md).

## Summary

- **Recommendation: do not deploy the 100,000 as a copy basket. Run the gray execution measurement.**
  - Up to 5,000 USDC live on two E1 sleeves at 2,500 each, under one loss budget of 750 USDC.
  - The other 95,000 stays in reserve as off-exchange USDC.
  - It ends when both 4 weeks and 200 live orders are reached, at the loss cap, or at 12 weeks.
- **This is the pre-registered outcome:** CONDITIONAL GO, with D1-D5 all true on run A
  (`research/holdout/decision_A.json`, ADR-0093).
- **CONDITIONAL GO is not evidence of skill.** D4 passed, but the IC is negative. Across all addresses the holdout's
  ordering ran against the selection's. This matches Phase 4: no capital-grade evidence of skill (section 3).
- **Rebuilt costs change nothing.** Run B charges rebuilt real conditions and fails no condition that run A passes
  (section 2.3).
- **The gray money buys a measurement, not a return.** It measures real fills, which no replay can. The holdout's
  returns are thin against costs, and costs decide whether the scheme makes money.
- **The live sleeves are 0x2cd9 and 0x971f** (ADR-0101, the user's decision of 2026-11-25). 0x971f was chosen for the
  measurement it gives, not for its own α (section 7).
- **O2 stays at its frozen bound** (ADR-0102, the user's decision of 2026-11-25). Live orders therefore have almost no
  price protection from O2. What limits the damage acts after a bad fill: the stress cap, the 750 USDC loss cap, C1
  and the revert rule (section 7).
- **Before any gray start** (section 7):
  - the limits are signed off (A10);
  - the hand-off is re-qualified on current data (A12).

## 1. Address pool and capital arrangement (written test, item 1)

### 1.1 Launch or postpone

- **The 100,000 basket: postpone.** No address shows skill that persists. The basket is not shown to be diversified,
  and the per-address evidence is a few weeks long. MinTRL is about 1,600 days (methodology section 8).
- **The gray launch: yes, as an execution measurement** (ADR-0090), under the rule written before the holdout. It pays
  at most 750 USDC to measure what the replays assume:
  - the delay from the leader's fill to ours;
  - slippage, fees, partial fills and rejections.
- **Resume conditions for capital** (ADR-0094; protocol section 8):
  - a pooled IC over at least 6 windows that is significant at one-sided 95% (on own-data α, a mean of about 0.047
    or more);
  - at least one E2 trading book that passes every stage;
  - a clean engine.

  Otherwise the project closes after 6 months.

### 1.2 The address set, and why each address is in or out

`research/cutoff/deliverables/trader_decisions.csv` has one row for each of the 1,471 addresses with a snapshot before
4 Jan. Each row gives the grade, the category, the first gate failed and the role. The funnel, in the pinned order
(ADR-0100 item 6), equals `research/cutoff/selection_v2/funnel_v2.csv`:

| Stage | Out | Left |
| --- | ---: | ---: |
| S1, data grade A or B | 1,048 (grade C) | 423 |
| S2, Phase 2's suitability gates | 401 | 22 |
| S3, selection gates (equity band 10, tradable share 5, break-even 2) | 17 | 5 |
| Category E1 or E2 | 1 (E-) | 4 |
| Near-duplicate screen | 0 | **4** |

- **The S2 failures by first gate:** evidence 186, rebuild fit 45, unpriced 44, active 35, intraday drawdown 33, and
  ten others.
  - **Reading the column:** for S2, the frozen code writes Phase 2's whole `gates_failed` list
    (`S2_gate_evidence;gate_active;...`), not only its first entry as ADR-0100 item 6 says. The first failed gate is
    the first entry listed. The code is frozen, so this is labelled, not changed (trial log, P5-9).
- **E2 is empty at 4 Jan, but for a numerical reason.** The frozen τ² is 0, so every posterior equals the prior and
  no address can reach E2 (ADR-0072).
  - At 3 Dec that zero is genuine (Cochran's Q p = 0.69).
  - At 4 Jan it is not: one address with a degenerate standard error takes all the weight (section 2.6, item 4).
  - The hand-off is all E1: shadow-only, except as the signal source of the gray measurement (ADR-0090).

The four hand-off addresses (`research/cutoff/selection_v2/origin=2026-01-04/eligible.parquet`). α is the own-data
holdings α of the 10k tradable copy over its training window, in bp per day of gross exposure (ADR-0071), with its
standard error:

| Address | Grade | α (s.e.) | Robust | Coins (mean exposure of the 10k copy, USDC) | Leader's median equity | Holdout G\* worst loss incl. exit, base / stress (USDC) |
| --- | --- | --- | --- | --- | ---: | --- |
| 0x2cd9f4645b14bf968212c7c108213eaeb193946e | A | 121.8 (82.3) | yes | HYPE 812, ETH 738, AAVE 241, SOL 19 (long) | 27,131 | 85.7 / 112.7 |
| 0x971fc0c9becffd708c52a195b8a87c27359e77fa | A | 65.8 (31.2) | yes | BNB 415, BTC 406 (long) | 7,719 | 22.1 / 15.0 |
| 0xe65c360b28bd3da42d9a07d97f500d8d480e8428 | B | 6.2 (11.8) | yes | ETH -4,165 (short) | 6,066 | 33.3 / 31.2 |
| 0x3a122449de235a40481689442271c0731b805d69 | A | 0.6 (6.0) | no | BTC 6,090, ETH 90, PUMP 30 (long) | 1,683,030 | 42.2 / 42.7 |

- **At 3 Dec the hand-off was 0x2cd9 alone,** with 0x971f declared as the observation sleeve. At 4 Jan 0x971f
  re-qualified under the frozen rules, and 0x3a12 and 0xe65c entered.
- **Each of the three new addresses had its own G\* run on the holdout,** and each passed D2b, before any gray start
  (ADR-0092 item 3).
- **How noisy membership is:** the hand-off was 3 / 2 / 1 / 1 / 1 addresses at the five development origins, then 4
  at the cutoff.

### 1.3 How the addresses form the portfolio

- **One live book, G\*.** The live sleeves sit in one book, under one stress cap and one loss budget. Each sleeve copies
  its leader's target positions in the leader's shape, scaled by its frozen `E_ref` (ADRs 0037, 0052).
- **A binding limit scales whole sleeves,** never single legs (ADR-0088).
- **Sleeves are equal at 2,500,** with no weighting. Ordering by the selection statistic did not predict next-window α
  in development (mean IC -0.030, positive at 1 of 4 origins), so it is not used (ADR-0075).
- **What was tested as a portfolio:** the two-sleeve paper scheme S\* and its unconstrained twin U\*, on the four
  development windows and on the holdout. The live book itself has only been tested as a single-address G\* per
  hand-off address.
- **Not tested as a portfolio:** a joint 100,000 account, cross-leader margin and netting at capital scale. These were
  out of scope (ADR-0064).
- **Diversification is unverified** (`decision/pre-holdout-checks.md`). At 3 Dec the sleeves were long crypto with a
  HYPE concentration (91% of 0x2cd9's gross). The 4 Jan hand-off adds a short-ETH book (0xe65c), but that does not
  show a diversification benefit.

### 1.4 Capital arrangement

`research/cutoff/deliverables/target_allocations.csv`:

| | USDC | Where |
| --- | ---: | --- |
| Live sleeves: 0x2cd9 and 0x971f (ADR-0101) | 2 × 2,500 = 5,000 | on the venue, gray |
| Paper sleeves: 0x3a12 and 0xe65c | 0 (10,000 notional each) | paper |
| Reserve | 95,000 | off-exchange USDC |

- **Number of addresses:** 4 handed off, 2 live, 2 in paper.
- **Unallocated capital:** the 95,000 stays off-exchange. It is not margin for the live book, and it does not move
  without a new ADR. Escalation to 15,000 goes only through the paper revisit conditions, never on PnL.

### 1.5 Risk limits, pause and exit

All values are PLACEHOLDER proposals (A10), checked against `config/risk.yaml` by
`scripts/check_protocol_parameters.py` (54/54 match).
- **Limits on the live book** (protocol section 4):
  - the stress cap: stress loss plus exit cost ≤ 750 USDC minus the loss to date, at every update and hourly;
  - O1-O4: participation 0.5% per coin per 4h bar; a limit price at the bucket's stress p99; minimum order 10 USDC;
    a post-trade check;
  - S1: gross ≤ 1.5× the sleeve;
  - S3: sleeve drawdown -10% reduce-only, -15% flatten and pause;
  - P6: the ladder at -5%, -10% and -15%.
- **Pause:** the triggers L1-L7 and C1-C3 move a sleeve to REDUCE_ONLY, FLATTEN or PAUSED (protocol section 5).
  Every resume needs a human decision at a review.
- **Exit and stop:**
  - **revert to paper** at the 750 USDC loss cap (flatten), or when the live shortfall exceeds the stress scenario
    at two consecutive reviews;
  - **sleeve exit** at a review: a binding gate fails, the category falls to E- or E0, the sleeve was paused all
    period, or L6/L7;
  - **the measurement ends** at 4 weeks plus 200 orders, or at 12 weeks.

## 2. The holdout: what was measured (3 Dec 2025 to 4 Jan 2026, opened once)

32 calendar days, on the 3 Dec origin's inputs, all four cost scenarios. S\* is the two-sleeve paper scheme (0x2cd9
and 0x971f at 10,000 each, with the limits); U\* is the same pair without them; G\* is the gray book (2,500, gray
limits). Files: `research/holdout/window_report/h1-h6`, `research/holdout/portfolio/run=A/`.

### 2.1 The decision (run A, ADR-0093)

| # | Condition | Measured | Result |
| ---: | --- | --- | --- |
| D1 | The engine works out of sample | 24 runs (6 books × 4 scenarios) complete, 0 faults, 0 untraced state events | true |
| D2a | S\*, base and stress: loss within 16.5% of `D` (3,300 USDC); no limit breached without its action | worst drawdown 277 / 720 USDC | true |
| D2b | G\*, base and stress: loss incl. exit ≤ 750 USDC; stress cap never breached at an update | 0x2cd9 86 / 113; reruns 0x3a12 42 / 43, 0x971f 22 / 15, 0xe65c 33 / 31; 0 breaches | true |
| D3 | Median shortfall per side (base) ≤ the development p90, per coin with ≥ 30 orders | BNB 10.3 ≤ 11.5; BTC 5.5 ≤ 7.4; ETH 5.7 ≤ 8.2; HYPE 9.9 ≤ 14.0 bp. **Model against model** (ADRs 0092, 0093) | true |
| D4 | IC of the frozen statistic > threshold. `m` is constant at 3 Dec, so own-data α against -0.14 (ADR-0093 item 4) | IC -0.085, n = 207 | true |
| D5 | The cutoff selection hands off something | 4 addresses | true |

- **D3 left one coin unmeasured.** AAVE had 62 holdout orders (median 12.6 bp) but no development distribution to
  compare with.
- **D3 and C1 are model against model** (ADRs 0092, 0093, 0096). Simulated fills are compared with the simulated
  cost model.
- **The decision was fixed before anything else.** `decision_A.json` was written at 12:55:11Z, before runs B and C
  started at 12:55:45Z (trial log).

### 2.2 Risk and returns (H2, H4, H6; reported, not decisive beyond D2)

| Book | Raw return, base | Raw return, stress | Worst drawdown, base / stress (USDC) | α, base (bp/day of gross) |
| --- | ---: | ---: | --- | ---: |
| S\* (20,000) | +0.78% | -2.58% | 277 / 720 | -133 |
| U\* (20,000) | +4.69% | -5.89% | 503 / 1,562 | +70 |
| G\* 0x2cd9 (2,500) | +4.60% | -3.19% | 121 / 181 | -131 |

- **Returns are thin against costs.**
  - In base, S\* made 155 USDC on 20,000 in 32 days. Under stress costs every book lost money.
  - The limits cost return, as in development: S\* gave up 3.9 points against U\* in base, and cut its stress
    drawdown by more than half (720 against 1,562 USDC).
  - Whether the scheme makes money is decided by costs, and that is what the gray measures.
- **Units of α.** `alpha_bps_day_ex_funding` is ADR-0071's holdings α: the factor-adjusted residual P&L per dollar
  of gross exposure per day, × 10⁴ (`phase5_pair.alpha_of`). It is not a return on NAV.
  - That is why G\* shows -131 beside +4.6% raw: the book held little gross, and the α is scaled by that gross.
  - On short windows it is very noisy. In development, G\*'s base α ranged from -568 to +466 across the four windows.
  - It decides nothing here.
- **Firings on S\* (base):** L6 once on 0x2cd9; C1 and L2 once each on 0x971f.
- **Limit binding (H6):** 0x2cd9's `λ` was 0.90 time-weighted and 0.58 exposure-weighted. P2 bound 3.0% of the hours.
  P5 never bound.
- **Sleeve by sleeve in S\* (base):** 0x2cd9 +1.58%, 0x971f -0.03%.

### 2.3 Rebuilt costs: runs B and C (reported, never changing the verdict; ADR-0098 item 7)

B and C are **rebuilt real conditions, not real fills**. Each order is priced from the market at its own time: a
delay drawn per order from the measured distribution, the Binance tape over that delay, the same day's spread and
impact. The risk rules keep the frozen model in B and use a daily refit in C.

| | S\* | U\* | G\* |
| --- | --- | --- | --- |
| P&L, base: A → B (USDC) | +155.2 → +171.8 | +938.7 → +976.0 | +114.9 → +123.7 |
| Cost per side, notional-weighted with fee: A → B (bp) | 8.16 → 7.06 | 8.94 → 7.86 | 8.79 → 6.75 |
| Frozen model minus rebuild, orders with tape drift (bp) | +0.86 (334 orders) | +1.00 (259) | +1.93 (118) |

- **B fails nothing A passes.** B has the same orders and firings as A. D3 on B passes for the same 4 coins, and C1
  fires once on S\* in both.
- **B equals C exactly,** because no stress limit set `λ` in either. On S\*, C's refitted model is off by only
  +0.02 bp against the frozen model's +0.86.
- **The rebuild leans on fallbacks.** The same-day spread fell back to the frozen value for 64-69% of orders, impact
  for 43% and the tape drift for 5-11% (`research/holdout/cost_runs/fallback_rates.csv`).

### 2.4 O2 never bound

- In run B, the frozen bound per liquidity bucket (the development stress p99, 408-2,682 bp) rejected no order. Run A
  does not simulate O2 (ADR-0098).
- Run C's shadow O2, on its own model, would have rejected 14. That shadow bound is a per-order stress cost, so it is
  not like-for-like with a bucket p99.
- **O2 stays at its frozen bound for the gray** (ADR-0102; section 7). The shadow count is reported, not used to set a
  bound.

### 2.5 The cross-section (H5)

The next-window α of all measured A/B addresses at 3 Dec, in bp per day of gross:

| Group | n | Mean next α |
| --- | ---: | ---: |
| E2 | 0 | n/a |
| E1 | 111 | -7.5 |
| E0 | 36 | +29.0 |
| E- | 63 | -19.1 |
| Robust / not robust | 66 / 45 | -10.8 / -2.7 |
| Break-even pass / fail | 134 / 73 | -8.0 / -29.9 |
| Carry books / trading books | 7 / 203 | +34.6 / -6.1 |

- **The ordering went against the selection.** E0 had the best mean next α, there was no E2, and carry books beat
  trading books. Robustness did not help.
- **Only the break-even gate pointed the right way.**
- **The IC of own-data α with the next α was -0.085.** That passes D4's guard against contrary evidence (> -0.14),
  but it is not evidence for the selection.

### 2.6 Labelled findings in the outputs (frozen code, not changed)

1. **The -100% for 0x971f in H2 and H4** (the G\* rerun in stress and severe) is a reporting artifact.
   - **The cause:** from 11 Dec the funding of the residual position is unknown (`unknown_funding` 8 on 11 Dec, 30 on
     12 Dec). So daily equity is null from 11 Dec to 3 Jan.
   - **The summary step** (`phase5_pair.summarize`) adds each day's equity over the book. Polars sums an all-null day
     to 0, so the final equity reads 0, and the raw return and the worst day read -100%. The nulls are summed to 0,
     not compounded.
   - **What the book did:** its gross was about 0.26 USDC from 9 to 16 Dec. It traded again from 17 to 21 Dec (gross
     up to 185.5 USDC) and was flat from 22 Dec.
   - **The hourly NAV** ends at 2,492.08 USDC (minimum 2,486.12) in stress and 2,491.64 (minimum 2,485.67) in severe,
     about -0.3%.
   - **D2b reads the hourly loss path,** so the decision is unaffected.
2. **The severe scenario is outside D2b, but not clean for 0x2cd9.** G\* for 0x2cd9 had 4 target updates on 17 Dec (15-minute sweeps)
   where the book's stress loss exceeded the remaining budget, by at most 11.9 USDC (1.9%). Its worst loss
   including exit was 183 USDC against 750. D2b reads base and stress, which had no such update. No development
   window had one.
3. **S2's first failed gate** in `trader_decisions.csv` lists every failed gate (section 1.2).
4. **τ² at 4 Jan is a numerical artifact.**
   - **The cause:** one address, 0x4c60401b…, has own α -1.8e-17 and standard error 7.1e-18 (floating-point noise,
     not a measurement). With inverse-variance weights it takes 100% of the weight in the frozen DerSimonian-Laird
     step. The denominator cancels to 0, so τ² is set to 0, although Cochran's Q rejects homogeneity (Q = 3,617 on
     255 df). Every `m` then equals the prior, so `m` is constant (`research/cutoff/selection_v2/tau2.csv`,
     `evidence.parquet`).
   - **Without that address,** τ² is 5.4e-7: a between-address sd of 7.3 bp/day, similar to 8 and 22 Oct (8.5 and
     8.8 bp/day).
   - **What it does not touch:**
     - the decision: D4 and H5 use the 3 Dec evidence, where τ² = 0 holds (Q p = 0.69; smallest standard error
       2.1e-5);
     - the hand-off's membership, which needs E1 or E2 and a positive own α.
   - **What it does touch:**
     - the E1/E2 labels at 4 Jan;
     - the frozen code's ordering of the live sleeves, which falls back to own α only because `m` is constant
       (section 7).
   - The categories and the order without the degenerate address have not been computed.
5. **The frozen texts disagree on the second live sleeve.** ADR-0101 resolves it for the 4 Jan cutoff. The conflict
   stays open for later origins (section 7).

## 3. What the evidence does not show

- **Skill.** No address shows capital-grade evidence of skill that persists into the next window
  (`decision/phase-4-v2-results.md`).
  - At 3 Dec, τ² is robustly 0: no measurable skill dispersion at all.
  - At 4 Jan the corrected estimate is small, a between-address sd of 7.3 bp/day (section 2.6, item 4), against own
    standard errors of tens of bp/day.
  - The holdout's H5 agrees (section 2.5).

  CONDITIONAL GO says the scheme behaved as designed. It does not say that the leaders have an edge.
- **Real execution.** H3, D3, C1, and runs B and C are all simulations. Only the gray measures how our own orders
  interact with the book.
- **Diversification.** It is unverified (section 1.3).
- **Profit after costs.** The base returns are a few percent over 32 days, the stress returns are negative, and the α
  is noise at this length.

## 4. Assumptions and operating arrangement (written test, item 2)

### 4.1 Key assumptions

| # | Assumption | Status |
| --- | --- | --- |
| A10 | The pilot has no approved risk policy | every limit is a proposal, signed off before trading |
| A11 | Venue documentation read in November 2026 describes today's venue | venue facts are pinned with their date; checked again at any start |
| A12 | The decision is historical, as of the cutoff | a GO at the cutoff does not authorise a launch today: re-qualify on current data, with fresh approvals |
| A13 | Reference coin prices come from outside the package | Binance USD-M 1m klines, with checksums, validated against the package's prints |
| — | Delays and fills | the measured receive delay and the cost model; untested on our own orders |
| — | Order-book depth at arrival | no historical book; impact is a square-root assumption |
| — | Venue details | tiered margin and auto-deleveraging of our own account are untested |
| — | Leaders' invisible activity | isolated or spot positions; gate 7 screens for them but cannot rule them out |

**Untested, so labelled (ADRs 0064 and 0094 item 5).** Only the gray can show:
- how our own orders interact with the book (queue position, hidden liquidity);
- venue rejections, outages and rate limits;
- our actual latency.

### 4.2 Operating arrangement (methodology section 12)

| Question | Answer |
| --- | --- |
| How decisions update on new records | Leader fills update the targets at once. Snapshots update `E_ref` at reviews, along with the triggers and the risk marks. The hand-off changes only at the 14-day review. |
| When instructions are generated | After a 250 ms debounce on leader fills, plus the 15-minute sweep and the flatten sweep, all through the deadband (10 USDC, 2% of target). An event older than 30 s is not executed; the book resyncs. |
| Several sources on one contract | Sleeve targets are summed after each sleeve's `λ`. Offsetting deltas cross internally at the decision mark; only the net goes to the venue. Attribution stays per sleeve. |
| Fills that differ from target | Recompute from state; never resend. Three non-converging reconciliation cycles freeze increases (C3). Reconciliation is daily. |
| When capital may increase | Only through the paper revisit conditions (pooled IC over ≥ 6 windows, an E2 trading book, a clean engine). Never on PnL. |
| When risk must fall | The limits (stress cap, S1, S3, P6) and the triggers (L1-L7, C1-C3) |
| Manual intervention | Every resume, every protocol change, L3-L5, the ladder at -10% and below |
| Set by hand or reviewed periodically | Loss caps and the protocol at each decision; limits and triggers monthly; cost and delay scenarios against live fills monthly; the hand-off at each 14-day review |

## 5. Result review (written test, item 3)

### 5.1 Tracing a decision from the raw data: 0x2cd9

1. **Raw:** `data/raw/fills.csv` and `traders.csv`, byte copies of the package, with checksums in
   `provenance/CHECKSUMS.txt`.
2. **Phase 2 evidence at the origin:** `research/leader/origin=2025-12-03/` (and `research/cutoff/leader/origin=2026-01-04/`):
   - account returns and daily marks;
   - `gates.parquet`, which the S2 gates read.
3. **The copy replay:** the training window of the tradable tree, `research/replay_tradable/origin=2025-12-03/` (and
   `research/cutoff/replay_tradable/`).
4. **The selection:** `research/selection_v2/origin=2025-12-03/` (`candidates.parquet` for every gate and category,
   `eligible.parquet` for the hand-off). At 4 Jan: `research/cutoff/selection_v2/origin=2026-01-04/`.
5. **The holdout:**
   - `research/holdout/portfolio/run=A/origin=2025-12-03/config=G2500/`, with fills, orders, decisions, hourly and
     daily tables;
   - the window report;
   - `decision_A.json`.
6. **The deliverables:** `research/cutoff/deliverables/`.

Any other address can be looked up the same way. Its row in `trader_decisions.csv` names the first gate it fails, and
`candidates.parquet` at the origin gives the measured value behind each gate.

### 5.2 Where the scheme can be wrong

- **The selection may select noise.**
  - The categories were not ordered by next-window α in development or in the holdout.
  - The hand-off changes from origin to origin. 0x2cd9 failed the robustness check at 3 Dec and passed it at 4 Jan.
- **The two-sleeve live book was never replayed as one book.** D2b tested a G\* for each hand-off address alone. A live
  pair shares one `L_gray`, so its stress cap binds sooner than either sleeve's alone, unless their positions offset.
- **One leader dominates the live book.** 0x2cd9 is HYPE-heavy. A HYPE shock hits the gray book through one sleeve.
  The stress cap bounds that loss in USDC, but the shock is fitted on history since 1 Jul 2025 (ADR-0017).
- **Cost misestimation.**
  - The frozen model was conservative against the rebuild by 0.9-1.9 bp per side, but the rebuild fell back to the
    model for most spreads.
  - HYPE's same-day spread was mostly unmeasured in development. Only 32 of S\*'s 108 HYPE orders had one, and the
    other 76 fell back to the frozen 5 bp (`research/cost_runs/origin=*/run=B/config=S/cost_records.parquet`,
    `half_flag`).
  - Real fills may be worse than either estimate.
- **The leader's unseen book.** An isolated position, a spot hedge or a sub-account would make the copied shape wrong.
- **Rules that read differently, and degenerate inputs.**
  - The ordering conflict. ADR-0101 resolves it for the 4 Jan cutoff; it stays open for later origins (section 7).
  - A single degenerate standard error can zero τ² and remove E2 at an origin (section 2.6, item 4). The pipeline has
    no floor on the standard error.
  - The reporting artifact for 0x971f (section 2.6), which a reader of H4 alone would take as a total loss.
- **Venue change after the cutoff** (A11, A12).

## 6. Review and continuation (written test, item 4)

### 6.1 Integrity

- **The freeze:**
  - `freeze_hash` 62eba6dab41bf74838957d355538796fd59f30876317691219600755687b6648, over 119 files
    (`provenance/HOLDOUT_FREEZE.txt`, frozen at 2026-11-24T10:51:48Z);
  - the files are the 1175b3b tree plus the 3 Dec shortlist (`research/selection_v2/origin=2025-12-03/eligible.parquet`),
    which first entered git in the freeze commit aea2e43;
  - **reviewers need aea2e43 or later.**
- **The holdout outputs** are commit d01e2ce. These P5-9 deliverables follow it.
- **The decision entry:** `research/holdout/decision_A.json`, sha256
  cb3dd576b3880ddfdf7459fd8dc97297fb93bfe249082cb15c731448586e7c2f. It was written at 12:55:11Z, before runs B and C
  started at 12:55:45Z.
- **The reviewer's check,** on a clone at aea2e43 or later, after `uv sync`:

  ```
  uv run python -c "import sys; sys.path.insert(0, 'src'); from pathlib import Path; from arkstream import freeze; r = Path('.').resolve(); _, env, h = freeze.read_freeze(r); print(freeze.combined(freeze.digest_lines(r) + env) == h, h)"
  ```

  It prints `True` and the hash.
- **Every holdout step is logged** in `provenance/trial_log.md`, with its start time, before its result: P5-8 steps 1-4
  and P5-9.

### 6.2 Reproduction

- [VERIFY.md](../VERIFY.md) gives the full check from a clean copy.
- The holdout steps rerun in the enforced order, each refused until the previous output exists:
  1. `uv run python -m arkstream phase5 holdout --stage a`
  2. `uv run python -m arkstream phase5 cutoff`
  3. `uv run python -m arkstream phase5 holdout --stage decision`
  4. `uv run python -m arkstream phase5 holdout --stage bc`
  5. `uv run python -m arkstream phase5 cutoff --deliverables`

  Use `POLARS_MAX_THREADS=8` for every step.
- The decisions are in the ADR index, `decision/adr/README.md`.

### 6.3 Continuing on new data

- **At any live start, or at each 14-day review:**
  - extend the data under the same manifests;
  - run the frozen pipeline at the new origin (the cutoff selection's code with that origin);
  - the hand-off comes from that run.
- **The paper panel** replays all A/B addresses every 14 days and adds one window to the pooled IC. Six windows decide
  the revisit test.
- **A larger address pool** runs through the same gates. Nothing in the funnel is sized to the sample.
- **Any rule change** is written as an ADR and logged before it is computed, then frozen again before it is tested.
  The holdout used here cannot be used again.

## 7. Decisions: made and open

**Decided: the second live sleeve at the 4 Jan cutoff is 0x971f** ([ADR-0101](adr/0101-second-live-sleeve-at-cutoff.md);
the user, 2026-11-25: "Go with 0x971f").
- **The conflict it resolves:**
  - the frozen code (ADR-0100 item 6, methodology section 10.3) orders by own-data α and puts 0x971f live;
  - ADR-0090 item 4 orders by address ("ordering by `m` is not used", ADR-0075) and would put 0x3a12 live.
- **The reason is the measurement.** In the holdout G\* reruns (base), 0x971f against 0x3a12:
  - orders per week: 16.0 against 3.3;
  - mean gross: 200 against 498 USDC;
  - worst loss including exit (base / stress): 22 / 15 against 42 / 43 USDC.

  0x971f also adds BNB, the coin whose D3 median came closest to its limit (10.3 against 11.5 bp).
- **Not the reason:**
  - own α, which has no predictive support and at 4 Jan rests on the τ² artifact (section 2.6, item 4);
  - returns: 0x3a12 had the higher holdout return.
- **It departs from ADR-0090 item 4's address order at this cutoff only.**
  - The live book is the frozen deliverable as computed: 0x2cd9 and 0x971f at 2,500 each, 0x3a12 and 0xe65c in paper,
    95,000 in reserve.
  - ADRs 0090 and 0100 are frozen, so the amendment is recorded in ADR-0101 and its index row.
- **The choice was made after the holdout,** with both candidates' runs known. Its criteria are order rate, exposure
  and worst loss, not a return or α measure.

**Decided: O2 stays at its frozen bound for the gray** ([ADR-0102](adr/0102-o2-kept-as-frozen.md); the user,
2026-11-25: "Yes, keep it").
- **The bounds** are the values in `research/cost_runs/o2_bounds.csv`, the development stress p99 per liquidity bucket:

  | Bucket | Bound |
  | --- | ---: |
  | ≥ 5M | 430 bp |
  | 1M-5M | 2,682 bp |
  | 250k-1M | 436 bp |
  | < 250k | 408 bp |

  Nothing in `config/risk.yaml`, the deliverables or the frozen set changes.
- **A change needs its own ADR, set on data not used here.** Run C's shadow count (14) is reported, not used.
- **Live orders have almost no price protection from O2.** A gray order can fill far through a thin book or a fast
  move. What limits the damage acts after a bad fill, not on the order:
  - the stress cap (stress loss plus exit cost ≤ 750 USDC minus the loss to date);
  - the 750 USDC loss cap, which flattens the book and reverts to paper;
  - C1, the 14-day median real shortfall against the stress scenario's;
  - the revert rule: back to paper when the live shortfall exceeds the stress scenario's at two consecutive reviews.
- **The gray measures what a tighter O2 would have cost.** Every live fill's shortfall against the decision mark is
  recorded, so the reviews can show how many fills a tighter bound would have rejected.
- **The 1M-5M bound (2,682 bp) is out of line** with the other buckets (408-436 bp). ADR-0102 records this; the reason
  has not been checked.

**Open:**
1. **The ordering at later origins.** The conflict between ADR-0090 item 4 and ADR-0100 item 6 remains in the frozen
   texts and in the code. It needs its own ADR and a new freeze before any re-qualification (A12).
2. **A floor on the standard error in the τ² step,** or the exclusion of degenerate measurements (section 2.6, item 4).
   This also needs its own ADR and a new freeze before any re-qualification.
3. **The limits' sign-off (A10)** and **the re-qualification on current data (A12)** before any live order.
