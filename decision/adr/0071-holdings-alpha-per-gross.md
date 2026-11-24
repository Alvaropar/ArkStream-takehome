# ADR-0071: Copy economics: holdings-based market adjustment, alpha per unit of gross exposure-time, static-replica decomposition

- Status: Accepted (placeholders); fixed before any rerun under it. `G` amended by ADR-0082 (max of start and end gross); α excluding funding reported by ADR-0083
- Date: 2026-11-23
- Phase: Phase 4 v2, stage S4 (measurement)
- Replaces: ADR-A0051's statistic (the mean daily NAV return) as the quantity Phase 4 judges; ADR-A0134's BTC/ETH
  regression stays as a cross-check
- Source: `decision/phase-4-v2-methodology.md` sections 5.2-5.3 (amendments A1 and A5)

## Context
A NAV return on a fixed 10k sleeve has three problems:
- it scales with how much of the sleeve is deployed, so a leader smaller than the sleeve (0x971f, about 7.5k) or an
  idle copy scores low for reasons unrelated to skill;
- it rewards market exposure: all three v1 sleeves were long-only HYPE, BNB and TAO, and a BTC/ETH regression misses
  HYPE;
- regressing about 60-90 sleeve days on several factors is noisy.

## Decision
1. **Holdings-based market component:**
   - `e_{i,c,t}`: the copy's signed notional in coin c at the start of day t (from the replay ledger at the
     Hyperliquid daily mark).
   - `β_{c,f}`: coin c's beta to factor f, **estimated once at each origin** from Hyperliquid daily marks over the
     **90 days before it**, by OLS on daily returns, then shrunk toward the cross-coin median beta for that factor with
     weight `n / (n + 30)`, where n is the coin's number of valid days. Every beta used at an origin has one fit date,
     before that origin, and none is re-estimated inside a window.
   - **Factors:** BTC, ETH and ALT. ALT is the equal-weight daily return of the tradable coins (ADR-0073) other than
     BTC and ETH, with membership fixed at the origin.
   - **Residual PnL:** `U_{i,t} = PnL_{i,t} - Σ_c e_{i,c,t} Σ_f β_{c,f} r_{f,t}`, after costs and funding.
2. **Primary statistic: alpha per unit of gross exposure-time.**

   ```
   α_i = Σ_t U_{i,t} / Σ_t G_{i,t}     (reported in bps per day per 1 USDC of gross)
   ```

   Scaling every position by a constant leaves `α_i` unchanged. So it does not change with the sleeve size, the
   no-scale-up multiplier or idle days. The utilisation `ū_i = mean_t G_{i,t} / A` (with p50 and p95) is measured and
   handed to Phase 5, which turns `m_i` into an expected sleeve return `m_i · ū_i · A`.
3. **Static-replica decomposition (mandatory).**
   - The replica allocates each exposed day's gross `G_{i,t}` across coins in the window's average signed mix
     (in-window weights, descriptive only).
   - `α_static` = the replica's residual PnL per unit of gross: **coin selection**.
   - `α_timing = α_i - α_static`: **when** the leader is in each coin.
   - Also reported: the share of residual PnL from the three largest coin-days.

   Coin selection counts as skill. The decomposition shows how much of α is one coin's run.
4. **Reported statistic set** (methodology section 5.3):
   - the information ratio of the residual, which is fairer to hedged books (per unit of gross, a hedged book looks
     less efficient);
   - residual return on sleeve NAV;
   - raw NAV and geometric return, volatility, max drawdown, 95% expected shortfall;
   - utilisation;
   - trip expectancy, PnL / peak notional and total CT as diagnostics;
   - capture and the ADR-0063 gap decomposition;
   - training stress and optimistic returns and the break-even delay;
   - the BTC/ETH regression as a cross-check.

## Consequences
- **Output:** `statistics.parquet` per origin.
- **Tests:**
  - a planted post-origin day changes nothing;
  - every beta has one fit date before the origin;
  - a synthetic one-coin book reproduces `α` exactly;
  - `α` is unchanged when every position is scaled by 0.5.
- **Known bias:** per unit of gross, hedged books are penalised. The information ratio sits beside `α` and is
  reported, not ranked.
