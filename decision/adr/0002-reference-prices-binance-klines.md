# ADR-0002: Reference prices from Binance 1m klines, with validity windows

- Status: Accepted (recorded retrospectively); amended by ADR-0040 (Binance validates daily metrics; still the intraday source for 163 coins); amended by ADR-0118 (lake rebuilt from verified zips)
- Date: 2026-11-19
- Phase: Milestone 1 (A13)

## Context
The package has no prices beyond its own fills (A07). Binance USD-M 1m klines cover 186 of the traded coins
(99.2% of notional). Archive bars for contracts that are not trading are flat with zero volume (FTT all period,
LIT before 2025-12-23, MKR/OMNI/NEIROETH/AI16Z after delisting, PUMP before 2025-07-10); using them would carry
a price forward, which the rules forbid. Evidence: `data/reference/binance/SOURCE.md`, `window_evidence.csv`.

## Decision
- Price = bar close x `price_factor_hl_per_binance`, known at the bar close; bars after CUTOFF dropped.
- Only bars inside each coin's validity window (first to last bar with volume > 0; delisting dates from the
  data: MKR 2025-09-08, OMNI 09-22, NEIROETH 09-26, AI16Z 11-06) and with volume > 0.
- A price answers (coin, t) only if known in [t - 60 s, t]; else the package's own print within 60 s; else
  unpriced and logged.
- Read only through `data/reference/prices/MANIFEST.yaml` (SHA-256 per file); any other or changed file stops
  the build.
- Status per coin computed from the windows: 181 full, 4 partial, 3 never valid, 7 unmapped.

## Consequences
47,400,103 price rows, 185 coins. 10 traded core-perp coins have no reference price (7 unmapped, FTT, FOGO,
MEGA). About 10.5% of package prints differ from the reference by > 50 bps, mostly intraminute movement against
a bar close up to 60 s old; the 50 bps threshold is a placeholder and is not calibrated on that rate.
