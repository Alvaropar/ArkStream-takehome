# Requires uv. On Windows use Git Bash / make from MSYS, or run the commands directly.
ASOF ?=
UV ?= uv

.PHONY: data build test audit lint all prices aggtrades-plan drift leader replay replay-sensitivities replay-frozen replay-sizing replay-cost-surface replay-size-study figures latency-probe latency-record latency replay-gray phase5-risk-model phase5-population phase5-pair phase5-report phase5

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

replay-frozen:   ## ADR-0052/0055 the current replay, frozen E_ref only (+ stress coverage, cost surface, size study) -> research/replay_frozen
	$(UV) run python -m arkstream replay --frozen

replay-sizing:   ## archived (ADR-A0116/0052, not rerun): frozen vs dynamic comparison -> research/replay_sizing
	$(UV) run python -m arkstream replay --sizing

replay-cost-surface:   ## ADR-0050 frozen base cost surface on the test windows -> research/replay_frozen
	$(UV) run python -m arkstream replay --cost-surface

replay-size-study:
	$(UV) run python -m arkstream replay --size-study

replay-gray:     ## P5-1 (ADR-0095 item 3): the two Phase 5 sleeves at 2,500 and 5,000 USDC -> research/replay_gray
	$(UV) run python -m arkstream replay --gray

phase5-risk-model:  ## P5-2: stress shocks, betas, covariance per origin -> research/risk_model
	$(UV) run python -m arkstream phase5 risk-model

phase5-population:  ## P5-4: trigger calibration and risk-rule variants on all A/B copies -> research/phase5_population
	$(UV) run python -m arkstream phase5 population

phase5-pair:     ## P5-5: S*, U*, G* on the test windows, random pairs, stress tests -> research/portfolio_replay
	$(UV) run python -m arkstream phase5 pair

phase5-report:   ## P5-6: the window report (H1-H6, D1-D5) on the development windows -> research/window_report
	$(UV) run python -m arkstream phase5 report

phase5: replay-gray phase5-risk-model phase5-population phase5-pair phase5-report  ## P5-1 to P5-6, development only

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
