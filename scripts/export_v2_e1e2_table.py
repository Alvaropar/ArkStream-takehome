"""The 3 Dec E1/E2 table of Phase 4 v2 (`decision/phase-4-v2-3dec-e1-e2.csv`) from the published selection outputs.

One row per E1 or E2 address at the origin: α and its parts in bps/day per USDC of gross (α excludes funding under
ADR-0084; `alpha_incl_funding_bps` is the former definition), the posterior, the robustness variants, the static /
timing split, exposure, S2/S3 status, hand-off and placebo. Sorted E2 first, then by α descending.
Usage: uv run python scripts/export_v2_e1e2_table.py [origin]
"""

import sys
from pathlib import Path

import polars as pl

C = pl.col
BPS = 10_000


def main() -> None:
    origin = sys.argv[1] if len(sys.argv) > 1 else "2025-12-03"
    d = Path("research/selection_v2") / f"origin={origin}"
    ev = pl.read_parquet(d / "evidence.parquet")
    st = pl.read_parquet(d / "statistics.parquet").select(
        "trader", "alpha_static", "alpha_timing", "top3_coinday_share", "exposed_days", "exposed_weeks", "util_mean")
    cand = pl.read_parquet(d / "candidates.parquet").select("trader", "s2", "s3", "s3_failed", "eligible")
    placebo_path = Path("research/selection_v2/placebo.csv")
    pb = (pl.read_csv(placebo_path).filter(C("origin") == origin).select("trader", "placebo_pass")
          if placebo_path.exists() else pl.DataFrame(schema={"trader": pl.String, "placebo_pass": pl.Boolean}))
    x = (ev.filter(C("category").is_in(["E1", "E2"])).join(st, on="trader", how="left")
         .join(cand, on="trader", how="left").join(pb, on="trader", how="left"))
    out = x.select(
        "trader", "category",
        *[(C(c) * BPS).round(2).alias(f"{c}_bps") for c in ("alpha", "s", "alpha_incl_funding", "alpha_funding")],
        "carry_book", (C("m") * BPS).round(2).alias("m_bps"), C("p_post").round(3),
        (C("alpha_ex_best_week") * BPS).round(2).alias("alpha_ex_best_week_bps"), "robust",
        C("p_own_ex_best_week").round(3), (C("alpha_ex_crash") * BPS).round(2).alias("alpha_ex_crash_bps"),
        C("best_week_share").round(3),
        *[(C(c) * BPS).round(2).alias(f"{c}_bps") for c in ("alpha_static", "alpha_timing")],
        C("top3_coinday_share").round(3), "exposed_days", "exposed_weeks", C("util_mean").round(3),
        "s2", "s3", "s3_failed", "eligible", "placebo_pass",
    ).sort(C("category") == "E1", -C("alpha_bps"), "trader")
    name = "phase-4-v2-3dec-e1-e2.csv" if origin == "2025-12-03" else f"phase-4-v2-{origin}-e1-e2.csv"
    out.write_csv(Path("decision") / name)
    print(out.height, "rows;", out["category"].value_counts().sort("category").rows())


if __name__ == "__main__":
    main()
