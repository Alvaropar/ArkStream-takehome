# Phase 3 development replay

Counts show gate-passing addresses with positive funded copy return on a 10,000 USDC allocation.

The base scenario produced positive funded copies for 6/16, 5/12, 8/15, 9/13 gate-passers in successive development tests.
The holding bands clearing mean round-trip costs in every test were 6-24h.
The first delay break-even screen passes for further research. At least one holding band cleared realised costs and gate-passing addresses earned positive base returns in every development test.
Individual address stress drawdowns and pricing coverage constrain that finding. The October 8 origin has no prior crash sample for parameterised stress orders; stress results with less than 80% priced intents are unmeasured (ADR-0049). Training includes the period before the September 8 archive start. Returns include the cash left idle after skipped signals.

## 2025-10-08

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 6 / 16 / 16 | 16 | 418 / 2090 | 8 |
| test | optimistic | 6 / 16 / 16 | 16 | 207 / 2111 | 6 |
| test | stress | 4 / 12 / 16 | 16 | 419 / 2095 | 6 |
| training | base | 7 / 16 / 16 | 16 | 3226 / 5288 | 8 |
| training | optimistic | 11 / 16 / 16 | 16 | 3019 / 5349 | 8 |
| training | stress | 0 / 1 / 16 | 16 | 3244 / 5319 | 1 |

Base test bands with positive mean funded net PnL per completed trip were 1-15m, 1-6h, 1-7d, 15m-1h, 6-24h, <1m, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 1,855 base intents in test. The omitted contribution at leader prices was 43,355.92 USDC across 300/300 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 3,638 base intents in training. The omitted contribution at leader prices was 34,214.63 USDC across 290/300 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.

## 2025-10-22

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 5 / 12 / 12 | 12 | 19 / 790 | 1 |
| test | optimistic | 8 / 12 / 12 | 12 | 9 / 795 | 1 |
| test | stress | 4 / 12 / 12 | 12 | 10 / 795 | 3 |
| training | base | 8 / 12 / 12 | 12 | 1842 / 4483 | 7 |
| training | optimistic | 10 / 12 / 12 | 12 | 1781 / 4535 | 5 |
| training | stress | 0 / 1 / 12 | 12 | 1834 / 4498 | 1 |

Base test bands with positive mean funded net PnL per completed trip were 1-6h, 6-24h.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 944 base intents in test. The omitted contribution at leader prices was 41,947.50 USDC across 326/327 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-15m, 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 4,980 base intents in training. The omitted contribution at leader prices was 79,503.60 USDC across 317/327 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.

## 2025-11-05

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 8 / 15 / 15 | 14 | 54 / 1280 | 2 |
| test | optimistic | 8 / 15 / 15 | 14 | 59 / 1283 | 2 |
| test | stress | 7 / 15 / 15 | 14 | 55 / 1282 | 4 |
| training | base | 9 / 15 / 15 | 15 | 1894 / 5566 | 8 |
| training | optimistic | 12 / 15 / 15 | 15 | 1839 / 5625 | 8 |
| training | stress | 0 / 1 / 15 | 15 | 1877 / 5588 | 1 |

Base test bands with positive mean funded net PnL per completed trip were 1-6h, 6-24h.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 784 base intents in test. The omitted contribution at leader prices was 16,553.90 USDC across 330/330 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 5,236 base intents in training. The omitted contribution at leader prices was 122,040.67 USDC across 319/330 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.

## 2025-11-19

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| test | base | 9 / 13 / 13 | 11 | 20 / 1009 | 1 |
| test | optimistic | 9 / 13 / 13 | 11 | 17 / 1012 | 1 |
| test | stress | 5 / 13 / 13 | 11 | 13 / 1014 | 3 |
| training | base | 11 / 13 / 13 | 13 | 1876 / 6298 | 6 |
| training | optimistic | 11 / 13 / 13 | 13 | 1816 / 6332 | 7 |
| training | stress | 1 / 1 / 13 | 13 | 1827 / 6322 | 0 |

Base test bands with positive mean funded net PnL per completed trip were 15m-1h, 6-24h.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 753 base intents in test. The omitted contribution at leader prices was 18,688.05 USDC across 357/358 measurable comparisons.

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 5,946 base intents in training. The omitted contribution at leader prices was 139,205.95 USDC across 346/358 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.

## 2025-12-03

| Window | Scenario | Positive / measured / gate-passers | Traded | Unpriced / intents | Drawdown over 10% |
| --- | --- | ---: | ---: | ---: | ---: |
| training | base | 9 / 11 / 11 | 11 | 1546 / 5341 | 6 |
| training | optimistic | 10 / 11 / 11 | 11 | 1508 / 5350 | 7 |
| training | stress | 3 / 3 / 11 | 11 | 1499 / 5355 | 2 |

Base training bands with positive mean funded net PnL per completed trip were 1-6h, 1-7d, 15m-1h, 6-24h, >7d.
Across the A/B universe the price-check rule as of the origin (ADR-0044) excluded 5,832 base intents in training. The omitted contribution at leader prices was 141,771.49 USDC across 340/354 measurable comparisons.

Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe.
