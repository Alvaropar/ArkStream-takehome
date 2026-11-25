# Deployment protocol: gray execution measurement (CONDITIONAL GO)

Written at P5-9 on 2026-11-24, after the holdout and the cutoff selection. The parameters were fixed before the holdout
(methodology section 10, ADRs 0090 and 0094) and are copied here unchanged. Section 9 lists them with their
`config/risk.yaml` keys; `scripts/check_protocol_parameters.py` compares the two.

- **Decision:** CONDITIONAL GO (`research/holdout/decision_A.json`, run A, ADR-0093). So the gray protocol applies, not
  the paper one.
- **Not a claim of skill.** The decision says the scheme behaved as designed out of sample. A small, capped, live
  measurement of real fills is therefore worth its cost. It says nothing about whether the leaders have an edge
  ([decision-memo.md](decision-memo.md) section 3).
- **Nothing here starts trading.**
  - Every limit is a proposal (A10). It must be signed off before any order.
  - Execution is disabled (`config/execution.yaml`: `live_trading_enabled: false`).
  - A CONDITIONAL GO at the cutoff (4 Jan 2026) does not authorise a launch on a later date (A12). That needs the
    start checks of section 7.

## 1. What the gray money is (ADR-0090)

- **An execution measurement paid as a research cost, not an allocation.**
- **What it measures:** each live order against its paper twin, for:
  - the delay from the leader's fill to ours;
  - slippage against the model and fees;
  - partial fills and rejections;
  - the would-be fill against the live book at signal time.
- **What it is not:**
  - it is not deployed capital and makes no skill claim;
  - it changes no address's category (all four live candidates are E1, shadow-only under ADR-0072 except as the
    signal source of this measurement);
  - its returns are never evidence for promotion.

## 2. The books at the cutoff (`research/cutoff/deliverables/`)

The frozen cutoff selection at 4 Jan 2026 00:00 UTC hands off four addresses, all E1 (ADR-0100;
`research/cutoff/selection_v2/origin=2026-01-04/eligible.parquet`). More than two qualify, so they are ordered, and the
first two go live at 2,500 USDC each.

`target_allocations.csv`, as written by the frozen code:

| Address | Role | Protocol | Deployed (USDC) | Paper notional (USDC) |
| --- | --- | --- | ---: | ---: |
| 0x2cd9f4645b14bf968212c7c108213eaeb193946e | hand-off | gray | 2,500 | 0 |
| 0x971fc0c9becffd708c52a195b8a87c27359e77fa | hand-off | gray | 2,500 | 0 |
| 0xe65c360b28bd3da42d9a07d97f500d8d480e8428 | hand-off | paper | 0 | 10,000 |
| 0x3a122449de235a40481689442271c0731b805d69 | hand-off | paper | 0 | 10,000 |
| reserve | reserve | off-exchange USDC | 95,000 | 0 |

- **0x971f** was the declared observation sleeve. It re-qualified under the frozen rules at 4 Jan, so it is a
  hand-off address, and no separate observation row is written (ADR-0090 item 4; `risk.yaml`
  `scheme.observation_capital_path`).
- **Every live address passed D2b** on the holdout before any gray start (ADR-0092 item 3). The worst G\* loss
  including exit, in base and stress, against `L_gray` = 750 USDC:

  | Address | Base | Stress | Cap breaches at update |
  | --- | ---: | ---: | ---: |
  | 0x2cd9 | 85.7 | 112.7 | 0 |
  | 0x3a12 | 42.2 | 42.7 | 0 |
  | 0x971f | 22.1 | 15.0 | 0 |
  | 0xe65c | 33.3 | 31.2 | 0 |

### 2.1 Decided: the second live sleeve is 0x971f (ADR-0101)

The user decided on 2026-11-25 ("Go with 0x971f"; [ADR-0101](adr/0101-second-live-sleeve-at-cutoff.md)). The live
sleeves are 0x2cd9 and 0x971f at 2,500 each; 0x3a12 and 0xe65c run in paper at 10,000; the reserve is 95,000. This is
the frozen deliverable above, unchanged.
- **The reason is the measurement:** more orders, less exposure, a smaller worst loss, and BNB, the coin whose D3
  median came closest to its limit (10.3 against 11.5 bp). See the table at the end of this section.
- **Not the reason:** own α, which has no predictive support and at 4 Jan rests on the artifact below, or returns
  (0x3a12's was higher).
- **ADR-0090 item 4's address order is departed from at this cutoff only.** ADRs 0090 and 0100 are frozen, so the
  amendment is in ADR-0101 and its index row.
- **The ordering at later origins stays open.** The conflict remains in the frozen texts and the code. It needs its own
  ADR and a new freeze before any re-qualification (A12).

The frozen texts disagree on the order when more than two addresses qualify, and the frozen code follows one reading:

| Text | Order after the category | Live at 4 Jan |
| --- | --- | --- |
| ADR-0100 item 6, methodology section 10.3, `cutoff.target_allocations` | D4's statistic at the origin, descending (own-data α, because `m` is constant at 4 Jan), then address | 0x2cd9, **0x971f** |
| ADR-0090 item 4 ("ordering by `m` is not used, ADR-0075"); ADR-0075 item 2 (no ordering unless the IC rule passes; it did not) | address | 0x2cd9, **0x3a12** |

**The first reading also rests on a numerical artifact.** `m` is constant at 4 Jan only because one address,
0x4c60401b…, has a degenerate measurement: own α -1.8e-17 and standard error 7.1e-18 (floating-point noise).
- With inverse-variance weights it takes 100% of the weight in the frozen DerSimonian-Laird step
  (`selection_v2_evidence.dersimonian_laird`). The denominator `c` cancels to 0, so τ² is set to 0, although Cochran's
  Q rejects homogeneity (Q = 3,617 on 255 df). Every posterior then equals the prior.
- Without that address, τ² is 5.4e-7: a between-address sd of 7.3 bp/day, similar to 8 and 22 Oct (8.5 and 8.8
  bp/day).
- With τ² above 0, `m` would not be constant. The first reading would then order by `m`, and E2 labels could appear.
- The second reading (address order) does not depend on τ².
- Neither the decision nor the hand-off's membership depends on it. D4 uses the 3 Dec evidence, where τ² = 0 holds
  (Q p = 0.69; smallest standard error 2.1e-5). Hand-off membership needs E1 or E2 and a positive own α, which τ² does
  not change.

The code is frozen, so this is labelled, not changed (trial log, P5-9). What the categories and the order would be
without the degenerate address has not been computed. A floor on the standard error, or the exclusion of degenerate
measurements, needs its own ADR and a new freeze before any re-qualification.

What differs between the two candidates (cutoff selection and holdout G\* rerun, base):

| | 0x971f | 0x3a12 |
| --- | --- | --- |
| Own-data α at 4 Jan (bp/day of gross; its standard error) | 65.8 (31.2) | 0.6 (6.0) |
| Robust (ADR-0072) | yes | no |
| Coins (mean exposure of the 10k copy) | BNB 415, BTC 406 USDC | BTC 6,090, ETH 90, PUMP 30 USDC |
| Leader's median equity | 7,719 USDC | 1,683,030 USDC |
| Holdout G\* orders per week | 16.0 | 3.3 |
| Holdout G\* mean gross | 200 USDC | 498 USDC |
| Holdout G\* worst loss incl. exit, base / stress | 22 / 15 USDC | 42 / 43 USDC |
| Holdout G\* intents under 10 USDC (reported, not used to resize; ADR-0090 item 4) | 12 of 138 (8.7%) | 2 of 19 (10.5%) |
| Holdout G\* raw return, base | +1.4% | +2.3% |

## 3. The envelope (ADR-0090 item 3)

- **`L_gray` = 750 USDC** (0.75% of the 100,000), one loss budget for the whole live book, booked as a research
  expense.
- **At most 5,000 USDC live:** 2,500 per live sleeve, so at most two sleeves.
  - The 5,000-per-sleeve size applies only if more than 10% of G\*'s sized intents fall under 10 USDC after `λ`. At
    P5-5 that share was 0 of 193, so the size is 2,500 and fixed (`gray.sleeve_usdc`).
- **Duration:** the measurement ends at whichever comes first:
  - **both** at least 4 weeks and at least 200 live orders;
  - the loss cap;
  - 12 weeks (six 14-day reviews).

  Stopping at 12 weeks with fewer than 200 orders is reported as under-powered, with the order count.
- **Expected order rate** (holdout G\*, base, physical fills; one 32-day window):
  - 0x2cd9 alone: 28.9 orders a week, so 200 orders take about 7 weeks;
  - with 0x971f, the live pair (ADR-0101): about 45 a week, so about 4.5 weeks, just past the 4-week minimum;
  - with 0x3a12 instead: about 32 a week, so about 6 weeks.
- **No extension or enlargement** without a new ADR.

## 4. Limits on the live book (ADR-0088 item 7, option C; ADR-0090 items 4 and 6)

- **The stress cap.** The live book's stress loss plus exit cost (ADR-0088 item 2) must stay within the remaining
  budget, `L_gray` minus the cumulative loss since the gray start. It is checked at every target update and hourly.
  - It is enforced by scaling the whole sleeve, never a single leg.
  - It replaces S2 and P2-P5.
- **Kept:** O1-O4, S1, S3 and the P6 ladder. S3 and P6 run on the live book's own high-water mark.

| # | Limit | Value | Action |
| --- | --- | --- | --- |
| O1 | Participation per coin per 4h bar, summed over sleeves | ≤ 0.5% | clip; remainder next bar |
| O2 | Limit price against the decision mark | ≤ the stress scenario's p99 shortfall for the coin's liquidity bucket | IOC at the bound |
| O3 | Minimum order; deadband | 10 USDC; 2% of target | skip |
| O4 | Post-trade projection | no limit below breached | solve `λ` before any order |
| S1 | Sleeve gross | ≤ 1.5 × the sleeve allocation | scale the sleeve |
| S3 | Sleeve drawdown from its high-water mark | -10% reduce-only; -15% flatten and pause | state machine |
| P6 | Drawdown ladder on the live book's high-water mark | -5% halve new risk; -10% reduce-only; -15% flatten all, stop | state machine |
| Cap | Stress loss plus exit cost | ≤ 750 USDC minus the loss to date | scale the whole sleeve |

**Open decision: O2.** In the holdout the frozen bound per bucket (the development stress p99, 408-2,682 bp) rejected
nothing. Run C's shadow O2, on its own per-order stress cost, would have rejected 14 orders. That shadow bound is not
like-for-like with a bucket p99. Whether the gray launch needs a tighter O2 is the user's decision. It is not set
here, and any change needs its own ADR.

## 5. The engine and its states (ADRs 0087 and 0089)

- **Signals:** the leader's fills, through a 250 ms debounce, plus a 15-minute sweep and the flatten sweep. All of them
  pass through the deadband.
- **Stale signals:** an event older than 30 s at decision is not executed; the book resyncs instead.
- **Several sleeves on one coin:** sleeve targets are summed after each sleeve's `λ`. Offsetting deltas are crossed
  internally at the decision mark, and only the net goes to the venue. Attribution stays per sleeve.
- **Fills that differ from target:** the next target is recomputed from state, and an order is never resent. Three
  reconciliation cycles that do not converge freeze increases (C3).
- **States per sleeve:** NORMAL → HALVED → REDUCE_ONLY → FLATTEN → PAUSED → (review) → NORMAL or EXITED. The more
  restrictive of the sleeve state and the P6 ladder applies.
- **Triggers** (thresholds from `risk.yaml`, PLACEHOLDER):

  | # | Trigger | Threshold | Action |
  | ---: | --- | --- | --- |
  | L1 | Leader drawdown beyond its own history | > 1.5 × its max drawdown before the origin | REDUCE_ONLY |
  | L2 | Leader leverage out of character | > 2 × its p95 | REDUCE_ONLY |
  | L3 | Leader equity collapse | < 0.7 × `E_ref` | REDUCE_ONLY until the next review |
  | L4 | Large withdrawal in 24 h | > 50% of equity | REDUCE_ONLY |
  | L5 | Leader liquidation or ADL | any forced fill | FLATTEN, then PAUSED |
  | L6 | Leader drifts to non-tradable coins (7 days) | > 10% of notional-hours | REDUCE_ONLY; exit at the review if it persists |
  | L7 | Leader inactive | > 14 days | release at the review |
  | C1 | Copy execution degrades: 14-day median shortfall per side | > the stress scenario's | REDUCE_ONLY |
  | C2 | Copy drawdown (S3) | -10% / -15% | REDUCE_ONLY / FLATTEN |
  | C3 | Feed stale while holding, or a position mismatch | > 60 s; any | freeze increases; resync |

  In the replays and the holdout, C1 compared simulated shortfall with simulated stress (model against model). In
  the gray it compares **real** fills with the stress scenario, its first measurement on real fills (ADR-0089
  item 3).

## 6. Operating cadence

- **Daily reconciliation:** live positions, fills and fees against the engine's state and the paper twin.
- **Reviews every 14 days**, with an 8-week summary.
  - **What each review checks:** the triggers' state; the exit rules (ADR-0089 item 4: a binding gate fails, the
    category falls to E- or E0, paused through the period, L7, or L6 persisting); `E_ref`; and the order count against
    the duration rule.
  - **The cross-sectional panel of the paper protocol runs alongside,** because escalation uses its pooled IC
    (ADR-0094 items 1-2). Every 14 days it replays all A/B addresses and computes the IC of the frozen statistic and
    the category ordering. `m` was constant at 3 Dec, the holdout's window, so a pool that includes it uses the
    own-data α (ADR-0094 item 1).
- **Every resume needs a human decision,** at a review, after the trigger has cleared.
- **Revert to paper** when:
  - the loss cap is hit: cumulative loss since the gray start (realised plus mark-to-market, including the modelled
    exit cost of the open book) reaches 750 USDC. The book is flattened;
  - or the live shortfall exceeds the stress scenario's at two consecutive reviews.
- **Human intervention** at: every resume; every protocol change; L3-L5; the ladder at -10% and below (methodology
  section 12).

## 7. Before any gray start

These are conditions, not results. None has been done.
1. **Re-qualification on current data (A12).** Run the frozen pipeline at the start date's origin. The live book is
   that origin's hand-off, not the cutoff's. Any rule change before that needs its own ADR and a new freeze.
2. **The venue and API as of the start date (A11).** This covers tiered margin, ADL, minimum sizes, rate limits and
   order types.
3. **Sign-off of the limits (A10).** Every number in `risk.yaml` is a PLACEHOLDER.
4. **The open decision on O2** (section 4). The second live sleeve is decided (section 2.1, ADR-0101).
5. **Enable execution.** This is the user's reviewed change to `config/execution.yaml`; nothing in this repository
   does it.
6. **Only the live amount goes on the venue.** The reserve stays off-exchange USDC (`target_allocations.csv`). The
   pilot capital is independent of the leaders' accounts (a fixed boundary of the written test).

## 8. Escalation and stopping (ADR-0094)

- **Escalation to a capital stage (15,000 USDC)** happens only through the paper revisit conditions, **never on PnL**.
  All of these must hold:
  - **The pooled IC over at least 6 windows** (the holdout plus the paper windows) is significant at one-sided 95%.
    - On `m`: window-sd 0.101, so a mean IC of about 0.068 or more after 6 windows.
    - On the own-data α: window-sd 0.0706, so about 0.047 or more. The α bar applies whenever `m` is constant at any
      window of the pool, as at 3 Dec.
    - The holdout's window gives -0.085 (n = 207).
  - At least one E2 **trading** book (not a carry book) passes every stage. There was none at 3 Dec. At 4 Jan the
    E2 labels rest on the τ² artifact (section 2.1).
  - The engine is clean.
- **P4-9** (ADR-0070 item 6) runs before a capital stage if its sleeve size differs from 10,000.
- **Stop rule:** if the revisit conditions are not met after 6 months, close the project (the user's choice,
  2026-11-24).

## 9. Parameters (checked against `config/risk.yaml`)

Every value below is the frozen value (ADRs 0088-0090, 0094; methodology section 10). `scripts/check_protocol_parameters.py`
reads this table and compares each row with the key in `config/risk.yaml`. Its result is in
`research/audit/protocol_parameters.md`.

| `risk.yaml` key | Value | Source |
| --- | --- | --- |
| `capital_usdc` | 100000 | ADR-0094 item 1 |
| `gray.loss_cap_usdc` | 750 | ADR-0090 item 3 |
| `gray.max_live_usdc` | 5000 | ADR-0090 item 3 |
| `gray.sleeve_usdc` | 2500 | ADR-0090 item 4 (set at P5-5) |
| `gray.sleeve_usdc_if_subminimum` | 5000 | ADR-0090 item 4 |
| `gray.subminimum_share_max` | 0.10 | ADR-0090 item 4 |
| `gray.subminimum_base` | gstar_after_lambda | ADR-0090 item 6 |
| `gray.min_weeks` | 4 | ADR-0090 item 3 |
| `gray.min_live_orders` | 200 | ADR-0090 item 3 |
| `gray.max_weeks` | 12 | ADR-0090 item 3 |
| `gray.revert_shortfall_reviews` | 2 | ADR-0090 item 4 |
| `gray.stress_cap_basis` | remaining | ADR-0090 item 6 |
| `gray.limits` | C | ADR-0088 item 7 |
| `gray.limits_kept` | [O1, O2, O3, O4, S1, S3, P6] | ADR-0088 item 7 |
| `gross_exposure_max_x` | 1.5 | ADR-0088 item 1 (S1) |
| `limits.S1_sleeve_gross_x` | 1.5 | ADR-0088 item 1 |
| `limits.O2_limit_price` | stress_p99_shortfall_by_bucket | ADR-0088 item 1 |
| `limits.O3_min_notional_usdc` | 10 | ADR-0088 item 1 |
| `limits.S3_sleeve_drawdown.reduce_only` | -0.10 | ADR-0088 item 1 |
| `limits.S3_sleeve_drawdown.flatten_pause` | -0.15 | ADR-0088 item 1 |
| `drawdown_ladder.halve_new_risk` | -0.05 | ADR-0088 item 1 (P6) |
| `drawdown_ladder.reduce_only` | -0.10 | ADR-0088 item 1 (P6) |
| `drawdown_ladder.flatten` | -0.15 | ADR-0088 item 1 (P6) |
| `engine.deadband.min_usdc` | 10 | ADR-0087 |
| `engine.deadband.share_of_target` | 0.02 | ADR-0087 |
| `engine.debounce_ms` | 250 | ADR-0087 |
| `engine.sweep_minutes` | 15 | ADR-0087 |
| `engine.participation_per_coin_bar` | 0.005 | ADR-0087 (O1) |
| `engine.stale_signal_s` | 30 | ADR-0087 |
| `engine.netting` | internal_cross_at_decision_mark | ADR-0087 |
| `states.halved_scale` | 0.5 | ADR-0089 item 2 |
| `states.flatten.twap_max_minutes` | 60 | ADR-0089 item 2 |
| `states.review_days` | 14 | ADR-0089 item 4 |
| `triggers.L1_leader_drawdown_x_hist_max` | 1.5 | ADR-0089 item 3 |
| `triggers.L2_leader_leverage_x_p95` | 2.0 | ADR-0089 item 3 |
| `triggers.L3_leader_equity_of_eref` | 0.7 | ADR-0089 item 3 |
| `triggers.L4_withdrawal_share_24h` | 0.5 | ADR-0089 item 3 |
| `triggers.L5_forced_fill` | any | ADR-0089 item 3 |
| `triggers.L6_nontradable_share_7d` | 0.10 | ADR-0089 item 3 |
| `triggers.L7_inactive_days` | 14 | ADR-0089 item 3 |
| `triggers.C1_shortfall_window_days` | 14 | ADR-0089 item 3 |
| `triggers.C3_feed_stale_s` | 60 | ADR-0089 item 3 |
| `triggers.C3_reconcile_freeze_cycles` | 3 | ADR-0089 item 3 |
| `paper.review_days` | 14 | ADR-0094 item 1 |
| `paper.summary_weeks` | 8 | ADR-0094 item 1 |
| `paper.revisit.min_windows` | 6 | ADR-0094 item 1 |
| `paper.revisit.one_sided_level` | 0.95 | ADR-0094 item 1 |
| `paper.revisit.window_sd` | 0.101 | ADR-0094 item 1 |
| `paper.revisit.min_mean_ic` | 0.068 | ADR-0094 item 1 |
| `paper.revisit.alpha_window_sd` | 0.0706 | ADR-0094 item 1 |
| `paper.revisit.alpha_min_mean_ic` | 0.047 | ADR-0094 item 1 |
| `paper.stop_months` | 6 | ADR-0094 item 1 |
| `scheme.sleeve_notional_usdc` | 10000 | ADR-0086 (paper sleeves) |
| `escalation_capital_usdc` | 15000 | ADR-0094 item 2 |

## 10. If the decision had been NO-GO (for the record)

The paper protocol (ADR-0094 item 1) would have applied:
- no capital, with the 100,000 in reserve;
- the frozen engine in paper on the cutoff hand-off, with U\* beside it;
- the same reviews, panel, revisit conditions and 6-month stop rule.

`research/cutoff_check/deliverables/` shows both branches at 3 Dec.
