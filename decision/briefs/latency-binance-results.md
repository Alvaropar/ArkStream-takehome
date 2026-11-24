# Brief: latency study results from the Binance trading repository

> ADR numbers below follow the renumbering of 2026-11-23 (ADR-0085; old numbers in
> `decision/adr/RENUMBERING.md`), except the reserved number blocks, which are quoted as they were reserved.

Written 2026-11-20 for a session in the user's separate Binance trading repository. Purpose: supply measured order
latency to the ArkStream copy-pilot replay (`C:\Projects\quant-task-arkstream`, ADR-0038), which today assumes its
copy delay.

## Prompt to start the session

> In this repository, find the latency measurements already made for Binance trading (order submission,
> acknowledgement and fills, and market-data receive delay if measured) and write them up for use in another
> project. Do not run new live orders for this; use the existing measured results, and rerun an existing
> read-only analysis only if a summary is missing. Produce two files:
>
> 1. `latency_study.csv`, one row per leg and measurement setup, with columns: `leg` (market_data_receive,
>    decision_compute, order_submit_to_ack, ack_to_fill, round_trip_total, network_rtt where available), `venue`,
>    `product` (spot / USD-M futures), `api` (REST / WebSocket), `environment` (region, machine or VPS type,
>    co-location or not), `period_start`, `period_end`, `n`, `mean_ms`, `p10_ms`, `p50_ms`, `p90_ms`, `p99_ms`,
>    `max_ms`, `clock_sync` (how time was synchronised and the measured offset), `source` (file or script that
>    produced it).
> 2. `latency_study.md`: how each leg was measured (start and end timestamps of each leg and which clock took
>    them), the code path and commit hash, the period, the sample sizes, known biases (for example retries, rate
>    limits, outliers removed and why), and anything that does not transfer to another exchange.
>
> Do not include API keys, account identifiers, balances or order IDs. Say plainly if a leg was never measured
> rather than estimating it. Report the median and 99th percentile of order submit to acknowledgement for USD-M
> futures in the final message.

## How the result is used here

Copy both files into `data/reference/latency/binance/`, record their checksums, and record the source (repository,
commit, period, environment) in ADR-0038. The decision-compute and order-acknowledgement legs feed the replay's
scenarios, labelled `transferred_from_binance`; the receive leg comes from the Hyperliquid recorder instead
(`decision/briefs/latency-hl-receive.md`).
