"""The follower replay under the only sizing policy, frozen reference equity (ADR-0119).

`run` writes under one folder (default `research/replay_frozen/`):

* the shared inputs, prepared without simulating the dynamically sized original model (`replay.run(simulate=False)`):
  `spread_estimates`, `drift_cells`, `drift_hold_bands`, `valuation_marks` and each window's `universe.parquet`;
* the frozen full stack `*_sqrt_cap_part_ns_sweep_frozen` on the nine windows, with `sensitivity_*.csv`;
* `stress_coverage.csv`: the stress results under both coverage measures, the stress check and the worst-measured
  sensitivity (ADR-0122), for every stress-regime scenario: `stress` (5 s, measured p99) and `severe` (the old
  60 s / 300 s, labelled sensitivity; ADR-0150);
* `cost_surface.csv`: the base cost surface (ADR-0117), frozen only;
* `leader_size/`: the leader-size drift study (ADR-0088, forced fills excluded); it does not depend on sizing.

No dynamic variant is run (ADR-0119); the archived comparison is `research/replay_sizing/`. The holdout test
window is never computed.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from arkstream import drift
from arkstream.config import load_yaml
from arkstream.replay_market import midnight

C = pl.col
MODEL = "part_ns_sweep_frozen"
SUFFIX = "_sqrt_cap_part_ns_sweep_frozen"
STRESS = "stress" + SUFFIX
MEASURES = {"broad_adr0115": "priced_share_broad", "pricing_failures_adr0122": "priced_share"}


def run(ctx, out: Path | None = None) -> Path:
    from arkstream import replay_capture, replay_surface
    from arkstream.replay import run as replay_run
    from arkstream.replay_sensitivity import run_sensitivities
    from arkstream.replay_size import study

    out = Path(out) if out else ctx.root / "research/replay_frozen"
    replay_run(ctx, output=out, simulate=False)
    run_sensitivities(ctx, output=out, models=(MODEL,), original=out)
    stress_coverage(ctx, out).write_csv(out / "stress_coverage.csv")
    replay_surface.run(ctx, out, policies=("frozen",))
    study(ctx, out / "leader_size")
    replay_capture.run(ctx, out)  # ADR-0162: capture and market-relative tables
    return out


def stress_scenarios(ctx) -> list[str]:
    """The scenarios priced under the stress regime (ADR-0150: stress and severe), in config order."""
    from arkstream.replay_orders import resolve_scenarios

    sc = resolve_scenarios(load_yaml("execution.yaml", ctx.root / "config")["scenarios"])
    return [name for name, st in sc.items() if st["costs"] == "stress"]


def stress_rows(ctx, out: Path, scenario: str = "stress") -> pl.DataFrame:
    """Gate-passing address-windows of one stress-regime scenario in the development tests (never the holdout)."""
    dr = drift.DriftRules.from_config(ctx.raw)
    origins = [midnight(o) for o in dr.origin_dates]
    stop = midnight(dr.holdout_start)
    parts = []
    for origin in origins:
        if origin >= stop:
            continue
        folder = out / f"origin={origin.date()}" / "window=test" / f"scenario={scenario}{SUFFIX}"
        path = folder / "address_summary.parquet"
        parts.append(
            pl.read_parquet(path)
            .filter("all_gates_pass")
            .select("trader", "measurement", "priced_share", "priced_share_broad", "copy_return", "max_drawdown",
                    "exhausted", "orders", "unpriced", "unpriced_broad", "cap_headroom")
            .with_columns(origin=pl.lit(str(origin.date())))
        )
    return pl.concat(parts).sort("origin", "trader")


def coverage_table(rows: pl.DataFrame, min_share: float, ladder: float) -> pl.DataFrame:
    """ADR-0122 safeguards, per test origin and pooled, for each coverage measure:

    1. windows measured, mean stress return over the measured windows and positives;
    2. the stress check: measured, not exhausted and maximum drawdown no worse than the ladder step; an unmeasured
       window fails it and stays in the denominator;
    3. each unmeasured window at the worst measured stress return of its test origin (none if the test has no
       measured window); the stress check is unchanged by it.
    """
    out = []
    for measure, share in MEASURES.items():
        r = rows.with_columns(measured=C(share) >= min_share)
        if measure == "pricing_failures_adr0122" and not r["measured"].equals(r["measurement"] == "measured"):
            raise ValueError("measurement flag disagrees with the ADR-0122 priced share")
        r = r.with_columns(
            ret=pl.when("measured").then("copy_return"),
            check=pl.when(~C("measured"))
            .then(pl.lit("fail_unmeasured"))
            .when(C("exhausted") | (C("max_drawdown") < ladder) | C("max_drawdown").is_null())
            .then(pl.lit("fail_loss"))
            .otherwise(pl.lit("pass")),
        )
        worst = r.filter("measured").group_by("origin").agg(worst_measured_return=C("ret").min())
        r = r.join(worst, on="origin", how="left").with_columns(
            ret_imputed=pl.when("measured").then("ret").otherwise("worst_measured_return")
        )
        stats = [
            pl.len().alias("gate_passers"),
            C("measured").sum().alias("measured"),
            (~C("measured")).sum().alias("unmeasured"),
            (C("ret") > 0).sum().alias("positive"),
            C("ret").mean().alias("mean_return"),
            C("ret").min().alias("min_return"),
            (C("check") == "pass").sum().alias("stress_check_pass"),
            (C("check") == "fail_loss").sum().alias("stress_check_fail_loss"),
            (C("check") == "fail_unmeasured").sum().alias("stress_check_fail_unmeasured"),
            (~C("measured") & C("ret_imputed").is_not_null()).sum().alias("imputed"),
            (~C("measured") & C("ret_imputed").is_null()).sum().alias("not_imputable"),
            C("ret_imputed").mean().alias("mean_return_worst_imputed"),
            (C("ret_imputed") > 0).sum().alias("positive_worst_imputed"),
            C(share).mean().alias("mean_priced_share"),
            C(share).min().alias("min_priced_share"),
            C("orders").sum().alias("intents"),
            C("unpriced" if share == "priced_share" else "unpriced_broad").sum().alias("unpriced_intents"),
            C("cap_headroom").sum().alias("cap_headroom_intents"),
        ]
        by = r.group_by("origin", maintain_order=True).agg(*stats, C("worst_measured_return").first())
        total = r.select(*stats).with_columns(origin=pl.lit("all_tests"),
                                             worst_measured_return=pl.lit(None, pl.Float64))
        out.append(pl.concat([by, total.select(by.columns)]).with_columns(measure=pl.lit(measure)))
    return pl.concat(out).select("measure", "origin", pl.exclude("measure", "origin"))


def stress_coverage(ctx, out: Path) -> pl.DataFrame:
    """ADR-0122 table for each stress-regime scenario (stress, then severe), with a leading `scenario` column."""
    rules = load_yaml("execution.yaml", ctx.root / "config")["replay"]
    ladder = load_yaml("risk.yaml", ctx.root / "config")["drawdown_ladder"]["reduce_only"]
    tables = [
        coverage_table(stress_rows(ctx, out, name), float(rules["stress_min_priced_share"]), float(ladder))
        .select(pl.lit(name).alias("scenario"), pl.all())
        for name in stress_scenarios(ctx)
    ]
    return pl.concat(tables)
