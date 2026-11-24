"""ADR-0067/0068 impact on Phase 2: pass counts by category per origin, before (saved gate tables) and after.

Before: `research/audit/phase2_before_adr0067/gates_<origin>.parquet` (the run under ADR-0066 grades' predecessor
universe, i.e. the published Phase 2). After: `research/leader/origin=<origin>/gates.parquet`. Universes differ by
the ADR-0066 grade changes, so both the universe and the passers are shown, and every address whose all-gates status
changes is listed with the reason. Writes research/audit/gate_change.csv and gate_change_addresses.csv.
Usage: uv run python scripts/audit_gate_change.py [before_dir_name] [output_suffix]
  e.g. `phase2_before_adr0069 _adr0069` compares gate 7 v2 against the ADR-0067 run.
"""

import sys

sys.path.insert(0, "src")
from pathlib import Path

import polars as pl

from arkstream.leader_risk import CATEGORIES, GATE_COLS

C = pl.col
ORIGINS = ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]
OUT = Path("research/audit")


def main() -> None:
    before_dir = sys.argv[1] if len(sys.argv) > 1 else "phase2_before_adr0067"
    suffix = sys.argv[2] if len(sys.argv) > 2 else ""
    rows, moved = [], []
    for o in ORIGINS:
        before = pl.read_parquet(OUT / before_dir / f"gates_{o}.parquet")
        after = pl.read_parquet(f"research/leader/origin={o}/gates.parquet")
        r = {"origin": o, "universe_before": before.height, "universe_after": after.height,
             "pass_before": int(before["all_gates_pass"].sum()), "pass_after": int(after["all_gates_pass"].sum())}
        for cat in CATEGORIES:
            r[cat] = int((after[cat] == "pass").sum())
        for g in GATE_COLS:
            if g in before.columns:
                r[f"{g}_before"] = int((before[g] == "pass").sum())
            r[f"{g}_after"] = int((after[g] == "pass").sum())
        rows.append(r)
        j = before.select("trader", pass_before="all_gates_pass", failed_before="gates_failed").join(
            after.select("trader", "all_gates_pass", "gates_failed", "gates_unmeasured", "style_flags"),
            on="trader", how="full", coalesce=True)
        moved.append(j.filter(C("pass_before").fill_null(False) != C("all_gates_pass").fill_null(False))
                     .with_columns(origin=pl.lit(o)))
    OUT.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(rows)
    df.write_csv(OUT / f"gate_change{suffix}.csv")
    mv = pl.concat(moved, how="diagonal_relaxed")
    mv.write_csv(OUT / f"gate_change_addresses{suffix}.csv")
    with pl.Config(tbl_cols=20, tbl_width_chars=240, tbl_rows=60, fmt_str_lengths=90):
        print(df.select("origin", "universe_before", "universe_after", "pass_before", "pass_after",
                        *CATEGORIES).transpose(include_header=True))
        print(mv.select("origin", C("trader").str.slice(0, 8), "pass_before", "all_gates_pass", "failed_before",
                        "gates_failed", "gates_unmeasured", "style_flags"))


if __name__ == "__main__":
    main()
