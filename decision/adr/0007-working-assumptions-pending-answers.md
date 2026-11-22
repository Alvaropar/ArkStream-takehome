# ADR-0007: Working assumptions while the recruiter questions are open

- Status: Superseded by ADR-0041 (answers received 2026-11-19; item 3 reversed)
- Date: 2026-11-19
- Phase: all

## Context
The four Day-0 questions are unanswered. Work continues on stated assumptions so that it can be redone, not
redesigned, if an answer differs.

## Decision
1. **Cutoff** = the last fill, 2026-01-04T23:59:42.020Z (`config/decision_context.yaml: cutoff`). The last
   snapshot is 23:59:31.671; no row, reference price or headline count changes versus 23:59:59 (audit 27/27).
2. **Scope: perpetuals only.** Core perps are eligible. HIP-3 perps (10,308 fills, $15M, 0.4% of notional; no
   Binance reference) stay excluded and disclosed; spot (34,707 fills) is out.
3. **equity is the account's total value** (A04). It equals `cross_margin_summary_account_value` on all
   129,665 snapshots; account returns from snapshots are whole-account returns. The pnl identity check stays.
4. **Public market data may be used** (A07): Binance public archive, Hyperliquid public API. Every source is
   recorded with URL, retrieval date and checksums; nothing is imputed.

## Consequences
Plan register rows A01, A04, A07, A08 annotated. `tests/test_seeded_leaks.py` keeps milliseconds when it moves
the cutoff. If an answer differs: change the config, rerun `make all`, and supersede this ADR.
