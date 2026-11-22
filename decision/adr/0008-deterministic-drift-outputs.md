# ADR-0008: Sorted drift outputs; retrying renames on Windows

- Status: Accepted
- Date: 2026-11-19
- Phase: engineering

## Context
`drift_hold_bands.csv` had the same rows in a different order on each run, breaking the byte-identical output
rule. The aggTrades download stopped once when Windows briefly locked `MANIFEST.csv` (antivirus, indexer or an
open preview) during the atomic rename.

## Decision
- `drift.hold_bands` sorts by trader; two reruns of `python -m arkstream drift` are byte-identical.
- `fetch_aggtrades._replace` retries `os.replace` on PermissionError with backoff (about 10 s), then stops with
  a message naming the file. Tested.

## Consequences
Any new output table must have a total sort order before it is written.
