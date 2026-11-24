# ArkStream Hyperliquid multi-trader copy pilot

Research and deployment configuration for deciding whether to deploy 100,000 USDC into a basket that
copies Hyperliquid perp traders. Plan: *ArkStream Hyperliquid Pilot — Revised Research & Deployment
Plan (v2)*. Phase 3 covers four development tests and the training history through the 3 December 2025 origin. [Follower replay results](decision/phase-3-results.md) · [Cost sensitivities](decision/phase-3-sensitivity-results.md). Pre-Phase 4 fixes: [results](decision/pre-phase-4-results.md) · [sizing comparison](decision/pre-phase-4-sizing-comparison.md) · [verify from a clean copy](VERIFY.md). Measured copy delay: [before/after results](decision/measured-latency-results.md); the delay scenarios come from measurement (ADR-0058: optimistic 1 s, base 1.2 s, stress 5 s, severe 60 s / 300 s as a labelled sensitivity). Alt-drift floor and receive delay: [before/after results and copy capture](decision/alt-floor-receive-results.md) (ADR-0061: split-order floor below 300 s in base; ADR-0062: receive 392 ms; ADR-0063: capture against a same-sizing benchmark, market-relative returns). Copies are sized on a frozen reference equity reviewed every 14 days, the only sizing policy (ADR-0052); Phase 4
ranks on the frozen copy series in `research/replay_frozen/` (`*_sqrt_cap_part_ns_sweep_frozen`). The dynamic
comparison in `research/replay_sizing/` is the archived record behind that choice.
Execution stays disabled in `config/execution.yaml` and the safety tests check the offline code path.

## Rerun

Python 3.12 is pinned (`.python-version`, `requires-python = ">=3.12,<3.13"`). Install it and the
locked dependencies with uv (`uv python install 3.12`, then `uv sync`). [VERIFY.md](VERIFY.md) gives the full
check from a clean copy: tests, audit, public-data fetch, every rebuild and the checksum comparison.

```
uv sync
make data                     # checksum raw inputs -> provenance/CHECKSUMS.txt; ingest to Parquet
make build ASOF=2025-11-19    # all M1 outputs as of a timestamp (default and cap: CUTOFF)
make test                     # unit (synthetic) + data tests: parsing, keys, continuity, prices, drift, fetcher, point-in-time, leaks, audit
make audit                    # headline counts must reproduce exactly (provenance/expected_counts.yaml)
make replay                   # follower orders, daily TWR and break-even tables under research/replay
make replay-sensitivities     # square-root impact, exposure cap and combined variants next to the originals
make replay-frozen            # ADR-0052/0058: frozen E_ref only, measured delays, stress coverage (ADR-0055), cost surface -> research/replay_frozen
```

Without `make`: `uv run python -m arkstream {checksums|ingest|build --asof <ts>|audit}` and `uv run pytest`.
A full build at the cutoff takes about 8 s.

Raw inputs go in `data/raw/` (`traders.csv`, `fills.csv`; byte copies of the package files).

Reference coin prices (A13) are in `data/reference/prices/`: Binance USD-M 1m kline closes, one Parquet file
per month, read **only** through `data/reference/prices/MANIFEST.yaml` (SHA-256 per file). Any other file in
that folder, or a changed file, stops the build with a message naming it. The mapping with each coin's
validity window, the source note, checksums of the original Binance zips and the fetch logs are in
`data/reference/binance/` (read `SOURCE.md` there). The build needs only these files.

```
uv run python -m arkstream refprices                       # rebuild prices + windows from the kline lake (~1 min)
uv run python -m arkstream_fetch.fetch_klines --dry-run --offline  # monthly 1m kline zips plan (1,270 files, 1.9 GB)
uv run python -m arkstream refprices --from-zips data/reference/binance/klines  # lake + prices from the zips alone
uv run python -m arkstream_fetch.fetch_aggtrades --dry-run # aggTrades plan: 476 files from 2025-09-08, ~8.3 GB
uv run python -m arkstream_fetch.fetch_aggtrades           # download (resumable; reuses verified files)
uv run python -m arkstream_fetch.fetch_hyperliquid --dry-run             # Hyperliquid funding plan (no network)
uv run python -m arkstream_fetch.fetch_hyperliquid [--kind candles_4h]   # funding / 4h candles, ~1.2 s per request
uv run python -m arkstream funding                                       # funding table, price check, userFunding check
uv run python -m arkstream funding --step price-check-origins            # ADR-0044: the price check as of each origin
uv run python -m arkstream drift                           # drift parameters: development windows only
uv run python -m arkstream leader                          # Phase 2 leader evidence per origin (~4 min; make leader)
```

Every consumer of the Binance-vs-Hyperliquid price check uses its outcome as of its own origin (ADR-0044),
computed from `research/hyperliquid/price_check_bars.parquet` (bars closing by that time); the per-origin lists
are in `research/hyperliquid/price_check_by_origin.csv`. `price_check.csv` is the CUTOFF record (ADR-0011).
Phase 2 also reads `research/hyperliquid/funding.parquet` and the manifest-verified Hyperliquid 4h candles.

**Phase 2 leader evidence** (ADRs 0023–0028). Each origin directory contains the A/B universe, primary address returns,
drawdowns through covered gaps, BTC/ETH exposure and confidence intervals, funded books and round trips, exact
snapshot fit, and suitability gate counts. Daily marks use Hyperliquid and record Binance validation. The
funding and mark ledgers retain their source keys. An address with a PnL identity breach uses the funded
core-perp book as its primary return and keeps cross-margin snapshot TWR as a check. The evidence records
the return source and coverage for both series in
`research/leader/origin=<date>/evidence.parquet`. See [the comparison report](decision/phase-2b-results.md).


`src/arkstream_fetch/` is the only code that touches the network (data.binance.vision and POST api.hyperliquid.xyz/info only, tested);
`src/arkstream`, the research pipeline, has none.

## Rules the code enforces

1. **Point in time.** Every producer takes `asof` and filters `ts <= asof` first. Test: outputs at T are
   identical on inputs truncated at T, full inputs, and inputs with adversarial rows appended after T.
   Seeded leak tests (`tests/test_seeded_leaks.py`) plant a snapshot-a-day-early leak and a moved cutoff
   and check that the tests catch both.
2. **CUTOFF** is read from `config/decision_context.yaml`; `asof` is capped at it.
3. **Nothing imputed.** Unknown entry prices give null realized PnL; missing reference prices are flagged.
4. **Determinism.** Byte-identical Parquet across reruns (tested); `provenance/OUTPUT_CHECKSUMS.txt`.
5. **Traceability.** Every derived row carries `src_row` (raw line number) and trader/tid/oid/ts;
   `research/quality_evidence.parquet` lists every raw row behind every flag.
6. **No orders.** No order code anywhere; no network code in `src/arkstream` (tested). The downloader in
   `src/arkstream_fetch` reads only data.binance.vision and the Hyperliquid info endpoint (tested).
7. **Holdout.** Drift and cost parameters come from before the holdout only (history 8 Sep to 2 Dec 2025,
   without 10-11 Oct), one estimate per test date from data before it; the drift reader refuses aggTrades files after 2 Dec (tested).

## Layout

```
config/       decision_context.yaml (cutoff, thresholds, grade placeholders), risk, execution, instruments
src/arkstream timeparse, ingest, instruments, positions, reconcile, prices, refprices, drift, copiers, quality, pipeline, audit, cli
src/arkstream_fetch  fetch_aggtrades, fetch_hyperliquid (standalone downloaders; the only network code)
tests/        unit (synthetic) + data tests (marked `data`)
decision/adr/ decision records (ADRs); decision/briefs/ briefs for parallel sessions
research/     DATA_DICTIONARY.md, quality_report.parquet, quality_evidence.parquet, cards/<address>.md
provenance/   CHECKSUMS.txt, OUTPUT_CHECKSUMS.txt, expected_counts.yaml, trial_log.md
decision/ operations/   (later milestones)
```

Read first: `research/DATA_DICTIONARY.md`, then `provenance/trial_log.md`.
