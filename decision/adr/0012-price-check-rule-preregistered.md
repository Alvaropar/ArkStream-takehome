# ADR-0012: Price check rule: Binance reference vs Hyperliquid, pre-registered

- Status: Accepted (pre-registered 2026-11-19, before any comparison was computed; results in ADR-0013)
- Date: 2026-11-19
- Phase: follower replay inputs (A13)

## Context
Every price in the build is Binance (ADR-0002). Hyperliquid positions should be valued at Hyperliquid prices
unless the two agree closely. Hyperliquid history reaching 2025 is 4h candles at the finest (ADR-0010). The
venues differ by a few bps by construction (different books, index and lead-lag, A16), so "equal" is not a
test. The rule is written before any 4h comparison or per-coin statistic was looked at; the only number seen
earlier is the package-print summary in ADR-0002 (median |gap| 9 bps, 10.5% beyond 50 bps).

## Decision
**Sample, per coin** (core perps traded in eligible fills that have a Binance mapping):
- Hyperliquid 4h candles from `data/reference/hyperliquid/candles_4h/` for 2025-07-27 .. CUTOFF. A candle's
  `t` is its open; its close `c` is known at `t + 4h`. Candles with `n == 0` trades (stale close) are dropped,
  counted.
- Binance reference = the 1m bar close known **at the same instant** `t + 4h`, via the build's own lookup
  (`prices.price_asof`, `max_age_s` 60, reference only: no package-print fallback), so it is inside the coin's
  validity window and has volume. A candle without one is dropped, counted. Never the bar open.
- `gap_bps = (c_HL / ref - 1) x 1e4` (the reference is already x `price_factor_hl_per_binance`).
- Only candles whose close time is <= CUTOFF.

**Rule** (on the sample without 10-11 Oct 2025, i.e. closes in [2025-10-10T00:00Z, 2025-10-12T00:00Z)
removed):
- **pass**: >= 30 candles, median |gap| <= 10 bps **and** 95th percentile |gap| <= 30 bps. Binance stands.
- **fail**: >= 30 candles and either bound exceeded. The coin needs Hyperliquid prices or exclusion.
- **insufficient**: < 30 candles. Treated as fail for decisions (Binance not shown to be adequate).
- **no_binance**: no mapping or never valid (APEX, BLAST, LAUNCHCOIN, MNT, PURR, REQ, YZY, FTT, FOGO, MEGA).

**Reported, not part of the rule**: the same statistics for 10-11 Oct alone; the signed median gap (basis);
and, as a second view at fill times, `prices.compare_to_prints` per coin (median and p95 |gap|), which mixes
in movement within the 60 s bar age and so is expected to be wider.

Thresholds are fixed here and are not tuned after the results are seen; a later change needs a new ADR that
says it was made after seeing them.

## Consequences
Output `research/hyperliquid/price_check.csv` (one row per coin, sorted by coin) and
`price_check_bars.parquet` (every compared candle with both prices and source keys). A 4h check cannot see
intraday divergence; a coin passing at 4h closes may still differ inside the bar.
