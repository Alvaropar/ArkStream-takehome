# ADR-0061: Fund core-perp books and use venue-specific marks

- Status: Accepted
- Date: 2026-11-19
- Phase: Phase 2 rework

## Context

ADRs 0011, 0013 and 0040 specify the accrual convention, approved validator coins and daily venue. The old daily table compounded hourly proxies, and the old funding hook could miss a position opened during the preceding hour.

## Decision

Use the fixed source assignments from ADR-0013 as research configuration at every origin. Its full-sample venue validation is an inherited source qualification. The per-origin balance, price, factor and funding observations all have their own time filters. The daily panel includes all 195 coins. A daily price requires a traded Hyperliquid 4h candle closing exactly at UTC midnight. Retain candle and Binance bar source keys. On the 163 approved coins show both the 10 and 30 bps exceedances. Use 30 bps as the individual-mark flag and retain 10 bps as a diagnostic because it is the cross-bar median bound. The 22 failed comparisons retain flagged venue status. The other 10 are unvalidated. A missing comparison also has unvalidated status.

Hourly marks and excursions use the approved Binance 1m closes with at most 60 seconds of age. Zero-trade or missing HL daily bars leave daily points unpriced. The funding proxy for other coins is the most recent traded HL 4h close up to four hours old. Read hourly rates through the publication-time filter. For every nonzero position strictly before hour h, post minus signed size times proxy price times published rate to the trip holding the position. A fill exactly at h changes the next accrual. Missing rates and proxies create explicit expected accrual rows with unknown payment. Record the fill, funding response and price keys. Unknown costs propagate into complete PnL.

Daily PnL differences two midnight states (fill cash plus marked holdings) and adds interval funding. Daily return divides by the last snapshot equity known at the opening midnight. Hourly drawdown uses priced intervals and reports valued and missing hours. Trip excursions require observed hourly marks with complete pricing and funding. Open positions retain their daily mark and marked PnL with known funding alongside the completion flag.

## Consequences

Publication is commonly milliseconds after the hour. An open trade at a midnight origin can have a valid closing mark while its complete funded return is pending. Cashflows that cannot be expressed in USDC are excluded from complete returns. No historical oracle prices or margin tiers were available in the supplied inputs. The 2.5% maintenance-margin placeholder remains in use.
