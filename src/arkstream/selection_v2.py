"""Phase 4 v2 at every origin (ADRs 0070-0075, 0076-0079): qualification only, handed to Phase 5.

`run` reads the two v2 replay trees (`research/replay_allpriced/`, `research/replay_tradable/`) and writes, under
`research/selection_v2/`:

* per origin: `coins.parquet` / `coins_loo.parquet` (T1-T5 with coverage), `leader_shares.parquet`
  (`sel_tradable_share`, `sel_direction`), `betas.parquet`, `factors.parquet`, `statistics.parquet`,
  `residual_daily.parquet`, `evidence.parquet`, `candidates.parquet` (S1-S3 and the category for every A/B address),
  `comovement.parquet`, `duplicates.parquet` and the hand-off `eligible.parquet`;
* across origins: `tau2.csv`, `ranking_validation.csv`, `walk_forward_v2.csv`, `calibration_v2.csv`,
  `gate_audit_v2.csv`, `coin_policy_v2.csv` and `funnel_v2.csv`.

Every input is point in time at its origin; the holdout window (3 Dec 2025 - 4 Jan 2026) is never computed: the 3 Dec
origin reads only its training window, and the development test windows end at 3 Dec.
"""

from __future__ import annotations

import itertools
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from arkstream import drift
from arkstream import selection as S
from arkstream import selection_v2_coins as SC
from arkstream import selection_v2_comove as CM
from arkstream import selection_v2_evidence as EV
from arkstream import selection_v2_stats as ST
from arkstream.replay_market import midnight
from arkstream.selection_v2_market import load_window, scenario_dir

C = pl.col
GATE7_ENTRY = "ADR-0069 gate 7 v2 rerun"
S3_GATES = ("sel_equity_band", "sel_break_even", "sel_tradable_share", "sel_direction", "sel_copier")
CAT_RANK = {"E2": 3, "E1": 2, "E-": 1, "E0": 0}


class MissingGate7Rerun(RuntimeError):
    """The S2 join needs the ADR-0069 gate 7 v2 Phase 2 rerun, which the trial log does not record."""


def write(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        df.write_csv(path)
    else:
        df.rechunk().write_parquet(path, statistics=True)


def gate7_rerun_logged(ctx) -> bool:
    log = (ctx.root / "provenance/trial_log.md").read_text(encoding="utf-8")
    return any(GATE7_ENTRY in line for line in log.splitlines() if line.startswith("|"))


def origins(ctx) -> list[date]:
    return list(drift.DriftRules.from_config(ctx.raw).origin_dates)


def trees(ctx) -> tuple[Path, Path, Path]:
    v2 = ctx.raw["selection_v2"]
    return ctx.root / v2["allpriced_dir"], ctx.root / v2["tradable_dir"], ctx.root / v2["out_dir"]


def universe(tree: Path, o: date) -> pl.DataFrame:
    return pl.read_parquet(tree / f"origin={o}" / "window=training" / "universe.parquet")


# ---------------------------------------------------------------------------------------------- S1-S3
def copier_weaker(clusters: pl.DataFrame, ev: pl.DataFrame) -> pl.DataFrame:
    """ADR-0079 item 1: in a confirmed copier cluster the weaker members are all but the strongest (higher category,
    then higher posterior mean, unmeasured last, then address)."""
    if clusters.height == 0:
        return pl.DataFrame(schema={"trader": pl.String, "copier_cluster": pl.String, "copier_weaker": pl.Boolean})
    c = clusters.join(ev.select("trader", "category", "m"), on="trader", how="left").with_columns(
        rank=C("category").replace_strict(CAT_RANK, default=0, return_dtype=pl.Int64),
        has=C("m").is_not_null().cast(pl.Int8), mm=C("m").fill_null(-1e18))
    c = c.sort("cluster_id", "rank", "has", "mm", "trader", descending=[False, True, True, True, False]).with_columns(
        copier_weaker=pl.int_range(pl.len()).over("cluster_id") > 0)
    return c.select("trader", copier_cluster="cluster_id", copier_weaker="copier_weaker")


def candidates(ctx, o: date, phase2: pl.DataFrame, stats: pl.DataFrame, ev: pl.DataFrame, shares: pl.DataFrame,
               clusters: pl.DataFrame, uni: pl.DataFrame) -> pl.DataFrame:
    """Every A/B address at the origin: S2, the S3 gates, the category and `qualified` (E1/E2 and S1-S3 pass)."""
    g = ctx.raw["selection"]["gates"]
    lo, hi = float(g["equity_band_usdc"][0]), float(g["equity_band_usdc"][1])
    base_ms = int(g["base_delay_ms"])
    be_ok = (C("break_even_delay_status") == "positive_through_grid") | (
        (C("break_even_delay_status") == "crossing_bracket") & (C("break_even_delay_lo_ms") >= base_ms))
    weak = copier_weaker(clusters, ev)
    t = (uni.select("trader")
         .join(phase2.select("trader", "grade", "all_gates_pass", "gates_failed", "median_equity", "snapshot_src_row",
                             "snapshot_ts", "last_fill_src_row", "tid", "oid", "last_fill_ts"), on="trader", how="left")
         .join(stats.select("trader", "break_even_delay_status", "break_even_delay_lo_ms", "hold_band",
                            "hold_band_diagnostic", "band_net_bps"), on="trader", how="left")
         .join(shares.select("trader", "non_tradable_share", "max_abs_delta_beta", "sel_tradable_share",
                             "sel_direction"), on="trader", how="left")
         .join(ev.select("trader", "measured", "alpha", "s", "m", "v", "p_post", "robust", "category"), on="trader",
               how="left")
         .join(weak, on="trader", how="left")
         .with_columns(C("copier_weaker").fill_null(False), C("all_gates_pass").fill_null(False),
                       C("sel_tradable_share", "sel_direction").fill_null("unmeasured"))
         .with_columns(
             sel_equity_band=S.gate(C("median_equity").is_between(lo, hi), C("median_equity").is_not_null()),
             sel_break_even=S.gate(be_ok, C("break_even_delay_status").is_not_null()
                                   & (C("break_even_delay_status") != "unmeasured")),
             sel_copier=S.gate(~C("copier_weaker"), pl.lit(True))))
    s3 = pl.all_horizontal([C(x) == "pass" for x in S3_GATES])
    failed = pl.concat_str([pl.when(C(x) != "pass").then(pl.lit(x + ":") + C(x)) for x in S3_GATES],
                           separator=",", ignore_nulls=True)
    return t.with_columns(
        s1=C("grade").is_in(["A", "B"]).fill_null(False), s2=C("all_gates_pass"), s3=s3, s3_failed=failed,
    ).with_columns(
        qualified=C("s1") & C("s2") & C("s3") & C("category").is_in(["E1", "E2"]), origin=pl.lit(o),
    ).sort("trader")


# ---------------------------------------------------------------------------------------------- P4-7 helpers
def subsets(n: int, k: int, cap: int, draws: int, rng: np.random.Generator) -> list[tuple[int, ...]]:
    if k <= 0 or k > n:
        return []
    if math.comb(n, k) <= cap:
        return list(itertools.combinations(range(n), k))
    return [tuple(sorted(rng.choice(n, size=k, replace=False).tolist())) for _ in range(draws)]


def set_vs_random(pool: pl.DataFrame, members: list[str], stat: str, o: date, idx: int, rules: dict) -> dict:
    """The equal-weight set's value of `stat` against same-size subsets of `pool` (ADR-0079 item 4)."""
    k = len(members)
    out: dict[str, Any] = {"k": k, "value": None, "random_median": None, "random_mean": None, "percentile": None,
                           "subsets": 0, "exact": None, "win": None}
    if k == 0:
        return out

    def value(rows: pl.DataFrame) -> float | None:
        if stat.startswith("alpha"):
            u = float(rows[f"sum_U{stat[5:]}"].to_numpy().sum())
            g = float(rows[f"sum_G{stat[5:]}"].to_numpy().sum())
            return u / g if g > 0 else None
        v = rows[stat].drop_nulls().to_numpy()
        return float(v.mean()) if len(v) else None

    out["value"] = value(pool.filter(C("trader").is_in(members)))
    defined = pool.filter((C(f"sum_G{stat[5:]}") > 0) if stat.startswith("alpha") else C(stat).is_not_null())
    n = defined.height
    rng = np.random.default_rng([int(rules["eval_seed"]), o.toordinal(), k, idx])
    subs = subsets(n, k, int(rules["max_enumerated_subsets"]), int(rules["eval_draws"]), rng)
    vals = []
    for sub in subs:
        v = value(defined[list(sub)])
        if v is not None:
            vals.append(v)
    if vals and out["value"] is not None:
        a = np.array(vals)
        out.update(random_median=float(np.median(a)), random_mean=float(a.mean()),
                   percentile=float((a < out["value"]).mean()), subsets=len(vals),
                   exact=math.comb(n, k) <= int(rules["max_enumerated_subsets"]),
                   win=bool(out["value"] > float(np.median(a))))
    return out


def raw_ex_crash(tree: Path, o: date, crash: list[date]) -> pl.DataFrame:
    d = pl.read_parquet(scenario_dir(tree, o, "test", "base") / "daily_copy_twr.parquet",
                        columns=["trader", "day", "daily_twr"])
    return d.filter(~C("day").is_in(crash)).sort("trader", "day").group_by("trader", maintain_order=True).agg(
        raw_ex_crash=pl.when(C("daily_twr").null_count() == 0).then((1 + C("daily_twr")).product() - 1))


def test_outcomes(ctx, o: date, nxt: date, tree: Path, market: ST.Market, traders: list[str],
                  crash: list[date]) -> pl.DataFrame:
    """Per address: next-window α (with and without the crash) and raw base return (with and without the crash)."""
    a = ST.window_alpha(ctx, o, tree, "test", o, nxt, market, traders, crash)
    raw = pl.read_parquet(scenario_dir(tree, o, "test", "base") / "address_summary.parquet").select(
        "trader", raw="copy_return")
    return a.join(raw, on="trader", how="left").join(raw_ex_crash(tree, o, crash), on="trader", how="left")


# ---------------------------------------------------------------------------------------------- main
def former_keys(ctx, o: date, tree: Path) -> pl.DataFrame:
    """ADR-0078 item 9: the ADR-A0051 NAV key and the ADR-A0131 trip key on the tradable training window."""
    rules = S.Rules.from_config(ctx.raw, "rule_a")
    daily = pl.read_parquet(scenario_dir(tree, o, "training", "base") / "daily_copy_twr.parquet",
                            columns=["trader", "day", "daily_twr", "equity", "gross"])
    f, fund = load_window(tree, o, "training", "base", o)
    trips = S.follower_trips(f, fund)
    nav = S.nav_keys(daily, rules, o).select("trader", nav_key="key")
    trip = S.address_keys(trips, rules, o).select("trader", trip_key="key")
    return nav.join(trip, on="trader", how="full", coalesce=True)


def order_profile(tree: Path, o: date) -> pl.DataFrame:
    f = pl.read_parquet(scenario_dir(tree, o, "training", "base") / "follower_orders.parquet",
                        columns=["trader", "status", "quantity", "fill_px"]).filter(C("status") == "filled")
    return f.with_columns(n=C("quantity").abs() * C("fill_px")).sort("trader", "n").group_by(
        "trader", maintain_order=True).agg(copy_order_notional_p50=C("n").quantile(0.5, "linear"),
                                           copy_order_notional_p95=C("n").quantile(0.95, "linear"),
                                           copy_orders_filled=pl.len())


def run(ctx, out: Path | None = None, verbose: bool = True) -> dict:
    from arkstream import copiers
    from arkstream.freeze import guard
    from arkstream.replay_market import bounded_inputs

    allpriced, tradable, default_out = trees(ctx)
    out = Path(out) if out else default_out
    v2 = ctx.raw["selection_v2"]
    tr_rules, rk_rules, dup_rules = v2["tradable"], v2["ranking"], v2["duplicates"]
    crash = [date.fromisoformat(d) for d in ctx.raw["selection"]["crash_dates"]]
    dr = drift.DriftRules.from_config(ctx.raw)
    stop = midnight(dr.holdout_start)
    guard(ctx, stop)  # nothing here reads a window ending after the holdout start
    from arkstream.config import load_yaml

    if float(v2["min_exposure_usdc"]) != float(load_yaml("execution.yaml", ctx.root / "config")["replay"][
            "min_notional_usdc"]):
        raise ValueError("ADR-0080: selection_v2.min_exposure_usdc must equal replay.min_notional_usdc")
    inp = bounded_inputs(ctx, stop)
    first = inp.fills["ts"].min().date()
    os_ = origins(ctx)
    marks = pl.read_parquet(tradable / "valuation_marks.parquet")
    taus: list[dict[str, Any]] = []
    per_rank: dict[date, tuple[pl.DataFrame, pl.DataFrame]] = {}
    eval_rows: list[dict[str, Any]] = []
    cal_rows: list[pl.DataFrame] = []
    audit_rows: list[pl.DataFrame] = []
    policy_rows: list[pl.DataFrame] = []
    funnel: list[dict[str, Any]] = []
    placebo_rows: list[pl.DataFrame] = []
    results: dict[str, Any] = {"origins": {}}
    gate7 = gate7_rerun_logged(ctx)
    for i, o in enumerate(os_):
        base = out / f"origin={o}"
        uni = universe(tradable, o)
        traders = uni["trader"].to_list()
        # P4-2: coins and the leader-level gates
        coins, loo = SC.coin_table(ctx, o, allpriced)
        pairs = SC.sets_from(coins, loo, universe(allpriced, o).select("trader"))
        stored = pl.read_parquet(tradable / "tradable_pairs.parquet").filter(C("origin") == o).select(
            "trader", "coin")
        if not stored.sort("trader", "coin").equals(pairs.sort("trader", "coin")):
            raise ValueError(f"{o}: the tradable replay's sets differ from coins.parquet (leave-one-out)")
        members = coins.filter("tradable")["coin"].to_list()
        nh = SC.leader_notional_hours(inp.fills, o, first).join(uni.select("trader"), on="trader", how="semi")
        market = ST.market_at(ctx, o, marks, members, extra_coins=nh["coin"].unique().to_list())
        shares = SC.leader_shares(nh, pairs, market.betas, tr_rules)
        shares = uni.select("trader").join(shares, on="trader", how="left")
        # P4-3
        stats, resid, rc, trips = ST.statistics(ctx, o, tradable, market)
        stats = stats.join(shares.select("trader", "non_tradable_share", "max_abs_delta_beta"), on="trader",
                           how="left")
        # P4-4: τ² first; behaviour clusters only when τ² > 0
        ev, tau = EV.evidence(ctx, o, stats, resid, trips)
        if (tau["tau2"] or 0.0) > 0:
            phase2_all = pl.read_parquet(ctx.root / "research/leader" / f"origin={o}" / "evidence.parquet")
            feats = S.behaviour_clusters(S.behaviour_features(ctx, o, phase2_all),
                                         int(ctx.raw["selection"]["clusters"]["behaviour_k"]))
            ev, tau = EV.evidence(ctx, o, stats, resid, trips, clusters=feats)
        taus.append(tau)
        # ADR-0075 item 4 and ADR-0081: the time-shift placebo when τ² is not robustly 0 and E2 addresses exist
        e2 = ev.filter(C("category") == "E2")["trader"].to_list()
        tau["placebo_required"] = bool(not tau["robust_zero"] and e2)
        if tau["placebo_required"]:
            placebo_rows.append(EV.placebo(rc, resid, market, stats["window_start"][0],
                                           stats["window_end"][0] + timedelta(days=1), e2,
                                           int(v2["evidence"]["seed"]), o, int(rk_rules["placebo_shifts"]),
                                           tuple(rk_rules["placebo_shift_days"])))
        for name, df in (("coins", coins), ("coins_loo", loo), ("leader_shares", shares),
                         ("betas", market.betas), ("factors", market.factors.with_columns(origin=pl.lit(o))),
                         ("statistics", stats), ("residual_daily", resid), ("evidence", ev)):
            write(df, base / f"{name}.parquet")
        # P4-5 inputs: the current key table and the next window's α
        keys = ev.select("trader", "m", "alpha").join(stats.select("trader", "info_ratio", "t_stat"), on="trader",
                                                      how="left").join(former_keys(ctx, o, tradable), on="trader",
                                                                       how="left")
        nxt = os_[i + 1] if i + 1 < len(os_) else None
        test = test_all = None
        if nxt is not None:
            test = test_outcomes(ctx, o, nxt, tradable, market, traders, crash)
            test_all = test_outcomes(ctx, o, nxt, allpriced, market, universe(allpriced, o)["trader"].to_list(),
                                     crash)
            per_rank[o] = (keys, test)
            write(test.with_columns(origin=pl.lit(o)), base / "test_outcomes.parquet")
        # S2 / S3 / the hand-off candidates (S2 needs the gate 7 v2 rerun)
        if not gate7:
            results["stopped"] = f"trial log has no '{GATE7_ENTRY}' entry: S2 join not built"
            results["origins"][o] = {"tau": tau}
            continue
        phase2 = pl.read_parquet(ctx.root / "research/leader" / f"origin={o}" / "evidence.parquet")
        if not set(phase2["trader"]) == set(traders):
            raise ValueError(f"{o}: the replay universe differs from the Phase 2 A/B set")
        cop = copiers.screen(inp.fills, midnight(o), ctx.raw["copiers"])["clusters"]
        cand = candidates(ctx, o, phase2, stats, ev, shares, cop, uni)
        q = cand.filter("qualified").sort("trader")
        prof = q.select("trader").join(stats.select("trader", "exposure_by_coin"), on="trader", how="left")
        start, end = stats["window_start"][0], stats["window_end"][0] + timedelta(days=1)
        daily = pl.read_parquet(scenario_dir(tradable, o, "training", "base") / "daily_copy_twr.parquet",
                                columns=["trader", "day", "daily_twr"])
        keep, sigma, sinfo = CM.risk_cov(market.returns, members, o, int(dup_rules["cov_lookback_days"]),
                                         int(dup_rules["cov_min_days"]), int(dup_rules["cov_min_complete_days"]))
        comove = CM.pair_table(q["trader"].to_list(), resid, daily, rc, market.factors, start, end, crash, keep,
                               sigma, prof, dup_rules).with_columns(
            origin=pl.lit(o), sigma_fit_date=pl.lit(o), sigma_coins=pl.lit(len(keep)),
            sigma_complete_days=pl.lit(sinfo["complete_days"]), sigma_shrinkage=pl.lit(sinfo["delta"], pl.Float64))
        dups = CM.duplicate_screen(q, comove)
        cand = cand.join(dups.select("trader", "duplicate_decision", "duplicate_of"), on="trader", how="left")
        cand = cand.with_columns(eligible=C("qualified") & (C("duplicate_decision") == "kept"))
        write(cand, base / "candidates.parquet")
        write(comove, base / "comovement.parquet")
        write(dups.with_columns(origin=pl.lit(o)), base / "duplicates.parquet")
        hand = handoff(ctx, o, cand, ev, stats, inp.traders, tradable, tau)
        write(hand, base / "eligible.parquet")
        cc = ev.group_by("category").len()
        funnel.append({"origin": o, "ab_universe": len(traders),
                       "s2_pass": int(cand["s2"].sum()),
                       **{f"{g}_pass": int((cand[g] == "pass").sum()) for g in S3_GATES},
                       "s1_s3_pass": int((cand["s1"] & cand["s2"] & cand["s3"]).sum()),
                       **{f"cat_{c}": int(cc.filter(C("category") == c)["len"].sum()) for c in CAT_RANK},
                       "measured": int(ev["measured"].sum()),
                       "qualified_E1": int((cand["qualified"] & (cand["category"] == "E1")).sum()),
                       "qualified_E2": int((cand["qualified"] & (cand["category"] == "E2")).sum()),
                       "near_duplicates_removed": int((dups["duplicate_decision"] == "near_duplicate").sum()),
                       "eligible": hand.height, "tradable_coins": len(members)})
        results["origins"][o] = {"tau": tau, "eligible": hand}
        # P4-7 on the development test windows
        if test is not None:
            evaluate_origin(o, cand, ev, stats, test, test_all, rk_rules, eval_rows, cal_rows, audit_rows,
                            policy_rows)
        if verbose:
            print(f"{o}: tau2={tau['tau2']} Q={tau['Q']} p={tau['Q_p']} eligible={hand.height}", flush=True)
    tau_t = pl.DataFrame(taus)
    write(tau_t, out / "tau2.csv")
    rv, decision = EV.ranking_validation(per_rank, rk_rules)
    extras_skipped = not any(t.get("placebo_required", False) for t in taus)
    dec_rows = pl.DataFrame([{"origin": None, "key": "decision", "n": decision["origins"], "ic": decision["mean_ic_m"],
                              "positive": decision["ordering_used"], "top_quintile_hit_rate": None}],
                            schema=rv.schema)
    write(pl.concat([rv, dec_rows]).with_columns(
        positive_origins_m=pl.lit(decision["positive_origins_m"]),
        undefined_origins_m=pl.lit(decision["undefined_origins_m"]),
        ordering_used=pl.lit(decision["ordering_used"]),
        placebo=pl.lit("skipped: tau2 robustly 0 or no E2" if extras_skipped else "run: placebo.csv")), out /
        "ranking_validation.csv")
    if placebo_rows:
        write(pl.concat(placebo_rows).sort("origin", "trader"), out / "placebo.csv")
    results.update(tau=tau_t, ranking=rv, decision=decision, extras_skipped=extras_skipped)
    if eval_rows:
        write(pl.DataFrame(eval_rows), out / "walk_forward_v2.csv")
        write(calibration(pl.concat(cal_rows)), out / "calibration_v2.csv")
        write(gate_audit(pl.concat(audit_rows)), out / "gate_audit_v2.csv")
        write(pl.concat(policy_rows), out / "coin_policy_v2.csv")
    if funnel:
        write(pl.DataFrame(funnel), out / "funnel_v2.csv")
    return results


def handoff(ctx, o: date, cand: pl.DataFrame, ev: pl.DataFrame, stats: pl.DataFrame, traders: pl.DataFrame,
            tree: Path, tau: dict) -> pl.DataFrame:
    """ADR-0079 item 5: `eligible.parquet` (fixed schema, one row per E1/E2 address passing S1-S3 and duplicates)."""
    prof = pl.read_parquet(ctx.root / "research/leader" / f"origin={o}" / "profiles.parquet",
                           columns=["trader", "median_order_notional", "order_to_volume_bps_median",
                                    "order_to_volume_bps_p95"])
    eref = traders.select(snapshot_src_row="src_row", e_ref="equity")
    e = cand.filter("eligible").select("trader", "category", "median_equity", "snapshot_src_row",
                                       "last_fill_src_row", "tid", "oid", "non_tradable_share", "max_abs_delta_beta")
    ev_cols = ["trader", "alpha", "s", "alpha_funding", "alpha_ex_funding", "s_ex_funding", "alpha_incl_funding",
               "s_incl_funding", "carry_book", "m", "v",
               "p_post", "alpha_ex_best_week", "s_ex_best_week",
               "p_own_ex_best_week", "alpha_ex_crash", "alpha_ex_best3_weeks", "alpha_ex_best_trip",
               "best_week_share", "top5_trip_share", "robust"]
    st_cols = ["trader", "alpha_static", "alpha_timing", "top3_coinday_share", "util_mean", "util_p50", "util_p95",
               "info_ratio", "exposed_days", "exposed_weeks", "copy_beta_BTC", "copy_beta_ETH", "copy_beta_ALT",
               "exposure_by_coin", "train_stress_return", "train_stress_max_drawdown", "train_stress_measurement",
               "train_copy_return", "train_max_drawdown"]
    out = (e.join(ev.select(ev_cols), on="trader", how="left").join(stats.select(st_cols), on="trader", how="left")
           .join(eref, on="snapshot_src_row", how="left").join(prof, on="trader", how="left")
           .join(order_profile(tree, o), on="trader", how="left")
           .with_columns(origin=pl.lit(o), tau2=pl.lit(tau["tau2"], pl.Float64),
                         tau2_robust_zero=pl.lit(bool(tau["robust_zero"])),
                         sleeve_usdc=pl.lit(float(ctx.raw["selection_v2"]["sleeve_usdc"]))))
    return out.select(HANDOFF_COLUMNS).sort("trader")


HANDOFF_COLUMNS = [
    "origin", "trader", "category", "alpha", "s", "alpha_funding", "alpha_ex_funding", "s_ex_funding",
    "alpha_incl_funding", "s_incl_funding", "carry_book",
    "m", "v", "p_post", "tau2", "tau2_robust_zero",
    "alpha_ex_best_week", "s_ex_best_week", "p_own_ex_best_week", "alpha_ex_crash", "alpha_ex_best3_weeks",
    "alpha_ex_best_trip", "best_week_share", "top5_trip_share", "robust",
    "alpha_static", "alpha_timing", "top3_coinday_share", "info_ratio", "exposed_days", "exposed_weeks",
    "util_mean", "util_p50", "util_p95", "sleeve_usdc",
    "median_equity", "e_ref", "copy_order_notional_p50", "copy_order_notional_p95", "copy_orders_filled",
    "median_order_notional", "order_to_volume_bps_median", "order_to_volume_bps_p95", "non_tradable_share",
    "max_abs_delta_beta", "copy_beta_BTC", "copy_beta_ETH", "copy_beta_ALT", "exposure_by_coin",
    "train_stress_return", "train_stress_max_drawdown", "train_stress_measurement", "train_copy_return",
    "train_max_drawdown", "snapshot_src_row", "last_fill_src_row", "tid", "oid",
]


def evaluate_origin(o, cand, ev, stats, test, test_all, rules, eval_rows, cal_rows, audit_rows, policy_rows):
    """ADR-0079 item 4 for one development origin."""
    e2 = cand.filter(C("eligible") & (C("category") == "E2"))["trader"].to_list()
    e12 = cand.filter(C("eligible"))["trader"].to_list()
    pool = test.with_columns(C("sum_G", "sum_G_ex_crash").fill_null(0.0))
    for name, members in (("E2", e2), ("E1_or_E2", e12)):
        for idx, stat in enumerate(("alpha", "alpha_ex_crash", "raw", "raw_ex_crash")):
            r = set_vs_random(pool, members, stat, o, idx, rules)
            eval_rows.append({"origin": o, "set": name, "statistic": stat, **r})
    j = ev.select("trader", "category").join(test.select("trader", "alpha", "sum_U", "sum_G"), on="trader",
                                             how="left")
    cal_rows.append(j.filter(C("category").is_in(["E-", "E1", "E2"]) & C("alpha").is_not_null()).with_columns(
        origin=pl.lit(o)))
    a = cand.join(test.select("trader", next_alpha="alpha", next_raw="raw"), on="trader", how="left").with_columns(
        s2_gate=pl.when(C("s2")).then(pl.lit("pass")).otherwise(pl.lit("fail")),
        measured_gate=pl.when(C("measured")).then(pl.lit("pass")).otherwise(pl.lit("fail")),
        robust_gate=pl.when(C("robust").fill_null(False)).then(pl.lit("pass")).otherwise(pl.lit("fail")),
        hold_band_gate=C("hold_band_diagnostic").fill_null("unmeasured"))
    audit_rows.append(a.select("trader", "next_alpha", "next_raw", *S3_GATES, "s2_gate", "measured_gate",
                               "robust_gate", "hold_band_gate").with_columns(origin=pl.lit(o)))
    p = test.select("trader", tradable_alpha="alpha", tradable_raw="raw").join(
        test_all.select("trader", allpriced_alpha="alpha", allpriced_raw="raw"), on="trader", how="full",
        coalesce=True).with_columns(origin=pl.lit(o), eligible=C("trader").is_in(e12), e2=C("trader").is_in(e2))
    policy_rows.append(p.sort("trader"))


def calibration(rows: pl.DataFrame) -> pl.DataFrame:
    """ADR-0079 item 4: mean next α by category per origin and pooled (decides "ordered"); the median and the pooled
    Σ U / Σ G are reported beside it."""
    stats = [pl.len().alias("n"), C("alpha").mean().alias("mean_next_alpha"),
             C("alpha").median().alias("median_next_alpha"),
             (C("sum_U").sum() / C("sum_G").sum()).alias("pooled_next_alpha")]
    by = rows.sort("origin", "category", "trader").group_by("origin", "category", maintain_order=True).agg(*stats)
    allr = rows.sort("category", "origin", "trader").group_by("category", maintain_order=True).agg(*stats).with_columns(
        origin=pl.lit(None, pl.Date))
    out = pl.concat([by, allr.select(by.columns)])
    order = []
    for o in out["origin"].unique(maintain_order=True).to_list():
        m = dict(out.filter(C("origin").is_null() if o is None else C("origin") == o).select(
            "category", "mean_next_alpha").rows())
        seq = [m[c] for c in ("E-", "E1", "E2") if c in m and m[c] is not None]
        order.append((o, all(a < b for a, b in zip(seq, seq[1:], strict=False))))
    flag = pl.DataFrame(order, schema={"origin": pl.Date, "ordered_by_mean": pl.Boolean}, orient="row")
    return out.join(flag, on="origin", how="left", nulls_equal=True).sort("origin", "category", nulls_last=True)


def gate_audit(rows: pl.DataFrame) -> pl.DataFrame:
    gates = [*S3_GATES, "s2_gate", "measured_gate", "robust_gate", "hold_band_gate"]
    out = []
    for g in gates:
        x = rows.group_by(C(g).alias("outcome")).agg(
            address_windows=pl.len(), n_alpha=C("next_alpha").count(), mean_next_alpha=C("next_alpha").mean(),
            n_raw=C("next_raw").count(), mean_next_raw=C("next_raw").mean()).with_columns(gate=pl.lit(g))
        out.append(x.select("gate", "outcome", "address_windows", "n_alpha", "mean_next_alpha", "n_raw",
                            "mean_next_raw"))
    return pl.concat(out).sort("gate", "outcome")


