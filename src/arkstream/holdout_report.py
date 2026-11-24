"""Phase 5 step P5-6: the window report (pre-registered outputs H1-H6, ADR-0092 item 4) and the decision rule
(D1-D5, ADR-0093), for any (origin, window).

It reads a portfolio-replay tree (`phase5_pair`: S*, U*, G* runs and `pair_summary.csv`) and the Phase 4 v2 outputs
at the origin (the frozen statistic and the categories, `evidence.parquet`, `candidates.parquet`) with the window's
outcome α per address (`test_outcomes.parquet` on a development window; the same function at the holdout, P5-8). The
schema of every table is fixed (`SCHEMA`) and identical across windows (pre-holdout Check 4). On a development
window the decision is computed but labelled "development: not a decision".
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from arkstream.selection_v2_math import spearman

C = pl.col
DEFAULT_OUT = "research/window_report"
HAND_OFF_LIMIT_SHARE = 0.165


def h1_engine(summary: pl.DataFrame, events: dict[str, pl.DataFrame]) -> pl.DataFrame:
    rows = []
    for (config, scenario), g in summary.filter(C("scope") == "combined").group_by("config", "scenario",
                                                                                   maintain_order=True):
        ev = events.get(f"{config}/{scenario}")
        untraced = 0
        if ev is not None and ev.height:
            st = ev.filter(C("event").str.contains("firing|release"))
            untraced = int(st.filter(C("reason").is_null() | (C("reason") == "")).height) if st.height else 0
        faults = int(g["engine_faults"].sum())
        rows.append({"config": config, "scenario": scenario, "completed": True, "engine_faults": faults,
                     "untraced_state_events": untraced, "clean": faults == 0 and untraced == 0})
    return pl.DataFrame(rows).sort("config", "scenario")


def h2_risk(summary: pl.DataFrame, D: float, l_gray: float) -> pl.DataFrame:
    c = summary.filter(C("scope") == "combined")
    out = c.select(
        "config", "scenario", "max_drawdown_hourly", "max_drawdown_usdc", "max_loss_incl_exit_usdc", "worst_day",
        "firings", "state_hours", "lambda_tw_mean", "lambda_set_by", "p5_binding_updates", "p4_passive_breaches",
        "flatten_orders",
        cap_breaches_at_update=C("cap_breaches_at_update") if "cap_breaches_at_update" in c.columns else pl.lit(None),
        loss_cap_hit=C("loss_cap_hit") if "loss_cap_hit" in c.columns else pl.lit(None),
    ).with_columns(
        limit_usdc=pl.when(C("config") == "S").then(pl.lit(HAND_OFF_LIMIT_SHARE * D))
        .when(C("config").str.starts_with("G")).then(pl.lit(l_gray)).otherwise(pl.lit(None)),
    ).with_columns(
        loss_measure_usdc=pl.when(C("config") == "S").then(C("max_drawdown_usdc"))
        .when(C("config").str.starts_with("G")).then(C("max_loss_incl_exit_usdc")),
    ).with_columns(within_limit=C("loss_measure_usdc") <= C("limit_usdc"))
    return out.sort("config", "scenario")


def fill_costs(fills: pl.DataFrame) -> pl.DataFrame:
    """Cost per side of each physical fill (bps of notional): signed fill against the order's anchor plus the fee."""
    f = fills.filter(C("kind") == "physical")
    return f.with_columns(
        cost_bps=(C("quantity").sign() * (C("fill_px") / C("anchor_px") - 1) * 1e4
                  + C("fee") / (C("quantity").abs() * C("fill_px")) * 1e4))


def h3_costs(window_fills: pl.DataFrame, dev_fills: pl.DataFrame, min_orders: int = 30) -> pl.DataFrame:
    """Per coin: this window's median cost per side (S*, base) against the development p90 (model against model)."""
    w = fill_costs(window_fills).group_by("coin").agg(orders=pl.len(), median_cost_bps=C("cost_bps").median())
    d = fill_costs(dev_fills).group_by("coin").agg(dev_orders=pl.len(), dev_p90_bps=C("cost_bps").quantile(0.9),
                                                   dev_median_bps=C("cost_bps").median())
    x = w.join(d, on="coin", how="full", coalesce=True).with_columns(C("orders", "dev_orders").fill_null(0))
    return x.with_columns(
        measured=(C("orders") >= min_orders) & (C("dev_orders") >= min_orders),
        within_p90=C("median_cost_bps") <= C("dev_p90_bps"),
        label=pl.lit("model against model: simulated fills (ADR-0093 item 3)"),
    ).sort("coin")


def h4_returns(summary: pl.DataFrame) -> pl.DataFrame:
    return summary.select("config", "scenario", "scope", "allocation", "raw_return", "alpha_bps_day_ex_funding",
                          "funding_usdc", "fees_usdc", "utilisation", "traded_usdc").with_columns(
        role=pl.lit("reported, not decisive (ADR-0092 H4)")).sort("config", "scenario", "scope")


def statistic_choice(keys: pl.DataFrame) -> tuple[str, float]:
    """ADR-0093 item 4: `m`, or the own-data α when `m` is constant over the measured addresses at the origin."""
    m = keys.filter(C("m").is_not_null() & C("m").is_finite())["m"].to_numpy()
    if m.size >= 3 and float(np.std(m)) > 0:
        return "m", -0.20
    return "alpha", -0.14


def h5_cross_section(evidence: pl.DataFrame, candidates: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    keys = evidence.select("trader", "m", "alpha", "category", "robust", "carry_book").join(
        candidates.select("trader", sel_break_even=pl.when(C("sel_break_even") == "pass").then(True)
                          .when(C("sel_break_even") == "fail").then(False)), on="trader", how="left")
    stat, threshold = statistic_choice(keys)
    j = keys.join(outcomes.select("trader", next_alpha="alpha"), on="trader", how="inner").filter(
        C("next_alpha").is_not_null())
    rows = []
    for k in ("m", "alpha"):
        x = j.filter(C(k).is_not_null() & C(k).is_finite()).sort("trader")
        ic = spearman(x[k].to_numpy(), x["next_alpha"].to_numpy()) if x.height else None
        rows.append({"test": f"ic_{k}", "group": "all", "n": x.height, "value": ic,
                     "note": "D4 statistic" if k == stat else "reported"})
    rows.append({"test": "d4", "group": stat, "n": None, "value": next(r["value"] for r in rows
                                                                       if r["test"] == f"ic_{stat}"),
                 "note": f"threshold {threshold}"})
    for cat in ("E2", "E1", "E0", "E-"):
        g = j.filter(C("category") == cat)
        rows.append({"test": "category_mean_next_alpha", "group": cat, "n": g.height,
                     "value": _mean(g["next_alpha"]), "note": "ordering"})
    for name, col in (("robust", "robust"), ("break_even_pass", "sel_break_even"), ("carry_book", "carry_book")):
        for flag in (True, False):
            g = j.filter(C("category").is_in(["E1", "E2"]) & (C(col) == flag)) if name == "robust" else j.filter(
                C(col) == flag)
            rows.append({"test": f"{name}_mean_next_alpha", "group": str(flag).lower(), "n": g.height,
                         "value": _mean(g["next_alpha"]), "note": "hypothesis"})
    return pl.DataFrame(rows, schema={"test": pl.String, "group": pl.String, "n": pl.Int64, "value": pl.Float64,
                                      "note": pl.String}, orient="row")


def _mean(s: pl.Series) -> float | None:
    v = s.drop_nulls()
    return float(v.sum()) / v.len() if v.len() else None


def h6_binding(summary: pl.DataFrame) -> pl.DataFrame:
    s = summary.filter((C("config") == "S") & (C("scope") != "combined"))
    rows = []
    for r in s.iter_rows(named=True):
        by = json.loads(r["lambda_set_by"] or "{}")
        rows.append({"scenario": r["scenario"], "sleeve": r["scope"], "lambda_tw_mean": r["lambda_tw_mean"],
                     "p2_share": sum(v for k, v in by.items() if k.startswith("P2")),
                     "p5_share": sum(v for k, v in by.items() if k.startswith("P5")),
                     "set_by": r["lambda_set_by"]})
    return pl.DataFrame(rows).sort("scenario", "sleeve")


SCHEMA = {
    "h1_engine": ["config", "scenario", "completed", "engine_faults", "untraced_state_events", "clean"],
    "h2_risk": ["config", "scenario", "max_drawdown_hourly", "max_drawdown_usdc", "max_loss_incl_exit_usdc",
                "worst_day", "firings", "state_hours", "lambda_tw_mean", "lambda_set_by", "p5_binding_updates",
                "p4_passive_breaches", "flatten_orders", "cap_breaches_at_update", "loss_cap_hit", "limit_usdc",
                "loss_measure_usdc", "within_limit"],
    "h3_costs": ["coin", "orders", "median_cost_bps", "dev_orders", "dev_p90_bps", "dev_median_bps", "measured",
                 "within_p90", "label"],
    "h4_returns": ["config", "scenario", "scope", "allocation", "raw_return", "alpha_bps_day_ex_funding",
                   "funding_usdc", "fees_usdc", "utilisation", "traded_usdc", "role"],
    "h5_cross_section": ["test", "group", "n", "value", "note"],
    "h6_binding": ["scenario", "sleeve", "lambda_tw_mean", "p2_share", "p5_share", "set_by"],
}


def decide(tables: dict[str, pl.DataFrame], handoff_nonempty: bool | None, development: bool) -> dict:
    """ADR-0093: CONDITIONAL GO only if D1-D5 all hold; unmeasured fails (ADR-0068)."""
    h1, h2, h3, h5 = tables["h1_engine"], tables["h2_risk"], tables["h3_costs"], tables["h5_cross_section"]
    d1 = bool(h1["clean"].all())
    s = h2.filter((C("config") == "S") & C("scenario").is_in(["base", "stress"]))
    g = h2.filter(C("config").str.starts_with("G") & C("scenario").is_in(["base", "stress"]))
    d2a = bool(s.height == 2 and s["within_limit"].all())
    d2b = bool(g.height >= 2 and g["within_limit"].all() and (g["cap_breaches_at_update"].fill_null(0) == 0).all())
    m3 = h3.filter("measured")
    d3 = bool(m3.height > 0 and m3["within_p90"].all())
    d4row = h5.filter(C("test") == "d4")
    ic = d4row["value"][0] if d4row.height else None
    threshold = float(d4row["note"][0].split()[-1]) if d4row.height else -0.2
    d4 = ic is not None and math.isfinite(ic) and ic > threshold
    d5 = handoff_nonempty
    verdict = all([d1, d2a, d2b, d3, d4, bool(d5)])
    return {"D1": d1, "D2a": d2a, "D2b": d2b, "D3": d3, "D3_coins_measured": m3.height, "D4": d4, "D4_ic": ic,
            "D4_statistic": d4row["group"][0] if d4row.height else None, "D4_threshold": threshold,
            "D5": d5, "decision": "CONDITIONAL GO" if verdict else "NO-GO",
            "label": "development: not a decision" if development else "pre-registered decision (ADR-0093)"}


def report(ctx, origin: date, tree: Path, outcomes: pl.DataFrame, dev_fills: pl.DataFrame, out: Path | None = None,
           development: bool = True, handoff_nonempty: bool | None = None) -> dict[str, pl.DataFrame]:
    from arkstream.config import load_yaml

    risk = load_yaml("risk.yaml", ctx.root / "config")
    D, l_gray = float(risk["scheme"]["notional_D_usdc"]), float(risk["gray"]["loss_cap_usdc"])
    summary = pl.read_csv(tree / "pair_summary.csv", try_parse_dates=True).filter(C("origin") == origin)
    folder = tree / f"origin={origin}"
    events = {}
    for p in sorted(folder.glob("config=*/scenario=*/events.parquet")):
        events[f"{p.parent.parent.name[7:]}/{p.parent.name[9:]}"] = pl.read_parquet(p)
    fills = pl.read_parquet(folder / "config=S" / "scenario=base" / "fills.parquet")
    sv = ctx.root / "research/selection_v2" / f"origin={origin}"
    tables = {
        "h1_engine": h1_engine(summary, events),
        "h2_risk": h2_risk(summary, D, l_gray),
        "h3_costs": h3_costs(fills, dev_fills),
        "h4_returns": h4_returns(summary),
        "h5_cross_section": h5_cross_section(pl.read_parquet(sv / "evidence.parquet"),
                                             pl.read_parquet(sv / "candidates.parquet"), outcomes),
        "h6_binding": h6_binding(summary),
    }
    for name, cols in SCHEMA.items():
        if tables[name].columns != cols:
            raise ValueError(f"{name}: schema {tables[name].columns} differs from the fixed schema {cols}")
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        for name, t in tables.items():
            t.write_csv(out / f"{name}.csv")
        dec = decide(tables, handoff_nonempty, development)
        (out / "decision.json").write_text(json.dumps(dec, indent=2, default=str) + "\n", encoding="utf-8")
    return tables


def run_development(ctx, tree: Path | None = None, out: Path | None = None) -> Path:
    """P5-6: the report on all four development windows, schema checked identical."""
    from arkstream import drift
    from arkstream.freeze import guard
    from arkstream.portfolio_replay import midnight

    dr = drift.DriftRules.from_config(ctx.raw)
    guard(ctx, midnight(dr.holdout_start))
    tree = tree or ctx.root / "research/portfolio_replay"
    out = out or ctx.root / DEFAULT_OUT
    origins = [o for o in dr.origin_dates if o < dr.holdout_start]
    dev = pl.concat([pl.read_parquet(tree / f"origin={o}" / "config=S" / "scenario=base" / "fills.parquet")
                     for o in origins], how="diagonal_relaxed")
    schemas = []
    for o in origins:
        outcomes = pl.read_parquet(ctx.root / "research/selection_v2" / f"origin={o}" / "test_outcomes.parquet")
        tables = report(ctx, o, tree, outcomes, dev, out / f"origin={o}", development=True)
        schemas.append({k: v.columns for k, v in tables.items()})
    if any(s != schemas[0] for s in schemas):
        raise ValueError("window report schema differs across development windows")
    (out / "schema.json").write_text(json.dumps(SCHEMA, indent=2) + "\n", encoding="utf-8")
    return out
