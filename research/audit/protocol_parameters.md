# Protocol parameters against `config/risk.yaml` (ADR-0094)

`decision/deployment-protocol.md` section 9: 54 parameters, 54 match, 0 differ or are missing.

| Key | Protocol | risk.yaml | Result |
| --- | --- | --- | --- |
| `capital_usdc` | 100000 | 100000 | match |
| `gray.loss_cap_usdc` | 750 | 750 | match |
| `gray.max_live_usdc` | 5000 | 5000 | match |
| `gray.sleeve_usdc` | 2500 | 2500 | match |
| `gray.sleeve_usdc_if_subminimum` | 5000 | 5000 | match |
| `gray.subminimum_share_max` | 0.10 | 0.1 | match |
| `gray.subminimum_base` | gstar_after_lambda | gstar_after_lambda | match |
| `gray.min_weeks` | 4 | 4 | match |
| `gray.min_live_orders` | 200 | 200 | match |
| `gray.max_weeks` | 12 | 12 | match |
| `gray.revert_shortfall_reviews` | 2 | 2 | match |
| `gray.stress_cap_basis` | remaining | remaining | match |
| `gray.limits` | C | C | match |
| `gray.limits_kept` | [O1, O2, O3, O4, S1, S3, P6] | ['O1', 'O2', 'O3', 'O4', 'S1', 'S3', 'P6'] | match |
| `gross_exposure_max_x` | 1.5 | 1.5 | match |
| `limits.S1_sleeve_gross_x` | 1.5 | 1.5 | match |
| `limits.O2_limit_price` | stress_p99_shortfall_by_bucket | stress_p99_shortfall_by_bucket | match |
| `limits.O3_min_notional_usdc` | 10 | 10 | match |
| `limits.S3_sleeve_drawdown.reduce_only` | -0.10 | -0.1 | match |
| `limits.S3_sleeve_drawdown.flatten_pause` | -0.15 | -0.15 | match |
| `drawdown_ladder.halve_new_risk` | -0.05 | -0.05 | match |
| `drawdown_ladder.reduce_only` | -0.10 | -0.1 | match |
| `drawdown_ladder.flatten` | -0.15 | -0.15 | match |
| `engine.deadband.min_usdc` | 10 | 10 | match |
| `engine.deadband.share_of_target` | 0.02 | 0.02 | match |
| `engine.debounce_ms` | 250 | 250 | match |
| `engine.sweep_minutes` | 15 | 15 | match |
| `engine.participation_per_coin_bar` | 0.005 | 0.005 | match |
| `engine.stale_signal_s` | 30 | 30 | match |
| `engine.netting` | internal_cross_at_decision_mark | internal_cross_at_decision_mark | match |
| `states.halved_scale` | 0.5 | 0.5 | match |
| `states.flatten.twap_max_minutes` | 60 | 60 | match |
| `states.review_days` | 14 | 14 | match |
| `triggers.L1_leader_drawdown_x_hist_max` | 1.5 | 1.5 | match |
| `triggers.L2_leader_leverage_x_p95` | 2.0 | 2.0 | match |
| `triggers.L3_leader_equity_of_eref` | 0.7 | 0.7 | match |
| `triggers.L4_withdrawal_share_24h` | 0.5 | 0.5 | match |
| `triggers.L5_forced_fill` | any | any | match |
| `triggers.L6_nontradable_share_7d` | 0.10 | 0.1 | match |
| `triggers.L7_inactive_days` | 14 | 14 | match |
| `triggers.C1_shortfall_window_days` | 14 | 14 | match |
| `triggers.C3_feed_stale_s` | 60 | 60 | match |
| `triggers.C3_reconcile_freeze_cycles` | 3 | 3 | match |
| `paper.review_days` | 14 | 14 | match |
| `paper.summary_weeks` | 8 | 8 | match |
| `paper.revisit.min_windows` | 6 | 6 | match |
| `paper.revisit.one_sided_level` | 0.95 | 0.95 | match |
| `paper.revisit.window_sd` | 0.101 | 0.101 | match |
| `paper.revisit.min_mean_ic` | 0.068 | 0.068 | match |
| `paper.revisit.alpha_window_sd` | 0.0706 | 0.0706 | match |
| `paper.revisit.alpha_min_mean_ic` | 0.047 | 0.047 | match |
| `paper.stop_months` | 6 | 6 | match |
| `scheme.sleeve_notional_usdc` | 10000 | 10000 | match |
| `escalation_capital_usdc` | 15000 | 15000 | match |

**Result: PASS**
