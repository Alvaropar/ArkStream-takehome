# ADR-0009: Treat addresses as assets: suitability gates, daily TWR, copyable series

- Status: Accepted; amended by ADR-0041 (equity is cross-margin equity: the snapshot TWR is a cross-margin account return; the rebuilt book is the series where the pnl identity fails)
- Date: 2026-11-19
- Phase: Phase 2 (evidence) to Phase 5 (portfolio)

## Context
Selection and sizing need one object per address that can be ranked, combined and stress-tested like a stock.
Leader accounts have frequent deposits and withdrawals, so raw equity growth is not a return. Phase 2 already
computes daily flow-adjusted account returns (ADR-0021), and a fills rebuild marked at the exact snapshot times
with funding matches the snapshots closely for core-perp-only accounts: median miss 0.037% of equity for grade A,
98.3% of active intervals within 1% (prototype, 2026-11-19). Several things make addresses unlike stocks: a copier
earns a delayed, costed copy rather than the leader's return; many addresses are mostly levered BTC/ETH exposure;
histories are short (median 32 completed round trips); addresses overlap and copy each other; and addresses stop,
withdraw everything or are liquidated.

## Decision
1. **Universe = an investable list per origin.** An address enters it at an origin only if it passes the
   suitability gates computed from data up to that origin: grade A/B (with coverage measured to the origin, see
   the open grading fix), not high-frequency (holding-time band, orders per day, maker share; the under-1-minute
   band is the first candidate for exclusion given the copy delay), active (fills within N days before the origin;
   a snapshot gap alone is not inactivity), the minimum round-trip count, and the tail-risk gates. All thresholds
   are PLACEHOLDER until set on development data.
2. **Return = daily time-weighted return (TWR).** Daily sub-period return r = (E_t - E_{t-1} - dND) / (E_{t-1} +
   dND) (flow at the start of the day, base case; flow at the end of the day as sensitivity; a day is excluded when
   the two differ by more than a threshold or opening equity is below 500 USDC), chained geometrically. A snapshot
   gap is one sub-period; nothing is interpolated. Inside a gap, the validated fills rebuild supplies the trading
   PnL path (drawdowns); the timing of deposits in the gap stays unknown and is stated.
3. **Two series per address.** The leader's TWR is evidence of skill. The investable "price" of an address is its
   copy series from Phase 3: the TWR of the follower replay after delay, fees, spread, impact, drift and funding.
   Phase 4 ranks and Phase 5 allocates on the copy series, never on the leader's TWR.
4. **Market exposure.** Each address's daily TWR is regressed on BTC and ETH daily returns (Hyperliquid prices,
   ADR-0040); beta and the residual return (alpha) are reported with confidence intervals. Copying is only worth it
   for the residual and for diversification; raw exposure is cheaper to buy directly.
5. **Portfolio hygiene.** Each copier cluster (copiers screen) counts as one asset; correlations are shrunk before
   any optimisation; an address that stops, withdraws everything or is liquidated keeps its final return and stays
   in the backtest universe (no survivorship).

## Consequences
Phase 2 adds the daily TWR series and the beta/alpha table per origin, and replaces hourly marks with exact
snapshot-time marks plus funding for the book-vs-account check. Phase 3's output is defined as one copy TWR series
per address. The grading fix (coverage to the origin, ADR pending) is a precondition for item 1.
