# ADR-0084: Square-root impact sensitivity

- Status: Accepted for research
- Date: 2026-11-20
- Phase: Phase 3 cost sensitivities

## Decision

For each coin sum volume times close over six consecutive, completed, traded Hyperliquid 4h bars. Estimate daily volatility as the sample standard deviation of the latest 42 consecutive four-hour log returns times √6. This seven-day window needs 43 positive closes, including its opening observation. Require the expected latest completed bar at decision time. A missing bar, nonpositive volume denominator or missing volatility leaves impact unavailable. Zero measured volatility is valid.

The seven-day window covers a full trading week in this continuously traded market and supplies 42 observations for the standard deviation. The candle archive gives volume in coin units. Multiplication by the corresponding bar close follows the original replay’s USDC-volume convention. The order’s coin and `bar_ms` identify its row in `impact_inputs.parquet`, which retains the candle file and the opening timestamp of the volatility window.

At acknowledgement take Q as absolute order quantity times the drifted reference price, consistent with the original linear model. Base impact in bps is 10,000 × Y × daily volatility × √(Q / daily volume). Y = 1 is a PLACEHOLDER. Stress uses three times the result. Optimistic impact is zero and requires neither input. Label nonzero-impact runs with the sqrt suffix. The optimistic sqrt result is identical to optimistic and the optimistic combined result is identical to optimistic_cap. Report those identities explicitly.

## Measurement

Calculate per-side mean fee, effective half-spread, impact and signed mid-to-reference drift in bps, weighted by absolute executed notional. Report both the full A/B universe and gate-passers separately. Report the anchor-to-mid adjustment separately so the drift statistic is interpretable. Aggregate profitability is the arithmetic mean of funded copy returns over measurable gate-passing address-windows. Report each origin's mean and the equal-origin mean as well. Compare the original and combined base cases before considering Phase 4.
