# ArkStream Hyperliquid multi-trader copy pilot

The answer to the ArkStream written test: what to do with the 100,000 USDC reserved for a Hyperliquid
multi-trader copy pilot, decided as of the data cutoff (2026-01-04T23:59:42Z).

中文：简要报告见 [ArkStream_Assignment_Report_zh-CN.docx](ArkStream_Assignment_Report_zh-CN.docx)，决策备忘录中文译本见
[decision/decision-memo.zh-CN.md](decision/decision-memo.zh-CN.md)（以英文原文为准）。

## For reviewers: start here

**The decision.**
- **Do not deploy the 100,000 as a copy basket.**
- **Run a gray execution measurement instead:**
  - 0x2cd9 and 0x971f live at 2,500 USDC each, under one loss budget of 750 USDC;
  - 0x3a12 and 0xe65c in paper;
  - 95,000 in reserve, off-exchange.
- **This is the pre-registered CONDITIONAL GO,** with D1-D5 all true on the holdout. It is not evidence that the
  leaders have skill.

**The short version:** a Word report of the whole assignment, in English
([ArkStream_Assignment_Report.docx](ArkStream_Assignment_Report.docx)) and in Simplified Chinese
([ArkStream_Assignment_Report_zh-CN.docx](ArkStream_Assignment_Report_zh-CN.docx)). Six sections: the decision, the
data and validation method, the address selection, the risk and portfolio rules, the holdout result with the basket at
the cutoff, and how to read this repository. Both are built from the saved outputs by `scripts/build_report.py`. Where
a report and the documents below differ, the documents are right.

**Read in this order:**
1. [The decision memo](decision/decision-memo.md): the answer, item by item, with the evidence and its limits
   (Chinese translation: [decision-memo.zh-CN.md](decision/decision-memo.zh-CN.md)).
2. [The deployment protocol](decision/deployment-protocol.md): the operating configuration (limits, triggers,
   reviews, escalation), with every parameter checked against `config/risk.yaml`.
3. The deliverables, in `research/cutoff/deliverables/`:
   - `trader_decisions.csv`: every address, with its grade, category, first failed gate and role;
   - `target_allocations.csv`: the books and the capital.
4. The holdout:
   - `research/holdout/decision_A.json`, run A's D1-D5 entry;
   - `research/holdout/window_report/` (H1-H6);
   - `research/holdout/cost_runs/`, runs B and C.
5. [The ADR index](decision/adr/README.md): every decision, in the order it was made. ADRs 0086-0102 are Phase 5.
6. [The trial log](provenance/trial_log.md): every run and trial, each written before its result.

**Where each item of the written test is answered:**

| Written test | Memo | Supporting material |
| --- | --- | --- |
| 1. Address pool and capital arrangement | section 1 | the deliverables; protocol sections 2-4 |
| 2. Assumptions and operating arrangement | section 4 | protocol sections 4-8 |
| 3. Result review | sections 2, 3 and 5 | the holdout report; the trial log |
| 4. Review and continuation | section 6 | [VERIFY.md](VERIFY.md) section 6; the ADR index |

**How it was built, phase by phase:**

| Phase | Documents |
| --- | --- |
| Milestone 1: data, prices, point in time | this README (Rerun, Rules); `research/DATA_DICTIONARY.md` |
| Phase 2: leader evidence | [phase-2b-results.md](decision/phase-2b-results.md) |
| Phase 3: follower replay and costs | [phase-3-results.md](decision/phase-3-results.md), [phase-3-sensitivity-results.md](decision/phase-3-sensitivity-results.md) |
| Copy delay, measured | [latency_study.md](decision/latency_study.md), [measured-latency-results.md](decision/measured-latency-results.md), [alt-floor-receive-results.md](decision/alt-floor-receive-results.md) |
| Before Phase 4 | [pre-phase-4-results.md](decision/pre-phase-4-results.md), [pre-phase-4-sizing-comparison.md](decision/pre-phase-4-sizing-comparison.md) |
| Phase 4: selection | [phase-4-v2-methodology.md](decision/phase-4-v2-methodology.md), [phase-4-v2-results.md](decision/phase-4-v2-results.md) (v1, superseded: [phase-4-results.md](decision/phase-4-results.md)) |
| Phase 5: portfolio, freeze, holdout | [phase-5-methodology.md](decision/phase-5-methodology.md), [phase-5-results.md](decision/phase-5-results.md), [pre-holdout-checks.md](decision/pre-holdout-checks.md) |

## Check and rerun in a few commands

You need [uv](https://docs.astral.sh/uv/). `.python-version` pins Python 3.12.15, the version recorded in the freeze, and
`uv sync` installs it with the locked packages. Run everything from the unzipped `arkstream/` folder (or a clone):

```
uv sync
uv run python scripts/rerun.py check               # ~1 min: package checksums, freeze hash, decision entry, protocol
uv run python scripts/rerun.py fetch               # the public Binance data the package does not ship (~11 GB)
uv run python scripts/rerun.py rebuild             # every development output (~2-3 h), compared with the published lists
uv run python scripts/rerun.py holdout --confirm   # the holdout and the cutoff, compared with the shipped record
uv run python scripts/rerun.py reports             # the English and Chinese Word reports and their figures
```

- **check** needs nothing rebuilt. Expected: every file in `MANIFEST.sha256` matches, the freeze prints `True` and
  `62eba6da…6648`, `decision_A.json` hashes to `cb3dd576…7c2f`, and the protocol check passes 54 of 54. Run it before
  `rebuild`: rebuilding regenerates some shipped files (the address cards in `research/cards/` predate ADR-0066 and
  gain six grading fields), so `MANIFEST.sha256` describes the package as shipped.
- **fetch** downloads the Binance 1-minute klines (1.9 GB) and the aggTrades of seven coins (9.3 GB), each checked
  against Binance's published checksum. It resumes, and skips files already verified.
- **rebuild** runs each phase in order: ingest, the kline lake and reference prices, Milestone 1, the audit, funding,
  drift, leader evidence, the copy replays, the two selections, the Phase 5 development runs, the holdout and cutoff
  code checks, and the tests. It then compares the outputs with `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt`,
  `provenance/CHECKSUMS.txt` and `provenance/HOLDOUT_OUTPUT_MANIFEST.txt`, and checks that the freeze still holds. It
  stops if a step changes a frozen file. The one known rewrite, `provenance/CHECKSUMS.txt` by `ingest` (the two
  original package files are not shipped), is checked line by line and put back.
- **holdout** reruns the five holdout and cutoff commands and compares the 76 files of the published record with the
  new ones; the run timestamp inside the two JSON entries is the only field it ignores. It rewrites
  `research/holdout/` and `research/cutoff/`, so it asks for `--confirm`: use a copy. The commands refuse to start
  unless the freeze holds, including the recorded environment (Python 3.12.15, the locked packages,
  `POLARS_MAX_THREADS=8`; the runner sets the threads).
- **reports** adds python-docx for that run only. It is kept out of `uv.lock` because the lock's hash is part of the
  frozen environment.
- `--list` shows a stage's steps, `--dry-run` prints its commands, and `--from N` resumes at step N after a failure.
  `make check`, `make fetch`, `make rebuild`, `make holdout CONFIRM=1` and `make reports` do the same where make is
  available.
- Disk: about 15 GB on top of the package and the fetched data. On Windows, unzip to a short path (or enable long
  paths): the longest file path inside `research/` is 190 characters.

[VERIFY.md](VERIFY.md) lists every command behind these stages and what each one checks.

## Research history (Milestone 1 to Phase 3)

Research and deployment configuration for deciding whether to deploy 100,000 USDC into a basket that
copies Hyperliquid perp traders. The research plan it followed (v2) is not included in this package. Phase 3 covers four development tests and the training history through the 3 December 2025 origin. [Follower replay results](decision/phase-3-results.md) · [Cost sensitivities](decision/phase-3-sensitivity-results.md). Pre-Phase 4 fixes: [results](decision/pre-phase-4-results.md) · [sizing comparison](decision/pre-phase-4-sizing-comparison.md) · [verify from a clean copy](VERIFY.md). Measured copy delay: [before/after results](decision/measured-latency-results.md); the delay scenarios come from measurement (ADR-0058: optimistic 1 s, base 1.2 s, stress 5 s, severe 60 s / 300 s as a labelled sensitivity). Alt-drift floor and receive delay: [before/after results and copy capture](decision/alt-floor-receive-results.md) (ADR-0061: split-order floor below 300 s in base; ADR-0062: receive 392 ms; ADR-0063: capture against a same-sizing benchmark, market-relative returns). Copies are sized on a frozen reference equity reviewed every 14 days, the only sizing policy (ADR-0052); Phase 4
ranks on the frozen copy series in `research/replay_frozen/` (`*_sqrt_cap_part_ns_sweep_frozen`). The dynamic
comparison in `research/replay_sizing/` is the archived record behind that choice.
Execution stays disabled in `config/execution.yaml` and the safety tests check the offline code path.

## Individual commands (Milestone 1 to Phase 3)

`scripts/rerun.py` (above) runs all of these in order. Python 3.12.15 is pinned (`.python-version`,
`requires-python = ">=3.12,<3.13"`). [VERIFY.md](VERIFY.md) gives the full check from a clean copy: tests, audit,
public-data fetch, every rebuild and the checksum comparison.

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
   The one exception is runs B and C (ADR-0098 item 9): they rebuild costs from holdout data, are reported, and never
   decide.
8. **The freeze.** Every holdout command is refused unless `provenance/HOLDOUT_FREEZE.txt` holds (`freeze.guard`;
   ADRs 0091, 0097). The holdout was opened once, on 2026-11-24.

## Layout

```
config/       decision_context.yaml (cutoff, thresholds), risk.yaml (limits, triggers, gray), execution, instruments
src/arkstream the research pipeline: ingest and prices, leader evidence, replay, selection (v1, v2), risk model,
              portfolio engine, Phase 5 steps, holdout and cutoff entry points, freeze, audit, cli
src/arkstream_fetch  fetch_klines, fetch_aggtrades, fetch_hyperliquid, hl_ws_latency (read-only; the only network code)
tests/        unit (synthetic) + data tests (marked `data`)
scripts/      rerun.py (check, fetch, rebuild, holdout, reports), build_report.py (the Word reports),
              package_submission.py, check_protocol_parameters.py, audits and diagnostics, make_figures.py
decision/     decision-memo.md (+ decision-memo.zh-CN.md), deployment-protocol.md, phase methodologies and results;
              adr/ (decisions); briefs/ (briefs for parallel sessions); figures/ (report/: the reports' figures)
*.docx        ArkStream_Assignment_Report.docx (English), ArkStream_Assignment_Report_zh-CN.docx (Chinese)
research/     cutoff/deliverables (the deliverables), holdout (the decision entry, window report, runs B and C),
              the phase outputs (leader, replay_*, selection_v2, portfolio_replay, ...), cards/<address>.md
provenance/   trial_log.md, HOLDOUT_FREEZE.txt, HOLDOUT_OUTPUT_MANIFEST.txt, CHECKSUMS.txt, expected_counts.yaml
```

Read first: "For reviewers: start here" at the top of this file.
