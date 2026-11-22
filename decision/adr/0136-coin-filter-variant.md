# ADR-0136: Coin filter variant (copy only coins with high training capture)

- Status: Accepted as a variant (thresholds PLACEHOLDER). Fixed before any test outcome of the rule. Scoring by
  attribution (items 1-4) superseded by ADR-0140 (the filter executed inside the replay); the coin-set definition stays
- Date: 2026-11-22
- Phase: Phase 4 (selection), item 5d

## Decision
1. **Coin set at each origin** (`selection_coins.coin_set`), from the training window, all A/B, base. Per-coin PnL
   of the follower and of the ADR-0162 benchmark is attributed from each ledger as cash + closing position x
   window-end mark + funding. A coin is kept if it is BTC, ETH, HYPE or SOL, or if its summed benchmark PnL is at
   least 500 USDC and the follower kept at least 0.5 of it. Every other coin is treated as uncopyable.
2. **Variant `rule_b_coin_filter`.** The key uses only trips in kept coins; the gates are unchanged. The test
   outcomes are the sleeves' PnL in kept coins over the allocation.
3. **Approximation, stated.** Dropped coins are removed from the existing replay ledgers rather than the replay
   being re-run without them, so the 1.5x cap, which scaled all coins together, is not re-solved.
4. **Daily series** (`selection_coins.coin_daily`). The filtered sleeves are valued day by day exactly as the replay
   values its ledger, counting only kept coins. With every coin kept it reproduces `daily_copy_twr.equity` to 4e-12
   USDC (tested). Their returns, returns without 10-11 Oct, drawdowns and stress check come from this series. The
   ADR-0122 stress measurement is the replay's own, which counts the dropped coins' intents too. Capture for the
   filtered sleeves is follower vs benchmark PnL in kept coins (the benchmark valued the same way). The ADR-0162 gap
   decomposition stays unfiltered and is not re-decomposed by coin. Added after the first evaluation pass, which
   left these fields uncomputed for this variant and printed them as failures. The returns and the choice
   criterion were not changed by it (trial log).

## Consequences
The variant counts as one of the item-6 variants (ADR-0137).
