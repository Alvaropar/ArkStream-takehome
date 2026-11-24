# v2 holdout entry point, check mode (ADR-0099 item 11)

Window 2025-11-19 -> 2025-12-03 (the last development window), trigger series at 2025-12-03. Nothing at or after the holdout start is read.

| Output | Compared with | Files | Differ |
| --- | --- | ---: | --- |
| 10k tradable tree | `research/replay_tradable/origin=2025-11-19/window=test` | 26 | none |
| 2,500 gray tree | `research/replay_gray/sleeve=2500/origin=2025-11-19/window=test` | 26 | none |
| run A books | `research/portfolio_replay/origin=2025-11-19` | 84 | none |
| runs B and C | `research/cost_runs/origin=2025-11-19` | 40 | none |
| window report H1-H6 | `research/window_report/origin=2025-11-19` | 6 | none |
| trigger series (`daily_twr`, `book_hourly`, read by the engine) | `research/leader/origin=2025-12-03` | 2 | none |
| other Phase 2 tables at the series date, to 1e-12 relative | same | 20 | none (byte-identical: 20 of 22) |
| valuation marks | development output | 1 | none |
| H5 outcomes | development output | 1 | none |

**Result: PASS**
