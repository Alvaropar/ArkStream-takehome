# ADR-0023: Grade coverage through each origin

- Status: Accepted; amended by ADR-0044 (frozen diagnosis uses the passing list as of asof)
- Date: 2026-11-19
- Phase: Phase 2 rework

## Context

Missing days after the last snapshot disappeared from the original denominator. The four development origins also precede the late-November feed interruption, making the omission material.

## Decision

Count UTC dates inclusively from first snapshot date through origin date, including the current date at a midnight origin. Presence counts distinct observed dates. A usable date needs a non-near-zero, non-frozen observation. Preserve the 95% presence and 20% unusable thresholds and the independent dropout flag.

Frozen means two consecutive snapshots report identical equity while fully priced core-perp trading PnL excluding funding changes by more than 0.000001 USDC (equity precision). Reconstruct that change from chain-ordered fill cash, USDC fees and Binance marks at both actual timestamps on the ADR-0020 passing panel. An unknown opening position, missing endpoint price or non-USDC fee prevents this diagnosis. Flat cash and repeated idle equity are common. The quality evidence retains the current and prior raw snapshot row.

## Consequences

| UTC origin | A before | B before | A after | B after | C after | Confirmed frozen rows, all grades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Oct 8 | 269 | 80 | 196 | 104 | 772 | 360 |
| Oct 22 | 324 | 72 | 217 | 110 | 791 | 473 |
| Nov 5 | 336 | 88 | 205 | 125 | 836 | 651 |
| Nov 19 | 355 | 88 | 246 | 112 | 856 | 857 |
| Dec 3 | 243 | 138 | 178 | 176 | 959 | 1,084 |

The previous published M1 cutoff table had 372 A, 175 B and 953 C. The revised audit fixture pins 344 A, 158 B, 998 C and 1,795 frozen rows. The full-cutoff run is confined to M1 accounting and data quality. Phase 2 results end at the December 3 origin.
