# ADR renumbering of 2026-11-23

Decided in [ADR-0085](0085-adr-renumbering-and-archive.md); done by `scripts/adr_renumber.py`. Look up an old number here.

**Where old numbers remain.** Every file uses the new numbers. The only old numbers left are column and value
names baked into outputs: `return_source_adr0065` (now 0028), `broad_adr0115` (now 0049),
`pricing_failures_adr0122` (now 0055) and v1's `adr0137_basis`. Renaming them would change output schemas and need a
replay rerun. Six hash lines in `provenance/SIZING_ARCHIVE_CHECKSUMS.txt` were updated after the rewrite, and the
record says so.

The reserved number blocks quoted in `decision/briefs/` are the blocks as they were reserved. `ADR-0018 D11` in
`decision/latency_study.md` and `data/reference/latency/binance/latency_study.md` is the Binance latency repo's own ADR.

| Old | New | Decision |
| --- | --- | --- |
| 0001 | [0001](0001-record-decisions-as-adrs.md) | Record decisions as ADRs |
| 0002 | [0002](0002-reference-prices-binance-klines.md) | Reference prices from Binance 1m klines, with validity windows |
| 0003 | [0003](0003-aggtrades-from-binance-zips.md) | Trade-level drift from verified Binance aggTrades zips, from 2025-09-08 |
| 0004 | [0004](0004-drift-per-test-date.md) | Drift estimated per test date from earlier data only |
| 0005 | [0005](0005-approximate-drift-venue-basis.md) | Approximate drift corrected by the venue basis, capped at 100 bps |
| 0006 | A0006 (deleted) | Delete the redundant aggTrades copies |
| 0007 | A0007 (deleted) | Working assumptions while the recruiter questions are open |
| 0008 | [0006](0006-deterministic-drift-outputs.md) | Sorted drift outputs; retrying renames on Windows |
| 0009 | [0007](0007-addresses-as-assets.md) | Treat addresses as assets: suitability gates, daily TWR, copyable series |
| 0010 | [0008](0008-hyperliquid-public-data-feasibility.md) | Hyperliquid public data: what the info endpoint serves for 2025 |
| 0011 | [0009](0009-hyperliquid-funding-rates.md) | Hyperliquid hourly funding rates: fetcher, table, Phase 3 convention |
| 0012 | [0010](0010-price-check-rule-preregistered.md) | Price check rule: Binance reference vs Hyperliquid, pre-registered |
| 0013 | [0011](0011-price-check-result-hyperliquid-4h-source.md) | Price check result; Hyperliquid 4h closes as a second reference for 32 coins |
| 0014 | [0012](0012-user-funding-check.md) | userFunding validates the funding convention; it stays a check |
| 0020 | [0013](0013-leader-evidence-scope.md) | Leader evidence per origin, for grade A/B addresses, ex-funding |
| 0021 | [0014](0014-account-returns.md) | Account returns: start convention base, end sensitivity, gaps as one return |
| 0022 | [0015](0015-hourly-book-valuation.md) | Book valued hourly by exact mark-to-market; unpriced hours are null |
| 0023 | [0016](0016-round-trip-metrics.md) | Round-trip return on peak notional; hourly excursions; open trades valued at asof |
| 0024 | [0017](0017-stress-shock.md) | Stress shock = largest 24 h fall (longs) and rise (shorts) before the origin |
| 0025 | [0018](0018-leverage-liquidation-gates.md) | Leverage, liquidation distance (stated margin), liquidations; gates as pass/fail/unmeasured |
| 0026 | [0019](0019-profiles-and-impact.md) | Profiles; order size against Binance daily quote volume |
| 0027 | A0027 (deleted) | Evidence minimum = 20 completed round trips (PLACEHOLDER) |
| 0040 | [0020](0020-hyperliquid-primary-daily-prices.md) | Hyperliquid prices for daily metrics, Binance as validator; the 32 coins |
| 0041 | [0021](0021-recruiter-answers.md) | Recruiter answers to the four Day-0 questions |
| 0042 | [0022](0022-hip3-excluded-for-now.md) | HIP-3 perpetuals stay out of scope for now |
| 0043 | [0037](0037-no-scale-up-frozen.md) | No scale-up is the copy sizing rule |
| 0044 | [0038](0038-measured-latency.md) | Replace the assumed copy delay with measured latency |
| 0045 | [0039](0039-worst-case-intrabar-drawdown.md) | Worst-case drawdown inside each 4h bar, with a gate |
| 0046 | [0064](0064-scope-go-no-go.md) | Scope is the gray-launch go/no-go decision; Phases 5 and 6 are not built |
| 0047 | [0065](0065-new-phase-5-portfolio-design.md) | New Phase 5 designs the capital arrangement, risk limits, pause and exit rules after basket selection |
| 0048 | [0066](0066-material-scope-offset-grading.md) | Grade the PnL-identity residual by economic size, not by a cent tolerance and a CV |
| 0049 | [0067](0067-phase2-gate-categories.md) | Phase 2 gates in four categories; uncertainty-aware data checks; style screens judged by the simulated copy |
| 0050 | [0068](0068-missing-measurement-policy.md) | One policy for missing measurements: no credit for what was not measured |
| 0051 | A0051 (deleted) | The ranking key uses the copy's mark-to-market daily NAV, not completed trips |
| 0052 | [0069](0069-gate7-v2-book-account.md) | Gate 7 v2: rank agreement, a steady-gap rate and a one-for-one slope between account and rebuilt book |
| 0053 | [0084](0084-funding-out-of-alpha.md) | Funding is a separate source of return, not skill: alpha excludes the copy's funding PnL |
| 0060 | [0023](0023-origin-coverage.md) | Grade coverage through each origin |
| 0061 | [0024](0024-funded-valuation.md) | Fund core-perp books and use venue-specific marks |
| 0062 | [0025](0025-snapshot-fit.md) | Reconcile at exact snapshot times and disclose uncheckable intervals |
| 0063 | [0026](0026-asset-returns-and-exposure.md) | Measure address TWR and joint BTC/ETH exposure |
| 0064 | [0027](0027-suitability-gates.md) | Count address suitability gates at each origin |
| 0065 | [0028](0028-cross-margin-return-source.md) | Choose the address return source using the cross-margin PnL identity |
| 0080 | [0029](0029-follower-execution-price.md) | Price follower orders at acknowledgement |
| 0081 | [0030](0030-follower-decision-and-sizing.md) | Size each copy against a fixed allocation at decision time |
| 0082 | [0031](0031-spread-and-impact.md) | Freeze print spreads after the first development window |
| 0083 | [0032](0032-follower-returns-and-break-even.md) | Measure the funded copy series and bracket the first delay crossing |
| 0084 | [0033](0033-square-root-impact.md) | Square-root impact sensitivity |
| 0085 | [0034](0034-address-gross-exposure-cap.md) | Cap each follower address at 1.5 times allocation |
| 0086 | [0035](0035-participation.md) | Limit each follower order to a share of the latest completed 4h volume |
| 0087 | A0087 (deleted) | Never copy a leader at more than their own size |
| 0088 | [0036](0036-leader-sweeps.md) | Anchor copies at the leader's own sweep; size-dependent drift tested, not applied |
| 0100 | [0040](0040-read-only-ws-recorder.md) | Read-only Hyperliquid stream recorder, standard library, subscribe-only |
| 0101 | [0041](0041-clock-offset-ntp.md) | Clock offset to NTP measured before and after each run; correction and usability rules |
| 0102 | [0042](0042-leaders-and-coins.md) | Leader addresses and coins for the receive-delay runs |
| 0103 | [0043](0043-receive-delay-analysis.md) | Receive-delay definition, snapshot exclusion, batching and outputs |
| 0104 | [0056](0056-hyperliquid-receive-delay-result.md) | Hyperliquid receive delay measured; ADR-0038 total copy delay (partly transferred from Binance) |
| 0105 | [0057](0057-clock-drift-corrected-steps-limited.md) | Steady clock drift is corrected; the 20 ms limit applies to clock steps |
| 0110 | [0044](0044-point-in-time-price-check.md) | Apply the price check as of each origin |
| 0111 | [0045](0045-material-return-source-switch.md) | Switch to the rebuilt book only on material, persistent PnL identity breaches |
| 0112 | [0046](0046-forced-fills-not-signals.md) | Forced fills are position changes, not signals |
| 0113 | [0047](0047-excluded-coin-exposure.md) | Report each address's notional in coins that cannot be copied |
| 0114 | [0048](0048-conservative-alt-drift.md) | Bound the base drift of parameterised coins below 300 s from below |
| 0115 | [0049](0049-stress-coverage.md) | Report a stress result with less than 80% priced intents as unmeasured |
| 0116 | A0116 (deleted) | Frozen reference equity between reviews, as a sizing variant to compare |
| 0117 | [0050](0050-cost-uncertainty-surface.md) | Cost uncertainty surface around the placeholder execution costs |
| 0118 | [0051](0051-reproducible-clean-copy.md) | Rebuild everything from a clean copy and public data |
| 0119 | [0052](0052-frozen-reference-equity-sizing.md) | Size every copy on the frozen reference equity |
| 0120 | [0053](0053-stress-fallback.md) | Price parameterised stress orders without their own crash-sample cell |
| 0121 | [0054](0054-reference-manifest-cutoff.md) | Regenerate the reference price manifest with the current cutoff |
| 0122 | [0055](0055-stress-coverage-pricing-failures.md) | Count only pricing failures as unpriced in the stress coverage measure |
| 0130 | A0130 (deleted) | Selection-level gates, with the equity band at 5k-2M |
| 0131 | A0131 (deleted) | Ranking key = 20th percentile of a week-block bootstrap of the follower's net return per trip |
| 0132 | A0132 (deleted) | Behaviour clusters, co-movement, the diversification walk and the basket |
| 0133 | A0133 (deleted) | Development walk-forward, baselines and the reported statistics |
| 0134 | A0134 (deleted) | Market-relative results and copy capture for the basket, sleeves and baselines |
| 0135 | A0135 (deleted) | Pre-registered Phase 4 diagnostics |
| 0136 | A0136 (deleted) | Coin filter variant (copy only coins with high training capture) |
| 0137 | A0137 (deleted) | Three rule variants and the criterion that chooses between them |
| 0138 | A0138 (deleted) | The selection rule in force is rule_b_coin_filter (chosen by the ADR-A0137 criterion) |
| 0139 | A0139 (deleted) | Holdout freeze hash and the guard on post-3-Dec windows |
| 0140 | A0140 (deleted) | The coin filter runs inside the frozen replay; the rule stays rule_b_coin_filter |
| 0141 | A0141 (deleted) | Holdout freeze re-cut on the executable coin filter |
| 0142 | [0070](0070-phase4-v2-structure-series.md) | Phase 4 v2: qualification only; the copy series, common window, exposed-day measurability and a provisional 10k sleeve |
| 0143 | [0071](0071-holdings-alpha-per-gross.md) | Copy economics: holdings-based market adjustment, alpha per unit of gross exposure-time, static-replica decomposition |
| 0144 | [0072](0072-evidence-shrinkage-categories.md) | Evidence: clustered uncertainty, DerSimonian-Laird shrinkage, own-data robustness and evidence categories |
| 0145 | [0073](0073-tradable-universe-copyability.md) | Copyability: an ex-ante tradable universe, leader-level exclusion, the cap on the full book; hold band as a diagnostic |
| 0146 | [0074](0074-duplicates-only.md) | Phase 4 removes only near-duplicates; co-movement is measured and handed to Phase 5; the walk and K are retired |
| 0147 | [0075](0075-ranking-validation-evaluation.md) | Ranking is used only if it predicts (pre-declared IC rule); Phase 4 is evaluated as qualification |
| 0150 | [0058](0058-measured-copy-delay-scenarios.md) | Set the replay's delay scenarios from the measured copy delay |
| 0151 | [0059](0059-millisecond-delays-and-horizons.md) | Delays and drift horizons in whole milliseconds; 1.2 s and 5 s horizons; delay grid extended |
| 0152 | [0060](0060-severe-scenario.md) | Add `severe`: the stress costs and rules at the old 60 s / 300 s delays |
| 0160 | [0061](0061-short-delay-alt-floor.md) | Bound base alt drift below 300 s by a point-in-time Hyperliquid split-order estimate |
| 0161 | [0062](0062-measured-receive-delay.md) | Set the replay's receive delay to the measured 392 ms |
| 0162 | [0063](0063-copy-capture-and-market-relative.md) | Copy capture against a same-sizing benchmark, and market-relative copy returns |
| 0170 | [0076](0076-p4-2-tradable-measurement.md) | P4-2 details: the all-priced rerun on the current universes, how T1-T5 are measured, per-wallet tradable sets, `not_tradable` in the replay |
| 0171 | [0077](0077-p4-3-statistic-details.md) | P4-3 details: day indexing, valid days, the beta fit, the clustered standard error, the static replica and the reported statistics |
| 0172 | [0078](0078-p4-4-p4-5-evidence-ranking-details.md) | P4-4 and P4-5 details: the DerSimonian-Laird pool, the degenerate posterior, robustness variants, the bootstrap draw, the outcome α and the IC rule's arithmetic |
| 0173 | [0079](0079-p4-6-to-p4-8-comovement-evaluation-handoff.md) | P4-6 to P4-8 details: which pairs, the co-movement measures and Σ, the S3 gates in v2, the qualification tests and the hand-off columns |
| 0174 | [0080](0080-exposure-materiality-dust.md) | An exposed day needs a gross of at least the replay's 10 USDC minimum order; dust residuals are not exposure |
| 0175 | [0081](0081-time-shift-placebo.md) | The time-shift placebo for E2 copies: a holdings-level circular shift of the copy's exposure path, same coins, sizes and costs |
| 0176 | [0082](0082-gross-max-start-end.md) | Gross exposure-time is the larger of the start-of-day and end-of-day gross; a day is exposed when it is at least 10 USDC |
| 0177 | [0083](0083-alpha-ex-funding-carry-books.md) | Report α excluding funding beside α, and label funding-carry books; no carry factor |

## The 18 deleted ADRs

They no longer carried any decision used by the study. They were archived and then deleted on 2026-11-23 at the user's request, after the parts still in force were copied forward (ADR-0085 item 3). 17 of them are in git commit `173f5a8` under their old file names (`decision/adr/<old number>-<slug>.md`). A0051 was never committed. Its definitions are kept in ADR-0078, and the history of the switch it records is in `decision/full_selection_criteria.md`.

| ID | Decision | Why it was removed |
| --- | --- | --- |
| A0006 | Delete the redundant aggTrades copies | an action (redundant aggTrades copies deleted), no rule in force |
| A0007 | Working assumptions while the recruiter questions are open | superseded by ADR-0021 |
| A0027 | Evidence minimum 20 completed round trips | replaced by ADR-0067 (gate 1 keeps the 20-trip minimum) |
| A0051 | Ranking key = p20 of a calendar-week block bootstrap of the copy's mark-to-market daily NAV return from first exposure (min 20 days, 4 weeks); trip statistics kept as diagnostics; amends ADR-A0131 | superseded by ADRs 0071, 0072; the NAV-key definition kept in ADR-0078 for the reported IC |
| A0087 | Never copy a leader at more than their own size (sensitivity) | promoted to the sizing rule by ADR-0037, which now carries its mechanics |
| A0116 | Frozen reference equity (14-day reviews, reduce-only on unusable equity) run beside the dynamic denominator | promoted to the sizing rule by ADR-0052, which now carries its mechanics |
| A0130 | Selection gates on top of grade A/B and the 18 Phase 2 gates: 90 snapshot / 60 usable days, median equity 5k-2M (user's choice from the capital; plan 20k), copyable notional >= 90%, copyable holding band, break-even delay above 1.2 s, not the weaker copier | Phase 4 v1 gates; superseded by ADR-0073 (the unchanged gates copied there) and ADR-0067 |
| A0131 | Key = 20th percentile of 2,000 entry-week block-bootstrap means of the follower's net return per completed training trip (min 10 trips, 4 blocks); key > 0 to be selectable; single-event flag | Phase 4 v1 trip key; superseded by ADRs 0071, 0072; definition kept in ADR-0078 |
| A0132 | Ward behaviour clusters (6, no outcome features); walk by within-cluster rank; correlation and position overlap < 0.5 with every chosen address; K = 5; equal sleeves | Phase 4 v1 walk and basket; superseded by ADR-0074; the clusters copied into ADR-0072 |
| A0133 | Development walk-forward vs matched and all-A/B random-k (1,000 seeded draws), equal weight, cash; win = above matched median; with and without 10-11 Oct; Clopper-Pearson, MinTRL | Phase 4 v1 baselines; superseded by ADR-0075 (seed and draws copied there) |
| A0134 | Market-relative (BTC/ETH buy-and-hold, alpha, betas) and capture (ratio, gap parts, leader-fee benchmark, won/lost medians) for basket, sleeves and baselines | Phase 4 v1 market-relative basket report; superseded by ADR-0071 |
| A0135 | Nine pre-registered diagnostics (persistence, feature screen, gate audit, attribution, capture drivers, alpha vs beta, crowding, tail, decay) | Phase 4 v1 diagnostics; the gate audit is restated in ADRs 0075 and 0079 |
| A0136 | Coin filter variant: BTC/ETH/HYPE/SOL plus coins whose training benchmark won >= 500 USDC with capture >= 0.5; attribution from the ledgers (cap not re-solved) | Phase 4 v1 coin filter; superseded by ADR-0073 |
| A0137 | Three variants (rule_a, rule_b_coin_filter, rule_c_p10); choose by most windows above the matched random-k median, ties to the simpler | Phase 4 v1 variant choice; superseded by ADR-0075 |
| A0138 | Rule in force: rule_b_coin_filter (3 of 4 matched wins vs 1 of 4); 3 Dec shortlist 0x2cd9, 0x971f, 0xd2f0; weak evidence (pools 3/2/3/5) | Phase 4 v1 rule and shortlist; superseded by ADR-0070 |
| A0139 | Holdout freeze: SHA-256 of config, rule sources and the 3 Dec shortlist in provenance/HOLDOUT_FREEZE.txt; `frozen: true`; selection and replay refuse windows after 3 Dec unless the hashes match | void freeze; the mechanism is restated in ADR-0065 |
| A0140 | Coin filter executed inside the frozen replay (excluded coins `coin_filter_excluded`, never traded; 1.5x cap and resize legs on kept coins; benchmark on kept coins); rule stays rule_b_coin_filter whatever the rerun shows; holdout path built now behind the guard (3 Dec - 4 Jan 00:00, 32 days) | Phase 4 v1 executable coin filter; superseded by ADR-0073 |
| A0141 | Freeze re-cut on the executable coin filter: 45 files incl. replay_coinfilter, the holdout path and the new 3 Dec shortlist; supersedes A0139's unsent hash | void freeze; the mechanism is restated in ADR-0065 |
