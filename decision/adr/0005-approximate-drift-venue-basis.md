# ADR-0005: Approximate drift corrected by the venue basis, capped at 100 bps

- Status: Accepted
- Date: 2026-11-19
- Phase: follower replay

## Context
Coins without aggTrades measure drift from the leader's Hyperliquid fill price to a Binance reference price,
so a persistent venue gap enters the drift. Trials (trial log, 2026-11-19): on BTC/ETH/HYPE/SOL, 8-21 Oct,
300 s, the uncorrected approximation reads 0.15-1.16 bps below aggTrades; a side-signed correction is worse
(up to -5 bps, because the bar close is up to 60 s stale); the unsigned median basis is within noise there but
moves 40 of 174 other coins by more than 2 bps (SNX -27, LAYER -25). CC sits about 940 bps from Binance.

## Decision
- drift = sign x (p1 (1 + b) / fill - 1), where b is the coin's median of fill / reference(t) - 1 over its
  orders in the trailing 7 days up to the order's day; no correction when p1 is a package print.
- Fewer than 10 basis observations: unmeasured (`no_basis_estimate`). |b| > 100 bps: unmeasured
  (`basis_too_large`), treated as a mapping question, not corrected.
- Only horizons >= 300 s; labelled approximate.

## Consequences
On the four main coins the approximation still reads 0.2-1.4 bps low at 300 s (correlation 0.90-0.93); this is
disclosed, not corrected. About half the other coins have enough orders for an estimate at each origin. The
thresholds (7 days, 10 observations, 100 bps) are placeholders.
