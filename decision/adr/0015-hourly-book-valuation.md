# ADR-0015: Book valued hourly by exact mark-to-market; unpriced hours are null

- Status: Accepted (cross-check thresholds PLACEHOLDER)
- Amended by ADRs 0024, 0025 for the Phase 2 rework.
- Date: 2026-11-19
- Phase: Phase 2

## Context
The plan wants positions rebuilt from fills, valued daily and hourly at reference prices, as the series for
drawdown and correlation, cross-checked against account returns. Reference prices are 1m bar closes, so hour
marks are exact bar closes. Ten coins have no Binance reference.

## Decision
- PnL of hour (m, m+1h] per coin = pos_m (P_{m+1h} - P_m) + sum over fills in the hour of
  delta (P_{m+1h} - price) - fee. A left-censored series' inherited position is marked from its first
  observed fill price (an observed price, not an imputed one). Funding term only if a table is given.
- Any missing price makes that address-hour null (`priced = false`); the priced part and the unpriced
  exposure (weighted by |position| x last fill price) are kept. Hours with no position and no fill are
  exactly zero and not stored.
- Equity base = latest snapshot at or before the mark. Daily book = hours ending in (d, d+1] over equity at
  the day start, on a complete calendar.
- Cross-check per snapshot interval: book PnL of the hours ending in (prev_ts, ts] against account PnL.
  `xc_flag`: `too_few_intervals` (< 10), `disagree_corr` (corr < 0.5), `disagree_tracking` (std of the
  return gap > 0.02), else `ok` (all PLACEHOLDER). The gap includes funding, HIP-3 and spot: reported, not
  fixed.

## Consequences
On a synthetic trade the hourly PnL sums exactly to realized PnL net of fees (test). At 22 Oct the interval
correlation of account and book PnL is 0.89 over all usable intervals; account PnL 14.3M vs book 8.6M
(trial log). Hour alignment to snapshot times is within one hour. Waiting for funding: the gap and every
book-based gate.
