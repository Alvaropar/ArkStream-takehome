# ADR-0045: Worst-case drawdown inside each 4h bar, with a gate

- Status: Accepted (threshold PLACEHOLDER)
- Date: 2026-11-20
- Phase: Phase 2 (leader evidence)

## Context
The Phase 2 drawdowns value positions at one price per period: hourly (Binance 1m close at the hour, the
"intraday" drawdown) and daily (Hyperliquid 4h close at midnight, max drawdown, worst day and worst 3 days). A coin
that falls 70% and recovers inside an hour is never seen, and hours with any unpriced position (the 32 coins
without an intraday price) were dropped from the hourly drawdown. The user requires that such holdings be caught.

## Decision
1. **Primary measure, all coins: Hyperliquid 4h OHLC** (`hlprices.load_candles_ohlc`, `leader_worstcase.py`). Per
   address, coin and 4h bar, each position is valued at the most adverse price the coin reached in the bar: the
   position at the bar open and the position after the bar's fills, each at the bar's low and high, taking the
   worst. Bars are chained on the close-to-close book PnL over the latest cross-margin snapshot equity known at the
   bar open; the worst-case trough of each bar is measured against the running peak. `wc_max_dd` is the deepest.
2. **Check, recorded, not used for the gate: Binance 1m highs and lows** over the same four hours (times the price
   factor; minutes with volume, inside the coin's validity window) for the 163 coins that passed the price check.
   Per address `wc_max_dd_binance_check` and the gap; per coin the median and tail gaps between the Hyperliquid and
   Binance extremes (`worstcase_check.parquet`).
3. **Gate** `gate_worstcase_dd`: passes when `wc_max_dd >= -0.50` (`leader.gates.max_worstcase_dd`, PLACEHOLDER,
   the same level as the max-drawdown gate). Missing means unmeasured, which never passes.
4. A loss larger than equity wipes the account: the chained index and the trough are floored at zero, so a
   drawdown is never below −100%. Sums across coins are sorted before aggregation, so reruns are byte-identical.
5. A held coin with no Hyperliquid bar makes that address's bar unpriced: counted (`wc_bars_unpriced`) and
   skipped, never filled in. Funding is left out of this measure; a position opened and closed inside one bar is
   not caught at 4h resolution (the Binance check does not change that, since it uses the same bar windows).

## Consequences
At 3 Dec: median worst-case drawdown across A/B addresses −51%, against −30% at the hourly closes; 171 of 341
measured addresses are worse than −50%. The gate removes 1, 4, 3, 4 and 2 addresses from those passing every gate
at the five origins (17 -> 16, 16 -> 12, 18 -> 15, 17 -> 13, 13 -> 11). The Binance check agrees closely: the
median per-address gap is 0.00-0.05 percentage points; Hyperliquid lows sit a median 9.5 bps above Binance lows
(Binance wicks are slightly deeper). With the new gate, the frozen Phase 3 copy (all sizing limits and the leader
sweep, ADRs 0043, 0086-0088) earns a mean funded base return of +0.77% over 56 gate-passing address-windows
(positive in 3 of 4 tests: +1.49%, +1.11%, −0.06%, +0.52%), stress −1.31%
(`research/replay/sensitivity_returns_worstcase_gate.csv`). The replay itself is unchanged; only the gate-passer set
moves.
