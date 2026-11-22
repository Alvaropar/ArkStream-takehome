# Phase 2 address evidence through December 3, 2025

All five origins use information available at 00:00 UTC. The December 3 run ends at the opening of the holdout.
All gate counts use placeholder thresholds.

## Coverage and fit

| Origin | A before → after | B before → after | A/B before → after | All gates before → after | Scored intervals | Within 1% | Median miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | 269 → 196 | 80 → 104 | 349 → 300 | 19 → 17 | 8,201 | 95.52% | 0.053% |
| 2025-10-22 | 324 → 217 | 72 → 110 | 396 → 327 | 18 → 16 | 9,790 | 97.69% | 0.047% |
| 2025-11-05 | 336 → 205 | 88 → 125 | 424 → 330 | 21 → 18 | 11,394 | 97.61% | 0.049% |
| 2025-11-19 | 355 → 246 | 88 → 112 | 443 → 358 | 24 → 17 | 13,886 | 97.64% | 0.050% |
| 2025-12-03 | 243 → 178 | 138 → 176 | 381 → 354 | 23 → 13 | 14,784 | 97.70% | 0.049% |

The denominator for grading includes every UTC date through the origin. At the M1 cutoff the audit counts are 344 A, 158 B and 998 C, with 1,795 confirmed frozen rows. The fit denominator requires priced, active intervals with a non-frozen closing snapshot and opening equity of at least 500 USDC. Each percentage above pools intervals.

## Rebuilt account bridge

Amounts are millions of USDC. Each row covers every snapshot interval of the revised A/B universe. Funded book is the sum of identified trading PnL and known funding. The final four columns sum to cross-margin snapshot PnL less funded book.

| Origin | Account | Core trading | Funding | Funded book | Before fill feed | Unpriced / unknown | Non-core | Unexplained |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | 4.461 | -7.421 | 4.243 | -3.179 | -1.834 | 2.399 | 3.640 | 3.434 |
| 2025-10-22 | 38.574 | 23.985 | 4.707 | 28.692 | -1.684 | 2.561 | 5.016 | 3.989 |
| 2025-11-05 | 59.940 | 44.172 | 5.471 | 49.643 | -2.747 | 2.317 | 7.291 | 3.437 |
| 2025-11-19 | 72.647 | 56.562 | 6.016 | 62.577 | -2.790 | 2.024 | 7.127 | 3.709 |
| 2025-12-03 | 76.305 | 60.453 | 6.283 | 66.736 | -2.717 | 1.805 | 6.899 | 3.582 |

A missing leg prevents dollar attribution to a specific coin. Unpriced and non-core amounts are residuals on the affected intervals. Non-core has priority when both apply. The unexplained column covers fully priced intervals including inactive, low-equity and frozen observations. Values in different origin rows overlap in time. [Reconciliation method](adr/0062-snapshot-fit.md)

The earlier hourly comparison used only usable account intervals with a priced hourly return, on the previous A/B universes. Its totals therefore have a different denominator.

| Origin | Old intervals | Old account | Old hourly book before funding |
| --- | ---: | ---: | ---: |
| 2025-10-08 | 21,590 | 4.518 | 1.978 |
| 2025-10-22 | 25,904 | 13.360 | 8.629 |
| 2025-11-05 | 29,115 | 27.877 | 17.972 |
| 2025-11-19 | 33,279 | 38.165 | 27.273 |
| 2025-12-03 | 34,568 | 44.962 | 33.895 |

## Primary return source

The recruiter confirmed that snapshot equity measures the cross-margin account. Transfers between accounts can
move that equity without a reported deposit. An A/B address with any PnL identity breach beyond 0.01 USDC by
the origin uses its funded core-perp daily book for the entire asset series. The original cross-margin TWR
remains available under `snapshot_twr_check`. The stable-offset column counts the subset explicitly flagged by
the data grade. Coverage is the median share of calendar days with a usable primary return among book-sourced
addresses. [Return-source method](adr/0065-cross-margin-return-source.md)

| Origin | Cross-margin snapshot primary | Core-perp book primary | With stable-offset grade reason | Measured book TWRs | Median book coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | 297 | 3 | 3 | 3 | 31.1% |
| 2025-10-22 | 311 | 16 | 1 | 16 | 71.6% |
| 2025-11-05 | 311 | 19 | 1 | 18 | 70.3% |
| 2025-11-19 | 337 | 21 | 2 | 20 | 78.8% |
| 2025-12-03 | 335 | 19 | 1 | 19 | 80.8% |

## Asset and price coverage

| Origin | Measured TWRs | Measured regressions | Median matched days | Paired daily marks | Above 10 bps | Above 30 bps | Open trades marked / total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-10-08 | 300 | 296 | 67 | 11,175 | 2,714 | 68 | 923 / 923 |
| 2025-10-22 | 326 | 323 | 79 | 13,400 | 3,319 | 133 | 794 / 794 |
| 2025-11-05 | 328 | 326 | 89 | 15,626 | 3,745 | 149 | 931 / 931 |
| 2025-11-19 | 357 | 355 | 99 | 17,858 | 4,218 | 185 | 845 / 845 |
| 2025-12-03 | 353 | 352 | 109 | 20,097 | 4,682 | 225 | 792 / 792 |

Price comparisons count coin-days for the fixed 163-coin Binance validator panel. Nontraded Hyperliquid bars leave daily marks missing. Regression estimates have daily units and 95% HAC intervals. Open trades retain their mark and PnL with published funding. Complete funded returns require the pending midnight rate.

## Gate passes

Cells show previous and revised pass counts. A dash identifies a new gate. [Pass, fail and unmeasured counts for every gate and origin](../provenance/phase2b_gate_comparison.csv)

| Gate | Oct 8 | Oct 22 | Nov 5 | Nov 19 | Dec 3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| gate_evidence | 114 → 113 | 152 → 150 | 167 → 165 | 181 → 179 | 178 → 174 |
| gate_intraday_dd | 271 → 226 | 292 → 236 | 300 → 231 | 294 → 240 | 245 → 225 |
| gate_worst_day | 274 → 225 | 304 → 235 | 316 → 230 | 328 → 250 | 271 → 245 |
| gate_worst_3d | 290 → 240 | 313 → 252 | 327 → 249 | 342 → 267 | 270 → 253 |
| gate_max_dd | 295 → 247 | 328 → 264 | 335 → 257 | 347 → 271 | 277 → 255 |
| gate_stress_peak | 229 → 199 | 203 → 177 | 213 → 176 | 210 → 179 | 185 → 169 |
| gate_leverage_p95 | 290 → 257 | 302 → 269 | 317 → 273 | 333 → 292 | 314 → 293 |
| gate_liq_distance | 286 → 252 | 297 → 263 | 305 → 260 | 316 → 275 | 295 → 272 |
| gate_liquidations | 348 → 300 | 393 → 325 | 421 → 328 | 440 → 356 | 379 → 352 |
| gate_top_dependence | 112 → 109 | 124 → 131 | 128 → 124 | 137 → 134 | 132 → 134 |
| gate_unpriced | 321 → 258 | 341 → 275 | 363 → 282 | 383 → 304 | 353 → 302 |
| gate_book_account | 131 → 174 | 143 → 192 | 155 → 203 | 191 → 225 | 172 → 219 |
| gate_hold | — → 267 | — → 302 | — → 295 | — → 319 | — → 326 |
| gate_order_rate | — → 299 | — → 326 | — → 328 | — → 355 | — → 351 |
| gate_maker | — → 240 | — → 266 | — → 265 | — → 290 | — → 289 |
| gate_active | — → 269 | — → 309 | — → 296 | — → 302 | — → 277 |
| gate_rebuild_fit | — → 167 | — → 191 | — → 195 | — → 219 | — → 207 |

## Verification

Ruff and mypy passed. All 109 tests passed, including the origin-specific return-source switch, seeded funding-publication leak and the candle-close, gap-path and missing-mark regressions. The Milestone 1 audit passed all 31 checks. Two independent five-origin CLI runs produced identical SHA-256 digests for all 111 output files. [Output checksums](../provenance/PHASE2B_OUTPUT_CHECKSUMS.txt)
