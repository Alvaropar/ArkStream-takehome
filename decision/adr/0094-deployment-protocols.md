# ADR-0094: Deployment protocols (paper for NO-GO, gray for CONDITIONAL GO) and the cutoff deliverables; parameters fixed before the holdout

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24); parameters PLACEHOLDER. The 6-month paper stop rule (section 15 item 2) is the
  user's choice of 2026-11-24. The full text, `decision/deployment-protocol.md`, is written at P5-9 with these parameters
  unchanged.
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), step P5-9
- Source: `decision/phase-5-methodology.md` sections 10 and 12 (revision 4)

## Context
The decision of ADR-0093 chooses one of two protocols. Writing their parameters before the holdout means the holdout
cannot shape them. Only the findings are filled in afterwards: the cost re-estimates, the limit binding and the
cutoff hand-off.

## Decision
1. **Paper protocol (NO-GO).**
   - **Capital:** none. The 100k stays in reserve as off-exchange USDC.
   - **Run:** the frozen engine in paper on the cutoff hand-off plus the observation sleeve, with U\* beside it.
     Recorded:
     - signal times, intended orders and would-be fills against the live book at signal time;
     - slippage against the model, tracking, and every state and limit event.
   - **Cross-sectional panel:** every 14 days, replay all A/B addresses, then compute the frozen statistic's IC and
     the category ordering.
   - **Reviews:** every 14 days, with a summary every 8 weeks.
   - **Revisit (move to gray or to capital)** only if **all** of:
     - the pooled IC over at least 6 windows (holdout plus paper) is significant at one-sided 95%, using the
       development window-sd of 0.101. After 6 windows that means a mean of 1.645 × 0.101 / √6 ≈ **0.068** or more.
     - **When `m` is constant** (τ² robustly 0, as at 3 Dec), the own-data α is used instead, as in D4 (ADR-0093
       item 4), and the bar is recomputed from the α IC's development window-sd of 0.071 (0.0706):
       1.645 × 0.0706 / √6 ≈ **0.047** after 6 windows.
     - **One statistic per pool (pinned here):** the pool uses `m` only if `m` is non-constant at every window in it;
       otherwise it uses the own-data α at every window, with the α bar;
     - at least one E2 **trading** book (not a carry book, ADR-0084) passes every stage;
     - the engine is clean.
   - **Stop rule:** close the project after **6 months** (PLACEHOLDER; the user's choice, 2026-11-24) if the revisit conditions
     are not met.
2. **Gray protocol (CONDITIONAL GO): ADR-0090 in full.**
   - The live book is G\*. The observation sleeve stays paper.
   - The envelope: 2,500 USDC per live sleeve (5,000 under the sub-minimum rule), at most 5,000 live,
     `L_gray` = 750 USDC.
   - It ends when both 4 weeks and 200 live orders are reached, at the loss cap, or at 12 weeks.
   - The revert rules and daily reconciliation are as in ADR-0090.
   - **Escalation to a capital stage (15k)** only through the paper revisit conditions (item 1), never on PnL.
     **P4-9** (ADR-0070 item 6) runs before that stage if its sleeve size differs from 10k.
3. **Cutoff selection.** The frozen rules on data to the cutoff (2026-01-04T23:59:42.020Z), at the cutoff origin.
   If its hand-off differs from 3 Dec, ADR-0092 item 3 applies before any gray start.
4. **Cutoff deliverables (both protocols):**
   - **`trader_decisions.csv`:** every address, with its category, the first gate it fails, and its role (hand-off,
     observation, none);
   - **`target_allocations.csv`:**
     - deployed 0 (paper), or the live sleeves (gray);
     - the observation sleeve marked zero-capital;
     - the reserve.
5. **Operating answers.** Methodology section 12 maps each operating question of the written test to the rule that
   answers it. Each answer is carried into the memo, with the untested parts labelled (ADR-0064):
   - live delays and fills;
   - order-book depth;
   - venue margin and ADL;
   - leaders' invisible activity;
   - change after the cutoff.

## Consequences
- **P5-9 checks** that the protocol parameters in `deployment-protocol.md` match this ADR and `config/risk.yaml`
  exactly.
- **The paper protocol's IC test uses the D4 substitution:** with τ² robustly 0, `m` is constant, so the own-data α
  and its bar of 0.047 apply (item 1; ADR-0093 item 4).
