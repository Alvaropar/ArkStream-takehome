# ADR-0092: The holdout is opened once: window, configurations, the G\* rerun for a different cutoff hand-off, and the pre-registered outputs

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24). The run (P5-8) needs the user's explicit go after the joint freeze
  (ADR-0091).
  Amended by ADR-0098: runs B and C (rebuilt real costs) join the single opening; A runs first and its
  outputs are written before B or C starts
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), step P5-8
- Source: `decision/phase-5-methodology.md` section 8 (revision 4); `decision/pre-holdout-checks.md` Check 4 (day
  counts)

## Context
The holdout (3 Dec 2025 to the cutoff, 2026-01-04T23:59:42.020Z) is the only out-of-sample test of the scheme
(ADR-0086 item 3). It can be used once, and only with outputs fixed in advance.

## Decision
1. **Window: 3 Dec 2025 00:00 → 4 Jan 2026 00:00 UTC, 32 calendar rows** (3 Dec … 3 Jan).
   - **The last partial day is excluded** (pinned here). 4 Jan runs only to 23:59:42 and has no closing daily mark
     inside the data: the 5 Jan 00:00 marks, the 4 Jan 20:00 4h bar and the 4 Jan 23:00-24:00 funding all settle
     after the cutoff.
   - This matches pre-holdout Check 4 and the code, which read `splits.holdout.end` as an exclusive midnight
     (`freeze.guard(ctx, midnight(end))` in `replay_coinfilter.run_holdout`).
   - 4 Jan data is not used by anything (corrected by ADR-0100 item 1: the cutoff selection's origin is 4 Jan 00:00,
     the last origin the frozen replay admits).
   - The report states 32 calendar rows and, separately, the number of valid daily returns.
2. **Selection** at 3 Dec with the frozen rules on data before it gives the hand-off 0x2cd9, with 0x971f as the
   observation sleeve.
   - S\*, U\* and G\* run in all four scenarios (optimistic, base, stress, severe).
   - The stress shock, betas and covariance come from the 3 Dec origin (ADR-0088 item 2).
3. **If the cutoff hand-off differs** (ADR-0094), that address's G\* is run on the same holdout window, with the
   frozen rules and the 3 Dec origin's replay inputs, before any gray start. It must pass D2b too (ADR-0093).
   - This step is declared here, so it is part of the single opening.
   - It is labelled in-sample: the cutoff qualification used data through 4 Jan, which covers the window. It tests
     the risk machinery on that book, not skill.
   - An address that cannot be replayed from the 3 Dec inputs (no grade, tradable set or usable `E_ref` there) has
     D2b unmeasured, which does not pass (ADR-0068).
4. **Pre-registered outputs:**

   | # | Output | Role |
   | ---: | --- | --- |
   | H1 | Engine validity: the run completes; every state and limit event is traceable; paper fills reconcile with the replay | decides (D1) |
   | H2 | Risk behaviour: max drawdown, worst day, ladder and state events; S\* losses against the flatten step; G\* losses against the 750 USDC cap; the `λ_i` paths and P5 events | decides (D2a, D2b) |
   | H3 | **Cost model against itself, out of sample:** the simulated median shortfall per side (base) by coin against the development distribution. The holdout fills are simulated, so H3 checks the stability of the cost inputs (spreads, volume, volatility, drift) on new data, **not real fills** | decides (D3) |
   | H4 | Returns of S\*, U\* and G\*: raw, α (excluding funding) and funding, per sleeve and combined, with and without the 0x971f sleeve | **reported, not decisive**: 32 days × 2 sleeves cannot measure skill (MinTRL ≈ 1,600 days) |
   | H5 | Cross-section of every measured address at 3 Dec: the IC of the frozen statistic with holdout α; category ordering; the robustness and break-even hypotheses (pass vs fail, next α); carry books against trading books | D4 uses the IC (of `m`, or of the own-data α when `m` is constant at the origin, as at 3 Dec; ADR-0093 item 4); the rest is reported and feeds the protocol's promotion test |
   | H6 | Limit binding on the pair (P2, P5) out of sample | reported; feeds the memo |

5. **Report:** the window-report module of P5-6, run unchanged. Its schema equals the development windows' schema
   (P5-8 check). Every outcome is written to the decision entry before any interpretation.

## Consequences
- **Opened once.** No rule is changed on its result. A failure is reported, never fixed and retested on the holdout.
- **The memo labels H3 and D3 "model against model".** Real fills are measured only by the gray protocol (ADR-0090).
- **Outputs:** the holdout report and the decision entry (ADR-0093) in the trial log and `decision/`.
