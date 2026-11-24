# ADR-0054: Regenerate the reference price manifest with the current cutoff

- Status: Accepted (requested by the user on 2026-11-21)
- Date: 2026-11-21
- Phase: pre-Phase 4 fixes (the user's change 3 before item 10)
- Amends: ADR-0051 item 2 (the manifest is now rewritten, not only reported)

## Context
`data/reference/prices/MANIFEST.yaml` recorded `cutoff: 2026-01-04T23:59:59+00:00`, written before ADR-0021 set the
cutoff to the last fill (`2026-01-04T23:59:42.020Z`). ADR-0051 showed that a rebuild reproduces every price file
byte for byte and that only this field differs.

## Decision
Regenerate the manifest with the current code and config: build the reference prices into a scratch folder, check
that the seven price files, the mapping and the window evidence are byte-identical to the shipped ones, then replace
only `MANIFEST.yaml`. Record the new hash in `provenance/CHECKSUMS.txt` (`python -m arkstream checksums`).

## Consequences
The manifest's file entries (SHA-256, bytes, rows) and `mapping_sha256` are unchanged; the loader, the audit and every
price-dependent output are unaffected. `refprices` now reproduces the shipped manifest exactly.
