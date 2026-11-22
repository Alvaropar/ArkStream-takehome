# ADR-0023: Round-trip return on peak notional; hourly excursions; open trades valued at asof

- Status: Accepted
- Amended by ADR-0061 for the Phase 2 rework.
- Date: 2026-11-19
- Phase: Phase 2

## Context
Round trips run flat to flat per coin (`positions.rebuild`). The plan asks for return, return per day held,
MAE and best gain, win rate, win/loss size, mean without the top 1%, and open positions at the test date
counted and valued. Here at the leader's own prices and fees; follower delay is Phase 3.

## Decision
- A zero-crossing fill is split into a closing and an opening part, fee pro rata to size.
- Trip PnL = sum of (-delta x price - fee) of its parts; an open trip adds position x grid price at asof
  (reference, else print, else `open_unpriced_at_asof`, excluded and counted).
- Return = PnL / peak notional (max |position| x fill price over the trip). Return per day held = return /
  max(hold, 1 h) (`leader.trips.min_hold_for_per_day_s`).
- MAE / best gain = worst / best trip-to-date PnL at hourly marks inside the trip over peak notional, labelled
  `excursion_resolution = 1h`.
- Left-censored trips (`left_censored_entry_unknown`) are excluded and counted.
- Top 1% = ceil(1% of usable trips), at least one; `top_pnl_share` = 1 - PnL without them / PnL.

## Consequences
At 22 Oct, 13,323 usable closed trips: PnL matches the package's closed_pnl - fees (corr 1.000; 6.0445M vs
6.0450M; 384 trips differ by > 1 USDC, from the fee split on crossing fills). 808 trips open at asof.
