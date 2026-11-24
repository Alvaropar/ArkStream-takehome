from datetime import date, timedelta

import polars as pl
import pytest
from conftest import need
from pit_check import _differs, replay_event_violations

from arkstream import drift
from arkstream.replay import delay_results, windows
from arkstream.replay_book import completed_trips, funding_entries, summaries, value_book
from arkstream.replay_market import DAY, DIRECT, midnight, ms, trade_queries
from arkstream.replay_orders import Parameters, batches, execute, order_inputs, quotes
from arkstream.replay_spreads import pair_estimates

START = midnight(date(2025, 10, 22))
END = START + timedelta(days=1)
T = ms(START)
BASE = {"fee_bps": 4.5, "half_spread_bps": {"majors": 1.0, "other": 5.0}, "impact": "linear"}
RULES = {
    "allocation_usdc": 10000.0,
    "min_notional_usdc": 10.0,
    "thin_volume_usdc": 1e6,
}


def parameters(include_own=True):
    cells = [(START.date(), p, c, "all", 10_000, 1.0, 30) for p in ("development", "stress") for c in DIRECT]
    if include_own:
        cells.extend([(START.date(), p, "ALT", "all", 300_000, 4.0, 30) for p in ("development", "stress")])
    return Parameters(
        pl.DataFrame(
            cells, schema=["origin", "period", "coin", "band", "horizon_ms", "mean_bps", "measured"], orient="row"
        )
    )


def example(coin="BTC", pos=2.0, maker=False, ideal=False, future=False, scenario="base", outcome="pass", delay=None,
            settings=None, bar_volume=1e7):
    h = 0 if ideal else 10_000 if delay is None else delay  # ms (ADR-0058); (normal, thin) for the thin-coin rule
    name = "unattainable_passing" if ideal else scenario
    zero = {"fee_bps": 0, "half_spread_bps": {"majors": 0, "other": 0}, "impact": "none"}
    settings = zero if ideal else settings or BASE
    times = [T + 3590000, T + 3590200, T + 3601000]
    rows = [
        (
            "a",
            coin,
            4 if i < 2 else 5,
            i,
            t,
            i + 40,
            i + 50,
            100.0 + i,
            "buy" if i < 2 else "sell",
            maker,
            pos / 2 if i == 0 else pos if i == 1 else 0.0,
        )
        for i, t in enumerate(times)
    ]
    if future:
        rows.append(("a", coin, 5, 9, ms(END) + 1, 100, 900, 1e9, "buy", False, 10000.0))
    ev = pl.DataFrame(
        rows,
        schema=["trader", "coin", "oid", "seq", "event_ms", "src_row", "tid", "price", "side", "is_maker", "pos_after"],
        orient="row",
    )
    b = batches(ev, 0 if ideal else 250, 0 if ideal else 250, START, END, ideal)
    snap = pl.DataFrame(
        {
            "trader": ["a", "a"],
            "eq_ms": [T, T + DAY + 1],
            "equity": [10000.0, 1e-8 if future else 10000.0],
            "equity_row": [1, 2],
            "frozen": [False, False],
        }
    )
    bar = pl.DataFrame({"coin": [coin], "bar_ms": [T], "bar_volume_usdc": [bar_volume]})
    checks = pl.DataFrame({"coin": [coin], "outcome": [outcome]})
    mapping = pl.DataFrame(
        {"coin": [coin], "valid_from": [START.date()], "valid_to": [END.date()], "price_factor_hl_per_binance": [1.0]}
    )
    tape = []
    for i, t in enumerate(times):
        tape.append((coin, t, i * 2, t, 200.0 + i, "archive"))
        for k, d in enumerate(sorted(set(h)) if isinstance(h, tuple) else [h] if h else []):
            tape.append((coin, t + d, i * 2 + 1 if k == 0 else 100 + i * 10 + k, t + d, 202.0 + i, "archive"))
    tape = pl.DataFrame(
        tape, schema=["coin", "query", "agg_trade_id", "transact_time", "price", "archive"], orient="row"
    )
    bands = pl.DataFrame({"origin": [START.date()], "trader": ["a"], "band": ["all"]})
    spread = pl.DataFrame({"coin": [coin], "known_at": [END], "cs_half_bps": [9999.0]})
    x = order_inputs(b, snap, bar, checks, mapping, tape, bands, [START.date()], spread, RULES, START, END, h)
    return execute(quotes(x, name, settings, parameters()), settings, RULES, ideal)


def portfolio(orders):
    uni = pl.DataFrame({"trader": ["a"], "leader_return": [0.01], "hold_band": ["1-6h"]})
    marks = pl.DataFrame({"coin": ["BTC"], "boundary": [T // DAY + 1], "mark": [100.0]})
    funding = pl.DataFrame(
        {
            "coin": ["BTC"],
            "hour": [(T + 3600000) // 3600000],
            "known_ms": [T + 3600100],
            "proxy": [100.0],
            "funding_rate": [0.001],
        }
    )
    daily, fund, f = value_book(orders, uni, marks, funding, START, END, 10000)
    summary = summaries(daily, orders, uni, 10000)
    return {
        "orders": orders,
        "daily": daily,
        "funding": fund,
        "summary": summary,
        "bands": completed_trips(f, fund, uni),
    }


def test_direct_ratio_mid_anchor_cost_sign_and_source_keys():
    o = example()
    r = o.row(0, named=True)
    assert r["quantity"] == 2 and r["source_rows"] == [40, 41] and r["source_tids"] == [50, 51]
    assert r["b0_ms"] == r["event_ms"] and r["m"] == 1 and r["mid_adjust_bps"] == -1
    assert r["ref_px"] == pytest.approx(100 * (1 - 0.0001) * 202 / 200)
    assert r["removed_basis_bps"] == 10000
    assert r["fill_px"] > r["ref_px"] and r["fee"] == pytest.approx(r["quantity"] * r["fill_px"] * 0.00045)
    assert o["fill_px"][1] < o["ref_px"][1]
    assert example(maker=True)["mid_L"][0] == pytest.approx(100.01)
    assert example(pos=0.09)["status"][0] == "below_minimum"
    assert example(pos=0.1)["status"][0] == "filled"
    # A decision exactly at the minimum may cross below it before the acknowledgement.
    tiny = o.head(1).with_columns(pos_after=pl.lit(0.1), ref_px=pl.lit(99.0))
    rejected = execute(
        tiny.drop("quantity", "intended_notional", "impact_bps", "fill_px", "fee", "status", "shortfall_bps"),
        BASE,
        RULES,
    )
    assert rejected["status"][0] == "below_minimum_at_ack" and rejected["fee"][0] is None


def test_parameterised_paths_and_missing_stress():
    assert example("ALT")["mean_bps"][0] == 4  # ADR-0048: base = max(four-coin proxy 1, own 300 s 4, 0)
    assert example("ALT", scenario="optimistic")["mean_bps"][0] == 1  # optimistic keeps the proxy
    assert example("ALT", scenario="stress")["mean_bps"][0] == 4
    assert example("ALT", delay=300_000)["method"][0] == "coin_approximate"
    assert example("ALT", outcome="fail")["status"][0] == "failed_price_check"
    assert example("ALT", outcome="no_binance")["status"][0] == "no_binance_mapping"
    p = parameters(False)
    assert p.lookup(START.date(), "stress", "ALT", "missing", 10_000)[0] is None
    assert p.lookup(date(2025, 10, 8), "stress", "ALT", "all", 60_000)[-1] == "stress_sample_unavailable"


def test_zero_cost_benchmark_and_funding_after_publication():
    o = example(ideal=True)
    assert o["fill_px"].to_list() == [100.0, 101.0, 102.0] and o["quantity"].to_list() == [1.0, 1.0, -2.0]
    tabs = portfolio(o)
    assert tabs["daily"]["pre_equity"][0] == 10003.0
    assert tabs["daily"]["equity"][0] == pytest.approx(10002.8)
    assert tabs["funding"]["payment"][0] == pytest.approx(-0.2)
    payment = tabs["funding"]
    from arkstream.replay_book import ledger

    led = ledger(o, END)
    future = payment.select("coin", "hour", "proxy", "funding_rate").with_columns(known_ms=pl.lit(ms(END) + 100))
    assert funding_entries(led, future, END)["payment"].null_count() == 1
    assert tabs["bands"]["completed"][0] == 1


def test_event_time_invariance_and_seeded_leaks():
    tables = portfolio(example())
    other = portfolio(example(future=True))
    assert not [name for name in tables if _differs(tables[name], other[name])]
    o = tables["orders"]
    assert replay_event_violations(o, ms(END), 250) == []
    assert "execution_print_clock" in replay_event_violations(o.with_columns(b1_ms=pl.col("event_ms")), ms(END), 250)
    leak = o.with_columns(source_event_ms=pl.concat_list(pl.col("source_event_ms"), pl.col("decision_ms") + 1))
    assert "unseen_source" in replay_event_violations(leak, ms(END), 250)


def test_holdout_guard_and_delay_bracket(ctx):
    rules = drift.DriftRules.from_config(ctx.raw)
    with pytest.raises(drift.HoldoutLeak):
        trade_queries(ctx, pl.DataFrame(), rules, midnight(rules.holdout_start) + timedelta(milliseconds=1))
    splits = list(windows(rules.origin_dates, rules.est_start, rules.holdout_start))
    assert len(splits) == 9 and splits[-1][1] == "training" and max(w[3] for w in splits) == rules.holdout_start
    g = pl.DataFrame({"trader": ["a"] * 6, "delay_ms": [1000, 1200, 5000, 10_000, 60_000, 300_000],
                      "copy_return": [0.01, 0.008, 0.006, 0.005, -0.01, 0.02]})
    expected = ("a", 10_000, 60_000, "crossing_bracket", 10.0, 60.0)
    assert delay_results(g.with_columns(filled=pl.lit(1))).row(0) == expected
    early = delay_results(g.with_columns(filled=pl.lit(1), copy_return=pl.Series([0.01, -0.001, 0.0, 0, 0, 0])))
    assert early.row(0) == ("a", 1000, 1200, "crossing_bracket", 1.0, 1.2)  # 1.2 s is a bracket edge, not 1 s
    assert delay_results(g.with_columns(filled=pl.lit(0)))["break_even_delay_status"][0] == "unmeasured"


def test_spread_pair_known_constant_mid():
    import numpy as np

    high, low = np.array([101.0]), np.array([99.0])
    cs, s2 = pair_estimates(high, low, high, high, low)
    assert cs.item() == pytest.approx(0.02)
    assert s2.item() == pytest.approx(4 * np.log(1.01) ** 2)


def test_verified_tape_backward_lookup_id_tie_and_staleness(ctx, tmp_path):
    import zipfile
    from dataclasses import replace

    from arkstream.config import Context
    from arkstream.provenance import sha256_file

    # Deliberately reverse tied IDs. A trade one millisecond after a query cannot enter its result.
    rel = "BTCUSDT/BTCUSDT-aggTrades-2025-10-22.zip"
    path = tmp_path / rel
    path.parent.mkdir()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "t.csv",
            "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
            + "".join(f"{i},{p},1,1,1,{t},false\n" for i, p, t in [(4, 204, T), (2, 202, T), (5, 205, T + 10001)]),
        )
    (tmp_path / "MANIFEST.csv").write_text(
        f"symbol,date,file,published_sha256\nBTCUSDT,2025-10-22,{rel},{sha256_file(path)}\n"
    )
    local = Context({**ctx.raw, "inputs": {**ctx.raw["inputs"], "aggtrades_dir": "."}}, tmp_path)
    rules = replace(drift.DriftRules.from_config(ctx.raw), aggtrades_symbols={"BTC": "BTCUSDT"})
    events = pl.DataFrame(
        {
            "symbol": ["BTC"] * 3,
            "ts": [START, START + timedelta(milliseconds=1001), START + timedelta(milliseconds=10001)],
        }
    )
    tape = trade_queries(local, events, rules, END)
    observed = dict(tape.select("query", "agg_trade_id").rows())
    assert observed[T] == 4 and observed[T + 1000] == 4 and observed[T + 10001] == 5
    assert T + 1001 not in observed and T + 10000 not in observed


@pytest.mark.data
def test_published_replay_windows_and_accounting(ctx):
    root = ctx.root / "research/replay"
    need(root / "origin=2025-10-08" / "window=test" / "scenario=base" / "follower_orders.parquet",
         "run the replay to inspect saved ledgers")
    rules = drift.DriftRules.from_config(ctx.raw)
    counts = pl.read_csv(root / "economic_screen.csv", try_parse_dates=True)
    assert counts.height == 27
    assert not (root / f"origin={rules.holdout_start}" / "window=test").exists()
    for origin, window in counts.select("origin", "window").unique().rows():
        end = origin if window == "training" else rules.origin_dates[rules.origin_dates.index(origin) + 1]
        for scenario in ("optimistic", "base", "stress"):
            folder = root / f"origin={origin}" / f"window={window}" / f"scenario={scenario}"
            # Project the audit columns so the test also works on larger ledgers.
            k = pl.col
            o = pl.read_parquet(
                folder / "follower_orders.parquet",
                columns=[
                    "trader",
                    "event_ms",
                    "decision_ms",
                    "eq_ms",
                    "ack_ms",
                    "last_visible_ms",
                    "b0_ms",
                    "b1_ms",
                    "status",
                    "price_source",
                    "quantity",
                    "fill_px",
                    "fee",
                    "mid_L",
                    "ref_px",
                    "b0",
                    "b1",
                ],
            )
            assert o["ack_ms"].max() < ms(midnight(end))
            assert o.filter((k("eq_ms") > k("decision_ms")) | (k("decision_ms") >= k("ack_ms"))).is_empty()
            filled = o.filter(k("status") == "filled")
            assert filled.filter(k("quantity").abs() * k("fill_px") < 10).is_empty()
            direct = filled.filter(k("price_source") == "binance_aggtrade")
            assert direct.filter(
                (k("b0_ms") > k("event_ms"))
                | (k("b1_ms") <= k("last_visible_ms"))
                | (k("b1_ms") > k("ack_ms"))
                | ((k("ref_px") / k("mid_L") - k("b1") / k("b0")).abs() > 1e-12)
            ).is_empty()
            cash = filled.group_by("trader").agg(net=(-k("quantity") * k("fill_px") - k("fee")).sum())
            d = pl.read_parquet(folder / "daily_copy_twr.parquet").group_by("trader").agg(net_daily=k("cash").sum())
            assert (
                d.join(cash, on="trader", how="left")
                .filter((k("net_daily") - k("net").fill_null(0)).abs() > 1e-6)
                .is_empty()
            )
            payments = pl.read_parquet(
                folder / "funding_payments.parquet", columns=["known_ms", "posting_ms", "payment"]
            )
            assert payments.filter(k("payment").is_not_null() & (k("posting_ms") < k("known_ms"))).is_empty()
