# Verify from a clean copy

Every command below runs from the unzipped `arkstream/` folder. Extract with a tool that honours UTF-8 file
names (`python -m zipfile -e arkstream_submission.zip .`, 7-Zip or Windows Explorer; Git Bash `unzip` garbles
the plan's file name). Nothing contacts the network except the fetchers
in `src/arkstream_fetch` (data.binance.vision and api.hyperliquid.xyz only, read-only). Execution stays disabled
(`config/execution.yaml: live_trading_enabled: false`).

## 1. Install

Python 3.12 is required (`.python-version`, `requires-python = ">=3.12,<3.13"`). With [uv](https://docs.astral.sh/uv/):

```
uv python install 3.12
uv sync                    # runtime + dev tools from uv.lock
uv sync --group figures    # only for `make figures`
```

## 2. Check the package, tests and audit

```
uv run python scripts/package_submission.py --check MANIFEST.sha256   # every shipped file matches
uv run python -m arkstream ingest                                     # data/raw -> data/processed (Parquet)
uv run ruff check src tests scripts
uv run mypy src
uv run pytest -q                                                      # unit + data tests (~8 min)
uv run python -m arkstream audit                                      # 31 headline counts, exact
```

In a clean copy seven data tests skip, naming what they need: four Phase 2 point-in-time tests need the kline
lake (step 4, `refprices --from-zips`) and three ledger audits need replay ledgers. Rerun `uv run pytest -q`
after step 4; the sizing ledger audit then runs, and the two Phase 3 audits run only if the original Phase 3
replay is regenerated as well (`uv run python -m arkstream replay` and `replay --sensitivities`, about 45 min,
into `research/replay`).

Byte-for-byte comparisons below assume the same thread count as the published runs: set
`POLARS_MAX_THREADS=8` (PowerShell: `$env:POLARS_MAX_THREADS = "8"`; bash: `export POLARS_MAX_THREADS=8`).
Some float aggregations in Phase 2 depend on the thread count in their last bits (values agree to 1e-9).

## 3. Fetch the public data that is not shipped

| Data | Command | Size | Verified against |
| --- | --- | ---: | --- |
| Binance 1m klines (monthly zips, 186 symbols, 2025-07..2026-01) | `uv run python -m arkstream_fetch.fetch_klines` | 1.9 GB, 1,270 files | Binance's published `.CHECKSUM`; `data/reference/binance/CHECKSUMS.txt` |
| Binance aggTrades (BTC, ETH, HYPE, SOL, 2025-09-08..2026-01-04) | `uv run python -m arkstream_fetch.fetch_aggtrades` | 7.2 GB | `.CHECKSUM`; `data/reference/binance/aggtrades/MANIFEST.csv` |
| Hyperliquid funding, 4h candles, userFunding | shipped in `data/reference/hyperliquid/` | 90 MB | each folder's `MANIFEST.csv` |

Both Binance fetchers have `--dry-run --offline` (plan only) and resume from verified files.

## 4. Rebuild each phase

```
uv run python -m arkstream refprices --from-zips data/reference/binance/klines   # kline lake + reference prices
uv run python -m arkstream build                                                 # Milestone 1 at the CUTOFF
uv run python -m arkstream funding                                               # funding table, price check (+ by origin)
uv run python -m arkstream drift                                                 # drift cells per origin
uv run python -m arkstream leader                                                # Phase 2 evidence per origin
uv run python -m arkstream replay --frozen                                       # frozen E_ref replay (ADR-0052, delays ADR-0058, ADRs 0061-0063)
uv run python -m arkstream replay --coin-filter                                  # the rule's coin filter inside the frozen replay (ADR-A0140)
uv run python -m arkstream select --evaluate                                     # Phase 4 selection, development walk-forward (ADRs A0130-A0140)
```

`refprices --from-zips` builds `data/lake` from the verified zips (the folder must be empty), then writes
`data/reference/prices/`. It reproduces the shipped price files and their `MANIFEST.yaml` byte for byte (the
manifest was regenerated with the current cutoff under ADR-0054).
Approximate runtimes on the reference machine: refprices 1-2 min, funding 1 min, drift 2 min, leader 2-4 min,
replay --frozen 17 min (on one machine, POLARS_MAX_THREADS=8).

`replay --frozen` is the current replay (ADR-0052: frozen reference equity is the only sizing policy). Its delays
come from the measured copy delay (ADR-0058): optimistic 1 s, base 1.2 s, stress 5 s for every coin, and `severe`
(the old 60 s / 300 s at stress costs, a labelled sensitivity, ADR-0060); delays and drift horizons are whole
milliseconds and the break-even grid is 1, 1.2, 5, 10, 60, 300 s (ADR-0059). It writes `research/replay_frozen/`:
the shared inputs and each window's universe without simulating any dynamically sized model, the frozen full stack
in the four scenarios on the nine windows, `stress_coverage.csv` (for stress and severe: both coverage measures, the
stress check and the worst-measured sensitivity, ADR-0055), the frozen cost surface (ADR-0050, base at 1.2 s) and
the size study (ADR-0036). In base, the drift of a parameterised coin below 300 s is bounded by a point-in-time
estimate from leaders' own split orders on Hyperliquid where there is evidence, else by the coin's own 300 s drift
(ADR-0061), and the receive delay is the measured 392 ms (ADR-0062). Each window also has the zero-delay, zero-cost
benchmark with the follower's own sizing (`benchmark=unattainable_frozen/`, ADR-0063) and the leader's daily series
(`leader_series.parquet`); at the end the run writes `capture_summary.parquet`, `capture_daily.parquet` and
`market_relative.parquet` (capture ratio and its exact gap breakdown, alpha and betas to BTC and ETH;
`replay --capture` rebuilds them from an existing tree in seconds). Before/after:
`decision/measured-latency-results.md` (ADR-0058) and `decision/alt-floor-receive-results.md` (ADRs 0061-0063).
The dynamic-versus-frozen comparison in `research/replay_sizing/` is the archived record behind ADR-0052 and is not
part of the rebuild.

`replay --coin-filter` (about 9 min) replays the frozen stack with the selection rule's coin filter executed
inside it: every coin outside each origin's coin set is never traded, and the 1.5x cap, resize legs and benchmark
use the kept coins only. It writes `research/replay_coinfilter/` (266 files; two runs byte-identical). Its
`--holdout` mode is the frozen holdout path and is refused unless the freeze holds.
`select --evaluate` (about 25 s) writes `research/selection/`. It covers every origin and variant: gates, key and
bootstrap, clusters, the walk, decisions with reasons, copier clusters and the coin set. It also writes the
walk-forward against both random-k baselines and equal weight, market-relative, capture, Clopper-Pearson, MinTRL,
the diagnostics and the 3 Dec shortlist; two runs are byte-identical. The v1 freeze file was void and has been
deleted; `provenance/HOLDOUT_FREEZE.txt` is written again only by the joint Phase 4 + Phase 5 freeze (ADR-0065).
Until then any selection or replay window ending after 3 Dec 2025 is refused (`freeze.guard`).

## 5. Compare with the published checksums

```
uv run python scripts/package_submission.py --check provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt
uv run python scripts/package_submission.py --check provenance/CHECKSUMS.txt
```

`PRE_PHASE4_OUTPUT_CHECKSUMS.txt` lists the drift, Phase 2, per-origin price check and frozen replay outputs (with
the stress coverage table, cost surface, size study, benchmark ledgers and capture tables; 396 files after the
alt-floor and receive rerun, ADRs 0061-0063); each matched an independent rerun byte for byte. The lists as they were
before ADR-0058 and before ADR-0061 are kept in `provenance/measured_latency_before/` (with the summary tables the
before/after comparison was made from) and `provenance/alt_floor_receive_before/`.
`SIZING_ARCHIVE_CHECKSUMS.txt` lists the archived comparison in `research/replay_sizing/` as it was when the policy
was chosen; it is not rebuilt (with the current code its address summaries would also carry the ADR-0055 coverage
fields; its orders and ledgers are the ones `replay --frozen` reproduces for the frozen variant). `CHECKSUMS.txt` lists the raw inputs and the
reference price files; its two package originals (`笔试题数据包-*`) are not shipped and are reported missing:
`data/raw/fills.csv` and `data/raw/traders.csv` are byte copies with the same SHA-256. The holdout test window (2025-12-03..2026-01-04) is not computed by any command.
