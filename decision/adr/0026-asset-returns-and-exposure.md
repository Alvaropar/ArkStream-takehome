# ADR-0026: Measure address TWR and joint BTC/ETH exposure

- Status: Amended by [ADR-0028](0028-cross-margin-return-source.md) for the primary return source
- Date: 2026-11-19
- Phase: Phase 2 rework

## Context

ADR-0007 defines the address as the unit of evidence. Multi-day account observations and unobservable deposit times constrain daily risk and exposure estimates.

## Decision

Chain the usable start- and end-flow subperiod returns separately. Keep a single return across a snapshot gap, exclude both intervals touching a confirmed frozen snapshot and retain ADR-0014's denominator, opening equity and convention checks. An excluded subperiod is absent from the product. Report covered calendar days out to the origin, one-day sample size, and both cumulative returns.

Add interim drawdown observations within usable multi-day intervals where the book is checkable. Start from the actual opening snapshot and compare the cumulative funded book there with each intervening UTC midnight valued on Hyperliquid. Scale trading PnL by opening equity plus interval flow. Deposit timing inside the gap is unknown. The endpoint is the measured TWR. Missing interior marks remain null and are counted. Measure drawdown from an initial wealth of one and all subsequent available peaks.

Use simple one-day start-flow returns for daily sample volatility and zero-risk-free daily Sharpe. Multi-day returns do not enter these statistics. Use joint OLS with an intercept for BTC and ETH. Align each snapshot to its nearest UTC midnight for market returns and require consecutive matched boundaries and both traded prices. This approximates the snapshot-to-snapshot market window. Only closes known by the origin can enter the regression. Alpha is the intercept per day. Report matched sample and calendar coverage. Fewer than four joint observations or a rank-deficient design yields null coefficients.

Report two-sided approximate 95% normal intervals using Bartlett HAC with up to seven observation lags for the regression scores and Sharpe influence function. Regression covariance uses the n/(n−3) small-sample multiplier. Volatility, alpha and Sharpe use daily units. These short-history intervals are descriptive.

## Consequences

The series, gap path and matched regression sample make the estimates independently reproducible. Gaps cannot establish a daily return path, and incomplete drawdown coverage can miss deeper interim losses.
