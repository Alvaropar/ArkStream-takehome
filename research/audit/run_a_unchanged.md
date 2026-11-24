# Run A unchanged (ADR-0098, ADR-0099)

The P5-5 S\*, U\* and G\* runs rerun with the current engine (cost-run hooks off) on the four development test windows in the four scenarios, compared byte for byte with `research/portfolio_replay`.

| Window | Files compared | Identical | Differ |
| --- | ---: | ---: | --- |
| 2025-10-08 | 96 | 96 | none |
| 2025-10-22 | 96 | 96 | none |
| 2025-11-05 | 96 | 96 | none |
| 2025-11-19 | 96 | 96 | none |

- summary rows (128) equal to `pair_summary.csv` (same columns, written and read back as CSV): **True**

**Result: PASS**
