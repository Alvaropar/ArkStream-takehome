# ADR-0032: Measure the funded copy series and bracket the first delay crossing

- Status: Accepted; amended by ADR-0049 (stress results below 80% priced are unmeasured)
- Date: 2026-11-20
- Phase: Phase 3

## Decision

Use follower fill cash and actual signed holdings before each closing midnight. Mark on Hyperliquid under ADR-0020. Start with the fixed allocation and no external flows. Daily TWR is closing divided by opening equity minus one, separately with and without funding. Accrue on the position strictly before each UTC hour inside the window. Book the payment once its rate is published, applying the hour's ADR-0024 oracle proxy. An accrual at the exclusive end belongs to the subsequent period. Show missing expected terms. Require a complete daily chain and positive equity for a positive economic-screen result. Skips are part of the simulated policy. Report coverage including skipped signals even when valid cash returns exist. Leader efficiency uses the origin's ADR-0028 source, chaining usable subperiods entirely inside the window. Report observed leader days. Zero or unavailable leader return leaves efficiency null.

At the same scenario fee, spread, impact rule and parameter pool, rerun each address at 1, 10, 60 and 300 seconds. Show returns on the grid. Report the first observed positive-to-nonpositive crossing as a bracket, separately labelling a loss at the shortest delay, an unmeasurable point or a return still positive throughout. No extrapolation or monotonicity assumption. A bracket describes the actual skip policy and can reflect changing coverage. With quantities fixed, break-even total cost per unit of turnover equals (net funded PnL + observed shortfall versus leader fills including fees) / executed notional. Additional cost headroom equals net funded PnL / executed notional. Report both in bps.

Compare completed follower round trips within each origin's leader holding band. Split reversals at zero, apportion fees by size, and divide gross cash PnL at leader anchors, execution shortfall plus fees, and funding by peak marked notional at the fills. Report their arithmetic means. A band with positive mean net funded result clears this descriptive screen. For the first screen, report strictly positive funded copies among the origin's gate-passers. Also report usable and traded counts, stress performance and skips. Consistency across development tests and the plan's 10% stress loss step inform the economic decision. No ranking is involved.

## Consequences

A grid point with zero executed orders cannot establish a delay crossing. The trip tables carry the origin's leader holding-time band. Orders without a completed leader trip contribute to a separate coverage row. The excluded-coins diagnostic reports the two benchmark books' terminal PnL difference, its trading and funding components, and the count with both closing valuations available.

Positive outcomes can be sensitive to the subset of orders with eligible prices. Mean shortfall on parameterised orders understates copy-series volatility for those coins and can distort Sharpe. Carry that note alongside each reported follower volatility or Sharpe.
