"""What would change if the Phase 4 ranking key used mark-to-market NAV instead of completed trips (development only).

Current key (ADR-A0131): p20 of 2,000 entry-week block-bootstrap means of the follower's net return per completed
training trip (min 10 trips, 4 weeks). Alternative (illustrative, not adopted): p20 of 2,000 calendar-week
block-bootstrap means of the follower's **daily NAV return** (`daily_copy_twr.daily_twr`, base, coin-filter tree),
from the first day the copy holds exposure to the origin (min 20 days, 4 weeks; days without a valid NAV return
dropped and counted). Same seeds, same percentile. Open positions are marked to market every day, so nothing is
censored.

Inputs are the stored selection candidates (the published rule, before the ADR-0066/0067 rerun), so the comparison
holds the pools fixed and changes only the key. Persistence: Spearman of each key at an origin with the copy's
compounded return over the next 14-day test window (base, coin-filter tree), over every A/B address with both.
Writes research/audit/mtm_key_comparison.csv. Usage: uv run python scripts/compare_mtm_key.py
"""

import sys

sys.path.insert(0, "src")
from datetime import date
from pathlib import Path

import polars as pl

from arkstream import selection_stats as st
from arkstream.selection import trader_rng

C = pl.col
ORIGINS = ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]
TREE = Path("research/replay_coinfilter")
SCEN = "scenario=base_sqrt_cap_part_ns_sweep_frozen"
DAY_MS = 86_400_000


def mtm_keys(origin: str) -> pl.DataFrame:
    d = pl.read_parquet(TREE / f"origin={origin}" / "window=training" / SCEN / "daily_copy_twr.parquet",
                        columns=["trader", "day", "gross", "daily_twr"])
    o = date.fromisoformat(origin)
    rows = []
    for (trader,), g in d.sort("trader", "day").group_by("trader", maintain_order=True):
        active = g.filter(C("gross") > 0)
        if active.is_empty():
            rows.append((trader, 0, 0, 0, None, None))
            continue
        g = g.filter(C("day") >= active["day"].min())
        valid = g.drop_nulls("daily_twr")
        r = valid["daily_twr"].to_numpy()
        ms = (valid["day"].cast(pl.Datetime("ms")).dt.epoch("ms")).to_numpy()
        blocks = st.entry_week_blocks(ms)
        nb = int(blocks.max()) + 1 if len(blocks) else 0
        key = mean = None
        if len(r) >= 20 and nb >= 4:
            means = st.block_bootstrap(r, blocks, 2000, trader_rng(20251008, trader, o))
            key, mean = st.quantile(means, 0.20), float(r.mean())
        rows.append((trader, len(r), g.height - valid.height, nb, mean, key))
    return pl.DataFrame(rows, schema={"trader": pl.String, "mtm_days": pl.Int64, "mtm_days_invalid": pl.Int64,
                                      "mtm_weeks": pl.Int64, "mtm_mean_daily": pl.Float64,
                                      "mtm_key": pl.Float64}, orient="row")


def test_return(origin: str) -> pl.DataFrame:
    p = TREE / f"origin={origin}" / "window=test" / SCEN / "daily_copy_twr.parquet"
    if not p.exists():
        return pl.DataFrame(schema={"trader": pl.String, "test_return": pl.Float64})
    d = pl.read_parquet(p, columns=["trader", "daily_twr"])
    return d.group_by("trader").agg(test_return=pl.when(C("daily_twr").null_count() == 0)
                                    .then((1 + C("daily_twr")).product() - 1))


def main() -> None:
    out, persist = [], []
    for o in ORIGINS:
        c = pl.read_parquet(f"research/selection/origin={o}/variant=rule_b_coin_filter/candidates.parquet",
                            columns=["trader", "eligible", "decision", "trips", "blocks", "mean_net", "key"])
        x = c.join(mtm_keys(o), on="trader", how="left").join(test_return(o), on="trader", how="left").with_columns(
            origin=pl.lit(o),
            selectable_trip=C("eligible") & (C("key") > 0).fill_null(False),
            selectable_mtm=C("eligible") & (C("mtm_key") > 0).fill_null(False))
        out.append(x)
        for name in ("key", "mtm_key"):
            for scope, f in (("all A/B", x), ("eligible", x.filter("eligible"))):
                v = f.drop_nulls([name, "test_return"])
                rho = st.spearman(v[name].to_numpy(), v["test_return"].to_numpy()) if v.height >= 3 else None
                persist.append({"origin": o, "key": name, "scope": scope, "n": v.height, "spearman_test": rho})
    df = pl.concat(out)
    Path("research/audit").mkdir(parents=True, exist_ok=True)
    df.write_csv("research/audit/mtm_key_comparison.csv", float_precision=6)
    pl.DataFrame(persist).write_csv("research/audit/mtm_key_persistence.csv", float_precision=4)
    both = df.drop_nulls(["key", "mtm_key"])
    with pl.Config(tbl_rows=60, tbl_cols=20, tbl_width_chars=230):
        print("all A/B with both keys:", both.height, "rank corr trip vs MTM key:",
              round(st.spearman(both["key"].to_numpy(), both["mtm_key"].to_numpy()) or float("nan"), 3),
              "| measured: trip", df["key"].is_not_null().sum(), "MTM", df["mtm_key"].is_not_null().sum())
        print(df.filter("eligible").select(
            "origin", C("trader").str.slice(0, 6), "decision", "trips", (C("key") * 1e4).round(1).alias("trip_key_bps"),
            "mtm_days", "mtm_weeks", (C("mtm_mean_daily") * 1e4).round(1).alias("mtm_mean_bps_day"),
            (C("mtm_key") * 1e4).round(1).alias("mtm_key_bps_day"), "selectable_trip", "selectable_mtm",
            (C("test_return") * 100).round(2).alias("test_ret_pct")))
        print(pl.DataFrame(persist).pivot(on="key", index=["origin", "scope"], values="spearman_test"))


if __name__ == "__main__":
    main()
