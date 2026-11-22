# ADR-0014: userFunding validates the funding convention; it stays a check

- Status: Accepted
- Date: 2026-11-19
- Phase: follower replay inputs (A07)

## Context
ADR-0011 sets payment = -position x price x rate. To test it, `userFunding` was fetched for the 5 leaders with
the most eligible fills (`data/reference/hyperliquid/user_funding/`, 12 requests; `funding.user_funding_leaders`
in the config): 4,557 records, 2025-07-27 .. 2026-01-04.

**What the endpoint returns for 2025** (found here, not in the docs): every record is stamped 00:00 UTC and is a
**daily rollup**: `usdc` sums the hourly payments of hours D 00:00 .. D 23:00, `nSamples` counts the hours with
a position (24 on 75% of records), `fundingRate` is an average rate and `szi` a position. The first per-hour
comparison (trial log) failed because of this; the check now expands each record to its 24 hours.

## Decision / result
Per record: position each hour = leader's rebuilt position (`positions.rebuild`, last fill strictly before the
hour), our hourly rate (ADR-0011), Binance reference at the hour as oracle proxy; calc = sum over held hours of
-position x price x rate. Output `research/hyperliquid/user_funding_check.parquet`, `user_funding_summary.csv`.

| Test | Result |
| --- | --- |
| sign of usdc == sign of -szi x rate | 99.9% of records |
| held hours (rebuilt) == nSamples | 95.6% |
| amount computable (position known and priced every held hour) | 4,125 records (90.5%) |
| \|calc / usdc - 1\| <= 1% | **98.4%** of computable records; median error 0.05%, p90 0.12% |
| total calc / total actual (computable) | 1.0014 ($65,179 actual) |
| mean of our rates over held hours == fundingRate | 73.7% (not reproduced; immaterial, amounts match) |

Per leader, the amount match is 96.5-99.7%. Not computable: 280 records with an hour before the leader's first
fill in the coin, 159 with a held hour that had no Binance price.

So the sign convention (longs pay a positive rate), the hourly rate table, the rebuilt positions and the Binance
proxy for the oracle price together reproduce actual payments to about 5 bps.

`userFunding` is **not** an input: it exists only for a few addresses, is a daily rollup, and its rate field is
an unexplained average. Phase 3 computes funding from the rate table.

## Consequences
The oracle-proxy error is about 5 bps of a payment, far below other cost uncertainties. The 1% tolerance is a
placeholder (`funding.user_funding_rel_tol`). Test: `tests/test_funding.py::test_user_funding_check_convention`.
