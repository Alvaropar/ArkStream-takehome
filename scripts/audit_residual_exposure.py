"""Residual exposure: the copy still holds a coin after the leader is flat in it (development data only).

Frozen replay with the executed coin filter (`research/replay_coinfilter`), base scenario, the four development test
windows and the 3 Dec training window. Rows of `follower_orders` (leader-triggered and cap resize legs) are taken per
(address, coin) in decision order; the follower position is the running sum of filled quantities; the leader position
is `pos_after`. A row leaves a **residual** when the leader is flat after it and the follower is not.

Per window: leader-flat events, the share leaving a residual and why (the flattening row's status, or a clipped fill),
residual notional x hours against all follower exposure x hours, and the residual's PnL to the next row in that
(address, coin), priced at the next row's anchor (a Hyperliquid leader price); the last interval of a window is
counted but not priced. Approximation: positions change at the decision time, not the acknowledgement 1.2 s later.

Writes research/audit/residual_exposure.csv. Usage: uv run python scripts/audit_residual_exposure.py
"""

import sys

sys.path.insert(0, "src")
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

C = pl.col
TREE = Path("research/replay_coinfilter")
SCEN = "scenario=base_sqrt_cap_part_ns_sweep_frozen"
WINDOWS = [("2025-10-08", "test"), ("2025-10-22", "test"), ("2025-11-05", "test"), ("2025-11-19", "test"),
           ("2025-12-03", "training")]
KEY = ["trader", "coin"]


def one(origin: str, window: str, basket: list[str] | None) -> dict:
    o = pl.read_parquet(TREE / f"origin={origin}" / f"window={window}" / SCEN / "follower_orders.parquet", columns=[
        "trader", "coin", "decision_ms", "seq", "batch", "resize_leg", "pos_after", "status", "quantity",
        "requested_qty", "anchor_px", "ref_px"])
    if basket is not None:
        o = o.filter(C("trader").is_in(basket))
    start = datetime.fromisoformat(origin).replace(tzinfo=UTC)
    end_ms = int(((start + timedelta(days=14)) if window == "test" else start).timestamp() * 1000)
    o = (o.sort(*KEY, "decision_ms", "seq", "batch")
         .with_columns(q=pl.when(C("status") == "filled").then(C("quantity")).otherwise(0.0).fill_null(0.0),
                       px=pl.coalesce("anchor_px", "ref_px"))
         .with_columns(fpos=C("q").cum_sum().over(KEY))
         .with_columns(fpos=pl.when(C("fpos").abs() < 1e-12).then(0.0).otherwise(C("fpos")),
                       next_ms=C("decision_ms").shift(-1).over(KEY).fill_null(end_ms),
                       next_px=C("px").shift(-1).over(KEY))
         .with_columns(hours=(C("next_ms") - C("decision_ms")) / 3_600_000,
                       expo=C("fpos").abs() * C("px")))
    leader_flat = (C("pos_after").abs() < 1e-12) & ~C("resize_leg")
    resid = leader_flat & (C("fpos") != 0)
    o = o.with_columns(flat=leader_flat, resid=resid,
                       clipped=(C("status") == "filled") & (C("quantity").abs() < C("requested_qty").abs() - 1e-12))
    r = o.filter("resid")
    why = (r.with_columns(why=pl.when("clipped").then(pl.lit("filled_but_clipped")).otherwise(C("status")))
           .group_by("why").len().sort("len", descending=True))
    priced = r.filter(C("next_px").is_not_null())
    return {
        "origin": origin, "window": window, "addresses": "basket" if basket else "all A/B",
        "leader_flat_events": o["flat"].sum(), "residual_events": r.height,
        "residual_share": r.height / max(o["flat"].sum(), 1),
        "residual_notional_hours": float((r["expo"] * r["hours"]).sum()),
        "all_exposure_notional_hours": float((o["expo"] * o["hours"]).sum()),
        "residual_pnl_usdc_priced": float((priced["fpos"] * (priced["next_px"] - priced["px"])).sum()),
        "residual_unpriced_events": r.height - priced.height,
        "median_residual_usdc": float(r["expo"].median()) if r.height else None,
        "median_residual_hours": float(r["hours"].median()) if r.height else None,
        "why": "; ".join(f"{w} {n}" for w, n in why.rows()),
    }


def main() -> None:
    rows = []
    for origin, window in WINDOWS:
        rows.append(one(origin, window, None))
        dec = pl.read_csv(f"research/selection/origin={origin}/variant=rule_b_coin_filter/decisions.csv")
        basket = dec.filter(C("decision") == "selected")["trader"].to_list()
        if window == "test" and basket:
            rows.append(one(origin, window, basket))
    df = pl.DataFrame(rows).with_columns(
        residual_exposure_share=C("residual_notional_hours") / C("all_exposure_notional_hours"))
    out = Path("research/audit")
    out.mkdir(parents=True, exist_ok=True)
    df.write_csv(out / "residual_exposure.csv", float_precision=4)
    with pl.Config(tbl_cols=20, tbl_width_chars=250, fmt_str_lengths=120, float_precision=3, tbl_rows=20):
        print(df.drop("why"))
        print(df.select("origin", "addresses", "why"))


if __name__ == "__main__":
    main()
