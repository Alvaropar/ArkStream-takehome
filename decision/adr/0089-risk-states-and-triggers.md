# ADR-0089: Risk states per sleeve and for the scheme, the leader and copy triggers, exit and resume

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24); every threshold PLACEHOLDER, calibrated for noise
  only (ADR-0095 item 1); trigger, review and resume details pinned in ADR-0096
- Date: 2026-11-23
- Phase: Phase 5 (revision 4)
- Builds on: ADR-0052 (reviews, reduce-only on an unusable equity), ADR-0046 (forced fills), ADR-0073 (the tradable
  share), ADR-0088 (S3, P6)
- Source: `decision/phase-5-methodology-1.md` section 5 (revision 4)

## Context
The limits of ADR-0088 bound exposure. They do not react to a leader who changes character, to a copy whose execution
degrades, or to a drawdown. Those reactions must be fixed rules, checked point in time and logged, because the
holdout tests them.

## Decision
1. **State machine per sleeve:** `NORMAL → HALVED → REDUCE_ONLY → FLATTEN → PAUSED → (review) → NORMAL or EXITED`.
   - The scheme-level state (the P6 ladder) caps both sleeves.
   - The more restrictive state wins, in the order NORMAL < HALVED < REDUCE_ONLY < FLATTEN < PAUSED < EXITED.
2. **The state scalar `s_i`** (ADR-0087 item 2):
   - **NORMAL:** 1.
   - **HALVED:** 0.5 on the whole sleeve.
   - **REDUCE_ONLY:** the sleeve keeps the leader's shape on the legs it already holds.
     - Its common scale may only fall. It is the largest value at or below the previous one at which no held leg grows
       or flips sign: `s_t = min(s_{t-1}, min_c |held_{i,c}| / |λ_i k_i q_{i,c}|)` over held legs whose target keeps
       its sign.
     - If the leader flips the sign of a held leg, any positive scale would flip it, so `s_t = 0` and the sleeve closes
       in the leader's shape.
     - Legs the leader opens during the state are not opened. That is the one deliberate departure from the leader's
       shape, logged as tracking error.
   - **FLATTEN:** 0, executed as reduce-only IOC slices within O1, or as a TWAP of at most 60 minutes for coins under
     1M USDC of latest completed 4h volume, at stress costs.
   - **PAUSED:** 0 and no orders.
   - **EXITED:** the sleeve is released.
3. **Triggers** (thresholds PLACEHOLDER). Each is computed point in time from data known at the check:

   | # | Trigger | Definition (pinned here) | Threshold | Action |
   | ---: | --- | --- | --- | --- |
   | L1 | Leader drawdown beyond its own history | drawdown of the leader's Phase 2 primary return index (flows removed, ADRs 0014, 0045) from its high-water mark, against its max drawdown in the history before the origin | > 1.5 × | REDUCE_ONLY |
   | L2 | Leader leverage out of character | hourly book gross / equity, against its p95 over the history before the origin | > 2 × | REDUCE_ONLY |
   | L3 | Leader equity collapse | latest snapshot equity against `E_ref` | < 0.7 × | REDUCE_ONLY until the next review |
   | L4 | Large withdrawal | recorded net outflow over the trailing 24 h against the equity at its start | > 50% | REDUCE_ONLY |
   | L5 | Leader liquidation or auto-deleveraging | any forced fill (ADR-0046 flags) | any | FLATTEN, then PAUSED |
   | L6 | Leader drifts to non-tradable coins | share of the leader's notional-hours outside the wallet's tradable set, trailing 7 days | > 10% | REDUCE_ONLY; exit at the review if it persists |
   | L7 | Leader inactive | no leader fill | > 14 days | release at the review |
   | C1 | Copy execution degrades | rolling 14-day median shortfall per side against the stress scenario's for the same coins | > | REDUCE_ONLY |
   | C2 | Copy drawdown | S3 (ADR-0088) | -10% / -15% | REDUCE_ONLY / FLATTEN |
   | C3 | Feed stale or position mismatch | no leader message for more than 60 s while holding, or any unexplained difference | > 60 s; any | freeze increases; resync |

   - A **firing** is a transition into the trigger's state, not each check that finds it still true.
   - In the replays, C1 compares simulated shortfall with simulated stress, model against model. Only the gray
     protocol measures it on real fills.
   - C3 has no data source in the replay. It is tested by fault injection (F1).
4. **Exit at a 14-day review** when any of these holds:
   - a binding gate fails on data to the review;
   - the category falls to E- or E0;
   - the sleeve was paused through the whole period;
   - L7 applies, or L6 has persisted since the previous review.
5. **Resume** only at a review, after the trigger clears, and with a human decision.
   - **In the replays (pinned here):** the human decision is modelled as "resume" at the first review at which the
     trigger has cleared, and labelled so. This exercises the resume path rather than hiding it.
   - The 14-day development test windows contain only their start review, so resume can occur only in the holdout
     (reviews on 3, 17 and 31 Dec).
6. **What a replay review can check (pinned here).** The gate and category re-checks need the Phase 2 and Phase 4
   pipelines at the review date. Those run only at the defined origins (the four development origins, 3 Dec and the
   cutoff).
   - Inside a run, the reviews check L6, L7, the paused-through-period rule and the `E_ref` review (ADR-0052).
   - The 17 Dec and 31 Dec holdout reviews do not re-grade the leaders. That is a stated limitation of the replay,
     not of the protocol.

## Consequences
- **Code:** the state machine in `portfolio_replay.py` (P5-3); calibration in `triggers_calibration.csv` (P5-4).
- **F1 tests (ADR-0095):**
  - every ladder step and state transition, both ways;
  - reduce-only never increases `|position|`;
  - a leader sign flip in REDUCE_ONLY closes the sleeve in shape;
  - flatten completes within O1 with its cost booked;
  - resume is refused outside a review;
  - the scheme state caps the sleeve state.
- **Reported:** time in each state, every firing with its trigger value, and the 14-day return and drawdown after
  firings against matched days without firing (descriptive; ADR-0095).
