# ADR-0090: Gray money is an execution measurement paid as a research cost, not an allocation

- Status: **Accepted** (the user's decision 1, 2026-11-23); envelope PLACEHOLDER. Items 3 (duration) and 5 are pinned
  here and were accepted on 2026-11-24. Item 6 (the stress cap's base, the sub-minimum base) and the G\* limit set
  (ADR-0088 item 7, option C) are the user's choices of 2026-11-24.
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), the gray protocol (CONDITIONAL GO)
- Amends: ADR-0072 item 5, the E1 consequence, which now reads "shadow-only; may serve as the signal source of an
  ADR-0090 execution measurement"
- Source: `decision/phase-5-methodology-1.md` sections 10.2 and 15 item 1 (revision 4)

## Context
ADR-0072 makes E1 shadow-only, and the only 3 Dec hand-off, 0x2cd9, is E1. Live money on it would contradict ADR-0072
unless that money is something other than an allocation.

What the paper engine and the holdout cannot observe is real execution:
- the delay from the leader's fill to ours;
- slippage against the decision mark;
- fees, partial fills and rejections as they happen.

The holdout's cost check (D3) compares the cost model with itself (ADR-0093). Only live orders measure real fills.

## Decision
1. **Purpose:** measure real fills, not earn returns. Each live order is recorded against its paper twin for:
   - delay, slippage against the model and fees;
   - partial fills and rejections;
   - the would-be fill against the live book at signal time.
2. **Not an allocation:**
   - it is not counted as deployed capital and makes no skill claim;
   - it changes no address's category;
   - its returns are never evidence for promotion. Escalation goes only through the paper revisit conditions
     (ADR-0094).
3. **Budget, fixed in advance (PLACEHOLDER):**
   - **`L_gray` = 750 USDC** (0.75% of the 100k), booked as a research expense;
   - at most **5,000 USDC** live;
   - **duration (pinned here):** it ends when **both** at least 4 weeks and at least 200 live orders are reached,
     or when the loss cap is hit, or at a **maximum of 12 weeks** (six 14-day reviews), whichever comes first;
   - the 12-week maximum bounds the budget in time if the hand-off trades rarely. A measurement that stops at the
     maximum with fewer than 200 orders is reported as under-powered, with its order count;
   - P5-1 reports the expected live order rate from the development windows, so that the user sees before the freeze
     whether 200 orders in 12 weeks is reachable;
   - the budget cannot be extended or enlarged without a new ADR.
4. **Mechanics:**
   - **Live book = G\*** (ADR-0086): the cutoff hand-off only. The observation sleeve stays paper unless it
     re-qualifies under the frozen rules.
   - **Live sleeve size:** 2,500 USDC, or 5,000 if more than 10% of the sleeve's orders fall under the 10 USDC
     minimum.
     - The share is the count share, among the sleeve's sized order intents (after the cap, before the minimum check),
       of those under 10 USDC, pooled over the four development test windows, base scenario.
     - It is measured on the G\* book after `λ` (the P5-3 engine on the four development test windows), not on the
       unscaled P5-1 replay (item 6). The 2.5k vs 5k choice is made then, before the freeze. P5-1's unscaled share
       is reported beside it.
     - The size is fixed at the freeze. A different cutoff hand-off is run at that size, and its own sub-minimum share
       is reported, not used to resize.
   - **The stress cap:** the live book's stress loss (ADR-0088 item 2) must stay within the remaining budget,
     `L_gray` minus the cumulative loss to date (item 6), at every target update and hourly.
     - It is enforced by scaling the whole sleeve, never a single leg.
     - At this stage it replaces P5: a single-leader live book cannot meet a ratio rule, and the absolute cap bounds the
       HYPE exposure in USDC directly. It also replaces S2 and P2-P4 (ADR-0088 item 7, option C).
   - **The ladder (P6)** applies to the live book.
   - **Daily reconciliation.** Every resume needs a human decision.
   - **Revert to paper** when the loss cap is hit (flatten), or when the live shortfall exceeds the stress scenario's
     for two consecutive reviews.
   - **The loss cap** is hit when the cumulative loss since the gray start (realised plus mark-to-market, including
     the modelled exit cost of the open book) reaches `L_gray`.
   - **More than one hand-off address at the cutoff (pinned here):** each goes live at the gray size while the live
     total stays within 5,000 USDC, under one `L_gray` for the whole live book. If not all fit, the higher category
     goes first, then address order (ordering by `m` is not used, ADR-0075).
5. **Fallback, if this ADR were withdrawn before the freeze:** gray stays paper. The two outcomes must then mean
   different things, or the decision changes nothing:
   - CONDITIONAL GO → the paper protocol with its revisit path;
   - NO-GO → close the project.

   The user adopted this ADR, so the fallback is not in force. It is recorded so that the freeze shows what the
   alternative was.
6. **Two details, decided by the user on 2026-11-24** (the options as put are kept):
   - **The stress cap's base: (b), the remaining budget.**
     - **(a) As written:** stress loss ≤ `L_gray` at every update. Then the realised loss is not bounded by
       `L_gray`: after a 700 USDC drawdown a full-cap shock can lose another 750. D2b and F2b test the realised loss.
     - **(b) Chosen:** stress loss ≤ `L_gray` minus the cumulative loss to date (the remaining budget). This
       bounds the total by design.
   - **The sub-minimum base: the G\* book after `λ` (chosen).** Whichever G\* limit set is chosen, its `λ` shrinks every order further. The 10% test is
     better measured on the G\* book after `λ` (P5-3 engine, development windows) than on the unscaled P5-1 replay,
     which understates the share when `λ < 1`.

## Consequences
- **ADR-0072's E1 row** is edited to the wording above, and its status line says so.
- **Protocol text:** `decision/deployment-protocol.md` (ADR-0094) carries these parameters unchanged.
- **Config:** the `gray` block of `config/risk.yaml` v3.
- **D2b and F2b** test G\* against `L_gray` (ADRs 0093, 0095). The holdout and the gray measurement are the only
  places where the cap is exercised.
