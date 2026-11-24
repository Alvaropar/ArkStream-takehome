"""ADR-0066 impact: grades under the old rule (0.01 USDC match share + offset CV <= 0.25) and the new one, per origin.

Builds the Milestone 1 quality report at each origin (data up to it only) and at the cutoff, with the current code
(which reports both the old and the new reconciliation columns), and re-derives the old grade from the old columns.
Writes research/audit/grade_change.csv (counts) and grade_change_addresses.csv (every address whose grade moves).
Usage: uv run python scripts/audit_grade_change.py
"""

import sys

sys.path.insert(0, "src")
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from arkstream.config import load_context
from arkstream.pipeline import build, load_inputs

C = pl.col
ORIGINS = ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]
OTHER_C = ("no_snapshots", "no_fills", "continuity_break", "equity_near_zero", "too_many_unusable_days")


def old_grade(r: pl.DataFrame) -> pl.DataFrame:
    """The pre-ADR-0066 rule on the same report: scope conditions from pnl_match_share and pnl_offset_cv."""
    reasons = C("grade_reason").str.split(";").list.eval(
        pl.element().filter(~pl.element().is_in(["unstable_scope_mismatch", "scope_offset_too_large",
                                                 "stable_scope_offset:use_rebuilt_book"])))
    mismatch = (C("pnl_match_share") < 0.99).fill_null(False)
    stable = (C("pnl_offset_cv").is_not_null() & (C("pnl_offset_cv") <= 0.25)).fill_null(False)
    other_c = reasons.list.eval(pl.element().is_in(list(OTHER_C))).list.any()
    other_b = reasons.list.eval(~pl.element().is_in(list(OTHER_C)) & (pl.element() != "")).list.any()
    return r.with_columns(old_grade=pl.when(other_c | (mismatch & ~stable)).then(pl.lit("C"))
                          .when(other_b | (mismatch & stable)).then(pl.lit("B")).otherwise(pl.lit("A")))


def main() -> None:
    ctx = load_context()
    inputs = load_inputs(ctx)
    counts, moved = [], []
    for label in [*ORIGINS, "cutoff"]:
        asof = ctx.cutoff if label == "cutoff" else datetime.fromisoformat(label).replace(tzinfo=UTC)
        r = old_grade(build(ctx, inputs, asof).tables["quality_report"])
        for old, new, n in r.group_by("old_grade", "grade").len().rows():
            counts.append({"asof": label, "old": old, "new": new, "n": n})
        moved.append(r.filter(C("old_grade") != C("grade")).select(
            pl.lit(label).alias("asof"), "trader", "old_grade", "grade", "grade_reason", "median_equity",
            "pnl_match_share", "pnl_offset_cv", "material_match_share", "offset_level", "offset_mad",
            "offset_match_share", "offset_shift"))
        print(label, r.group_by("old_grade").len().sort("old_grade").rows(),
              "->", r.group_by("grade").len().sort("grade").rows(), flush=True)
    out = Path("research/audit")
    out.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(counts).sort("asof", "old", "new").write_csv(out / "grade_change.csv")
    pl.concat(moved).write_csv(out / "grade_change_addresses.csv", float_precision=6)


if __name__ == "__main__":
    main()
