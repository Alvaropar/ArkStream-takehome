# ADR-0048: Bound the base drift of parameterised coins below 300 s from below

- Status: Accepted; amended by ADR-0061 (base below 300 s: the point-in-time Hyperliquid split-order estimate where it exists, this floor as its fallback)
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief item 5)
- Amends: ADR-0029 (base scenario of the `four_coin_proxy` path)

## Context
About 159 coins pass the price check but have no aggTrades archive. Below 300 s their drift is the four-coin proxy
(BTC, ETH, HYPE, SOL weighted by measured orders, ADR-0029). Liquid-coin drift is close to zero or negative, so
the proxy is optimistic for thin coins, where the move after a visible fill is likely larger.

## Decision
For a parameterised order with delay below 300 s, the signed drift parameter is:
- **base**: max(four-coin proxy, the coin's own development-period 300 s estimate, 0). The own estimate uses the
  same vintage and holding-band lookup as ADR-0029 (band row, else the coin's `all` row). Both the proxy and the
  own estimate are required; either missing leaves the order unpriced (`no_drift_cell`). Method
  `base_max_proxy_coin_300s_zero`; the cells used are kept in `parameter_cells`.
- **optimistic**: the four-coin proxy (unchanged).
- **stress**: max(proxy, the coin's own stress-period 300 s estimate) (unchanged).
At 300 s and above every scenario keeps the coin's own estimate. The direct-price coins are unaffected.

## Consequences
Base costs on thin coins rise wherever their own 300 s drift is positive; base can never assume a favourable
drift below 300 s. Address summaries add `parameterised_notional_share` (filled notional on parameterised coins /
filled notional), reported per address. Tests: `tests/test_pre_phase4.py` (the bound, the missing own cell, the
optimistic and stress rules).
