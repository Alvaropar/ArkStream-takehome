# Requires uv. On Windows use Git Bash / make from MSYS, or run the commands directly.
ASOF ?=
UV ?= uv

.PHONY: data build test audit lint all prices aggtrades-plan drift leader replay replay-sensitivities replay-frozen replay-sizing replay-cost-surface replay-size-study figures latency-probe latency-record latency

data:            ## checksum raw inputs, ingest to date-partitioned Parquet
	$(UV) run python -m arkstream ingest

build: data      ## all Milestone 1 outputs as of ASOF (default: CUTOFF)
	$(UV) run python -m arkstream build $(if $(ASOF),--asof $(ASOF),)

test:            ## unit + data tests
	$(UV) run pytest

audit:           ## headline counts must reproduce exactly
	$(UV) run python -m arkstream audit $(if $(ASOF),--asof $(ASOF),)

prices:          ## reference prices + validity windows from the Binance kline lake (data/lake)
	$(UV) run python -m arkstream refprices

aggtrades-plan:  ## dry run of the aggTrades download: file count and expected size
	$(UV) run python -m arkstream_fetch.fetch_aggtrades --dry-run

drift:           ## drift parameters (development windows only; 10-11 Oct separately)
	$(UV) run python -m arkstream drift

leader:          ## Phase 2 leader evidence per origin -> research/leader/ (ex-funding)
	$(UV) run python -m arkstream leader

lint:
	$(UV) run ruff check src tests
	$(UV) run mypy src

replay:
	$(UV) run python -m arkstream replay

replay-sensitivities:
	$(UV) run python -m arkstream replay --sensitivities

all: data build test audit

replay-frozen:   ## ADR-0119/0122 the current replay, frozen E_ref only (+ stress coverage, cost surface, size study) -> research/replay_frozen
	$(UV) run python -m arkstream replay --frozen

replay-sizing:   ## archived (ADR-0116/0119, not rerun): frozen vs dynamic comparison -> research/replay_sizing
	$(UV) run python -m arkstream replay --sizing

replay-cost-surface:   ## ADR-0117 frozen base cost surface on the test windows -> research/replay_frozen
	$(UV) run python -m arkstream replay --cost-surface

replay-size-study:
	$(UV) run python -m arkstream replay --size-study

figures:         ## key review figures from saved outputs (decision/figures/)
	$(UV) run --group figures python scripts/make_figures.py

MINUTES ?= 90
NETWORK ?=
latency-probe:   ## pick 10 currently active leaders (subscribe-only probe) -> data/reference/latency/hyperliquid/leaders.csv
	$(UV) run python -m arkstream_fetch.hl_ws_latency --probe-leaders

latency-record:  ## one read-only stream run: make latency-record MINUTES=90 NETWORK="wired fibre, ..."
	$(UV) run python -m arkstream_fetch.hl_ws_latency --duration-min $(MINUTES) --network "$(NETWORK)"

latency:         ## receive-delay analysis (no network) -> research/latency/
	$(UV) run python -m arkstream latency
