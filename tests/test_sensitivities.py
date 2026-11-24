from datetime import timedelta

import numpy as np
import polars as pl
import pytest
from conftest import need
from test_replay import BASE, END, RULES, START, T, example

from arkstream.replay_cap import BAR, MINUTE, CapBook, MinuteMarks, cap_legs, impact_bars
from arkstream.replay_orders import batches, execute, square_root_bps
from arkstream.replay_sensitivity import canonical

C = pl.col


def test_sqrt_price_and_missing_inputs():
    assert square_root_bps(10000, 1e6, 0.02, 1) == pytest.approx(20)
    assert square_root_bps(40000, 1e6, 0.02, 1) == pytest.approx(40)
    assert square_root_bps(10000, None, 0.02, 1) is None
    assert square_root_bps(10000, 1e6, 0, 1) == 0
    f = (
        example()
        .head(1)
        .drop("status", "quantity", "intended_notional", "shortfall_bps", "fill_px", "impact_bps", "fee")
    )
    frame = f.with_columns(volume_daily=pl.lit(1e6), sigma_daily=pl.lit(0.02))
    base = execute(frame, dict(BASE, sqrt_y=1), RULES)
    stress = execute(frame, dict(BASE, sqrt_y=1, impact="3x_base"), RULES)
    expected = square_root_bps(abs(base["quantity"][0]) * base["ref_px"][0], 1e6, 0.02, 1)
    assert base["impact_bps"][0] == pytest.approx(expected)
    assert stress["impact_bps"][0] == pytest.approx(3 * expected)
    missing = frame.with_columns(sigma_daily=pl.lit(None, pl.Float64))
    assert execute(missing, dict(BASE, sqrt_y=1), RULES)["status"][0] == "missing_sqrt_inputs"
    assert execute(missing, dict(BASE, sqrt_y=1, impact="none"), RULES)["impact_bps"][0] == 0


def test_candle_clocks_and_internal_gaps():
    times = [START + timedelta(hours=4 * i) for i in range(47)]
    close = np.exp(4 + np.cos(np.arange(47) / 6) * 0.1)
    raw = pl.DataFrame(
        {
            "coin": ["A"] * 47,
            "ts": times,
            "price": close,
            "volume": np.arange(1, 48),
            "n_trades": [1] * 47,
            "src_file": ["source"] * 47,
        }
    )
    now = times[42]

    def observed(data, decision):
        return impact_bars(data, decision, 42).tail(1).row(0, named=True)

    row = observed(raw, now)
    assert row["volume_daily"] == pytest.approx(sum(close[37:43] * np.arange(38, 44)))
    assert row["sigma_daily"] == pytest.approx(np.std(np.diff(np.log(close[:43])), ddof=1) * np.sqrt(6))
    assert row["bar_ms"] == T + 42 * BAR and row["volatility_start_ms"] == T
    assert observed(raw, now - timedelta(milliseconds=1))["sigma_daily"] is None
    poisoned = raw.with_columns(
        price=pl.when(C("ts") > now).then(1e12).otherwise("price"),
        volume=pl.when(C("ts") > now).then(10**9).otherwise("volume"),
    )
    assert observed(poisoned, now) == row
    full_panel = impact_bars(poisoned, times[-1], 42)
    assert full_panel.filter(C("bar_ms") == row["bar_ms"]).row(0, named=True) == row
    gap = raw.filter(C("ts") != times[40])
    assert observed(gap, now)["volume_daily"] is None and observed(gap, now)["sigma_daily"] is None
    assert observed(raw.filter(C("ts") != times[1]), now)["sigma_daily"] is None


def test_scale_all_visible_targets_and_minimum_after_scaling():
    marks = MinuteMarks(T, ms_end := T + 24 * 3600000, ["A", "B"])
    marks.values["A"][:] = 100.0
    marks.values["B"][:] = 100.0
    rows = [
        ("w", "A", 1, 1, T + 1000, 1, 11, 100.0, "buy", False, 300.0),
        ("w", "B", 2, 2, T + 2000, 2, 12, 100.0, "buy", False, 0.15),
        ("w", "A", 3, 3, ms_end + 1, 3, 13, 90000.0, "buy", False, 1e7),
    ]
    ev = pl.DataFrame(
        rows,
        schema=["trader", "coin", "seq", "oid", "event_ms", "src_row", "tid", "price", "side", "is_maker", "pos_after"],
        orient="row",
    )
    snaps = pl.DataFrame({"trader": ["w"], "equity": [10000.0], "frozen": [False], "eq_ms": [T], "equity_row": [22]})
    b = batches(ev, 250, 250, START, END)
    legs = cap_legs(b, ev, snaps, marks, {"A", "B"}, 10000, 15000, 250, START, END)
    decision = legs.filter(C("signal") == 1).sort("coin")
    scale = 15000 / 30015
    assert decision["cap_scale"].to_list() == pytest.approx([scale, scale])
    assert decision["capped_target"].to_list() == pytest.approx([300 * scale, 0.15 * scale])
    assert decision["resize_leg"].to_list() == [True, False]
    assert decision["target_row"].to_list() == [1, 2]
    assert decision["source_rows"].to_list() == [[2], [2]]
    assert decision["mark_ms"].max() <= T + 2500
    candidate = decision.filter(C("coin") == "B").with_columns(
        equity=pl.lit(10000.0),
        frozen=pl.lit(False),
        ack_ms=C("decision_ms") + 500,
        ref_px=pl.lit(100.0),
        price_reason=pl.lit(""),
        half_bps=pl.lit(1.0),
        bar_volume_usdc=pl.lit(1e6),
        mean_bps=pl.lit(None, pl.Float64),
        mid_L=pl.lit(100.0),
    )
    got = execute(candidate, BASE, dict(RULES, cap_usdc=15000), cap_marks=marks).row(0, named=True)
    assert got["uncapped_target"] * 100 > 10 and got["quantity"] * 100 < 10 and got["status"] == "below_minimum"

    marks.values["A"][0] = np.nan
    missing = cap_legs(b, ev, snaps, marks, {"A", "B"}, 10000, 15000, 250, START, END)
    assert missing["cap_scale"].null_count() == missing.height
    assert missing["capped_target"].null_count() == missing.height


def test_minute_mark_publication_and_exact_staleness_boundary():
    marks = MinuteMarks(T, T + 2 * MINUTE, ["A"])
    marks.values["A"][:] = [100.0, np.nan, 120.0]
    assert marks.at("A", T - 1) is None
    assert marks.at("A", T + MINUTE) == 100
    assert marks.source_ms("A", T + MINUTE, 100) == T
    assert marks.at("A", T + MINUTE + 1) is None
    assert marks.at("A", T + 2 * MINUTE - 1) is None
    assert marks.at("A", T + 2 * MINUTE) == 120


def test_pending_reduction_cannot_finance_growth_or_hide_drifted_exposure():
    marks = MinuteMarks(T, T + 2 * MINUTE, ["A", "B"])
    marks.values["A"][:] = [100, 120, 120]
    marks.values["B"][:] = 100
    book = CapBook(marks, 15000)
    book.advance(T)
    book.submit("A", 150, T + 10, 1, True, 15000, 100)
    book.advance(T + 20)
    reduction = book.reservation("A", -50, 100)
    book.submit("A", -50, T + 100, 2, False, reduction, 100)
    assert book.reservation("B", 50, 100) == 20000
    book.advance(T + 101)
    assert book.size("A", 100) == -50 and book.gross == 15000
    book.advance(T + MINUTE)
    assert book.gross == 18000 and book.reservation("B", 1, 100) > book.gross
    book.submit("A", -50, T + MINUTE + 1, 3, True, book.reservation("A", -50, 120), 120)
    book.advance(T + MINUTE + 2)
    assert book.gross == 12000 and book.reservation("B", 30, 100) == 15000
    assert canonical("optimistic", "sqrt") == "optimistic" and canonical("optimistic", "sqrt_cap") == "optimistic_cap"


@pytest.mark.data
def test_published_sensitivity_ledgers(ctx):
    root = ctx.root / "research/replay"
    need(root / "origin=2025-10-08" / "window=test" / "scenario=base_sqrt" / "follower_orders.parquet",
         "run the sensitivity replay to inspect its saved ledgers")
    from arkstream.drift import DriftRules
    from arkstream.replay_market import midnight, ms

    dates = DriftRules.from_config(ctx.raw).origin_dates
    comparisons = pl.read_csv(root / "sensitivity_returns.csv", try_parse_dates=True)
    assert comparisons.select("origin", "scenario", "variant").unique().height == comparisons.height == 4 * 3 * 7
    assert sorted(comparisons["origin"].unique()) == list(dates[:-1])
    assert not (root / f"origin={dates[-1]}" / "window=test").exists()
    for i, origin in enumerate(dates):
        for window in ["training", "test"] if i + 1 < len(dates) else ["training"]:
            folder = root / f"origin={origin}" / f"window={window}"
            boundary = ms(midnight(origin if window == "training" else dates[i + 1]))
            for label in (
                "base_sqrt",
                "stress_sqrt",
                "optimistic_cap",
                "base_cap",
                "stress_cap",
                "base_sqrt_cap",
                "stress_sqrt_cap",
                *(
                    f"{sc}_sqrt_cap_{m}"
                    for sc in ("optimistic", "base", "stress")
                    for m in ("part", "part_ns", "part_ns_sweep")
                ),
            ):
                output = folder / f"scenario={label}"
                orders = pl.scan_parquet(output / "follower_orders.parquet")
                filled = C("status") == "filled"
                bad = (
                    (C("ack_ms") >= boundary)
                    | (C("decision_ms") >= C("ack_ms"))
                    | (C("bar_ms") > C("decision_ms"))
                    | (C("eq_ms") > C("decision_ms"))
                    | (C("visible_ms") > C("decision_ms"))
                    | (C("source_rows").list.len() == 0)
                    | (C("source_event_ms").list.max() + 250 > C("decision_ms"))
                    | (filled & (C("quantity").abs() * C("fill_px") < 10))
                )
                if "sqrt" in label and label.startswith("optimistic"):
                    bad |= filled & (C("impact_bps") != 0)  # optimistic has zero impact
                elif "sqrt" in label:
                    mult = 3 if label.startswith("stress") else 1
                    expected = (
                        10000 * mult * C("sigma_daily") * (C("quantity").abs() * C("ref_px") / C("volume_daily")).sqrt()
                    )
                    bad |= filled & (expected.is_null() | ((C("impact_bps") - expected).abs() > 1e-8))
                if "cap" in label:
                    scale = C("cap_scale")
                    bad |= (
                        (C("mark_ms") > C("decision_ms"))
                        | (C("decision_ms") - C("mark_ms") > MINUTE)
                        | (scale <= 0)
                        | (scale > 1)
                        | (C("uncapped_gross_usdc") * scale > 15000 + 1e-8)
                        | ((C("capped_target") - C("uncapped_target") * scale).abs() > 1e-8)
                        | (filled & (scale.is_null() | C("decision_mark").is_null()))
                        | (C("reserved_gross_after") > pl.max_horizontal(15000, "reserved_gross_before") + 1e-8)
                    )
                if "_part" in label:  # ADR-0035: the filled notional stays inside the order budget
                    bad |= filled & (
                        C("order_budget_usdc").is_null()
                        | (C("quantity").abs() * C("fill_px") > C("order_budget_usdc") + 1e-6)
                    )
                if "_part_ns" in label:  # never larger than the leader
                    bad |= C("uncapped_target").abs() > C("pos_after").abs() + 1e-9
                    bad |= filled & (C("order_budget_usdc") > C("leader_notional") + 1e-6)
                if label.endswith("_sweep"):  # ADR-0036 anchor by scenario
                    rule = {"optimistic": "leader_first_px", "base": "leader_vwap", "stress": "leader_deepest"}
                    col = rule[label.split("_")[0]]
                    swept = C("anchor_rule") != "first_fill"
                    bad |= swept & ((C("anchor_px") - C(col)).abs() > 1e-9)
                    bad |= ~swept & ~C("resize_leg") & ((C("anchor_px") - C("leader_first_px")).abs() > 1e-9)
                assert not orders.select(bad.any()).collect().item(), (origin, window, label)
                keys = orders.select(pl.struct("trader", "coin", "ack_ms", "decision_ms", "batch", "oid").alias("key"))
                order_keys = keys.collect()["key"]
                assert order_keys.is_sorted() and order_keys.n_unique() == len(order_keys), (origin, window, label)
                filled_cash = orders.filter(filled).group_by("trader").agg(
                    cash=(-C("quantity") * C("fill_px") - C("fee")).sum()
                )
                daily = pl.scan_parquet(output / "daily_copy_twr.parquet").group_by("trader").agg(
                    book_cash=C("cash").sum()
                )
                errors = daily.join(filled_cash, on="trader", how="left").filter(
                    (C("book_cash") - C("cash").fill_null(0)).abs() > 1e-6
                )
                assert errors.collect().is_empty(), (origin, window, label)
