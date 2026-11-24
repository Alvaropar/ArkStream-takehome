# ADR-0051: Rebuild everything from a clean copy and public data

- Status: Accepted; amended by ADR-0054 (manifest regenerated)
- Date: 2026-11-21
- Phase: pre-Phase 4 fixes (brief item 9)
- Amends: ADR-0002 (how the kline lake is obtained)

## Context
The reference prices and the Phase 2 Binance checks read a Parquet kline lake built by an external tool
(qh_data), and large inputs and outputs are not shipped. A reviewer with only the submission zip could not
rebuild the prices or check the outputs.

## Decision
1. **Kline fetcher.** `src/arkstream_fetch/fetch_klines.py` downloads Binance USD-M monthly 1m kline zips
   (`data.binance.vision/.../monthly/klines/<SYM>/1m/<SYM>-1m-<YYYY-MM>.zip`, the 186 symbols of
   `data/reference/binance/binance_um_symbols.txt`, 2025-07..2026-01) with the aggTrades fetcher's rules: standard
   library, one allowed host, the published `.CHECKSUM` checked while writing, resumable, seeds from the lake's raw
   zips, `MANIFEST.csv`. A month Binance does not publish (404, not yet listed) is `not_published`, not a failure.
2. **Lake from zips.** `python -m arkstream refprices --from-zips <dir>` checks every zip against a verified
   SHA-256 (the fetcher's `MANIFEST.csv`, else `data/reference/binance/CHECKSUMS.txt`), writes the lake (one Parquet
   per symbol and month of known time; known time = open + 60 s) into an empty folder, then runs the unchanged
   ADR-0002/0020 build. From the 1,270 local verified zips it reproduces all seven reference price files, the
   mapping and the window evidence byte for byte. The published `MANIFEST.yaml` differs only in its `cutoff` field
   (`23:59:59`, written before ADR-0021 set the cutoff to the last fill at `23:59:42.020`); no bar is known between
   the two, so it is reported and not rewritten (inputs are read-only).
3. **Package.** `scripts/package_submission.py` builds `dist/arkstream_submission.zip` from an explicit include list
   (code, config, tests, scripts, decision/, provenance/, the small verified inputs, the small research summaries)
   with `MANIFEST.sha256` for every file. The zip is deterministic (sorted entries, fixed timestamps). Latency
   recordings are shipped only when finished (`run.json` and `MANIFEST.csv` present), so a run another session is
   still writing is never packed. `--check FILE` verifies any `sha256  bytes  path` list against a tree.
4. **Large outputs are regenerated, not shipped**: commands and runtimes in `VERIFY.md`; expected hashes in
   `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt` (726 files when written; 312 after ADR-0055, with the archived
   comparison moved to `provenance/SIZING_ARCHIVE_CHECKSUMS.txt`) and the earlier `provenance/*CHECKSUMS*.txt`.
5. **Determinism convention.** Byte comparisons use `POLARS_MAX_THREADS=8`. With a different thread count some
   Phase 2 float aggregations differ in the last bits (values agree to 1e-9); every pre-Phase 4 output matched an
   independent rerun byte for byte at 8 threads.

## Consequences
A clean unzip can install (Python 3.12, `uv sync`), test, fetch the public data, rebuild each phase and compare
checksums without the external lake tool. Tests: `tests/test_fetch_klines.py` (fetcher offline, zip parsing with and
without header, month-boundary bars, refusal of unverified zips, both hash sources).
