# ADR-0020: Leader evidence per origin, for grade A/B addresses, ex-funding

- Status: Accepted
- Amended by ADR-0060–0064 for the Phase 2 rework.
- Date: 2026-11-19
- Phase: Phase 2 (leader evidence)

## Context
The plan's "Leader evidence" section measures every grade A/B address at the daily and trade level. Phase 3
(replay) and Phase 4 (selection) need this evidence point in time at each test date. Hyperliquid funding is
being fetched by another session (`decision/briefs/hyperliquid-data.md`).

## Decision
- Origins = `config/decision_context.yaml: drift.origins` (8 Oct, 22 Oct, 5 Nov, 19 Nov, and 3 Dec for the
  holdout). asof = 00:00 UTC of the origin; only rows with ts <= asof are used.
- Universe = addresses graded A or B by `pipeline.build(ctx, inputs, asof)` at that origin (not the cutoff
  grades). 349 / 396 / 424 / 443 / 381 addresses.
- Positions and round trips come from `pipeline.positions_asof` (`positions.rebuild`), core perps only
  (ADR-0007); prices from the hourly grid built with `prices.price_asof` (Binance reference, else package
  print within 60 s, else unpriced; ADR-0002).
- Book and round-trip returns are labelled `ex_funding`. Extension points that leave other outputs unchanged:
  `leader.funding` (Parquet `ts, coin, funding_rate`) adds a funding term to the hourly book; any
  `leader_returns.PriceGrid` (or a precomputed grid) replaces the price source.
- Gates are computed and counted, never applied. No selection, ranking, replay or holdout result.
- Code `src/arkstream/leader*.py`; command `python -m arkstream leader` / `make leader`; outputs
  `research/leader/origin=<date>/` (11 Parquet tables, `gate_counts.csv`, `summary.md`) and
  `research/leader/gate_counts.csv`.

## Consequences
Five origins take about 70 s. Two reruns are byte-identical (66 files). The 3 Dec origin's tables use only
data before 3 Dec; no holdout-period result is computed. Tests: `tests/test_leader_unit.py` (synthetic),
`tests/test_leader_pit.py` (invariance on real data plus a seeded leak).
