# ADR-0021: Recruiter answers to the four Day-0 questions

- Status: Accepted
- Date: 2026-11-19
- Phase: all
- Supersedes: ADR-A0007. Amends: ADR-0007 (what the TWR measures).

## Context
The answers arrived on 2026-11-19 (original in Chinese; translation ours):

1. 数据截止时间：按照所提供数据的实际截止时间即可。 *Cutoff: use the actual end of the data provided.*
2. 账户权益定义：`equity` 指全仓账户权益。 *`equity` is the cross-margin account equity.*
3. 外部市场数据：如研究需要，可以使用公开的历史市场数据，包括 Funding History、L2 订单簿等。 *Public historical
   market data may be used where the research needs it, including funding history and L2 order books.*
4. 交易品种范围：主要针对永续合约（Perp），也可以包含 HIP-3 永续合约，暂不考虑 Spot。 *Mainly perpetuals; HIP-3
   perpetuals may also be included; spot is out of scope for now.*

## Decision
1. **Cutoff confirmed** as the end of the data: the last fill, 2026-01-04T23:59:42.020Z (already in
   `config/decision_context.yaml`). No longer provisional.
2. **equity = cross-margin account equity, not total account value.** This reverses ADR-A0007 item 3 and restores
   the plan's A04 wording: never called NAV. A snapshot-based TWR (ADR-0007) is the return of the cross-margin
   account. Transfers between the cross account and spot, isolated margin or HIP-3 can move `equity` without a
   matching change in `net_deposit`, so the pnl identity check (`pnl = equity - net_deposit`) stays the guard:
   where it fails or shows a scope offset, the rebuilt core-perp book is the return series and the snapshot TWR
   is reported only as a check (grade B reason `stable_scope_offset:use_rebuilt_book`).
3. **Public historical market data is allowed**, as ADR-A0007 assumed, now including L2 order books. Each source is
   recorded with URL, retrieval date and checksums. Hyperliquid's historical L2 data is in a requester-pays archive;
   using it needs the user's go-ahead because it costs money and needs an account. Phase 3 decides whether to
   use it for spread and impact.
4. **Scope: perpetuals; spot out.** Core perps stay in scope. **HIP-3 perps are permitted but not yet included**
   (10,308 fills, 110 addresses, $15.2M, 0.39% of perp notional; dexes xyz, vntl, hyna, flx). Including them needs
   prices and funding from the Hyperliquid info endpoint for HIP-3 coins, and a check of whether their PnL appears
   in cross-margin `equity` (HIP-3 dexes have their own margin). Until that is decided by ADR they stay excluded
   and disclosed.

## Consequences
Plan register rows A01, A04, A07 and A08 updated. The Phase 2 rework brief (`decision/briefs/phase-2b-rework.md`)
must describe TWR as a cross-margin account return and use the rebuilt book where the pnl identity fails. Code and
ADR text that say "total account value" (`leader_returns.py` docstring, ADR-0014) are corrected by the rework.
