"""Check 1: coverage of the ADR-A0136 coin filter at the 3 Dec origin (training window only; no holdout data).

For each coin: A/B addresses that traded it, valued / unvalued follower and benchmark (address, coin) PnL observations,
the reason for each unvalued one (funding unknown, closing mark unavailable), the capture ratio exactly as
`selection_coins.coin_set` computes it, and the capture recomputed on addresses valued on both sides. Also the share of
the coin's traded notional that sits in unvalued observations, as a size measure for the missing part.

Reads `research/replay_frozen` (the tree `replay_coinfilter.coin_sets` uses). Writes
`research/audit/coin_filter_coverage_2025-12-03.csv` (all coins) and prints the kept ones.
Usage: uv run python scripts/audit_coin_filter_coverage.py [origin]
"""

import sys

sys.path.insert(0, "src")
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from arkstream import selection as S
from arkstream import selection_coins as SC
from arkstream.config import load_context
from arkstream.replay_book import ledger
from arkstream.replay_capture import BENCH
from arkstream.replay_market import DAY, midnight, ms

C = pl.col
KEY = ["trader", "coin"]


def obs(ctx, origin: date, scenario: str | None) -> pl.DataFrame:
    """`selection_coins.coin_pnl` per (trader, coin) with the reason for a null kept, plus traded notional."""
    end_ms = ms(midnight(origin))
    d = S.window_dir(ctx, origin, "training") / BENCH if scenario is None else S.scenario_dir(
        ctx, origin, "training", scenario)
    orders = pl.read_parquet(d / "follower_orders.parquet", columns=[
        "trader", "coin", "status", "quantity", "fill_px", "fee", "ack_ms", "decision_ms", "batch", "oid"])
    f = ledger(orders, datetime.fromtimestamp(end_ms / 1000, tz=UTC))
    fund = pl.read_parquet(d / "funding_payments.parquet", columns=["trader", "coin", "payment"])
    marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet")
    me = marks.filter(C("boundary") == end_ms // DAY).select("coin", m_end="mark")
    book = f.group_by(KEY).agg(pos=C("pos").sort_by("ack_ms", "decision_ms", "batch", "oid").last(),
                               notional=C("turnover").sum())
    fu = fund.group_by(KEY).agg(unknown=C("payment").null_count())
    o = (book.join(fu, on=KEY, how="full", coalesce=True).join(me, on="coin", how="left")
         .with_columns(C("unknown").fill_null(0), C("notional", "pos").fill_null(0.0)))
    o = o.with_columns(funding_unknown=C("unknown") > 0, mark_missing=(C("pos").abs() > 1e-10) & C("m_end").is_null())
    ref = SC.coin_pnl(f, fund, marks, end_ms).select(*KEY, "pnl")
    o = o.join(ref, on=KEY, how="left")
    # the reasons reproduce the module's nulls exactly
    assert o.filter(C("pnl").is_null() != (C("funding_unknown") | C("mark_missing"))).height == 0
    return o.select(*KEY, "notional", "funding_unknown", "mark_missing", "pnl")


def main() -> None:
    origin = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2025, 12, 3)
    ctx = load_context()
    raw = {**ctx.raw, "selection": {**ctx.raw["selection"], "replay_dir": "research/replay_frozen"}}
    base = type(ctx)(raw=raw, root=ctx.root)
    rules = S.Rules.from_config(base.raw, "rule_b_coin_filter")
    official = SC.coin_set(base, origin, rules)

    fol, ben = obs(base, origin, rules.scenario), obs(base, origin, None)
    both = fol.join(ben, on=KEY, how="full", coalesce=True, suffix="_b")
    # a side with no row for (trader, coin) never traded it: PnL exactly 0 (valued), not missing
    unval_f = C("notional").is_not_null() & C("pnl").is_null()
    unval_b = C("notional_b").is_not_null() & C("pnl_b").is_null()
    both = both.with_columns(ok_both=~(unval_f | unval_b))

    agg = both.group_by("coin").agg(
        addresses=C("trader").n_unique(),
        fol_valued=C("pnl").is_not_null().sum(), fol_unvalued=unval_f.sum(),
        fol_funding_unknown=C("funding_unknown").fill_null(False).sum(),
        fol_mark_missing=C("mark_missing").fill_null(False).sum(),
        ben_valued=C("pnl_b").is_not_null().sum(),
        ben_unvalued=unval_b.sum(),
        ben_funding_unknown=C("funding_unknown_b").fill_null(False).sum(),
        ben_mark_missing=C("mark_missing_b").fill_null(False).sum(),
        fol_pnl=C("pnl").sum(), ben_pnl=C("pnl_b").sum(),
        fol_unvalued_notional_share=(C("notional").filter(unval_f).sum()
                                     / C("notional").sum()),
        ben_unvalued_notional_share=(C("notional_b").filter(unval_b).sum()
                                     / C("notional_b").sum()),
        fol_pnl_both=C("pnl").filter("ok_both").sum(),
        ben_pnl_both=C("pnl_b").filter("ok_both").sum(),
    )
    agg = agg.join(official.select("coin", "kept", capture_official="capture", follower_pnl_official="follower_pnl",
                                   benchmark_pnl_official="benchmark_pnl"), on="coin", how="full", coalesce=True)
    agg = agg.with_columns(
        capture=pl.when(C("ben_pnl") > 0).then(C("fol_pnl") / C("ben_pnl")),
        capture_both_valued=pl.when(C("ben_pnl_both") > 0).then(C("fol_pnl_both") / C("ben_pnl_both")),
        kept_both_valued=C("coin").is_in(list(rules.filter_always)) | (
            (C("ben_pnl_both") >= rules.filter_min_benchmark_usdc)
            & (C("fol_pnl_both") / C("ben_pnl_both") >= rules.filter_min_capture)),
    )
    # the recomputed capture must equal the module's
    chk = agg.filter(C("capture_official").is_not_null()).select(
        ((C("capture") - C("capture_official")).abs().max()).alias("d")).item()
    assert chk is None or chk < 1e-9, chk
    agg = agg.with_columns(always=C("coin").is_in(list(rules.filter_always))).sort(
        "kept", "coin", descending=[True, False])
    out = Path("research/audit")
    out.mkdir(parents=True, exist_ok=True)
    cols = ["coin", "kept", "always", "addresses", "fol_valued", "fol_unvalued", "fol_funding_unknown",
            "fol_mark_missing", "ben_valued", "ben_unvalued", "ben_funding_unknown", "ben_mark_missing",
            "fol_unvalued_notional_share", "ben_unvalued_notional_share", "fol_pnl", "ben_pnl", "capture",
            "capture_both_valued", "kept_both_valued"]
    agg.select(cols).write_csv(out / f"coin_filter_coverage_{origin}.csv", float_precision=6)
    with pl.Config(tbl_rows=80, tbl_cols=30, tbl_width_chars=260, fmt_str_lengths=10, float_precision=3):
        print(agg.filter("kept").select(cols))
        print("kept coins:", agg.filter("kept").height,
              "| any unvalued (fol or ben):", agg.filter("kept", (C("fol_unvalued") + C("ben_unvalued")) > 0).height,
              "| decision changes when both-valued only:",
              agg.filter(C("kept").fill_null(False) != C("kept_both_valued").fill_null(False))["coin"].to_list())
        print(agg.filter(~C("kept").fill_null(False), (C("fol_unvalued") + C("ben_unvalued")) > 0).select(cols))


if __name__ == "__main__":
    main()
