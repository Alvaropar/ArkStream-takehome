# ADR-0086: Phase 5 tests a two-sleeve paper scheme (S\*) beside its unconstrained twin (U\*) and the capital book (G\*)

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24, with the recommended option on every open item,
  before any Phase 5 result). Items 4 and 5 (U\*, G\*) carry the user's decisions 2 and 3 of 2026-11-23.
- Date: 2026-11-23
- Phase: Phase 5 (revision 4)
- Amends: ADR-0065 item 2 (the scope: no weighting across a basket while there are two sleeves; item 7 below);
  applies ADR-0070 item 6 (P4-9 is not triggered, item 6 below)
- Supersedes: revision 2 of the Phase 5 methodology (never written up as ADRs; deleted on 2026-11-24, when revision 4
  took its file name)
- Source: `decision/phase-5-methodology.md` sections 0-2, 7 and 11 (revision 4)
- **Designed after seeing the Phase 4 v2 results.** Phase 5 is designed on development data by ADR-0065, so this is
  not a change to an existing rule. The choice of 0x971f as observation sleeve uses data up to 3 Dec (item 3).

## Context
Phase 4 v2 found no capital-grade evidence of skill (`decision/phase-4-v2-results.md`, run 4 with ADR-0084):
- τ² is robustly 0 at 3 Dec (Q p = 0.69), so every posterior is the point mass at μ0 = 0, and no address is E2;
- the 3 Dec hand-off is 0x2cd9 only: E1, α 26.7 ± 61.9 bps per day of gross, -8.7 without its best week (not robust);
- ordering is not used: the mean IC of `m` is -0.030, positive at 1 of 4 origins (ADR-0075);
- the copy keeps about 16% of a leader's edge after costs and delay.

Revision 2 designed allocation across a basket that this evidence does not support. A direct GO needs research
validity, which is not met. 0x2cd9 is about 91% HYPE, long only: alone it cannot meet the coin-concentration limit P5
(ADR-0088), so a one-sleeve "portfolio" would test something that cannot exist inside our own limits.

## Decision
1. **What Phase 5 decides:** CONDITIONAL GO or NO-GO (ADR-0093), which chooses the deployment protocol, gray or paper
   (ADR-0094). **GO is rejected.**
2. **The two sleeves** (both E1 at 3 Dec; figures from `decision/phase-4-v2-3dec-e1-e2.csv`):

   | | 0x2cd9f4645b14bf968212c7c108213eaeb193946e | 0x971fc0c9becffd708c52a195b8a87c27359e77fa |
   | --- | --- | --- |
   | Role | **formal hand-off**: the frozen Phase 4 rule's only 3 Dec hand-off | **observation sleeve**: declared here, outside the hand-off |
   | α ± s, bps/day of gross, excl. funding | 26.7 ± 61.9 | 75.7 ± 44.9 |
   | α without its best week | -8.7 (not robust) | 56.5 (robust) |
   | Book | about 91% HYPE, long only | about 62% BNB, 38% BTC, long only |
   | S2 / S3 | pass / pass | **fails gate 7b only** / pass |

   - **Why 0x971f is run:** it is the only robust E1 address at 3 Dec outside HYPE, and only two or more sleeves
     exercise per-coin netting, limits that bind across sleeves, shared participation and one sleeve in a risk state
     beside a normal one.
   - **What its status is:** gate 7 is not changed. 0x971f fails 7b (gap-rate lower bound 5.46 against 5.0
     bps/day), entirely from two recorded withdrawals (src_row 75841, 12 Oct, -420 USDC; src_row 75852, 23 Oct,
     -728 USDC). It runs with the same engine, sleeve size and limits as 0x2cd9, with **zero capital in every
     protocol**.
   - **Its capital path:** none unless it re-qualifies under the frozen rules, at the cutoff selection or a later
     review (section 15 item 4; confirmed by the user on 2026-11-24).
3. **Selection is in-sample on every development window.** Both addresses were chosen with data up to 3 Dec. Every
   development result for the pair is labelled "selection in-sample on these windows; machinery test, not skill".
   The holdout is the only out-of-sample test of the scheme.
4. **S\*, the scheme:** a paper copy of the two sleeves.
   - **Sleeves:** 10,000 USDC notional each, the provisional Phase 4 size (ADR-0070 item 6); `D` = 20,000.
   - **Sizing:** frozen reference equity (ADR-0052), `k_i = min(A_i / E_ref,i, 1)`, no scale-up (ADR-0037).
     0x971f's equity (about 7.5k) is below its sleeve, so its sleeve is partly idle; that is reported as utilisation.
   - **Coins:** each wallet's tradable universe at the origin (ADR-0073), with the 1.5x cap solved on the full book.
   - **Weights:** equal. There are no weighting variants: with two sleeves there is nothing to optimise.
   - **Rules:** execution ADR-0087, limits ADR-0088, risk states and triggers ADR-0089. The two risk-rule variants
     (cap denominator; `E_ref` at reviews) are settled on the population by ADR-0095.
5. **Three configurations, run side by side** on the same leader events, delays and costs, in one event loop:

   | Configuration | What it is | Why |
   | --- | --- | --- |
   | **S\*** | both sleeves, 10k each, every limit, state and trigger | the strategy under test |
   | **U\*** (unconstrained twin) **[decision 2]** | both sleeves, 10k each; the execution model of ADR-0087 in full and the sleeve gross cap S1; no other limit, no risk state, no trigger | the leader-shaped copy. S\* minus U\* is the effect and cost of the limits |
   | **G\*** (the capital book) **[decision 3]** | the hand-off alone (0x2cd9 at 3 Dec) at the gray size, under the gray rules and the `L_gray` = 750 USDC loss cap (ADR-0090) | the book that would hold money, judged by D2b (ADR-0093) |

   G\*'s limits are option C of ADR-0088 item 7 (the user's choice, 2026-11-24): the `L_gray` stress cap on the
   remaining budget replaces S2 and P2-P5; O1-O4, S1, S3 and the P6 ladder stay, with S3 and P6 on the live book's
   own high-water mark.
6. **P4-9 (ADR-0070 item 6) is not triggered.**
   - S\* and U\* run at 10k, the size Phase 4 qualified at.
   - G\* runs at 2.5k (set at P5-5; the rule allowed 5k), but it is an execution measurement paid as a research cost, not an allocation
     (ADR-0090). Its size is not a Phase 5 capital size in the sense of ADR-0070 item 6.
   - A smaller sleeve only eases the size-dependent tests:
     - T3 (fit under 0.5% participation) passes more often as orders shrink, so every coin tradable at 10k stays
       tradable. G\* trades the 10k universe, which is a subset of what a 2.5k universe would allow, so it never
       trades a coin that fails T3 at its own size;
     - impact, T4 and the break-even delay only improve;
     - the equity band is on the leader's equity, not the sleeve.
   - The one effect that works against a small sleeve is orders under the 10 USDC minimum. P5-1 reports it unscaled;
     the gray size is set on G\* after `λ`, from the P5-3 engine on the development test windows (ADR-0090 item 4).
   - **What this costs:** a 2.5k universe could be wider and could add addresses to the hand-off. That widening is
     not used: the hand-off stays the one qualified at 10k.
   - P4-9 runs, as ADR-0070 describes, before the first capital stage whose sleeve size differs from 10k (ADR-0094).
7. **Deferred until at least 3-4 capital-eligible candidates exist,** and brought back with the first capital stage:
   - subset search and the effective number of bets;
   - the weighting rules (capped equal weight, inverse stress, equal risk contribution) and the risk-model blend;
   - capacity grids beyond the gray sizing;
   - 1,000-scheme evaluation and the pilot-horizon bootstrap;
   - the account-structure (one account vs sub-accounts) and margin-contagion tests.

## Consequences
- **Development findings feed the memo** (methodology section 7, ADR-0095):
  - whether the two books can live inside the limits: 0x2cd9's time-weighted `λ`, how often P5 binds, S\* against U\*.
    The section 4.1 arithmetic put 0x2cd9 at `λ ≈ 0.15` near full gross: the pre-run estimate, which would have read
    "our per-coin limits hold a single-coin leader at about one-seventh of a sleeve; capital needs more independent
    sleeves". Measured at P5-5 (`decision/phase-5-results.md` section 7): the leader runs at about 0.1x leverage, so
    the copy holds 5-14% of its sleeve (51% in the crash window), and the exposure-weighted `λ` is 0.19 in the 8 Oct
    window and 0.34-0.81 in the others. Either way a result, not a failure;
  - the trading cost of the risk actions and their effect in the crash window;
  - whether the cost model matches on these books.
- **Outputs** are produced by P5-1 to P5-6 under ADR-0095. The joint freeze (ADR-0091) covers this declaration,
  including the observation sleeve.
- **Tests:** F6 (shape: S\* and G\* targets equal `λ_i` × the U\* targets on every leg, ADR-0095) and the in-sample
  label in every development table.
