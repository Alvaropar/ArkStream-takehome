# ADR-0064: Scope is the gray-launch go/no-go decision; Phases 5 and 6 are not built

- Status: Accepted; items 1, 3 and 4 amended by ADR-0065 (new Phase 5: capital, limits, pause and exit designed before the holdout)
- Date: 2026-11-22
- Phase: all remaining work (after Phase 4 development, before the holdout)
- Amends: the plan v2 phase list (Phase 5 portfolio replay, Phase 6 operations)

## Context
The plan v2 lists Phase 5 (a shared 100k USDC account replay with cross-leader netting, margin, allocation and
portfolio stress) and Phase 6 (runbook, incident playbook, copy-engine state machine, reconciliation, WebSocket
limits). The user ruled on 2026-11-22 that these cannot be done inside the take-home and that the deliverable is
the go/no-go decision for the gray launch.

The written test (`ArkStream_Quant_Researcher_Written_Test_EN.pdf`) still asks, in prose, for:
1. Launch or postpone; if launch: the address set, why each is in or out, how they form the portfolio, the capital
   arrangement, number of addresses, unallocated capital, risk limits, pause and exit conditions. If postpone: the
   conditions to resume evaluation.
2. Key assumptions, then the operating arrangement: how decisions update on new records, when instructions are
   generated, how simultaneous instructions on one contract become one order, fill-vs-target discrepancies, when
   capital may increase and when risk must be cut, what needs manual intervention, what is set or reviewed by hand.
3. Key decisions traced to specific addresses and records, and where the scheme can be wrong.
4. How reviewers trace conclusions from raw data and how the work continues on new data.

## Decision
1. **Not built:** the Phase 5 shared-account replay and portfolio stress, and the Phase 6 engine, state machine,
   reconciliation code, runbook and incident playbook.
2. **Kept, as memo text from existing evidence:** items 2 and 4 above are answered in writing from what the
   replay already implements and measured (target-position mirroring with netting, ADR-0001/0002 lineage; frozen
   E_ref sizing, ADR-0037/0052; 1.5x gross cap; delays ADR-0058/0062; coin filter ADR-A0140; gates and equity band
   ADR-A0130). Statements the replay did not test (cross-leader margin interaction, live reconciliation) are labelled
   as untested assumptions, never as results.
3. **Item 1 follows the evidence.** If the holdout outcome is postpone or shadow-only, the memo gives the resume
   conditions instead of a capital arrangement; if it is launch, the arrangement uses per-address allocations from
   the shortlist with the cap and limits already in the replay, and states that the joint account was not replayed.
4. Remaining work: research the user still wants before the holdout; re-freeze if hashed files change; holdout once;
   `trader_decisions.csv` and `target_allocations.csv`; the decision memo; the package and its independent re-check.

## Consequences
The memo cannot claim portfolio-level results (joint drawdown, margin calls, netting savings across leaders); it
reports per-address copies and says so. The plan v2 phase list is superseded on these two phases.
