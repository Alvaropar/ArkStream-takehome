"""Phase 5 step P5-4: trigger calibration and the two risk-rule variants on the population (ADR-0095 items 1-2).

Every A/B address of an origin's universe is copied as a basket of one (10,000 USDC, the frozen tradable tree's
signals) through the P5-3 engine:
* **`S` population rules**: S1, S3, the state machine and the triggers, with the execution model. The scheme limits
  (S2, P1-P5, P6) are defined on the two-sleeve `D` and are off (`portfolio_limits=False`);
* **`U` twin**: S1 and execution only, for the copy's forward 14-day return and drawdown after a firing.

`triggers_calibration.csv` (training windows, base): per trigger the firings (a trigger's condition turning on,
whatever the state), the sleeve-months (30 days with a usable `E_ref`), the rate, the share of sleeves above one per
sleeve-month, the copy's mean forward 14-day return and drawdown after firings against the same sleeves' hours
without a firing (descriptive), and the false-alarm share (forward return >= 0).

`variants.csv` (four test windows, base): each address-window return under the current rules and each variant;
`variant_decision.json`: the criterion of ADR-0095 item 2 applied as written.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from arkstream import portfolio_replay as PR
from arkstream.portfolio_engine import DAY, HOUR, Engine, Signal

C = pl.col
DEFAULT_OUT = "research/phase5_population"
TRIGGERS = ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "C1", "S3")


def universe(tree: Path, origin: date, window: str) -> list[str]:
    return sorted(pl.read_parquet(tree / f"origin={origin}" / f"window={window}" / "universe.parquet",
                                  columns=["trader"])["trader"].to_list())


def window_start(tree: Path, origin: date, window: str) -> datetime:
    d = pl.read_parquet(tree / f"origin={origin}" / f"window={window}" / f"scenario={PR.canonical('base', PR.MODEL)}"
                        / "daily_copy_twr.parquet", columns=["day"])["day"].min()
    assert isinstance(d, date)
    return PR.midnight(d)


def forward(nav: list[tuple[int, float]], t: int, horizon: int = 14 * DAY) -> tuple[float | None, float | None]:
    """Forward return and drawdown of the U twin's hourly NAV from t over the horizon (None past the window)."""
    times = [x[0] for x in nav]
    import bisect

    i = bisect.bisect_left(times, t)
    j = bisect.bisect_right(times, t + horizon) - 1
    if i >= len(nav) or j <= i or times[j] < t + horizon - HOUR:
        return None, None
    v0 = nav[i][1]
    if v0 <= 0:
        return None, None
    path = [x[1] for x in nav[i:j + 1]]
    return path[-1] / v0 - 1, min(path) / v0 - 1


def run_copy(data, rules, costs, signals: list[Signal]) -> Engine:
    eng = Engine(rules, costs, data.market, PR.ms(data.win.start), PR.ms(data.win.end), triggers=data.triggers,
                 reviews=PR.review_times(data.win.start, data.win.end, rules.review_days), light=True)
    eng.run(signals)
    return eng


def calibrate(ctx, out: Path, bars, costs, ex, tree: Path) -> pl.DataFrame:
    from arkstream import drift

    dr = drift.DriftRules.from_config(ctx.raw)
    stress = costs["stress"]
    rows, fwd_rows = [], []
    for origin in dr.origin_dates:
        traders = universe(tree, origin, "training")
        win = PR.WindowInputs(origin, "training", window_start(tree, origin, "training"), PR.midnight(origin), origin)
        data = PR.WindowData(ctx, win, traders, [tree], bars, costs, ex)
        sigs = PR.signals_from_orders(PR.tree_orders(tree, origin, "training", "base", traders))
        for tr in traders:
            s = sigs.get(tr, [])
            eng_s = run_copy(data, PR.scheme_rules(ctx, "S", {tr: 10000.0}, stress, portfolio_limits=False),
                             costs["base"], s)
            eng_u = run_copy(data, PR.scheme_rules(ctx, "U", {tr: 10000.0}, stress), costs["base"], s)
            nav = [(h["t"], h["nav"]) for h in eng_u.hourly]
            months = eng_s.usable_hours[tr] / 720.0
            fired: dict[str, list[int]] = {k: [] for k in TRIGGERS}
            for e in eng_s.events:
                if e["event"] == "trigger_on":
                    fired[str(e["trigger"])].append(int(e["t"]))
                elif e["event"] == "state_firing" and e.get("reason") == "S3":
                    fired["S3"].append(int(e["t"]))
            on_hours = {t for ts in fired.values() for t in ts}
            for k in TRIGGERS:
                rows.append((origin, tr, k, len(fired[k]), months))
                for t in fired[k]:
                    r, d = forward(nav, t)
                    fwd_rows.append((origin, tr, k, "after_firing", t, r, d))
            for t, _ in nav[::24]:  # matched: the same sleeve's hours without a firing, sampled daily
                if t in on_hours:
                    continue
                r, d = forward(nav, t)
                if r is not None:
                    fwd_rows.append((origin, tr, "none", "matched_no_firing", t, r, d))
        print(f"{origin} training calibration: {len(traders)} copies", flush=True)
    counts = pl.DataFrame(rows, schema={"origin": pl.Date, "trader": pl.String, "trigger": pl.String,
                                        "firings": pl.Int64, "sleeve_months": pl.Float64}, orient="row")
    fwd = pl.DataFrame(fwd_rows, schema={"origin": pl.Date, "trader": pl.String, "trigger": pl.String,
                                         "kind": pl.String, "t": pl.Int64, "fwd_return": pl.Float64,
                                         "fwd_drawdown": pl.Float64}, orient="row")
    out.mkdir(parents=True, exist_ok=True)
    counts.write_parquet(out / "trigger_firings.parquet")
    fwd.write_parquet(out / "trigger_forward.parquet")
    matched = fwd.filter(C("kind") == "matched_no_firing").select(
        matched_fwd_return=C("fwd_return").mean(), matched_fwd_drawdown=C("fwd_drawdown").mean())
    per = counts.with_columns(rate=pl.when(C("sleeve_months") > 0).then(C("firings") / C("sleeve_months")))
    table = (counts.group_by("origin", "trigger").agg(C("firings", "sleeve_months").sum(), sleeves=pl.len())
             .vstack(counts.group_by("trigger").agg(C("firings", "sleeve_months").sum(), sleeves=pl.len())
                     .with_columns(origin=pl.lit(None, pl.Date)).select("origin", "trigger", "firings",
                                                                         "sleeve_months", "sleeves")))
    above = per.filter(C("sleeve_months") > 0).group_by("origin", "trigger").agg(
        share_sleeves_above_1=(C("rate") > 1).mean())
    above_all = per.filter(C("sleeve_months") > 0).group_by("trigger").agg(
        share_sleeves_above_1=(C("rate") > 1).mean()).with_columns(origin=pl.lit(None, pl.Date))
    after = fwd.filter(C("kind") == "after_firing").group_by("origin", "trigger").agg(
        fwd_n=C("fwd_return").count(), fwd_return=C("fwd_return").mean(), fwd_drawdown=C("fwd_drawdown").mean(),
        false_alarm_share=(C("fwd_return") >= 0).mean())
    after_all = fwd.filter(C("kind") == "after_firing").group_by("trigger").agg(
        fwd_n=C("fwd_return").count(), fwd_return=C("fwd_return").mean(), fwd_drawdown=C("fwd_drawdown").mean(),
        false_alarm_share=(C("fwd_return") >= 0).mean()).with_columns(origin=pl.lit(None, pl.Date))
    table = (table.join(pl.concat([above, above_all.select(above.columns)]), on=["origin", "trigger"],
                        how="left", nulls_equal=True)
             .join(pl.concat([after, after_all.select(after.columns)]), on=["origin", "trigger"], how="left",
                   nulls_equal=True)
             .join(matched, how="cross")
             .with_columns(rate_per_sleeve_month=pl.when(C("sleeve_months") > 0).then(
                 C("firings") / C("sleeve_months")),
                           f4_pass=C("firings") <= C("sleeve_months"),
                           scope=pl.when(C("origin").is_null()).then(pl.lit("pooled_training_windows"))
                           .otherwise(pl.lit("training_window")),
                           note=pl.lit("training windows overlap (each starts 27 Jul); pooled counts repeat days"))
             .sort("trigger", "origin", nulls_last=True))
    table.write_csv(out / "triggers_calibration.csv")
    return table


def previous_reference(ctx, origin: date, traders: list[str], at: datetime) -> dict[str, float]:
    """ADR-0095 item 2 variant (pinned): `E_ref,prev` = the leader's latest usable snapshot equity at or before the
    previous review (window start - 14 days), from the origin's Phase 2 table (history before the origin)."""
    t = pl.read_parquet(ctx.root / "research/leader" / f"origin={origin}" / "daily_twr.parquet",
                        columns=["trader", "ts", "equity"]).filter(
        C("trader").is_in(traders) & (C("ts") <= at) & (C("equity") > 0))
    last = t.sort("trader", "ts").group_by("trader", maintain_order=True).last()
    return dict(last.select("trader", "equity").rows())


def hwm_signals(signals: list[Signal], prev: float | None) -> list[Signal]:
    from dataclasses import replace

    if prev is None:
        return signals
    return [replace(s, e_ref=max(s.e_ref, prev) if s.e_ref else s.e_ref) for s in signals]


def variants(ctx, out: Path, bars, costs, ex, tree: Path, rules_cfg: dict) -> dict:
    stress = costs["stress"]
    rows = []
    for win in PR.dev_windows(ctx):
        traders = universe(tree, win.origin, "test")
        data = PR.WindowData(ctx, win, traders, [tree], bars, costs, ex)
        sigs = PR.signals_from_orders(PR.tree_orders(tree, win.origin, "test", "base", traders))
        prev = previous_reference(ctx, win.origin, traders, win.start - timedelta(days=14))
        for tr in traders:
            s = sigs.get(tr, [])
            for name, kw, sg in (("current", {}, s), ("cap_min_nav", {"cap_denominator": "min_nav"}, s),
                                 ("eref_high_water", {}, hwm_signals(s, prev.get(tr)))):
                eng = run_copy(data, PR.scheme_rules(ctx, "S", {tr: 10000.0}, stress, portfolio_limits=False, **kw),
                               costs["base"], sg)
                ret = eng.sleeves[tr].nav / 10000.0 - 1
                rows.append((win.origin, tr, name, ret, len(s)))
        print(f"{win.origin} test variants: {len(traders)} copies", flush=True)
    v = pl.DataFrame(rows, schema={"origin": pl.Date, "trader": pl.String, "variant": pl.String,
                                   "window_return": pl.Float64, "signals": pl.Int64}, orient="row")
    v.write_csv(out / "variants.csv")
    crit = rules_cfg["criterion"]
    wide = v.pivot(on="variant", index=["origin", "trader"], values="window_return")
    decision: dict = {"criterion": dict(crit), "scope": "all A/B single-sleeve copies, four development test windows,"
                      " base", "n_address_windows": wide.height}

    def es(col: str) -> float:
        x = sorted(wide[col].drop_nulls().to_list())
        n = max(1, math.ceil((1 - float(crit["es_level"])) * len(x)))
        return sum(x[:n]) / n

    es_cur = es("current")
    decision["es_current"] = es_cur
    for name, item in (("cap_min_nav", "cap_denominator"), ("eref_high_water", "eref_at_review")):
        es_var = es(name)
        diff = (wide["current"] - wide[name]).drop_nulls()
        cost = float(diff.sum()) / diff.len() if diff.len() else 0.0
        reduction = 1 - abs(es_var) / abs(es_cur) if es_cur else 0.0
        adopt = reduction >= float(crit["min_es_reduction"]) and cost <= float(crit["max_mean_cost_pp"]) / 100
        decision[item] = {"variant": name, "es_variant": es_var, "es_reduction": reduction,
                          "mean_cost_per_window": cost, "adopted": adopt,
                          "chosen": name if adopt else "current"}
    (out / "variant_decision.json").write_text(json.dumps(decision, indent=2, default=str) + "\n", encoding="utf-8")
    return decision


RANK_RO = 2  # portfolio_engine.RANK["REDUCE_ONLY"]


def forward_to(nav: list[tuple[int, float]], t: int, end: int, horizon: int = 14 * DAY
               ) -> tuple[float | None, float | None, float | None, bool]:
    """Forward return, drawdown and horizon (days) of an hourly NAV from t to min(t + horizon, end), and whether the
    full horizon fitted. A test window lasts 14 days, so the copy's own horizon is cut at the window end."""
    import bisect

    times = [x[0] for x in nav]
    i = bisect.bisect_left(times, t)
    stop = min(t + horizon, end)
    j = bisect.bisect_right(times, stop) - 1
    if i >= len(nav) or j <= i or nav[i][1] <= 0:
        return None, None, None, False
    v0 = nav[i][1]
    path = [x[1] for x in nav[i:j + 1]]
    return (path[-1] / v0 - 1, min(path) / v0 - 1, (times[j] - times[i]) / DAY,
            t + horizon <= end and times[j] >= t + horizon - HOUR)


def leader_index(ctx, traders: list[str], stop: datetime) -> dict[str, list[tuple[int, float]]]:
    """The leaders' Phase 2 TWR index from the holdout origin's table (built from history before it), cut at `stop`."""
    t = pl.read_parquet(ctx.root / "research/leader" / f"origin={stop.date()}" / "daily_twr.parquet",
                        columns=["trader", "ts", "index_end"]).filter(
        C("trader").is_in(traders) & C("index_end").is_not_null() & (C("ts") < stop)).sort("trader", "ts")
    out: dict[str, list[tuple[int, float]]] = {}
    for tr, ts, v in t.select("trader", "ts", "index_end").rows():
        out.setdefault(tr, []).append((PR.ms(ts), float(v)))
    return out


def leader_forward(series: list[tuple[int, float]], t: int, stop: int, horizon: int = 14 * DAY
                   ) -> tuple[float | None, float | None, str]:
    """The leader's forward index return and drawdown over [t, t + horizon], each value used from its own time;
    'cut_holdout' when the horizon reaches past the holdout start (nothing after it is read)."""
    import bisect

    if t + horizon > stop:
        return None, None, "cut_holdout"
    times = [x[0] for x in series]
    i = bisect.bisect_right(times, t) - 1
    j = bisect.bisect_right(times, t + horizon) - 1
    if i < 0 or j <= i or series[i][1] <= 0:
        return None, None, "no_index"
    v0 = series[i][1]
    path = [v0] + [x[1] for x in series[i + 1:j + 1]]
    return path[-1] / v0 - 1, min(path) / v0 - 1, "full"


def l1_out_of_sample(ctx, out: Path, bars, costs, ex, tree: Path) -> dict:
    """L1 on the four development test windows, where its threshold is out of sample (trial log, 2026-11-24).

    Descriptive only: the P5-4 population copies under the current rules and their U twins, rerun with the
    firing output the variant test did not keep."""
    from arkstream import drift
    from arkstream.portfolio_engine import RANK

    assert RANK["REDUCE_ONLY"] == RANK_RO
    dr = drift.DriftRules.from_config(ctx.raw)
    stop_dt = PR.midnight(dr.holdout_start)
    stop = PR.ms(stop_dt)
    stress = costs["stress"]
    counts, fwd_rows, firings, returns = [], [], [], []
    for win in PR.dev_windows(ctx):
        assert win.end <= stop_dt
        traders = universe(tree, win.origin, "test")
        data = PR.WindowData(ctx, win, traders, [tree], bars, costs, ex)
        sigs = PR.signals_from_orders(PR.tree_orders(tree, win.origin, "test", "base", traders))
        lead = leader_index(ctx, traders, stop_dt)
        end = PR.ms(win.end)
        for tr in traders:
            s = sigs.get(tr, [])
            eng_s = run_copy(data, PR.scheme_rules(ctx, "S", {tr: 10000.0}, stress, portfolio_limits=False),
                             costs["base"], s)
            eng_u = run_copy(data, PR.scheme_rules(ctx, "U", {tr: 10000.0}, stress), costs["base"], s)
            returns.append((win.origin, tr, eng_s.sleeves[tr].nav / 10000.0 - 1))
            nav_u = [(h["t"], h["nav"]) for h in eng_u.hourly]
            nav_s = [(h["t"], h["nav"]) for h in eng_s.hourly]
            state_s = {h["t"]: RANK[h["state"]] for h in eng_s.hourly}
            months = eng_s.usable_hours[tr] / 720.0
            l1 = [e for e in eng_s.events if e["event"] == "trigger_on" and e["trigger"] == "L1"]
            any_on = {int(e["t"]) for e in eng_s.events if e["event"] == "trigger_on"} | {
                int(e["t"]) for e in eng_s.events if e["event"] == "state_firing" and e.get("reason") == "S3"}
            counts.append((win.origin, tr, len(l1), months))
            tser = data.triggers.get(tr)
            limit = tser.drawdown_limit if tser else None
            for e in l1:
                t = int(e["t"])
                r, d, hz, full = forward_to(nav_u, t, end)
                lr, ld, lstatus = leader_forward(lead.get(tr, []), t, stop)
                fwd_rows.append((win.origin, tr, "after_firing", t, r, d, hz, full))
                hours = sorted(x for x in state_s if x >= t)
                release = next((x for x in hours if state_s[x] < RANK_RO), None)
                spell_end = release if release is not None else (hours[-1] if hours else t)
                s0, s1 = dict(nav_s).get(t), dict(nav_s).get(spell_end)
                u0, u1 = dict(nav_u).get(t), dict(nav_u).get(spell_end)
                diff_usdc = diff_pp = None
                if s0 is not None and s1 is not None and u0 is not None and u1 is not None:
                    diff_usdc = (s1 - s0) - (u1 - u0)
                    diff_pp = s1 / s0 - u1 / u0 if s0 and u0 else None
                before = state_s.get(t - HOUR)
                firings.append({
                    "origin": win.origin, "trader": tr, "t": t,
                    "time_utc": datetime.fromtimestamp(t / 1000, tz=stop_dt.tzinfo).strftime("%Y-%m-%d %H:%M"),
                    "l1_value": float(e["value"]) if e["value"] is not None else None,
                    "l1_threshold": limit, "hist_max_dd": limit / 1.5 if limit is not None else None,
                    "value_over_threshold": float(e["value"]) / limit if limit and e["value"] is not None else None,
                    "state_before_rank": before,
                    "reduce_only_hours": (spell_end - t) / HOUR,
                    "reduce_only_censored_at_window_end": release is None,
                    "u_fwd_return": r, "u_fwd_drawdown": d, "u_fwd_horizon_days": hz, "u_fwd_full_14d": full,
                    "leader_fwd14_return": lr, "leader_fwd14_drawdown": ld, "leader_fwd14_status": lstatus,
                    "copy_minus_twin_spell_usdc": diff_usdc, "copy_minus_twin_spell_pp": diff_pp,
                    "sleeve_nav_at_firing": s0,
                })
            for t, _ in nav_u[::24]:
                if t in any_on:
                    continue
                r, d, hz, full = forward_to(nav_u, t, end)
                if r is not None:
                    fwd_rows.append((win.origin, tr, "matched_no_firing", t, r, d, hz, full))
        print(f"{win.origin} test L1: {len(traders)} copies", flush=True)
    cnt = pl.DataFrame(counts, schema={"origin": pl.Date, "trader": pl.String, "firings": pl.Int64,
                                       "sleeve_months": pl.Float64}, orient="row")
    fwd = pl.DataFrame(fwd_rows, schema={"origin": pl.Date, "trader": pl.String, "kind": pl.String, "t": pl.Int64,
                                         "fwd_return": pl.Float64, "fwd_drawdown": pl.Float64,
                                         "horizon_days": pl.Float64, "full_14d": pl.Boolean}, orient="row")
    fir = pl.DataFrame(firings, infer_schema_length=None) if firings else pl.DataFrame(
        schema={"origin": pl.Date, "trader": pl.String, "t": pl.Int64})
    if fir.height:
        fir = fir.sort("t", "trader")

    def summary(c: pl.DataFrame, f: pl.DataFrame, origin) -> dict:
        per = c.filter(C("sleeve_months") > 0).with_columns(rate=C("firings") / C("sleeve_months"))
        after = f.filter(C("kind") == "after_firing")
        matched = f.filter(C("kind") == "matched_no_firing")
        months = float(c["sleeve_months"].sum())
        n = int(c["firings"].sum())
        return {
            "origin": origin, "trigger": "L1", "firings": n, "sleeve_months": months, "sleeves": c.height,
            "sleeves_with_firing": int((c["firings"] > 0).sum()),
            "rate_per_sleeve_month": n / months if months else None,
            "share_sleeves_above_1": float((per["rate"] > 1).mean()) if per.height else None,  # type: ignore[arg-type]
            "fwd_n": after["fwd_return"].count(), "fwd_full_14d_n": int(after["full_14d"].sum()),
            "fwd_horizon_days_median": after["horizon_days"].median(),
            "fwd_return": after["fwd_return"].mean(), "fwd_drawdown": after["fwd_drawdown"].mean(),
            "false_alarm_share": float((after["fwd_return"] >= 0).mean()) if after.height else None,  # type: ignore[arg-type]
            "matched_n": matched.height, "matched_horizon_days_median": matched["horizon_days"].median(),
            "matched_fwd_return": matched["fwd_return"].mean(),
            "matched_fwd_drawdown": matched["fwd_drawdown"].mean(),
            "f4_pass": n <= months,
            "scope": "pooled_test_windows" if origin is None else "test_window",
        }

    rows = [summary(cnt.filter(C("origin") == o), fwd.filter(C("origin") == o), o)
            for o in sorted(set(cnt["origin"].to_list()))]
    pooled = summary(cnt, fwd, None)
    table = pl.DataFrame(rows + [pooled], infer_schema_length=None)
    out.mkdir(parents=True, exist_ok=True)
    table.write_csv(out / "l1_test_windows.csv")
    fir.write_csv(out / "l1_test_firings.csv")
    fwd.write_parquet(out / "l1_test_forward.parquet")
    cnt.write_parquet(out / "l1_test_counts.parquet")
    by_date = (fir.with_columns(date=C("time_utc").str.slice(0, 10))
               .group_by("date", "origin").agg(firings=pl.len(), addresses=C("trader").n_unique(),
                                                u_fwd_return=C("u_fwd_return").mean(),
                                                leader_fwd14_return=C("leader_fwd14_return").mean(),
                                                copy_minus_twin_spell_usdc=C("copy_minus_twin_spell_usdc").sum())
               .sort("date") if fir.height else pl.DataFrame())
    by_date.write_csv(out / "l1_test_by_date.csv")
    check = pl.DataFrame(returns, schema={"origin": pl.Date, "trader": pl.String, "rerun": pl.Float64},
                         orient="row").join(
        pl.read_csv(out / "variants.csv", try_parse_dates=True).filter(C("variant") == "current")
        .select("origin", "trader", C("window_return").alias("variants")), on=["origin", "trader"], how="full",
        coalesce=True)
    mismatch = check.filter((C("rerun") - C("variants")).abs().fill_null(1.0) > 1e-12).height
    crash = fir.filter(C("time_utc").str.slice(0, 10).is_in(["2025-10-10", "2025-10-11"])).height if fir.height else 0
    result = {
        "scope": "L1 only; all A/B single-sleeve copies, current rules, four development test windows, base",
        "holdout_start": str(stop_dt), "read_after_holdout_start": False,
        "copy_windows": cnt.height, "pooled": pooled,
        "f4_pass": pooled["f4_pass"], "threshold_changed": False,
        "firings_10_11_oct": crash,
        "u_fwd_cut_at_window_end": int(fir.height - fir["u_fwd_full_14d"].sum()) if fir.height else 0,
        "u_fwd_cut_at_holdout_start": int(fir.filter(
            (C("t") + 14 * DAY > stop) & ~C("u_fwd_full_14d")).height) if fir.height else 0,
        "leader_fwd_cut_at_holdout_start": int((fir["leader_fwd14_status"] == "cut_holdout").sum())
        if fir.height else 0,
        "rerun_vs_variants_current_mismatches": mismatch, "rerun_rows": check.height,
    }
    (out / "l1_test_summary.json").write_text(json.dumps(result, indent=2, default=str, sort_keys=True) + "\n",
                                              encoding="utf-8")
    return result


def run(ctx, out: Path | None = None, steps=("calibrate", "variants")) -> Path:
    from arkstream import drift, hlprices
    from arkstream.config import load_yaml
    from arkstream.freeze import guard
    from arkstream.replay_cap import impact_bars

    dr = drift.DriftRules.from_config(ctx.raw)
    stop = PR.midnight(dr.holdout_start)
    guard(ctx, stop)
    out = Path(out) if out else ctx.root / DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    costs, ex = PR.costs_by_scenario(ctx)
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), stop)
    bars = impact_bars(candles, stop, ex["square_root"]["volatility_bars"])
    tree = ctx.root / ctx.raw["selection_v2"]["tradable_dir"]
    if "calibrate" in steps:
        calibrate(ctx, out, bars, costs, ex, tree)
    if "variants" in steps:
        variants(ctx, out, bars, costs, ex, tree, load_yaml("risk.yaml", ctx.root / "config")["variants"])
    if "l1-oos" in steps:
        l1_out_of_sample(ctx, out, bars, costs, ex, tree)
    return out
