# ADR-0042: HIP-3 perpetuals stay out of scope for now

- Status: Accepted
- Date: 2026-11-19
- Phase: all
- Decides: ADR-0041 item 4 (HIP-3 permitted, inclusion pending)

## Context
The recruiter allows HIP-3 perps (ADR-0041). They are 10,308 fills, 110 addresses and $15.2M, 0.39% of perp
notional, on the xyz, vntl, hyna and flx dexes. Including them would need Hyperliquid prices and funding for HIP-3
coins and a check of whether their PnL appears in cross-margin `equity` (HIP-3 dexes keep their own margin); if it
does not, adding them would worsen the rebuild-vs-snapshot check.

## Decision
HIP-3 perps stay excluded (user decision, 2026-11-19): not eligible for copying, not in leader metrics, not
priced. The exclusion is disclosed wherever it affects a number: an address's share of HIP-3 activity is reported,
and positions in HIP-3 remain unpriced and flagged, never valued from another source.

## Consequences
No change to code or outputs: the pipeline already treats HIP-3 as ineligible. Revisit with a new ADR if the
shortlist turns out to depend on addresses with material HIP-3 activity.
