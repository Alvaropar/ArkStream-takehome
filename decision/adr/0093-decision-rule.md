# ADR-0093: Pre-registered decision rule: CONDITIONAL GO (gray) only if D1-D5 all hold, else NO-GO (paper)

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24); thresholds PLACEHOLDER. D2b is the user's decision 3 of 2026-11-23. The D4
  threshold (section 15 item 2) and D4's statistic (item 4, option c) are the user's choices of 2026-11-24.
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), applied at P5-8
- Source: `decision/phase-5-methodology-1.md` sections 0 and 9 (revision 4)

## Context
Phase 4 v2 found no capital-grade evidence of skill (ADR-0086), and a 32-day holdout cannot measure skill (H4,
ADR-0092). So the decision cannot rest on holdout returns.

What the holdout can test is whether the scheme behaves as designed out of sample:
- the engine works;
- the risk design holds on the scheme and on the book that would hold money;
- the cost inputs are stable;
- no contrary selection evidence appears.

## Decision
1. **GO is rejected:** the plan's GO needs research validity, which is not met.
2. **CONDITIONAL GO → gray protocol (ADR-0094)** if **all** of:

   | # | Condition | Measure (pinned here where the methodology left it open) |
   | ---: | --- | --- |
   | D1 | The engine works out of sample | H1 clean, and the F1 fault tests pass on the frozen code |
   | D2a | The risk design holds on the scheme | S\*, under base and under stress: the largest drawdown of the scheme's NAV from its high-water mark over the run, including the exit costs of every flatten, is ≤ 16.5% of `D` (3,300 USDC); and no limit is breached without its designed action (event log) |
   | D2b | The risk design holds on the book that would hold capital **[decision 3]** | G\* (the hand-off alone, gray size and rules), under base and under stress: the largest cumulative loss from the start (start NAV minus the lowest NAV, including exit costs) is ≤ `L_gray` = 750 USDC; and its stress cap is never breached without its action. For every cutoff hand-off address (ADR-0092 item 3) |
   | D3 | The cost model holds (**model against model**) | for each coin with at least 30 base orders both in the holdout and in the four development test windows: the holdout's simulated median shortfall per side (base) ≤ the development p90 for that coin. No such coin → unmeasured → fails (ADR-0068) |
   | D4 | No contrary selection evidence | holdout IC of the frozen statistic `m` > -0.20 (PLACEHOLDER: two development window-sds below zero; the sd of the `m` IC is 0.101). **When `m` is constant at the origin** (as at 3 Dec): the IC of the own-data α instead, > -0.14 (two development window-sds of the α IC, 0.071; item 4) |
   | D5 | Something to trade live | the cutoff selection (frozen rules, data to the cutoff) has a non-empty hand-off |

3. **NO-GO → paper protocol** if any condition fails or is unmeasured.
   - H4 (returns) is reported in full but decides nothing beyond D2a and D2b.
   - **CONDITIONAL GO is not a claim of skill.** It says that the scheme behaves as designed out of sample, so a
     small, capped live execution measurement is worth its cost (ADR-0090).
   - **D3 checks model against model.** The holdout's fills are simulated, so D3 tests whether the cost inputs
     (spreads, volume, volatility, drift) stay inside their development range. It does not test real fills.
4. **D4's statistic, undefined at the holdout origin: (c)** (the user's choice, 2026-11-24). The options as put to
   the user are kept.
   - The frozen statistic of ADR-0075 is the posterior mean `m`. At 3 Dec τ² is robustly 0, so every posterior is
     the point mass at μ0, and `m` = 0 for every address (`m_bps` = 0.0 in
     `decision/phase-4-v2-3dec-e1-e2.csv`). A Spearman IC of a constant is undefined.
   - **(a) Keep `m`, and treat undefined as 0** (the ADR-0078 convention for the development mean). D4 then passes
     by construction (0 > -0.20) and tests nothing.
   - **(b) Keep `m`, and treat undefined as unmeasured** (ADR-0068). D4 fails, and NO-GO is decided before the
     holdout is opened.
   - **(c) Chosen: when `m` is constant at the origin, use the own-data α** (unshrunk, ADR-0071), whose IC is
     always defined. The hand-off is chosen on own α (E1 needs own α > 0), so its IC is the natural test of
     contrary evidence.
     - Its threshold would be set the same way, two development window-sds below zero. The development ICs of α are
       -0.043 / +0.053 / -0.085 / -0.107 (`research/selection_v2/ranking_validation.csv`): sample sd 0.071 (0.0706), so
       the threshold is -0.14.
   - The same substitution applies to the paper revisit test, the pooled IC over at least 6 windows (ADR-0094
     item 1).

## Consequences
- **Applied once,** at P5-8, from the pre-registered outputs. The decision entry records each condition's value and
  verdict before any interpretation.
- **The memo states each condition's measure as above,** including the model-against-model label on D3.
- **The D4 item is settled** (item 4), as the freeze requires (ADR-0091 item 4). Which statistic applies is read
  at the origin, from whether `m` is constant there, before the holdout is opened. At 3 Dec it is the own-data α.
