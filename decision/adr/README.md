# Architecture decision records

One file per decision: `NNNN-short-title.md`, numbered in order, never renumbered or deleted. A changed
decision gets a new ADR that supersedes the old one; the old one's status becomes `Superseded by ADR-NNNN`.

**When to write one.** Any choice that changes a result, a data source, a rule, a threshold, the scope or
the layout of the project, and any choice another session or a reviewer would otherwise have to rediscover.
Exploratory trials and their numbers go in `provenance/trial_log.md`; the ADR records what was decided and
why, and points to the trials.

**Parallel sessions.** Sessions working at the same time take ADR numbers from their own reserved block
(given in their brief) so they never collide; the index below is updated by each session for its own rows.

## Template

```markdown
# ADR-NNNN: <decision in a few words>

- Status: Proposed | Accepted | Superseded by ADR-NNNN
- Date: YYYY-MM-DD
- Phase: <milestone or phase>

## Context
What forced the decision; the evidence (numbers, files, trial-log rows).

## Decision
What we do, precisely enough to implement or check.

## Consequences
What changes, what it costs, what stays open, how it is tested.
```

## Index

| ADR | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-record-decisions-as-adrs.md) | Record decisions as ADRs | Accepted | 2026-11-19 |
| [0002](0002-reference-prices-binance-klines.md) | Reference prices from Binance 1m klines, with validity windows | Amended by 0040, 0118 | 2026-11-19 |
| [0003](0003-aggtrades-from-binance-zips.md) | Trade-level drift from verified Binance aggTrades zips, from 2025-09-08 | Accepted | 2026-11-19 |
| [0004](0004-drift-per-test-date.md) | Drift estimated per test date from earlier data only | Amended by 0112 | 2026-11-19 |
| [0005](0005-approximate-drift-venue-basis.md) | Approximate drift corrected by the venue basis, capped at 100 bps | Accepted | 2026-11-19 |
| [0006](0006-delete-redundant-aggtrades-copies.md) | Delete the redundant aggTrades copies | Accepted | 2026-11-19 |
| [0007](0007-working-assumptions-pending-answers.md) | Working assumptions while the recruiter questions are open | Superseded by 0041 | 2026-11-19 |
| [0008](0008-deterministic-drift-outputs.md) | Sorted drift outputs; retrying renames on Windows | Accepted | 2026-11-19 |
| [0009](0009-addresses-as-assets.md) | Addresses as assets: suitability gates, daily TWR, copy series as the investable price | Amended by 0041 | 2026-11-19 |
| [0010](0010-hyperliquid-public-data-feasibility.md) | Hyperliquid info endpoint: funding history go, 4h candles for the price check, 1h no-go | Accepted | 2026-11-19 |
| [0011](0011-hyperliquid-funding-rates.md) | Hyperliquid hourly funding rates: fetcher, table, Phase 3 payment convention | Accepted | 2026-11-19 |
| [0012](0012-price-check-rule-preregistered.md) | Price check rule (Binance vs Hyperliquid 4h closes), pre-registered | Accepted | 2026-11-19 |
| [0013](0013-price-check-result-hyperliquid-4h-source.md) | Price check: 163 coins keep Binance; 32 use Hyperliquid 4h closes (daily marks, no hourly) | Amended by 0110 | 2026-11-19 |
| [0014](0014-user-funding-check.md) | userFunding (daily rollups) reproduces rate x position x proxy price to ~5 bps; check only | Accepted | 2026-11-19 |
| [0020](0020-leader-evidence-scope.md) | Leader evidence per origin for grade A/B addresses, ex-funding | Amended by 0060–0064 | 2026-11-19 |
| [0021](0021-account-returns.md) | Account returns: start convention base, end sensitivity, gaps as one return | Amended by 0063 and 0065 (placeholders) | 2026-11-19 |
| [0022](0022-hourly-book-valuation.md) | Book valued hourly by exact mark-to-market; unpriced hours null | Amended by 0061–0062 (placeholders) | 2026-11-19 |
| [0023](0023-round-trip-metrics.md) | Round-trip return on peak notional; hourly excursions; open trades valued at asof | Amended by 0061 | 2026-11-19 |
| [0024](0024-stress-shock.md) | Stress shock: largest 24 h fall (longs) / rise (shorts) before the origin | Accepted (placeholder) | 2026-11-19 |
| [0025](0025-leverage-liquidation-gates.md) | Leverage, liquidation distance at a stated 2.5% MMR; gates pass/fail/unmeasured | Amended by 0064 (placeholders) | 2026-11-19 |
| [0026](0026-profiles-and-impact.md) | Profiles; order size against Binance daily quote volume | Accepted | 2026-11-19 |
| [0027](0027-evidence-minimum-placeholder.md) | Evidence minimum 20 completed round trips | Accepted (placeholder) | 2026-11-19 |
| [0040](0040-hyperliquid-primary-daily-prices.md) | Hyperliquid prices for daily metrics, Binance validates; 22 failing and 10 unmapped coins on Hyperliquid prices | Amended by 0110 | 2026-11-19 |
| [0041](0041-recruiter-answers.md) | Recruiter answers: cutoff = end of data; equity = cross-margin equity; public data incl. L2; perps, HIP-3 permitted, spot out | Accepted | 2026-11-19 |
| [0042](0042-hip3-excluded-for-now.md) | HIP-3 perps stay out of scope for now (permitted, not included) | Accepted | 2026-11-19 |
| [0043](0043-no-scale-up-frozen.md) | No scale-up frozen as the copy sizing rule (promotes ADR-0087) | Accepted (frozen); amended by 0119 | 2026-11-20 |
| [0044](0044-measured-latency.md) | Measured latency replaces the assumed copy delay (Hyperliquid receive delay measured; decide and acknowledge from the Binance repo) | Accepted; scenarios amended by 0150 | 2026-11-20 |
| [0045](0045-worst-case-intrabar-drawdown.md) | Worst-case drawdown inside each 4h bar (Hyperliquid OHLC, Binance 1m check) with a −50% gate | Accepted (placeholder) | 2026-11-20 |
| [0060](0060-origin-coverage.md) | Grade coverage through each origin | Amended by 0110 | 2026-11-19 |
| [0061](0061-funded-valuation.md) | Fund core-perp books and use venue-specific marks | Accepted | 2026-11-19 |
| [0062](0062-snapshot-fit.md) | Reconcile at exact snapshot times and disclose uncheckable intervals | Accepted | 2026-11-19 |
| [0063](0063-asset-returns-and-exposure.md) | Measure address TWR and joint BTC/ETH exposure | Amended by 0065 | 2026-11-19 |
| [0064](0064-suitability-gates.md) | Count address suitability gates at each origin | Accepted | 2026-11-19 |
| [0065](0065-cross-margin-return-source.md) | Choose the primary return using the cross-margin PnL identity | Amended by 0111 | 2026-11-19 |
| [0080](0080-follower-execution-price.md) | Price follower orders at acknowledgement using aggTrades or point-in-time drift and skip the 32 coins without intraday prices | Amended by 0110, 0114, 0120 | 2026-11-20 |
| [0081](0081-follower-decision-and-sizing.md) | Debounce visible fills, size against cross-margin equity and reserve pending quantity | Amended by 0119, 0161 | 2026-11-20 |
| [0082](0082-spread-and-impact.md) | Freeze minute-print spreads and assume impact against completed 4h volume | Accepted | 2026-11-20 |
| [0083](0083-follower-returns-and-break-even.md) | Value follower daily TWR, completed trips and the delay and cost break-even | Amended by 0115, 0122 | 2026-11-20 |
| [0084](0084-square-root-impact.md) | Test square-root impact using trailing Hyperliquid volatility and volume | Accepted for research | 2026-11-20 |
| [0085](0085-address-gross-exposure-cap.md) | Scale all address targets to 1.5 times fixed allocation | Accepted for research | 2026-11-20 |
| [0086](0086-participation.md) | Limit each follower order to 0.5% of the latest completed 4h volume (sensitivity) | Accepted (placeholder) | 2026-11-20 |
| [0087](0087-no-scale-up.md) | Never copy a leader at more than their own size (sensitivity) | Accepted | 2026-11-20 |
| [0088](0088-leader-sweeps.md) | Anchor copies at the leader sweep (base VWAP, stress deepest); size drift term tested, none qualified | Amended by 0112 | 2026-11-20 |
| [0100](0100-read-only-ws-recorder.md) | Read-only Hyperliquid stream recorder: stdlib client, one host, subscribe-only guard, raw + manifest | Accepted | 2026-11-20 |
| [0101](0101-clock-offset-ntp.md) | NTP offset before/after each run (best of 5 servers, ±RTT/2), linear correction; unusable if it moves > 20 ms | Amended by 0105 | 2026-11-20 |
| [0102](0102-leaders-and-coins.md) | Leaders: package top 30 probed, 10 active with most fills in 24 h; coins BTC/ETH/HYPE/SOL + ZEC/PENDLE/AIXBT/TRX | Accepted | 2026-11-20 |
| [0103](0103-receive-delay-analysis.md) | Receive delay per event; snapshots and the initial trades backlog excluded; batching, size bins, outputs | Accepted | 2026-11-20 |
| [0104](0104-hyperliquid-receive-delay-result.md) | Receive delay measured: userFills p50 392 / p99 1,218 ms (run p50 339-738); total ~1.1 s median, ~4.4 s p99, partly from Binance; scenarios unchanged | Accepted; scenarios amended by 0150; receive used by the replay, 0161 | 2026-11-21 |
| [0105](0105-clock-drift-corrected-steps-limited.md) | Steady clock drift corrected (counter cross-check), 20 ms limit on steps only; NTP bound beside every number; NTP every 5 min in future runs | Accepted | 2026-11-21 |
| [0110](0110-point-in-time-price-check.md) | Price check applied as of each origin (bars closing by it); `insufficient` not copied; every consumer uses its own origin's list | Accepted | 2026-11-20 |
| [0111](0111-material-return-source-switch.md) | Rebuilt book primary only on material (> max(10 USDC, 0.5% equity)) and persistent (>= 5% or 3 in a row) breaches; else breaching intervals excluded | Accepted (placeholders) | 2026-11-20 |
| [0112](0112-forced-fills-not-signals.md) | ADL, liquidation and settlement fills left out of drift, the sweep anchor and the size study; still mirrored as reductions | Accepted | 2026-11-20 |
| [0113](0113-excluded-coin-exposure.md) | Per-address notional share in coins not passing at the origin and in HIP-3 (reported, no gate) | Accepted | 2026-11-20 |
| [0114](0114-conservative-alt-drift.md) | Base drift below 300 s on parameterised coins = max(four-coin proxy, own 300 s, 0) | Accepted; amended by 0160 (split-order estimate first, this floor as fallback) | 2026-11-20 |
| [0115](0115-stress-coverage.md) | Stress results with < 80% priced intents are unmeasured | Amended by 0122 | 2026-11-20 |
| [0116](0116-frozen-reference-equity-variant.md) | Frozen reference equity (14-day reviews, reduce-only on unusable equity) run beside the dynamic denominator | Promoted and amended by 0119 | 2026-11-20 |
| [0117](0117-cost-uncertainty-surface.md) | Cost surface: Y, participation and cap one at a time plus best/worst corners; lower bound = least favourable point | Accepted | 2026-11-21 |
| [0118](0118-reproducible-clean-copy.md) | Kline fetcher, lake rebuilt from verified zips (prices byte-identical), deterministic package, VERIFY.md, 8-thread byte checks | Amended by 0121 | 2026-11-21 |
| [0119](0119-frozen-reference-equity-sizing.md) | Sizing policy: frozen `E_ref` (user's choice), first review at the first usable snapshot, plain, target mirroring with netting; frozen only from 2026-11-21 (dynamic = mean-reversion overlay, archived) | Accepted | 2026-11-21 |
| [0120](0120-stress-fallback.md) | Stress fallback for parameterised coins without a crash-sample cell: max(liquidity-bucket estimate, 3x own base drift, 0) | Accepted (placeholders) | 2026-11-21 |
| [0121](0121-reference-manifest-cutoff.md) | Regenerate the reference price manifest with the current cutoff; price files unchanged | Accepted | 2026-11-21 |
| [0122](0122-stress-coverage-pricing-failures.md) | Stress coverage counts only pricing failures as unpriced (decided after seeing results); unmeasured fails the stress check; worst-measured sensitivity | Accepted (placeholder) | 2026-11-21 |
| [0130](0130-selection-gates.md) | Selection gates on top of grade A/B and the 18 Phase 2 gates: 90 snapshot / 60 usable days, median equity 5k-2M (user's choice from the capital; plan 20k), copyable notional >= 90%, copyable holding band, break-even delay above 1.2 s, not the weaker copier | Accepted (placeholders) | 2026-11-22 |
| [0131](0131-ranking-key-block-bootstrap.md) | Key = 20th percentile of 2,000 entry-week block-bootstrap means of the follower's net return per completed training trip (min 10 trips, 4 blocks); key > 0 to be selectable; single-event flag | Accepted (placeholders) | 2026-11-22 |
| [0132](0132-clusters-walk-basket.md) | Ward behaviour clusters (6, no outcome features); walk by within-cluster rank; correlation and position overlap < 0.5 with every chosen address; K = 5; equal sleeves | Accepted (placeholders) | 2026-11-22 |
| [0133](0133-walk-forward-baselines.md) | Development walk-forward vs matched and all-A/B random-k (1,000 seeded draws), equal weight, cash; win = above matched median; with and without 10-11 Oct; Clopper-Pearson, MinTRL | Accepted | 2026-11-22 |
| [0134](0134-market-relative-and-capture-basket.md) | Market-relative (BTC/ETH buy-and-hold, alpha, betas) and capture (ratio, gap parts, leader-fee benchmark, won/lost medians) for basket, sleeves and baselines | Accepted | 2026-11-22 |
| [0135](0135-preregistered-diagnostics.md) | Nine pre-registered diagnostics (persistence, feature screen, gate audit, attribution, capture drivers, alpha vs beta, crowding, tail, decay) | Accepted | 2026-11-22 |
| [0136](0136-coin-filter-variant.md) | Coin filter variant: BTC/ETH/HYPE/SOL plus coins whose training benchmark won >= 500 USDC with capture >= 0.5; attribution from the ledgers (cap not re-solved) | Accepted (placeholders); scoring superseded by 0140 | 2026-11-22 |
| [0137](0137-variants-and-choice.md) | Three variants (rule_a, rule_b_coin_filter, rule_c_p10); choose by most windows above the matched random-k median, ties to the simpler | Accepted | 2026-11-22 |
| [0138](0138-chosen-rule-coin-filter.md) | Rule in force: rule_b_coin_filter (3 of 4 matched wins vs 1 of 4); 3 Dec shortlist 0x2cd9, 0x971f, 0xd2f0; weak evidence (pools 3/2/3/5) | Accepted | 2026-11-22 |
| [0139](0139-holdout-freeze.md) | Holdout freeze: SHA-256 of config, rule sources and the 3 Dec shortlist in provenance/HOLDOUT_FREEZE.txt; `frozen: true`; selection and replay refuse windows after 3 Dec unless the hashes match | Superseded by 0141 (hash never sent) | 2026-11-22 |
| [0140](0140-executable-coin-filter.md) | Coin filter executed inside the frozen replay (excluded coins `coin_filter_excluded`, never traded; 1.5x cap and resize legs on kept coins; benchmark on kept coins); rule stays rule_b_coin_filter whatever the rerun shows; holdout path built now behind the guard (3 Dec - 4 Jan 00:00, 32 days) | Accepted (before the rerun) | 2026-11-22 |
| [0141](0141-holdout-freeze-executable.md) | Freeze re-cut on the executable coin filter: 45 files incl. replay_coinfilter, the holdout path and the new 3 Dec shortlist; supersedes 0139's unsent hash | Accepted | 2026-11-22 |
| [0150](0150-measured-copy-delay-scenarios.md) | Delay scenarios from the measured copy delay (user's choice before Phase 4): optimistic 1 s, base 1.2 s, stress 5 s all coins, severe 60 s / 300 s thin (labelled sensitivity); costs unchanged | Accepted | 2026-11-21 |
| [0151](0151-millisecond-delays-and-horizons.md) | Delays and drift horizons in whole ms end to end; horizons and delay grid 1, 1.2, 5, 10, 60, 300 s; size study keeps 1/10/60/300 s | Accepted | 2026-11-21 |
| [0152](0152-severe-scenario.md) | `severe` = stress costs and rules (drift pool, fallback, sweep anchor, coverage, stress check) at the old delays; shares the stress delay grid | Accepted | 2026-11-21 |
| [0160](0160-short-delay-alt-floor.md) | Base alt drift below 300 s = max(four-coin proxy, point-in-time Hyperliquid split-order estimate of the delay's bin, 0); ADR-0114 floor where the bin has no estimate (decided after seeing results, fixed before running) | Accepted | 2026-11-21 |
| [0161](0161-measured-receive-delay.md) | Replay receive delay 250 -> 392 ms (measured userFills median); batch grouping unchanged, decision time moves (decided after seeing results, fixed before running) | Accepted | 2026-11-21 |

Reserved blocks for the sessions started on 2026-11-19: Hyperliquid data session 0010-0019; Phase 2
(leader evidence) session 0020-0039. The main session uses 0001-0009 and 0040-0059. Phase 2 rework session: 0060-0079. Phase 3 (follower replay) session: 0080-0099. Hyperliquid latency session: 0100-0109. Pre-Phase-4 fix session: 0110-0129. Phase 4 (selection) session: 0130-0149. Measured-latency rerun session: 0150-0159. Alt-floor and receive session: 0160-0169.
