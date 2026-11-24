"""Diagnostic (not a rule change): gate 7 v2 with check 7b computed without intervals that carry a recorded external
flow (|d_net_deposit| > 0). 7a (rank), 7c (slope) and 7d (tracking) stay as published (ADR-0069).

Why: 0x971f's 7b failure comes from two withdrawals recorded in `net_deposit` without a matching equity fall inside the
interval, which inflate the account return by exactly the flow (trial log, ADR-0069 result). This asks what Phase 4
v2 hands to Phase 5 if 7b ignored such intervals. The Phase 2 gates are re-applied in memory to the stored evidence and
`selection_v2.run` reads them (same mechanism as `diag_loosen_evidence.py`); output in
research/audit/diag_gate7_flows/. Published outputs are not touched.
Usage: uv run python scripts/diag_gate7_flows.py
"""

import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from pathlib import Path

import polars as pl

from arkstream import leader_book as lb
from arkstream import leader_risk as lk
from arkstream import selection_v2 as V2
from arkstream.config import load_context

C = pl.col
ORIGINS = ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]
OUT = Path("research/audit/diag_gate7_flows")


def reflag(ctx, o: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    rules = ctx.raw["leader"]
    book = rules["book"]
    d = ctx.root / "research/leader" / f"origin={o}"
    ev = pl.read_parquet(d / "evidence.parquet")
    x = pl.read_parquet(d / "book_vs_account.parquet").filter(C("fit_eligible") & C("usable"))
    noflow = x.filter(C("d_net_deposit").fill_null(0).abs() == 0)
    gap = lb.agreement_v2(noflow, rules).select("trader", gap_lower_noflow="xc_gap_rate_lower_bps",
                                                gap_rate_noflow="xc_gap_rate_bps")
    flows = x.group_by("trader").agg(flow_intervals=(C("d_net_deposit").fill_null(0).abs() > 0).sum())
    ev = ev.join(gap, on="trader", how="left").join(flows, on="trader", how="left")
    lo, hi = book["slope_band"]
    flag = (pl.when(C("agreement_n").fill_null(0) < book["min_intervals"]).then(pl.lit("too_few_intervals"))
            .when(C("xc_corr").is_nan() | C("xc_corr").is_null()).then(pl.lit("no_variation"))
            .when(C("xc_spearman_lower").fill_null(-1.0) < book["min_corr"]).then(pl.lit("disagree_rank"))
            .when(C("gap_lower_noflow").is_null()).then(pl.lit("gap_unmeasured"))
            .when(C("gap_lower_noflow") > book["max_gap_bps_per_day"]).then(pl.lit("disagree_gap"))
            .when(~C("xc_ts_slope").is_between(lo, hi).fill_null(False)).then(pl.lit("disagree_slope"))
            .when(C("xc_gap_std") > book["max_tracking_gap_std"]).then(pl.lit("disagree_tracking"))
            .otherwise(pl.lit("ok")))
    new = ev.with_columns(xc_flag_published=C("xc_flag")).with_columns(xc_flag=flag)
    moved = new.filter(C("xc_flag") != C("xc_flag_published")).select(
        "trader", "xc_flag_published", "xc_flag", "xc_gap_rate_bps", "gap_rate_noflow", "xc_gap_rate_lower_bps",
        "gap_lower_noflow", "flow_intervals").with_columns(origin=pl.lit(o))
    return lk.apply_gates(new.drop("xc_flag_published", "gap_lower_noflow", "gap_rate_noflow", "flow_intervals"),
                          rules), moved


def main() -> None:
    ctx = load_context()
    tables, moves = {}, []
    for o in ORIGINS:
        g, mv = reflag(ctx, o)
        tables[str((ctx.root / "research/leader" / f"origin={o}" / "evidence.parquet").resolve())] = g
        moves.append(mv)
    real = pl.read_parquet

    def read_parquet(source, *args, **kwargs):
        key = str(Path(source).resolve()) if isinstance(source, (str, Path)) else None
        if key in tables:
            t = tables[key]
            return t.select(kwargs["columns"]) if kwargs.get("columns") else t
        return real(source, *args, **kwargs)

    OUT.mkdir(parents=True, exist_ok=True)
    pl.concat(moves).write_csv(OUT / "gate7_moves.csv")
    print("Phase 2 passes:", [int(t["all_gates_pass"].sum()) for t in tables.values()], flush=True)
    pl.read_parquet = read_parquet
    try:
        V2.run(ctx, out=OUT, verbose=False)
    finally:
        pl.read_parquet = real


if __name__ == "__main__":
    main()
