"""Wide daily-TWR matrices (rows = addresses, columns = UTC days) for the training period only.
Values are daily returns in percent (0.5 = +0.5% that day), i.e. daily TWR x 100; compound as prod(1 + v/100).

Origin 2025-12-03 (the holdout origin): its training window, 2025-07-27..2025-12-02, contains every earlier
window. Nothing at or after 2025-12-03 is read or written; the holdout stays closed.

1. research/leader_book_daily_twr_training.csv: the leader's rebuilt core-perp book (Phase 2), calendar-day book
   PnL divided by the leader's account equity at the day start (research/leader/origin=2025-12-03/book_daily,
   column book_ret). Blank = no return (before the first active day, no equity snapshot, or unpriced hours).
2. research/copy_daily_twr_training.csv: the follower copy of that leader, frozen E_ref sizing, base scenario
   (1.2 s delay, receive 392 ms, fees, spread, sqrt impact, alt drift floor, 1.5x cap, 0.5% participation;
   scenario=base_sqrt_cap_part_ns_sweep_frozen), daily_copy_twr.daily_twr. Blank = no return (missing marks).
   Days before the copy holds a position are a flat account (0.0), not blank. Days before 2025-09-08 are blank:
   the replay cannot price any copy order before the execution history starts (aggTrades and drift cells begin
   at estimate_window.start; orders there end as no_drift_cell / no_eligible_aggtrade), so the 0.0 the replay
   writes there is "not executable", not a flat return.

Missing values are never imputed. Usage: uv run python scripts/export_twr_matrices.py
"""

import sys

sys.path.insert(0, "src")
from datetime import date
from pathlib import Path

import polars as pl

ORIGIN = "2025-12-03"
LAST = date(2025, 12, 2)
COPY_FIRST = date(2025, 9, 8)  # config/decision_context.yaml drift.estimate_window.start
LEADER = Path(f"research/leader/origin={ORIGIN}/book_daily.parquet")
COPY = Path(f"research/replay_frozen/origin={ORIGIN}/window=training/"
            "scenario=base_sqrt_cap_part_ns_sweep_frozen/daily_copy_twr.parquet")
OUT = Path("research")


def wide(df: pl.DataFrame, value: str, days: list[date], traders: list[str]) -> pl.DataFrame:
    long = df.select("trader", "day", (pl.col(value) * 100).alias("v")).filter(pl.col("day") <= LAST)
    assert long.select(pl.struct("trader", "day").is_duplicated().any()).item() is False
    w = long.with_columns(pl.col("day").cast(pl.String)).pivot(on="day", index="trader", values="v")
    cols = [d.isoformat() for d in days]
    for c in cols:
        if c not in w.columns:
            w = w.with_columns(pl.lit(None, pl.Float64).alias(c))
    base = pl.DataFrame({"trader": traders})
    return base.join(w, on="trader", how="left").select("trader", *cols).rename({"trader": "address"})


def main() -> None:
    leader = pl.read_parquet(LEADER)
    copy = pl.read_parquet(COPY)
    copy = copy.with_columns(pl.when(pl.col("day") >= COPY_FIRST).then(pl.col("daily_twr")).alias("daily_twr"))
    assert copy["day"].max() <= LAST and leader["day"].max() <= LAST, "training data must end before the origin"
    traders = sorted(set(copy["trader"]) | set(leader["trader"]))
    days = pl.date_range(copy["day"].min(), LAST, "1d", eager=True).to_list()
    for name, df, col in [("leader_book_daily_twr_training.csv", leader, "book_ret"),
                          ("copy_daily_twr_training.csv", copy, "daily_twr")]:
        w = wide(df, col, days, traders)
        w.write_csv(OUT / name, float_precision=8)
        n = w.drop("address").select(pl.sum_horizontal(pl.all().is_not_null())).sum().item()
        print(f"{name}: {w.height} addresses x {len(days)} days ({days[0]}..{days[-1]}), {n} non-blank cells")


if __name__ == "__main__":
    main()
