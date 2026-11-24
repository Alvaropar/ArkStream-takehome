# ADR-0098: Holdout cost runs B and C: rebuilt real costs with the strategy frozen

- Status: Accepted (the user approved it on 2026-11-24: "Accept it"). It amends ADR-0092 (two more runs in the
  single opening), ADR-0093 (B and C reported, A still decides), ADR-0091 (the frozen set grows), ADR-0089 (C1's
  benchmark in run C) and rule 3 of `config/decision_context.yaml` (holdout data may set cost inputs inside B and C
  only). Its item 11 details are pinned in ADR-0099.
  **Erratum (2026-11-24):** the first draft said "the S1 stress cap" in three places (Context, the item 5 table,
  Consequences). S1 is the sleeve gross cap and reads no cost model; the stress limits that read the cost model are
  S2, P4 and P5 (and `L_gray` for G\*). The three places now say so, as ADR-0099 item 9 read them.
- Date: 2026-11-24
- Phase: Phase 5 (revision 4): built and tested before P5-7 (joint freeze), run at P5-8
- Source: the user's design of 2026-11-24 (runs A, B, C; the cost rebuild is "not a run"), and the C1 point the user
  raised the same day

## Context
**What the frozen run (A) charges.** Only copy orders on BTC, ETH, HYPE and SOL see real prices: the Binance tape over
the fixed delay. Every other cost is a parameter fixed before the holdout:
- the spread: one fit on 8-22 Oct (ADR-0031). HYPE's estimate, 4.36 bp, is under the 5 bp floor, so the floor applies;
- the drift table: fitted per origin, so once for the holdout (3 Dec);
- impact: square-root model with `y` = 1.0, a placeholder (ADR-0033);
- the delay: fixed 1,200 ms (ADR-0058);
- fill completeness: every order fills in full. The O2 price bound (ADR-0088) is not simulated.

So the cost check (D3) and the execution trigger (C1) in A compare the model with itself (ADR-0092 H3, ADR-0089 item 3).

**The user's questions** (2026-11-24):
1. How does the frozen strategy perform under the frozen cost model?
2. How accurate is that model on unseen data?
3. How does the frozen strategy perform under real conditions?
4. How does it perform when the cost model updates through time on point-in-time data, as it would live?

**The risk rules read the cost model.** The stress exit cost (`exit_bps` with the stress costs, `portfolio_engine.py`) feeds:
- the stress limits S2, P4 and P5 (and the `L_gray` stress cap for G\*), through `stress_loss` in the λ solver;
- the gray loss cap, through `exit_cost` in the hourly loop;
- C1, which compares the 14-day median realised shortfall with the stress model's for the same orders (≥ 5 orders).

O2's bound is also a stress-model quantity: the stress p99 shortfall by liquidity bucket.

**C1 in development.** Base: 1 firing in 8 sleeve-windows of S\* (8 Oct, 0x971f), none for G\*. Stress and severe: 3
each for S\*, 1 each for G\*. Source: `research/portfolio_replay/pair_summary.csv`.

**Data.**
- The user rejected the Hyperliquid L2 archive on 2026-11-24: "Data from Hyperliquid L2 archive is rejected, only
  Binance files can be retrieved if needed."
- On disk:
  - Binance aggTrades for BTC, ETH, HYPE and SOL, 2025-09-08 to 2026-01-04;
  - the package's Hyperliquid prints and fills, with `is_maker`;
  - the delay distribution in `research/latency/total_delay.csv`. Per-draw method: p50 1,225 ms, p99 3,540 ms. The
    receive leg was measured on Hyperliquid in Nov 2026 (284 fills, ADR-0056); the acknowledgement leg is transferred
    from Binance (30 orders).

## Decision
1. **Three holdout runs, one frozen strategy.**

   | Run | Strategy rules | Cost model in the risk rules | Costs charged on fills |
   | --- | --- | --- | --- |
   | **A** | frozen | frozen | the frozen model (base, plus the other scenarios as in ADR-0092) |
   | **B** | frozen | frozen | the cost rebuild (item 2) |
   | **C** | frozen, except through the updated risk inputs of item 5 | updated daily on point-in-time data (item 4) | the cost rebuild (item 2) |

   - B runs on S\*, U\* and G\*. C runs on S\* and G\*: U\* has no limits or triggers, so C on U\* would equal B.
   - **C is a variant, not the frozen strategy.** It is evidence for a later version with a live-updated cost model.
     It decides nothing.

2. **The cost rebuild (not a run).** It prices each order from the market records at that order's time.

   | Part | Rebuild | Fallback, flagged on the fill |
   | --- | --- | --- |
   | Delay | one draw per order from the per-draw delay distribution (`total_delay.csv`), fixed seed | none |
   | Drift | the Binance tape over the drawn delay, basis-corrected, for **every** order on BTC, ETH, HYPE, SOL (copy and non-copy) | other coins: the frozen approximate method (rule 5), unless the user approves aggTrades downloads for them |
   | Spread | the ADR-0031 estimator on the Hyperliquid prints of the order's UTC day, without the scenario floor | fewer than 20 one-minute pairs that day: the frozen value |
   | Impact | the square-root form (ADR-0033) with `y` fitted on the leaders' taker fills (`is_maker` false) of the same day, cost measured against the basis-corrected Binance tape | coins without tape, or too few taker fills: the frozen `y` |
   | Fill completeness | an IOC at the frozen O2 bound: if the rebuilt shortfall exceeds the bound, the order gets no fill and is recorded as rejected. The engine's failure path recomputes `Δ` from state (ADR-0087) | binary: no depth data, so no partial fills |
   | Fee | 4.5 bps, unchanged | none |

   - Funding and marks are unchanged.
   - Binance `bookDepth` may be added as a cross-check on impact only, if the user approves each download. Its bands
     are coarse, and it is another venue.

3. **Timing.**
   - The rebuild may use data from around the order's time, because it stands in for the market.
   - It never enters a decision in A or B.
   - In C, a past fill's rebuilt cost enters the cost model only after that fill's rebuild window has closed.

4. **C's cost model** is refitted daily at 00:00 UTC on data before that time:
   - the spread: the ADR-0031 estimator on the trailing 14 days of prints (the length of the original fit), floor kept;
   - the drift table: the development estimation rules (rules 4 and 5) on the trailing data;
   - impact `y`: the trailing 14 days of leader taker fills, plus C's own past fills' rebuilt costs.

   **Fixed in C:**
   - the delay (1,200 ms; C has no orders of its own to measure);
   - the fee;
   - the stress model's fixed parts: half-spread floors 3 / 15 bp, 5,000 ms delay, the 3× impact multiple;
   - the benchmarks of item 5.

   **Hourly refits are rejected.** The spread fit needs 20 consecutive one-minute pairs with at least 2 prints each,
   and an hour gives at most 59. Volatility, volume and basis already update every 4h bar or daily in every run.

5. **A check that tests the cost model keeps a frozen benchmark. A rule that uses the cost model to estimate a loss
   may use the updated one.**

   | | The stress limits S2, P4 and P5, the gray loss cap | C1, O2 |
   | --- | --- | --- |
   | A | frozen model | frozen model |
   | B | frozen model | frozen model; realised = rebuilt cost |
   | C | updated model | frozen model; realised = rebuilt cost. A shadow C1 and a shadow O2 on the updated model are logged and never acted on |

   - In C the realised cost is the quantity the updated model learns from. A C1 benchmarked on that model would
     absorb gradual deterioration, the failure C1 exists to catch. The shadow logs measure how many firings it would
     miss.

6. **Recording.** Every physical fill in B and C records, per part (delay, drift, spread, impact, fee, fill status):
   - the frozen model's cost (base);
   - in C, the updated model's cost (base);
   - the rebuilt cost.

   The accuracy measurement uses these, within each run. Orders are not matched across runs: NAV, limits, triggers
   and positions diverge once costs differ.

7. **Order and decision.**
   - **A runs first.** Its outputs and D1-D5 verdict are written to the decision entry (ADR-0093) before B or C starts.
   - **A decides; B and C are reported.** They never change the verdict.
   - **D3 and C1 are also reported on B,** where they test real costs against a fixed benchmark for the first time.
     If B fails a condition A passes, the memo's summary says so.
   - **B and C are labelled "rebuilt real conditions",** not real fills.

8. **Development first.**
   - Before the freeze, B and C run on the four development test windows (8 Oct-3 Dec), as their test and a first
     accuracy reading.
   - The results go in `decision/phase-5-results.md`. They are descriptive: no strategy parameter changes on them,
     and a code fix is logged in the trial log.
   - The rebuild, C's refit, the holdout entry point and their tests join the frozen set (ADR-0091, ADR-0097). One
     hash is computed after that.

9. **Rule 3 amended.** Holdout data may set cost inputs only inside runs B and C, under items 2-5. It never sets
   anything used by A, by D1-D5, or by any frozen parameter.

10. **Data.**
    - The Hyperliquid L2 archive is not used.
    - The core design needs no download. Binance public files (`bookDepth`; aggTrades for traded coins without tape)
      are downloaded only after the user approves each one (name, source, size).
    - Before the freeze, only files for dates before 2025-12-03 are read.

11. **Pinned before the freeze, on development data:**
    - the rebuild windows (the spread day, the impact fit window and its reference price);
    - the spread estimator's bias handling in the rebuild;
    - the delay seed;
    - C's trailing windows;
    - the minimum print and taker-fill counts for each fallback.

## Consequences
**What each comparison answers:**
- **A vs B:** how much the frozen cost model's error changes P&L, with rules and risk inputs identical.
- **B vs C:** what updating the cost model is worth through position sizing (the stress limits S2, P4 and P5, the
  gray loss cap). Both are charged rebuilt costs.
- **Accuracy:** per order, the frozen model's cost against the rebuilt cost (B), and the updated model's cost against
  the rebuilt cost (C).
- **The shadow logs:** the safety cost of letting C1 and O2 adapt.

**Limits:**
- The rebuild is a reconstruction from prints and the tape, not an order book. It is the best reference available,
  not ground truth.
- The delay distribution was measured in Nov 2026 on a home connection (ADR-0056), not in Dec 2025.
- Fill completeness is binary.
- Coins without tape keep the approximate drift unless downloads are approved.
- The leaders' taker fills reflect their order sizes, not ours.

**Only the gray (ADR-0090) can show:**
- how our own orders interact with the book (queue position, hidden liquidity);
- venue rejections, outages and rate limits;
- our actual latency.

**The freeze:**
- The frozen set grows by the rebuild, C's refit and the holdout entry point.
- The hash is computed once, after they are built and tested, and sent nowhere before then.

**Follow-up edits,** made with this ADR on 2026-11-24, after the Phase 5 commits:
- the index row;
- the status lines of ADRs 0089, 0091, 0092 and 0093;
- the note on rule 3 in `config/decision_context.yaml`.
