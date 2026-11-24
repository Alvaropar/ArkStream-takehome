# ADR-0034: Cap each follower address at 1.5 times allocation

- Status: Accepted for research
- Date: 2026-11-20
- Phase: Phase 3 cost sensitivities

## Decision

Start each window flat. At each decision reconstruct the visible leader positions observed in that window across copyable coins. Use the latest valid cross-margin equity for every target. Mark each coin using its latest approved intraday reference close known at decision time (maximum age 60 seconds). Compute gross as the sum of absolute target quantities times their marks. Multiply all targets by min(1, 1.5 × fixed allocation / gross), using one for a flat target. Take the multiple from config/risk.yaml for this sensitivity only. Missing equity or a necessary mark leaves the basket measurement unavailable.

When scaling binds or is released, send the resulting resize intents for the other coins as well as the triggering signal. Keep the triggering batch's leader keys and the target coin's last visible position key. A cap-only leg has no contemporary leader fill of its own. Use its observed decision mark as a mid proxy, with zero maker/taker adjustment. Apply the existing coin's delay and spread, the direct Binance price ratio or the signed parameterised drift using the resize direction, and the variant's impact. The minute close sets the arrival level only. It never measures a sub-minute move. Label such legs separately.

Size against acknowledged holdings and outstanding quantity. Reserve exposure for pending increases without spending the proceeds of an unacknowledged reduction. Orders whose full scaled size cannot fit are deferred to later signals. Apply the minimum notional after scaling, including the acknowledgement check. Repricing can put already-held exposure above the limit without an order. Permit risk reductions and block new risk in that state. Record the decision mark, full target, scale, scaled target, requested delta, and gross including reservations so that passive breaches and refused increases can be audited. Delays, minimum-size skips and unavailable inputs can leave actual holdings short of the target.

For signals at the same decision time, process the triggering coin, source batch and order ID in ascending order. Within a signal, process its own leg first and other target coins alphabetically. Process outstanding acknowledgements by timestamp, then by submission sequence. This fixes which order can use available headroom on a tie.

## Consequences

In the order ledger, `source_rows`, `source_tids`, `source_event_ms`, `oid`, `trigger_coin` and `trigger_batch` identify the signal. `target_row` identifies the position observation for the order coin. On a resize, `side` describes the trigger fill. The sign of `quantity` is the follower order direction. `mark_ms` identifies the decision mark by coin and timestamp in the approved reference panel. `uncapped_target`, `cap_scale` and `capped_target` expose the projection. `quantity` is the capped order delta after subtracting holdings and outstanding quantities. Orders skipped after sizing retain that delta and their status.

The cap can change turnover in several coins on one signal. Use actual capped positions for funding, marks, completed trips and the delay grid. Economically identical optimistic variants share the canonical optimistic or optimistic_cap artifacts. This is a per-address research experiment on the existing 10,000 USDC allocation.
