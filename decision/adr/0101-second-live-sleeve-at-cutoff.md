# ADR-0101: The second live sleeve at the 4 Jan cutoff: 0x971f, chosen for the measurement

- Status: Accepted (the user's decision, 2026-11-25: "Go with 0x971f"). For the 4 Jan 2026 cutoff only, it resolves
  the conflict between ADR-0090 item 4 and ADR-0100 item 6.
  - ADRs 0090 and 0100 are in the frozen set (`freeze.FROZEN_ADRS`, ADR-0097), so their status lines are not edited:
    an edit would change the freeze hash.
  - The amendment is recorded here and in the index row instead.
- Date: 2026-11-25
- Phase: Phase 5 (revision 4), P5-9. Decided after the holdout and after the cutoff deliverables were computed.

## Context
**The cutoff hand-off has four addresses, and two fit live.**
- The four are 0x2cd9, 0x3a12, 0x971f and 0xe65c, all E1
  (`research/cutoff/selection_v2/origin=2026-01-04/eligible.parquet`).
- The gray envelope takes two of them at 2,500 USDC each (ADR-0090 item 3).

**Two frozen texts order them differently after the category:**

| Text | Order after the category | Live at 4 Jan |
| --- | --- | --- |
| ADR-0090 item 4 (the user's decision, pinned before the freeze) | address order ("ordering by `m` is not used", ADR-0075) | 0x2cd9, 0x3a12 |
| ADR-0100 item 6 (methodology section 10.3; `cutoff.target_allocations`) | D4's statistic at the origin, descending (`m`, or own-data α when `m` is constant), then address order | 0x2cd9, 0x971f |

- ADR-0100's "Refines" list does not name ADR-0090. The conflict was not noticed when ADR-0100 was written; it was
  found at P5-9.
- The deliverable `research/cutoff/deliverables/target_allocations.csv` is the frozen code's output: 0x2cd9 and 0x971f
  live.

**The frozen code falls back to own α only because of a numerical artifact.**
- At 4 Jan `m` is constant because τ² is 0.
- τ² is 0 because one E- address, 0x4c60401b…, has own α -1.8e-17 and standard error 7.1e-18. It takes all the
  inverse-variance weight in the DerSimonian-Laird step, although Cochran's Q rejects homogeneity (Q = 3,617 on 255
  df, p = 0; `research/cutoff/selection_v2/tau2.csv`).
- Without that address, τ² is 5.4e-7. The categories and the order without it have not been computed.
- The decision (D4 at 3 Dec) and the hand-off's membership do not depend on it (`decision/deployment-protocol.md`
  section 2.1).

**What each candidate did in the holdout.** Each address ran alone as a G\* book at 2,500 USDC, base scenario
(`research/holdout/portfolio/run=A/origin=2025-12-03/config=G2500_0x971f` and `config=G2500_0x3a12`; H2, H4):

| | 0x971f | 0x3a12 |
| --- | --- | --- |
| Orders (per week) | 73 (16.0) | 15 (3.3) |
| Mean gross | 200 USDC | 498 USDC |
| Worst loss incl. exit, base / stress | 22 / 15 USDC | 42 / 43 USDC |
| Coins | BNB and BTC, long | BTC long (small ETH, PUMP) |
| Intents under 10 USDC | 12 of 138 (8.7%) | 2 of 19 (10.5%) |
| Raw return, base | +1.43% | +2.27% |
| α, base (bp per day of gross) | -30 | -24 |

Paired with 0x2cd9, the live book would place about 45 orders a week with 0x971f, so the 200-order minimum would take
about 4.5 weeks. With 0x3a12 it would place about 32 a week, about 6 weeks (`decision/deployment-protocol.md`
section 3).

## Decision
1. **The live sleeves at the 4 Jan 2026 cutoff are 0x2cd9 and 0x971f, at 2,500 USDC each.**
   - 0x3a12 and 0xe65c run in paper at 10,000 notional.
   - The reserve is 95,000 USDC, off-exchange.
   - This equals the frozen deliverable, which stays as computed.
2. **The reason is the measurement, not the ranking.**
   - The gray is an execution measurement (ADR-0090).
   - 0x971f gives about five times the orders of 0x3a12, with less exposure and a smaller worst loss.
   - It also adds BNB, the coin whose D3 median came closest to its limit (10.3 against 11.5 bp).
3. **What is not the reason:**
   - **Own α,** the frozen code's reason. It has no predictive support: D4's IC was -0.085, and the development mean
     IC was -0.030 (ADR-0075). At 4 Jan it also rests on the τ² artifact.
   - **Returns.** 0x3a12 had the higher holdout return.
4. **The tiebreak in ADR-0090 item 4 is departed from at this cutoff.** The departure is recorded here and in the
   memo.
5. **Scope: the 4 Jan cutoff only.** This ADR sets no ordering rule for any other origin.

## Consequences
- **The deliverable, the memo and the protocol agree.** No override file is needed. The Phase 5 session updates
  `decision/decision-memo.md`, `decision/deployment-protocol.md` (sections 2.1 and 7) and `provenance/trial_log.md`
  to cite this ADR.
- **How it was chosen.** The user chose after the holdout, with both candidates' holdout runs known.
  - The criteria are the order rate, the exposure and the worst loss, not a return or α measure.
  - The data predate the cutoff.
- **ADRs 0090 and 0100 are unchanged** because of the freeze. The index row carries the amendment.
- **Still open before any re-qualification (A12).** Each needs its own ADR and a new freeze before use:
  - **The ordering at later origins.** The conflict between ADR-0090 item 4 and ADR-0100 item 6 remains in the frozen
    texts and in the code. The options put to the user:
    - address order;
    - expected live orders per week per USDC of stress loss on the training window, then address order.
  - **A floor on the standard error,** or the exclusion of degenerate measurements, in the τ² step.
- **O2 stays open.** It is the user's decision and is not touched here.
- **The pair was never replayed as one book.** D2b tested each address alone. A shared `L_gray` binds sooner than
  either sleeve alone, unless their positions offset.
- **0x971f's sub-minimum share is 8.7%** in its holdout G\* rerun, under the 10% line. It is reported, not used to
  resize (ADR-0090 item 4).
