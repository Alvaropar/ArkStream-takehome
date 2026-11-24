# ADR-0031: Freeze print spreads after the first development window

- Status: Accepted
- Date: 2026-11-20
- Phase: Phase 3

## Decision

Use the first 14-day development window for calibration. Deduplicate observations of the same print by coin, timestamp, trade ID, price and size, retaining a deterministic close. Use adjacent one-minute UTC bars, each with at least two prints, and at least 20 usable pairs per coin (PLACEHOLDER). The development print-count comparison is in the trial log. Compute the Corwin–Schultz relative spread with each negative pair clipped to zero. Compute Abdi–Ranaldo from the same pairs using the nonnegative mean squared estimate before the square root. Convert both full spreads to half-spread bps. Apply the larger of the configured and Corwin–Schultz half-spreads in each scenario starting at the calibration end. Prior orders and coins without a fit use the configured spread.

Simulate 2,048 pairs per eligible coin with seed 8082, resampling its observed pair of minute print counts. Simulate a log random walk with its observed RMS one-minute close move and independent equiprobable buys and sells at its known configured base half-spread. Report the CS bias and Monte Carlo standard error. Describe a downward bias only if bias plus 1.96 simulation standard errors is negative. The simulation models sparse sampling and clipping. It does not reproduce exchange tick rounding.

Base impact in bps equals 10,000 times absolute order notional at the drifted reference divided by the volume of the latest completed traded Hyperliquid 4h bar, valued at its close. Stress triples this value and optimistic impact is zero. A missing current completed bar makes impact unavailable. Treat a coin with less than 1 million USDC of volume in that bar, or an unavailable bar, as thin for the stress delay. These are PLACEHOLDER assumptions. A candle close and its volume become usable at its closing time.

## Consequences

Only coins with enough consecutive active minutes get a fitted spread. Publish the bar count rule, number of pairs, estimator gap, bias and effective spread increase. Record the volume observation time on orders.
