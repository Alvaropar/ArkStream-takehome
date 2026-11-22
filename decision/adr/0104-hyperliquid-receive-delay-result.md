# ADR-0104: Hyperliquid receive delay measured; ADR-0044 total copy delay (partly transferred from Binance)

- Status: Accepted (measurement); decision 4 (scenarios unchanged) amended by ADR-0150 (base 1.2 s, stress 5 s); the pooled receive median is the replay's `receive_ms` from ADR-0161
- Date: 2026-11-21
- Phase: Phase 3 / Phase 6 (latency measurement, ADR-0044 item 1)
- Feeds: ADR-0044 items 1 and 3. Rules: ADR-0100 to ADR-0103, ADR-0105.

## Context
Three read-only runs of the recorder (ADR-0100), about 91 minutes each, 10 leaders chosen by the probe of 2026-11-20
(ADR-0102), 8 coins. Data: `data/reference/latency/hyperliquid/<run_id>/`, each with a SHA-256 manifest. Outputs from
`python -m arkstream latency`, byte-identical on rerun: `research/latency/hl_receive_delay.csv`,
`hl_receive_delay_by_size.csv`, `total_delay.csv`, `hl_receive_delay.md`.

**Environment:** a Windows 11 laptop at home (32 logical CPUs) on China Telecom home Wi-Fi. That is not a cloud
VM like the Binance acknowledgement leg (GCE europe-west4) and not co-located. The clock was corrected to NTP
(ADR-0101, ADR-0105).

| Run (start, UTC) | Session | Messages | Gaps | NTP offset before / after (ms) | NTP +/- | Step | Counter check | Label |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20261120T110332Z (11:03) | Asia close / Europe | 29,801 | 2 (2.8 s, 2.2 s) | +86.8 / +120.2 | 34 ms | 13.4 ms | 1.0 ms | |
| 20261120T162706Z (16:27) | US session | 48,397 | 0 | +83.1 / +133.0 | 20 ms | 15.6 ms | 4.4 ms | |
| 20261121T034440Z (03:44) | Asia | 61,049 | 1 (17 s) | -26.9 / +65.1 | 83 ms | 14.8 ms | 6.0 ms | wide NTP bound; counter check > 5 ms |

The gaps came from a recorder defect, now fixed: a TLS read timeout (`SSLWantReadError`) was treated as a
disconnect. Fills during a gap arrive in the next snapshot, so they are excluded, not mis-timed.
`20261120T162655Z` is **an aborted start with no data** (no messages, no `run.json`). It is left in place, and the
analysis ignores it.

## Decision
1. **Measured receive delay `d_receive` (primary): `userFills`**, NTP-corrected receive time minus fill time
   (ADR-0103). Every number is shown with its run's NTP bound.

   | Run | Fills | Messages | p10 | p50 | p90 | p99 | NTP +/- |
   | --- | --- | --- | --- | --- | --- | --- | --- |
   | 11:03 | 180 | 115 | 261 | 339 | 640 | 952 | 34 |
   | 16:27 (US) | 79 | 26 | 387 | 738 | 797 | 1,164 | 20 |
   | 03:44 (labelled) | 25 | 21 | 380 | 553 | 798 | 1,194 | 83 |
   | **Pooled** | **284** | **162** | **265** | **392** | **793** | **1,218** | 83 (largest) |

   All values are in ms. Cross-check from `trades` (438k events), p50 / p99: 496 / 1,904, 534 / 1,639 and
   571 / 2,239; pooled 545 / 1,938.
2. **What limits the result:**
   - **The run-to-run spread is the main uncertainty.** The `userFills` median ranges from **339 to 738 ms**
     across runs, more than any clock bound (+/-20-83 ms). It follows the time of day and the network, not the
     clock.
   - **The sample is small.** It holds 284 fills but only 162 messages, and fills arrive in bursts
     (1.6-3.0 per message). The pooled figures lean on run 1 (180 of 284 fills). The 99th percentile rests on
     about two messages, and the per-run p99s on one.
   - **The environment is a home laptop on Wi-Fi.** A cloud VM near the venue would likely be faster and steadier.
     These are figures for this setup, not a floor.
3. **ADR-0044 total** = receive + debounce 250 ms (ADR-0081) + decision compute about 120 ms (Binance study,
   single-asset median 115-128 ms, measured on a Windows laptop) + acknowledgement (Binance USD-M **Demo**, order
   submit -> POST answer, p10 322, p50 354, p90 574, p99 = max 2,767 ms, n = 30, GCE europe-west4). The ack
   figures are read from `data/reference/latency/binance/latency_study.csv` after its checksum is verified.
   **Partly transferred from Binance** (`transferred_from_binance` for compute and acknowledgement):

   | Quantile | Receive | Ack | **Total, sum of quantiles** | Total, per draw |
   | --- | --- | --- | --- | --- |
   | p10 | 265 | 322 | 957 | 994 |
   | p50 | 392 | 354 | **1,116** | 1,225 |
   | p90 | 793 | 574 | 1,737 | 1,844 |
   | p99 | 1,218 | 2,767 | **4,354** | 3,540 |

   - **Measured median total: about 1.1 s. Measured p99 total: about 4.4 s.**
   - The sum of quantiles is the headline. For the tail it is an upper bound, because it adds both legs' worst cases
     as if they always coincided.
   - "Per draw" combines every pooled receive sample with the ack distribution (interpolated through its four
     published quantiles, flat outside them) and assumes the legs are independent. It gives about 1.2 s and 3.5 s.
   - Using the slowest run's receive alone (p50 738, p99 1,164) gives a median total of about 1.5 s.
4. **Replay scenarios are not changed.** Optimistic stays 1 s, base 10 s, stress 60 s (300 s for thin coins), as
   in `config/execution.yaml`. Against the measured total, **the 10 s base is conservative** (about 9 times the
   measured median) and **the 60 s stress is conservative** (about 14 times the measured p99). **The replay's
   existing 1 s point** (the optimistic scenario, and the shortest point of the 1 / 10 / 60 / 300 s grid of
   ADR-0083) **is the closest case consistent with the measurement**. It sits just below the measured median and
   below the p99. ADR-0044 item 3 (scenarios set from these quantiles, the replay rerun) is not carried out. Any
   change to the scenarios needs a new decision.

## Consequences
ADR-0044 now has a measured receive leg and a stated total. The replay's 1 / 10 / 60 s results stay as they are,
and they can be read against a measured median of about 1.1 s and a p99 of about 4.4 s.

What stays open:
- **Hyperliquid's own acknowledgement cannot be measured here.** It would mean sending orders, which this project
  forbids. The Binance Demo figure (n = 30; p99 is one order; a Netherlands VM) stands in for it, and that gap is
  stated, not corrected.
- **More runs would narrow the spread.** Runs on a cloud VM, recorded with NTP readings during the run (ADR-0105),
  would tighten both the spread and the clock bound. None was recorded now.
- **The leader set needs refreshing.** Leaders were probed on 2026-11-20; a later run should probe again (ADR-0102).
