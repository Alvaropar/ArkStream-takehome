# ADR-0132: Behaviour clusters, co-movement, the diversification walk and the basket

- Status: Accepted (k, thresholds and K PLACEHOLDER). Pre-registered before any test outcome of the rule
- Date: 2026-11-22
- Phase: Phase 4 (selection)

## Decision
1. **Behaviour clusters.** Ward clustering, with Lance-Williams updates in numpy (`selection_stats.ward`), on
   z-scored features of every A/B address at the origin, cut at **6 clusters**. The features come from Phase 2 at
   the origin and include no outcome measure:
   - log10 median hold, and the IQR of log10 hold over closed leader trips;
   - log10 orders per day;
   - log10 median order notional / median equity;
   - median and 95th-percentile hourly gross leverage;
   - share of held hours net long;
   - coin concentration (HHI of trip peak notional) and BTC+ETH share;
   - leader beta to BTC;
   - maker share and fills per order;
   - log10 turnover per active day / median equity.
   "Adds to losing positions" is not available from the Phase 2 tables and is left out. An address with any missing
   feature is `unclustered`, its own group; no value is filled in.
2. **Ranking within clusters.** Selectable addresses (eligible, key > 0) are ranked by key within their behaviour
   cluster. The walk visits them in order of within-cluster rank, then key (descending), then address, so each
   style's best address comes before any style's second.
3. **Co-movement** among eligible addresses, from the training window:
   - Pearson correlation of daily copy TWR (base) over common days, unmeasured under 20 days;
   - position overlap, the cosine similarity of signed follower exposures by (midnight, coin) at the replay's
     daily marks.
   Co-movement clusters use average linkage on 1 - correlation, merged below 1 - 0.5 (reported; the walk uses the
   pairs).
4. **Walk.** An address joins only while its correlation **and** its overlap with every chosen address are
   **below 0.5**. An unmeasured pair does not block. The walk stops at **K = 5**. A duplicate or near-duplicate is
   the later, weaker address in the walk, and is rejected with the pair named.
5. **Basket.** k = the number the walk selects (0 is valid and reported as such), equal weights, one separate copy
   sleeve per address at the replay allocation. Its window return = mean of the sleeves' copy returns.

## Consequences
The thresholds were chosen without outcomes. On the training windows the eligible pairs that block reach 0.73-0.74
correlation, so 0.5 removes only clear co-movers. The shared account (netting, common margin) is Phase 5.
