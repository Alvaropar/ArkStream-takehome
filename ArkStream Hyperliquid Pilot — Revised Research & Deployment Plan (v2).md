# ArkStream Hyperliquid Pilot — Revised Research & Deployment Plan (v2)

Nov 18, 2026 · @alvaro

## Summary

The deliverable stays a committed decision as of the research cutoff (provisionally 4 Jan 2026): named addresses, weights and limits. The decision is reached through three separate gates: research validity, economic feasibility and operational readiness. Follower results are correct on timing: the follower acts only on information it had received. Execution cost is an explicit, labelled scenario, because the package holds trades, not quotes. Any live launch after the cutoff requires re-qualifying the leaders on current data.

Changes from v1, including corrections from the 18 Nov review:

| Area | v1 | Now |
| --- | --- | --- |
| Timing | Latency was a lag from the leader's fill time | Fills arrive as events with a receipt delay; the follower acts only after receipt |
| Prices | A panel built from the package's trade prints | Reference coin prices supplied by us drive all daily valuation; package prints are a fallback and a cross-check |
| Execution cost | One base cost model | Shortfall split into drift during the delay (measured from prices), spread and impact (scenarios labelled as assumptions) |
| Spread proxy | (v2) maker vs taker price gap | Dropped. 195 trades seen from both sides each carry one price, so the gap measures noise, not spread. |
| Funding | (v2) bounded by the equity-vs-fill residual | The residual is an unexplained reconciliation difference. Funding comes from per-coin rates × rebuilt positions if allowed, otherwise pre-funding results plus a cost range. |
| Performance metric | Daily returns only | Two levels: round trips (flat to flat in a coin) measure skill and copyability; daily valuation measures risk, correlation and portfolio effects |
| Returns | Flows assumed at the start of each day | Both flow conventions computed; days where they disagree materially are excluded |
| Validation | (v2) walk-forward from September, no final holdout | Point-in-time from 8 Oct 2025; four development windows to 3 Dec, then an untouched holdout from 3 Dec to the cutoff |
| Leakage rule | Implicit | Methods are designed once; every value feeding selection is computed as of each test date |
| Statistics | Deflated Sharpe, false-discovery control and shrinkage as main tools | Robust measures, baselines and honest uncertainty lead; false-discovery control, deflated Sharpe and PBO are secondary diagnostics |
| Screens | None | Copier and duplicate screen, minimum round trips, account-size band, holding-time band, tail-risk gates |
| Diversification | (v2) spread picks across style clusters | Quality first; a leader is added only if its correlation and position overlap with the chosen set stay below thresholds set on development data. A single-coin leader is welcome. |
| Breadth | (v2) 4 to 7, capped by the 10-user WebSocket limit | Set by statistics and the risk budget. The WebSocket cap is infrastructure, solved with a node feed or polling. The $10 minimum rarely binds: a leader's median order is 15% of their equity. |
| Equity guard | (v2) a floor that still allowed up to 1/(1−δ) scale-up | Reference equity frozen between reviews, so our exposure moves only when the leader's positions move |
| Decision | (v2) one threshold table | Three gates; feasible but underpowered evidence leads to a shadow pilot, not a NO-GO |
| First milestone | The full pipeline | A data contract and accounting-reconstruction report |
| Spread level | (v2) a placeholder per scenario | (19 Nov) Also estimated from the package's own prints (Corwin–Schultz on minute bars), as a labelled estimate whose bias direction is checked by simulation, not assumed |
| Gate evidence | (v2) direction, size and consistency | (19 Nov) Plus exact Clopper–Pearson intervals on "beat random-k in k of n windows" and a minimum track record length that sets the shadow stage's length |
| Look-ahead tests | (v2) invariance tests | (19 Nov) Plus seeded leak tests: each plants a known leak and checks that the invariance test catches it |
| Holdout freeze | (v2) by discipline | (19 Nov) A hash of the frozen config and rules, committed and shared before the holdout is read; the holdout run refuses to start if it changed |

## Decision context and assumption register

All assumptions live in a versioned `decision_context.yaml` and are frozen before any outcome is examined. The cutoff in particular is never moved after results are seen.

| ID | Assumption or gap | Treatment |
| --- | --- | --- |
| A01 | No cutoff note in the package. The last fill is at 2026-01-04 23:59:42.020 UTC, the last snapshot at 23:59:31.671. | Provisional cutoff 2026-01-04 23:59:59 UTC, pending confirmation. The pipeline takes CUTOFF as an argument. (19 Nov, ADR-A0007) While unanswered: CUTOFF = the last fill, 2026-01-04 23:59:42.020 UTC; no row or headline count changes. Answered (ADR-0021): the actual end of the data, so the last fill. |
| A02 | Timestamps are event times, not the moment a follower could have known | Replay adds a receipt delay: fills become usable at event time + d, snapshots at their own timestamp |
| A03 | Timestamps mix formats and precision | Parse with mixed formats and force UTC; a test asserts no rows fail to parse |
| A04 | equity is the cross-margin account value, not total account NAV | Never called NAV. Addresses where pnl ≠ equity − net\_deposit are flagged and reconciled, or excluded. (19 Nov, ADR-A0007) While unanswered: equity is taken as the account's total value (it equals `cross_margin_summary_account_value` on all 129,665 snapshots), so account returns are whole-account returns; the pnl identity check is kept. Answered (ADR-0021): equity is the cross-margin account equity, so the original wording stands; account returns are cross-margin returns, and the rebuilt book is used where the pnl identity fails. |
| A05 | The timing of flows within a day is unknown | Compute both start- and end-of-day conventions and exclude days where they differ materially |
| A06 | Positions opened before 2025-07-27 are left-censored | Start from the first observed start\_position, and record exposure before that as unknown, not zero |
| A07 | No quotes, order book, mark prices or funding ledger in the package | Reference coin prices we supply value all positions daily (A13). Spread and impact are labelled scenarios. Funding uses per-coin rates if allowed, otherwise pre-funding results plus a cost range. Nothing is filled in. (19 Nov, ADR-A0007) While unanswered: public market data may be used (Binance archive, Hyperliquid public API), recorded with source, retrieval date and checksums. Answered (ADR-0021): allowed, including funding history and L2 order books. |
| A08 | Markets differ (core perps, spot, HIP-3) and change over time | A point-in-time instrument master; spot and HIP-3 are ineligible unless authorized. (19 Nov, ADR-A0007) While unanswered: perpetuals only; core perps in scope, HIP-3 perps (0.4% of notional, no Binance reference) stay excluded and disclosed. Answered (ADR-0021): perps mainly, HIP-3 perps may be included, spot not for now; HIP-3 inclusion pending a data check. |
| A09 | The sample is part of a larger pool that changes over time | Addresses that dropped out stay in the validation universe; the cohort is versioned |
| A10 | The pilot has no approved risk policy | All limits are proposals, calibrated from data and signed off before trading |
| A11 | Documentation read in November 2026 describes today's venue | Venue facts are pinned with their date; no assumption that a feature existed in January 2026 |
| A12 | The decision is historical, as of the cutoff, while this plan is dated November 2026 | A GO at the cutoff does not authorize a launch today. That needs leaders re-qualified on current data, live shadow results and fresh approvals. |
| A13 | Reference coin prices come from outside the package | Record the source, resolution and coverage; filter to the cutoff; store checksums and the retrieval date; validate against the package's own trade prints. (19 Nov) Source: Binance USD-M 1m klines, known at the bar close, times each coin's price factor, only inside its validity window (`hl_binance_map.csv`) and only bars with volume > 0; read only through `data/reference/prices/MANIFEST.yaml`. A price answers (coin, t) only if known within 60 s; otherwise the package's own print within 60 s; otherwise unpriced and logged. Drift: Binance aggTrades zips for BTC, ETH, HYPE and SOL, estimated at each test date (8 Oct, 22 Oct, 5 Nov, 19 Nov; 3 Dec for the holdout) only from orders whose delay ends before it, over an expanding history from 8 Sep (aggTrades fetched from then so 8 Oct has an estimate), without 10-11 Oct, which is reported separately for the stress scenario at test dates after it; pooled by coin and holding-time band, not per leader. Other coins: the leader's fill price to the reference price at 5 minutes or more, plus the coin's trailing 7-day median Hyperliquid/Binance basis times the order's side (basis above 100 bps: unmeasured), labelled approximate. On BTC, ETH, HYPE and SOL (8-21 Oct, 5 minutes) the approximation correlates 0.90-0.93 with trade-level drift and reads 0.2-1.4 bps low; 1m klines never under 5 minutes. Holdout prices only compute the frozen follower's holdout results. |
| A14 | External data policy | Allowed: verifiable market data (prices, funding rates, order-book snapshots). Cross-check only, unless allowed: extra data on the same addresses. Never: identity, labels, leaderboards or commentary. A package-only result is kept beside the external-data result. |
| A15 | Leakage | Methods are designed once on the whole dataset only where they are data hygiene (parsing, keys, instrument map, grade definitions). Every value that feeds selection is computed from data up to the test date. |
| A16 | Venue lead-lag between Binance and Hyperliquid | (19 Nov) On 8-21 Oct 2025, Binance leads Hyperliquid by about 1-1.5 s for BTC, ETH and SOL; Hyperliquid leads by about 0.25 s for HYPE. Drift is measured on Binance from the leader's Hyperliquid fill time, so the 1 s optimistic delay sits inside the lead-lag band: it is read as a bound at venue-lag precision, not a measured 1 s cost. Re-estimated if the shortlist trades other coins. |

Questions for the recruiter: the exact cutoff; whether equity is meant to be total account value; whether public Hyperliquid market data (per-coin funding history, the L2 book archive) may be used; and whether spot and HIP-3 markets are in scope.

## Milestone 1: data contract and accounting reconstruction

No address can be ranked until this report says which addresses have trustworthy returns and rebuildable positions. It is the dependency for every later step.

1. **Ingest and hash.** Store a checksum of the raw zip. Load into Parquet partitioned by date. Parse mixed timestamp formats to UTC.
2. **Reference prices.** Load the supplied coin prices. Record source, resolution and coverage, and filter to the cutoff. Validate them against the package's trade prints: flag any coin and time where the two disagree beyond a tolerance, and any coin the shortlist might trade that has no price coverage.
3. **Keys and deduplication.** tid alone is not a key: 785 rows have tid = 0, and 551 (trader, tid) pairs repeat, all Spot Dust Conversion. Use (trader, tid, oid, timestamp, symbol, dir) and keep dust conversions as non-trade events, not deleted rows.
4. **Instrument classification.** Core perps; spot (`@n` plus PURR/USDC: 34,707 rows); HIP-3 (`dex:symbol`: 1.2% of perp fills). Only core perps are eligible.
5. **Position continuity.** Group fills by trader, symbol and millisecond. Order single-sided groups by signed start\_position. Resolve groups that mix buys and sells by a feasible chain: for example, 0xa0d0… on ETH at 2025-10-15 15:39:40.221 UTC bought 2.1 and 0.4372, then sold 2.5372, all in one millisecond.
   - With that rule there are no breaks across 864,623 perp fills.
   - Continuity shows the observed sequence is internally consistent. It cannot detect a missed round trip that opens and closes between observed fills, activity before 27 Jul, or position changes not caused by fills.
6. **Accounting reconciliation per address.**
   - pnl against equity − net\_deposit: 10,696 rows across 410 addresses differ by more than 0.01 USDC (408 addresses at 1 USDC). Beyond 1 USDC, pnl is always the larger, which suggests positions outside cross margin. Example: 0x0146… reconciles exactly in July (35,588 = 10,000 + 25,588) and diverges by 1 August.
   - closed\_pnl sums against realized PnL rebuilt from fills.
   - Equity-based against fill-based PnL, valued at reference prices. The difference is an unexplained reconciliation difference; it mixes funding, pricing and scope, and bounds none of them.
7. **Copier and duplicate screen.** For each pair of addresses, count orders in the same coin and direction placed within 30 seconds after the other's. A first pass over 16,184 pairs flags one cluster: 0xd9ea… and 0xa112… match almost every order of 0x890e…, and 0x8f30… about a third. To confirm a pair:
   - a placebo test with randomly shifted timestamps, giving the chance rate;
   - a consistent ratio between the two addresses' order sizes;
   - the distribution of time lags between paired orders.

   Copier or one operator, a confirmed cluster is one bet: keep at most one member, preferably the original.
8. **Coverage flags.** Snapshot gaps (1,815 longer than 1.5 days); the outage from 11-23 to 11-27 (309 addresses); stale equity (38,679 rows); zero equity (2,539 rows); addresses with no fills (300); pool joins and dropouts.
9. **Output.** A quality table with one row per address and one column per flag, plus pointers to the raw rows behind each flag, and a grade for each address (below). All of it is computed as of each test date.

| Grade | Meaning | Proposed criteria (thresholds fixed on development data) |
| --- | --- | --- |
| A | Trustworthy as is | At least 95% of days present; pnl = equity − net\_deposit within 0.01 USDC on at least 99% of rows; fills present and continuity holds; no zero-equity days while holding positions |
| B | Usable with a stated fix | A scope mismatch with a stable offset (use the rebuilt book, valued at reference prices); snapshot gaps (use multi-day returns); heavy flow days leaving at most 20% of days excluded |
| C | Excluded, with the reason | No fills; a scope mismatch the rebuilt book cannot explain; more than 20% of days unusable; equity near zero most of the time |

## Leader evidence

Every address graded A or B is measured at two levels. Round trips measure skill and copyability; daily valuation measures risk and how the address fits a portfolio. Tail risk is checked separately, because a bootstrap cannot reveal losses that are not in the sample.

**Daily level: the account and its book.**

- *Account returns* are flow-adjusted from the snapshots. Treating each day's flow as arriving at the start or the end of the day brackets the true return:

```latex
r^{start}_t = \frac{E_t - E_{t-1} - \Delta ND_t}{E_{t-1} + \Delta ND_t}, \qquad r^{end}_t = \frac{E_t - E_{t-1} - \Delta ND_t}{E_{t-1}}
```

- The start convention is the base case; the end convention is a sensitivity. A day is excluded when the two differ by more than a set threshold, or when opening equity is below 500 USDC. A gap gives one return over the whole gap; nothing is interpolated.
- *Book returns*: positions rebuilt from fills and valued every day at the reference coin prices, and every hour where the price resolution allows. This is the series for drawdown, correlation and portfolio weights. It is cross-checked against account returns.
- Coverage (the share of days used) is reported beside every statistic. Nothing is annualized without a confidence interval.

**Trade level: round trips.** A round trip runs from flat to flat in one coin, read from each fill's position before the fill. That avoids ambiguous matching of individual orders when leaders scale in and exit in pieces. For each round trip, as the follower would have traded it:

- return after costs, with the follower's delayed entry and exit;
- return per day held, so a 10-minute trade and a 10-day trade are comparable;
- the worst unrealized loss during the hold (maximum adverse excursion) and the best unrealized gain;
- win rate and the size of wins against losses, and the average result with the largest 1% of trades removed;
- any position still open at the test date, counted as an open trade valued at the reference price. Leaving it out would reward traders who close winners and keep losers open.

**How much evidence an address has.** Among 572 active addresses (at least 30 orders and one completed round trip), the median has 32 completed round trips, and 40% have fewer than 20. For addresses whose typical hold exceeds a day, the median is 16. Their daily returns mostly re-measure the same few positions, so the round-trip count is the measure of evidence. A minimum of 20 to 30 round trips is set on development data; about half the active addresses fail 30.

**Tail-risk gates.** These are gates, not score adjustments. A tail event already in the sample is evidence of instability, not an outlier to trim.

- Intraday drawdown from hourly valuation of the rebuilt book, which daily snapshots hide.
- Worst day, worst 3-day stretch and maximum drawdown.
- A stress shock: the largest observed move in each coin (for example 10 Oct 2025) applied to the address's typical and peak exposure, giving an implied loss as a share of equity.
- The 95th percentile of leverage, and how close positions came to liquidation.
- Liquidations and auto-deleveraging. A forced exit is a different signal from a chosen loss, but both are reviewed.
- Dependence on a few trades: PnL with the top 1% of round trips removed.

**Holding time and frequency.** Most of the pool is not high-frequency. Median holding time per address, among the 572 active:

| Median hold | Addresses |
| --- | --- |
| Under 1 minute | 10 |
| 1 to 15 minutes | 26 |
| 15 minutes to 1 hour | 43 |
| 1 to 6 hours | 117 |
| 6 to 24 hours | 133 |
| 1 to 7 days | 160 |
| Over 7 days | 83 |

The median address places 1.75 orders a day. The bigger copyability problem is the 92 addresses with more than 70% maker fills: they earn the spread and rebates that a taker follower would pay. The break-even study in the replay section sets the copyable holding-time band.

**Account size.** Size is a filter, not a style variable. Because we copy proportionally, the leader's size does not have to match ours. It matters because large accounts move prices before we follow and pay lower fees, while very small accounts often run extreme leverage.

| Median equity band | All 1,500 addresses | Of the 572 active |
| --- | --- | --- |
| 50k to 500k | 237 | 111 |
| 30k to 1M | 355 | 175 |
| 20k to 2M | 460 | 223 |

The starting band is 20k to 2M, tuned on development data and computed as of each test date. Two checks go with it: each leader's typical order size against that coin's traded volume (impact risk), and their actual fee rate from the fee column. A leader whose edge depends on a fee discount we will not have is caught directly.

## Follower replay

Copy returns come from an event-sourced replay that is correct on timing: the follower acts only on what it had received. Whether each simulated fill could actually have happened is a separate question. It is answered with labelled scenarios, because the package holds trades, not quotes. No result is described as executable without naming its scenario.

**Event model.** Each leader fill becomes visible at event time + d\_receive. The engine decides after a debounce d\_decide. The order is acknowledged after d\_ack. Nothing is priced at or before its visibility time.

**Execution shortfall, in three parts.**

```latex
\text{shortfall} = \underbrace{\text{drift during the delay}}_{\text{measured from trade prints}} + \underbrace{\text{spread paid}}_{\text{scenario}} + \underbrace{\text{market impact}}_{\text{scenario}}
```

- **Drift** is measured from the reference prices between the leader's fill and our order time. Where the price resolution is coarser than the delay, the package's trade prints, pooled across all 1,200 addresses, fill the gap. With no print inside a tolerance window, the order is logged as unpriced and no fill is assumed.
- **Spread and impact** are scenarios. The v2 proxy (maker vs taker price gaps) is dropped. In the sample, 195 trades appear from both sides, one maker and one taker, and each carries a single price. Across unrelated BTC trades in the same minute, the taker-minus-maker gap averages 0.2 bps with a standard deviation of 17 bps: that is noise, not spread.
- **Spread estimate from the package's prints (Corwin–Schultz).** Build one-minute high/low bars per coin from the pooled prints of all 1,200 addresses, and apply the two-bar Corwin–Schultz estimator (the five-line expression in `qh_compute.spreads.corwin_schultz`, copied rather than imported). Also apply Abdi–Ranaldo, from the same source, and report the gap between the two.
  - **Bar rules.** A bar is used only if both minutes have at least a minimum number of prints, set on development data. Negative pair estimates are set to zero. A coin that is too thin gets no estimate and keeps the scenario value. Nothing is filled in.
  - **Calibration.** Fit on the development period only, one frozen value per coin. Never fit on the holdout.
  - **Bias check before use.** Simulate a random-walk mid with a known spread, sampled at each coin's observed print rate, and confirm the direction of the bias.
    - Sparse prints can miss one side of the book, which biases the estimate down.
    - Setting negative pairs to zero, and price ticks on thin coins, bias it up.
    - The estimate is called a **floor** only for coins where the simulation shows a downward bias.
  - **How it is used.** Where the estimate exceeds the base half-spread, the base scenario is wrong and is raised. If a holding-time band fails at the estimate, the break-even result gets stronger. Market impact is still a pure assumption.

What each level of market data can support:

| Data available | What can be estimated |
| --- | --- |
| Historical L2 book and trades | Spread, marketable execution price, depth, approximate impact |
| Historical mid or mark prices and trades | Drift during the delay; spread and impact still need assumptions |
| Only the supplied fills (this package) | Approximate transaction-price movement; a print-based spread estimate (Corwin–Schultz, bias checked); not executable quotes |

With the reference prices, the submission sits at the second level: drift is measured, while spread and impact remain assumptions. If allowed, add L2 snapshots from Hyperliquid's archive for the few symbols the shortlist trades most, after checking their coverage.

| Scenario | Delay (receive + decide + ack) | Fee | Half-spread, BTC/ETH vs others (assumed) | Impact |
| --- | --- | --- | --- | --- |
| Optimistic | 1 s (about the measured 10th percentile) | 4.5 bps taker | 0.5 / 2 bps | None |
| Base | 1.2 s, the measured median (was 10 s, assumed) | 4.5 bps | 1 / 5 bps | Linear in order size relative to the symbol's traded volume (assumed) |
| Stress | 5 s for every symbol, the measured 99th percentile rounded up (was 60 s; 5 min for thin symbols) | 4.5 bps; 9 bps on HIP-3 if ever enabled | 3 / 15 bps | 3× base |
| Severe (sensitivity) | 60 s; 5 min for thin symbols (the old stress delays, for disconnects the measurement does not capture) | as stress | 3 / 15 bps | 3× base |

(21 Nov, ADR-0058) The delays come from measurement (ADR-0038, ADR-0056: Hyperliquid receive + debounce + compute + a Binance Demo acknowledgement, about 1.1-1.2 s at the median and 3.5-4.4 s at the 99th percentile) and were chosen before Phase 4. The break-even delay grid is 1, 1.2, 5, 10, 60 and 300 s (ADR-0059).

(21 Nov, ADR-0061, ADR-0062; decided after seeing results, fixed before running) In base, the drift of a coin without trade-level reference prices below 300 s is bounded from below by a point-in-time estimate from leaders' own split orders on Hyperliquid at the same elapsed time, and never favourable; without enough of that evidence it keeps the coin's own 5-minute drift as the bound (ADR-0048). d\_receive is the measured median, 392 ms.

The spread and impact values are placeholders, to be calibrated on L2 data if allowed and labelled as assumptions either way. The zero-delay, zero-cost case is shown as an upper bound and labelled unattainable.

**Funding.** It is not in the package. If allowed, multiply hourly per-coin funding rates by the rebuilt positions to get funding directly. Otherwise, report results before funding plus a grid of constant funding costs on gross exposure, labelled as assumptions. The equity-vs-fill residual is reported as an unexplained reconciliation difference, not as a funding estimate.

**Delay break-even study (the first economic screen).** For each address, find the delay and cost at which copy return falls to zero. Stratify by holding-time band (the table under Leader evidence). For each band, compare the average gross result per round trip with the cost per round trip: about 2 × (fee + half-spread), or 11 to 20 bps under the base scenario. Bands where cost absorbs most of the edge fall outside the copyable band. Addresses whose break-even falls inside the base scenario are not copyable, however good their own record. If almost none survive the base scenario, economic feasibility fails before any ranking happens.

**Output per address:** copy efficiency (copy return divided by leader return) under each scenario, before and after funding; break-even delay; share of orders below $10; share of orders unpriced.

## Selection and point-in-time validation

Selection is a point-in-time procedure in four steps: gates, ranking within peer groups, a diversification check, and validation against random picks. Its statistics are scaled to the evidence: a five-month history supports robust measures, fair baselines and honest uncertainty, not elaborate inference.

**Splits.** At every test date t, the whole procedure runs on data up to t only:

1. Form the candidate universe from data available by t.
2. Compute grades, flags, copier links, clusters and correlations from records up to t.
3. Estimate metrics and rankings on the training window only.
4. Select leaders and set weights.
5. Freeze that portfolio through the next window and measure its follower PnL after scenario costs.

| Set | Dates | Use |
| --- | --- | --- |
| Development | Test dates 8 Oct, 22 Oct, 5 Nov and 19 Nov 2025; four 14-day windows ending 3 Dec | All rules and thresholds are tuned here |
| Holdout | Select on 3 Dec with frozen rules; measure 3 Dec to 4 Jan (32 days) | Touched once, never tuned on; guarded by the freeze hash below |
| True out of sample | Data after the cutoff (if reviewers hold it), then the shadow pilot | The real test |

The first test date is 8 Oct because it is the first date any address has 90 snapshot days. Eligible counts by that rule grow from 312 addresses on 8 Oct to 472 on 1 Nov and 671 at the cutoff. A 32-day holdout is weak evidence on its own, but it is clean. A short-history rule for earlier dates would test a different policy, so it appears only as a labelled side analysis.

**Gates, recomputed at every test date.**

- Data grade A or B.
- At least 90 snapshot days and 60 usable return days.
- At least 20 to 30 completed round trips (threshold set on development data).
- Median equity in the 20k to 2M band.
- At least 90% of traded notional in eligible core perps.
- Holding time inside the copyable band from the break-even study, and break-even delay above the base delay.
- Not a maker-heavy or high-frequency account.
- Passes every tail-risk gate.
- Not the weaker member of a confirmed copier or duplicate cluster.

**Ranking.**

- The statistic is each address's mean return per round trip after follower costs, over its training window.
- Its uncertainty comes from a block bootstrap: resample the address's round trips in calendar-week blocks, keeping trades that overlap in time together, 2,000 times, and recompute the mean each time.
- The ranking key is a low percentile of those 2,000 means: the lower bound of a one-sided interval. The confidence level is set on development data; 80% (the 20th percentile) is the starting proposal. A short or erratic record has a wide spread and a low bound, so it cannot rank high by luck.
- Addresses are ranked within behavior clusters, so like is compared with like.

**Clusters: what they are for, and how they are built.** Clusters serve two purposes: comparing like with like, and finding duplicates. They are not a quota to fill.

| Analysis | Variables | Method |
| --- | --- | --- |
| Behavior | Timing: median and spread of holding time, orders per day. Sizing: order size relative to equity, median and 95th-percentile gross leverage. Market: share of time net long, concentration across coins, share in BTC and ETH, correlation with BTC. Execution: maker share, fills per order. Behavior: turnover relative to equity, how often it adds to losing positions. | Hierarchical clustering (Ward) on standardized features. Outcome measures such as win rate are left out, so style is not just past performance. |
| Co-movement | Correlation of daily book returns; position overlap (cosine similarity of signed exposures by coin) | Hierarchical clustering on correlation distance; feeds the diversification check and the duplicate screen |

Supervised tree models (random forests, gradient boosting) predicting future copy returns are exploratory only. Four development windows across a few hundred addresses is too little, too noisy and too overlapping to trust a fitted model.

**Diversification check.** Quality comes first. Walk down the ranking and add an address only if its daily copy-return correlation and its position overlap with the leaders already chosen stay below thresholds. Those thresholds are set once development results exist; there are no values yet. A stable single-coin leader is welcome. The number of leaders comes from this check and the risk budget, not from infrastructure.

**Statistical priorities.**

| Method | Role |
| --- | --- |
| Point-in-time rolling selection | Essential |
| Conservative return and downside-risk measures | Essential |
| Fee, delay and funding sensitivity | Essential |
| Matched random-k and equal-weight benchmarks | Essential |
| Cross-leader correlation and position overlap | Essential |
| Block bootstrap uncertainty | Useful, with caveats about time dependence |
| Empirical-Bayes shrinkage within style clusters | Extension |
| False-discovery estimate of the skilled share | Exploratory only; never sets portfolio size |
| Deflated Sharpe and PBO | Secondary diagnostics; too few windows for a precise PBO |
| Hierarchical Bayesian skill model; supervised tree models | Future research |

**Selection bias is a premise, not a measured number.** 78.8% of the 741 addresses with a full history were profitable. That suggests a pre-selected pool, but there is no like-for-like base rate: the published platform-wide figure of about 14% covers a different population and period, so it serves only as illustration. The 290 addresses dropped on 21–22 Nov did not underperform: 86% of the 22 with enough history were profitable, against 77% of survivors. The method guards against selection bias by design: point-in-time gates, conservative ranking and random-k baselines.

**Research discipline.** Every rule and threshold is frozen on the development windows before the holdout is opened. Every variant tried is logged in `provenance/trial_log`.

**Freeze hash before the holdout (about 10 lines plus a test).** Before the holdout is read, `provenance/HOLDOUT_FREEZE.txt` records SHA-256 hashes of four things:
- `decision_context.yaml`;
- the other config files;
- the selection and replay source code (the rules live in code as well as in config);
- the development-window shortlist.

The freeze is committed, and the hash is sent to the reviewers before the holdout run. A hash alone proves the holdout used the frozen rules. Only a commit or message dated before the run proves the order of events. Any returns, replay or selection call with `asof` after 3 Dec refuses to run unless the current hashes match the freeze. Moving the cutoff changes `decision_context.yaml`, so it trips this check too.

Disclosed in the trial log: the Milestone 1 data-quality tables were computed over the full period, holdout included. They contain no returns. Grade thresholds are tuned on the 19 Nov build, never the cutoff build.

## Sizing and portfolio construction

The pilot is sized by what it must measure, not by comfort alone. The plan takes its number of leaders from the diversification check and the risk budget, starts with 30,000 USDC deployed, and always keeps at least 20,000 USDC as an unallocated reserve.

**How many leaders.** The number comes from the selection's diversification check and the risk budget. Infrastructure doesn't limit it. Hyperliquid caps user-specific WebSocket subscriptions at 10 unique users per connection setup ([rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)). The ways past that cap:

- run our own non-validating node, which streams every fill with no per-user cap; this is also the scaling path to a larger pool;
- poll each leader's position state over the REST API within the request-weight budget;
- spread subscriptions across several connections, after checking the terms of service.

The minimum order does not bind either: with 5,000 USDC behind a leader, 4.7% of their scaled orders would fall below $10, and 1.3% at 15,000.

**How much capital, in stages.**

| Stage | Deployed | Reserve | Purpose and exit test |
| --- | --- | --- | --- |
| 0. Shadow | 0 | 100,000 | 2 weeks of live replay with real feeds and paper fills; checks the receipt delay, reconciliation and alerts |
| 1. Pilot | 30,000 | 70,000 | At least 4 weeks; enough orders to estimate slippage and tracking error against the base scenario |
| 2. Scale | 60,000 | 40,000 | After the stage 1 gates pass and are signed off |
| 3. Cap | 80,000 at most | 20,000 or more | The reserve is a permanent allocation, not cash waiting to be invested |

v1 proposed 40 to 60% deployed from day one. The review's 20,000 was too small to measure anything in a few weeks. 30,000 across 5 leaders gives about 6,000 each, which keeps small-order rounding near 4% of orders.

**Weights.** Run three allocation rules through the same replay and constraints: capped equal weights, inverse volatility, and cluster-aware equal risk contribution. Keep the simplest unless a more complex rule improves out-of-sample copy results. Correlation is measured two ways:

- on returns, only over dates both addresses report, with a minimum overlap and shrinkage;
- on position overlap: cosine similarity of signed symbol exposures, because two leaders long the same coin are one bet.

**Target and projection.** The desired notional in symbol a sums each leader's weight w\_i, signed position s\_{i,a} and price P\_a over a reference equity that is frozen between reviewed rebalances. It is then projected onto the constraint set K:

```latex
T_a(t) = C \sum_i w_i \, \frac{s_{i,a}(t)\, P_a(t)}{E_i^{ref}}, \qquad T^{feas} = \Pi_K(T)
```

- E\_i^ref is the leader's validated equity at the last reviewed rebalance. It changes only at the next review.
- With positions and prices fixed, a change in the leader's equity cannot change our exposure. Only the leader's own trades can. A dedicated unit test enforces this invariant.
- Why not the v2 floor? Under max(E, (1−δ)E\_ref), our exposure still rises as the leader's equity falls: by 1.11× at a 10% drop and up to 1.25× when δ = 20%.
- A running high-water mark would also prevent scale-up, but it shrinks our copy of a winning leader and so changes tracking. The frozen reference is simpler.
- If the leader's equity falls below (1−δ)·E\_ref, the pause rule fires.

| Limit | Starting value | Basis |
| --- | --- | --- |
| Per leader | 25% of deployed capital | Single-leader concentration |
| Gross exposure | 1.5× deployed capital | Below the leaders' median peak of about 2.85× equity |
| Net per symbol | BTC and ETH: 25% of account equity; others: 10% per leader holding the coin, at most 20% in total, so a single-coin leader is not starved | Crowding and liquidity |
| Eligible markets | Core perps with enough internal prints | Data quality and cost |
| Account drawdown | −5%: halve new risk. −10%: reduce-only. −15%: flatten and review. | Loss budget |
| Leader pause | Drawdown beyond 1.5× their own history; leverage above their 95th percentile × 2; withdrawal above 50% of equity; equity below (1−δ)·E\_ref; liquidation; data stale | Out-of-character behavior |

## Live operating model

The live system keeps a virtual book per leader, nets all of them into one feasible target per symbol, and trades only the drift between that target and what we actually hold. When it is unsure, it stops adding risk.

&#91;embedded content: live event loop · one decision, one feedback path, one safe state\]

Every cycle measures drift against actual exchange holdings, so a partial fill feeds back as a smaller remainder, never a resent order. Stale data, a breach or persistent drift sends the account to reduce-only.

**The loop.**

1. **Subscribe and archive.** Leader fills through WebSocket or our own node feed; gaps backfilled through the API and checked against the leader's position state. Each event stores its raw payload plus event\_time, received\_at and processed\_at, a hash, and the config version.
2. **Normalize.** Map instruments through the point-in-time master. Deduplicate on the composite key. A watermark handles out-of-order arrivals.
3. **Update the virtual leader book.** A stale or inconsistent leader state freezes increases for that leader and triggers a resync from clearinghouseState. A leader's withdrawal never triggers a top-up from us.
4. **Net and project.** Compute T, scale by the frozen reference equity, apply the constraint set, and keep each leader's virtual attribution even when physical positions cancel.
5. **Decide.** Act after a 2 to 5 second debounce, plus a sweep every 15 minutes. Trade only if |target − actual − open orders| exceeds max($10, 2% of target).
6. **Execute.** Bounded-price IOC or limit orders with a deterministic client order id, within the slippage cap. After a partial fill, rejection or timeout, recompute the remaining order from actual state; never resend the original size.
7. **Reconcile.** Exchange state is authoritative. Drift beyond tolerance for 3 cycles freezes that symbol and alerts. Log tracking error against the paper target daily.
8. **Cut risk.** Fail closed on a data outage, a margin or exposure breach, slippage beyond the cap, unverified positions, excessive latency or a venue incident. Reduce-only and flatten are separate actions.

**Answers to the brief's six questions.**

| Question | Answer |
| --- | --- |
| How new data updates decisions | Fills update targets at once (step 3). Snapshots update risk metrics and pause rules daily. Weights change only at the weekly review or when a hard rule fires. |
| When orders are generated | Steps 5 and 6: debounce plus sweep, deadband, and the minimum order |
| Several sources on one contract | Step 4: sum the signed targets, project, and cut contributions pro rata when caps bind |
| Fills that differ from target | Steps 6 and 7: recompute the remainder, freeze on persistent drift, escalate |
| When to add capital and when to cut risk | Stage gates in the sizing section; the drawdown ladder and pause rules; reduce-only on stale data |
| When a human steps in | Unreconciled accounting; any auto-deleveraging or liquidation investigation; changes to selection or weights; an outsized loss; repeated feed gaps; venue changes; manual overrides; key incidents; resuming after a hard stop; every capital increase |

**Reviewed periodically:** weights and the shortlist (weekly); limits and the drawdown ladder (monthly); the spread and impact scenarios against live fills; the delay budget; the deadband; the instrument master; data-quality thresholds.

## Decision gates

The decision separates three questions. That way a lack of statistical power cannot force a NO-GO, and a good score can never override an unresolved safety problem. Values are frozen in `decision_context.yaml` before the last test windows are examined.

| Gate | Question | Evidence | Passes when |
| --- | --- | --- | --- |
| Research validity | Is the selection process supported by credible, point-in-time evidence? | Data grades, the point-in-time walk-forward, random-k and equal-weight baselines, uncertainty bands | Shortlisted addresses are grade A or B, and the selected basket beats matched random-k in most development windows and in the holdout, without trailing equal-weight |
| Economic feasibility | Is following likely to stay profitable after realistic costs? | Break-even study, cost scenarios, funding, turnover, the 10 Oct stress | Expected copy return is positive under the base scenario across the funding range, and the stress loss stays within the −10% step of the drawdown ladder |
| Operational readiness | Can the system trade safely? | Fault tests, reconciliation, margin controls, monitoring | Every fault test passes, replays are deterministic, and limits are signed off |

No test of statistical significance is required. With 5 test windows (four development windows plus the holdout), a confidence interval that must exclude zero would reject real skill for lack of data. Instead, the memo reports the direction, size and consistency of the result against the baselines, with uncertainty bands, and lets the outcome table weigh it.

**Exact intervals on the gate outcomes.** These are reported, not used as pass/fail tests.
- **Clopper–Pearson on "beat random-k in k of n windows."**
  - A window counts as a win when the basket's follower return is above the median of the matched random-k draws, so a basket with no skill wins with probability exactly 0.5.
  - For 4 of 5 windows, the two-sided 95% interval is 0.28–0.99.
  - Even 5 of 5 gives a lower bound of 0.48 (0.55 one-sided), which cannot exclude 0.5. With five windows, research validity can show at most "positive but underpowered". That is why the CONDITIONAL GO row exists.
  - The windows are neither independent nor equal: the development windows were used for tuning. The interval is therefore optimistic.
  - The basket's percentile within the random-k distribution is reported for each window next to the count.
- **Minimum track record length (Bailey and López de Prado, 2012) on the basket's daily follower returns after costs.**
  - It turns "stated evidence targets before any scaling" into a number of shadow days.
  - The selected basket's in-sample Sharpe is inflated by selection, so MinTRL is computed on the holdout Sharpe and on half of it, and reported as a range.
  - For scale: an annualised Sharpe of 2, normal returns, SR\* = 0 and α = 0.05 need about 250 daily observations. The confidence level for the shadow target is set before the holdout.
  - If the range runs past the pilot horizon, the memo says so. The shadow-stage targets then fall back to copy efficiency and tracking error, which need fewer days.
- **Implementation.** Copy `clopper_pearson` and `min_track_record_from_moments` from `qh_validate.stats`, with their reference tests. Swap their SciPy calls for the standard library: `statistics.NormalDist` for the normal quantile, and bisection on the binomial CDF for the beta quantile at integer parameters. No new dependency.

| Research validity | Economic feasibility | Operational readiness | Outcome |
| --- | --- | --- | --- |
| Passes | Passes | Passes | **GO:** stage 1 with 30,000 USDC, then scale through the stage gates |
| Positive but underpowered | Passes | Passes | **CONDITIONAL GO:** shadow stage, then stage 1 at 15,000 USDC, with stated evidence targets before any scaling |
| Clearly fails (no better than random-k) | Any | Any | **NO-GO:** defer, naming the evidence that would reopen the case |
| Any | Fails | Any | **NO-GO:** defer |
| Any | Any | Fails | **No capital**, whatever the other gates show |

**The decision date.** The decision is made as of the research cutoff, provisionally 4 Jan 2026. It does not by itself authorize a launch at a later date. A live start requires leaders re-qualified on current data, current market data, live shadow results and fresh operational approvals.

## Fault tests and acceptance criteria

The engine passes each scenario below in replay before any capital moves. Each is a test in `tests/` with an expected end state.

| Scenario | Expected behavior |
| --- | --- |
| Two leaders reverse the same coin within seconds | One netted order after the debounce; no churn |
| Leader A is long and leader B is short the same coin | Net physical position near zero; both virtual books tracked; risk still attributed |
| A spot `@107` or HIP-3 `xyz:` fill arrives | Classified, ignored for trading, logged |
| Many partial fills in the same millisecond | One position update; buy-and-sell groups in one millisecond resolved by a feasible chain |
| Dust conversions sharing a tid | Kept as non-trade events, not deleted or traded |
| A leader holds an isolated position not in their equity | Flagged; frozen reference equity applies; no inflated scaling |
| A leader's equity collapses or they withdraw heavily | With positions fixed, our exposure is unchanged (invariant unit test); pause fires below (1−δ)·E\_ref |
| An order times out, then fills later | No double position after restart; remainder recomputed |
| WebSocket drops during a fast move | Reduce-only until resynced; stale signals discarded, never executed late |
| The rate limit is hit | Backoff; no unbounded retries; alert |
| The leader is auto-deleveraged or liquidated | Pause and human review; no automatic exclusion |
| The leader makes money but the follower loses after delay and costs | Shows in tracking-error monitoring and triggers the review |
| Correlated leaders all hit maximum risk in a shock | Per-symbol and gross caps bind; drawdown ladder steps in |

**Acceptance criteria:**

- Every as-of join is point-in-time (tested). Seeded leak tests check that the tests can catch a leak. Each one plants a known leak with a monkeypatch and checks that the point-in-time invariance test then **fails**:
  1. **Snapshot used before its timestamp:** the snapshot filter is shifted one day early. This applies from Milestone 1.
  2. **Cutoff moved by one day:** a marker row is placed 12 h after CUTOFF. It must be excluded under the real cutoff and included once the cutoff is moved one day later, which shows CUTOFF really comes from config. The freeze hash must also reject the moved config. This applies from Milestone 1.
  3. **Price at the event time instead of event time + d:** the replay is priced at the leader's fill time. Copy returns on a synthetic trend must change, and the timing test must fail. This applies from the follower replay.
- Replays are deterministic and identical after a restart.
- Retries are bounded.
- Kill switch and caps are fault-tested.
- Expected edge stays positive under the base cost and delay scenario.
- Money at risk and exceptions are signed off.
- The code never sends real orders by default.

## Deliverables and work plan

The submission opens on the decision. Two commands rebuild everything: one regenerates the research tables for a given cutoff, and one replays the portfolio's decisions from source events.

```
quant-task-arkstream/
  README.md                  what to read first, how to rerun
  decision/
    DECISION_MEMO.md         GO / CONDITIONAL GO / NO-GO, addresses, weights, reserve
    decision_context.yaml    cutoff, assumptions, thresholds (frozen, versioned)
    trader_decisions.csv     every address: grade, gates passed or failed, reason
    target_allocations.csv   selected addresses, weights, caps
    record_evidence.csv      file / address / timestamp / tid or oid / conclusion
  research/
    DATA_DICTIONARY.md  quality_report.csv  cards/<address>.html
    walkforward_report.html  breakeven_study.html  stress_2025-10-10.html
  src/                       ingest, reconstruct, prices, returns, replay, score, allocate, engine
  tests/                     point-in-time, continuity, return identities, fault scenarios
  config/                    risk.yaml, execution.yaml, instruments.yaml
  operations/                RUNBOOK.md, INCIDENT_PLAYBOOK.md, MONITORING_SPEC.md
  provenance/                input hashes, environment lock, trial log
  data/reference/            supplied coin prices, source note, checksums
```

New data rerun with a later cutoff recomputes only the affected address partitions and writes a diff of decisions, naming the rule behind each change.

**Work plan, about 7 days, ordered so the steps that can kill the thesis come first:**

1. **Day 0, contract.** Send the four questions. Freeze `decision_context.yaml`, the assumption register and the research protocol.
2. **Day 1, data contract.** Milestone 1: reference prices, keys, instruments, continuity, reconciliation, copier screen, A/B/C grades.
3. **Day 2, leader evidence.** Account and book returns at reference prices, round-trip metrics, tail-risk gates, holding-time and account-size profiles.
4. **Day 3, follower replay.** Event model, drift from trade prints, spread and impact scenarios, Corwin–Schultz spread estimate with its bias simulation, funding, break-even study, the event-time leak test. **First go/no-go screen.**
5. **Day 4, selection.** Point-in-time walk-forward from 8 Oct with gates recomputed at each origin; lower-bound ranking within style clusters; random-k and equal-weight baselines; freeze hash committed and sent; the holdout opened once, at the end; Clopper–Pearson and MinTRL in the gate table. **Second screen.**
6. **Day 5, portfolio.** Three allocation baselines on the same replay, constraints, stress run, gate table.
7. **Day 6, operations.** Engine skeleton with netting, the frozen reference equity and its invariant test, reconciliation and fault tests; runbook; evidence cards; memo.
8. **Day 7, independent check.** Clean-clone rerun; three headline numbers recomputed by hand from raw rows; a cold read of the memo.

## Interview discussion map

Each question below has a short answer from this plan and a deeper thread to open in later rounds.

| Likely question | Short answer | Deeper thread |
| --- | --- | --- |
| Why not the top-PnL addresses? | The pool looks pre-selected (79% profitable); past PnL ranks luck along with skill | Point-in-time walk-forward against random-k; lower-bound ranking |
| Why do pnl, equity and net\_deposit disagree? | Different account scopes; 410 addresses diverge by more than 0.01 USDC | 0x0146… reconciles in July, then diverges |
| How do you know the fills are complete? | Position continuity holds across 864,623 perp fills once same-millisecond groups are resolved; that is consistency, not completeness; the start date matches Hyperliquid's S3 fill archive | Why one account has 15,100 fills when the API serves at most 10,000 |
| Why not copy every fill? | A target-state engine nets internally, recovers after outages and is idempotent | Pro-rata cap cutting; virtual attribution |
| Does A long and B short cancel the risk? | Physically yes, but not the strategy risk | Virtual books; flip risk |
| How do you prevent look-ahead? | Receipt delay, frozen cutoff, point-in-time joins, a trial log | Instrument master over time; pinned venue facts |
| What if the edge is maker rebates or very fast trading? | The break-even study rejects it | Edge against cost per round trip, by holding-time band |
| How many leaders, and why? | Set by the diversification check and the risk budget. The WebSocket cap is solved with a node feed, and the $10 minimum rarely binds. | Node or indexer feed for scale |
| Why measure round trips and daily returns? | Round trips measure skill and copyability; daily valuation measures risk and portfolio fit | Open trades counted at market; worst unrealized loss; round-trip count as the measure of evidence |
| Are some addresses copying others? | One cluster found around 0x890e…; treated as one bet | Placebo timing test, size ratios, lag distribution |
| When is the right answer NO-GO? | The three gates: selection no better than random picks, no edge after costs, or unsafe operations | What evidence would reopen it |
| How would this scale to 100,000 addresses? | Partitioned storage, incremental features, an indexer instead of WebSocket | The multiple-testing penalty grows with N |

Extensions to offer:

- a hierarchical Bayesian skill model;
- Thompson-sampling capital allocation with drawdown-aware priors;
- meta-labeling individual leader trades;
- clustering leaders by style from their books;
- funding-aware PnL;
- measuring crowding from other copiers on-chain.

## Sources

Data figures come from the provided traders.csv and fills.gz, profiled on 2026-11-18. Venue facts are as of that date.

- [Hyperliquid docs: rate limits and user limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)
- [Hyperliquid docs: fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- [Hyperliquid docs: historical data](https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data)
- [Chainstack: clearinghouseState](https://docs.chainstack.com/reference/hyperliquid-info-clearinghousestate.md)
- [Chainstack: userFillsByTime limits](https://docs.chainstack.com/reference/hyperliquid-info-user-fills-by-time)
- [Chainstack: order precision and the $10 minimum](https://docs.chainstack.com/docs/hyperliquid-order-precision)
- [Dwellir: node\_fills\_by\_block coverage](https://www.dwellir.com/docs/hyperliquid/data-catalog/node-feeds/fills)
- [Bailey & López de Prado: The Deflated Sharpe Ratio](https://papers.ssrn.com/abstract=2460551)
- [Bailey et al.: The Probability of Backtest Overfitting](https://escholarship.org/uc/item/4w1110bb)
- [Barras, Scaillet & Wermers (2010)](https://archive-ouverte.unige.ch/unige:79989)
- [Andrikogiannopoulou & Papakonstantinou (2019)](https://law-journals-books.vlex.com/vid/reassessing-false-discoveries-in-855665429)
- [Zhai (2026): Public Trader Identity, arXiv 2608.04373](https://arxiv.org/abs/2608.04373)
- [BeInCrypto: Hyperliquid trader profitability](https://beincrypto.com/hyperliquid-traders-profitability)
- [hyperliquid-python-sdk](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)
- [NautilusTrader: Hyperliquid integration](https://nautilustrader.io/docs/latest/integrations/hyperliquid/)
- [Hummingbot: Hyperliquid connector](https://hummingbot.org/exchanges/hyperliquid/)
- [skfolio](https://pypi.org/project/skfolio/) · [Riskfolio-Lib](https://portfoliooptimization.org/riskfoliolib/hcportfolio.html) · [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt)
- [GoldRush: Hyperliquid fundingHistory endpoint](https://goldrush.dev/docs/api-reference/hyperliquid-info/funding-history)
