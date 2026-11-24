# leader.compute past the last configured origin (ADR-0099 item 11), development data

Configured origins truncated to 8 Oct, 22 Oct, 5 Nov; the Phase 2 tables built at 19 Nov through `holdout.trigger_tables` (beyond the last origin, behind `freeze.guard`), compared with `research/leader/origin=2025-11-19` (built by `leader.run` over the five origins).

| Table | Byte-identical | Equal to 1e-12 |
| --- | --- | --- |
| account_coverage | True | True |
| account_returns | True | True |
| book_attribution | True | True |
| book_daily | True | True |
| book_hourly | True | True |
| book_vs_account | True | True |
| daily_marks | False | False |
| daily_twr | True | True |
| evidence | False | True |
| funding_payments | True | True |
| gap_path | True | True |
| gates | True | True |
| market_exposure | True | True |
| market_sample | True | True |
| profiles | True | True |
| round_trips | True | True |
| snapshot_marks | True | True |
| stress_shocks | True | True |
| trip_summary | False | True |
| twr_summary | True | True |
| worstcase_check | True | True |
| worstcase_dd | True | True |
