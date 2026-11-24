# ADR-0030: Size each copy against a fixed allocation at decision time

- Status: Accepted; amended by ADR-0052 (frozen reference equity replaces the decision-time denominator) and ADR-0062 (receive 392 ms, measured)
- Date: 2026-11-20
- Phase: Phase 3

## Decision

Start every address with 10,000 USDC and a flat book at the start of each training or test window. Training begins on the first day of the fill feed. Report skipped direct-price orders before the archive starts. Test windows begin independently at the origin. Copy a held position on its first visible update. Use the latest visible chain-ordered leader position times 10,000 divided by the latest published cross-margin equity. Use that same denominator when ADR-0028 selects the rebuilt book as the leader return. Skip missing, frozen and nonpositive equity. A rebalance uses acknowledged holdings plus signed outstanding orders. Release a rejected reservation at acknowledgement. A subsequent visible signal can retry.

Allow 250 ms for receipt and 250 ms for a fixed debounce, both PLACEHOLDER. Each first unbatched fill starts a batch for its trader, coin and oid. Include fragments received through the deadline, inclusive. The remaining scenario delay is acknowledgement. Ignore acknowledgements at or beyond the exclusive window end. The unattainable benchmark copies each fill in chain order at its own time and price, without fees, minimum size or latency. Funding applies to both benchmarks.

Screen size at the visible anchor price and check the final simulated notional at acknowledgement. Skip orders strictly below 10 USDC at either check and count them. A rejection at acknowledgement releases pending quantity then. The exchange documents the perp minimum as $10 under MinTradeNtl. [Hyperliquid error responses](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/error-responses)

## Consequences

At decision time a difference below 1e-12 coin units is numerically at target. In the funded ledger a residual below 1e-10 units is numerically flat. These are arithmetic tolerances for floating-point accumulation. The economic size threshold applies in USDC. Diagnose a frozen snapshot from the exact interval under ADR-0023 using only position series visible by its closing snapshot.

The replay approximates complete taker fills. Missing execution evidence skips the order. Count unpriced attempts, minimum-size skips, missing equity and intents on the 32 excluded coins separately. Exclude zero target differences from intent counts. A missed close leaves the previous position exposed to price changes and funding.
