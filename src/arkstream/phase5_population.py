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
    return out
