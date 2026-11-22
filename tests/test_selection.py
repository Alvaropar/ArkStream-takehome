"""Phase 4 selection (ADRs 0130-0139): bootstrap, clusters and the walk, random-k baselines, exact intervals, capture
aggregation, the freeze guard and the selection seeded leak."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import yaml
from conftest import need

from arkstream import freeze
from arkstream import selection as S
from arkstream import selection_eval as E
from arkstream import selection_stats as st
from arkstream.config import ROOT, Context, load_context
from arkstream.replay_capture import PARTS

DAY = 86_400_000
REPLAY = ROOT / "research/replay_frozen"


def rules(**kw) -> S.Rules:
    r = S.Rules.from_config(load_context().raw, "rule_a")
    from dataclasses import replace

    return replace(r, **kw)


def ms(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=UTC).timestamp() * 1000)


# ------------------------------------------------------------------------------------------------ bootstrap and key


def test_entry_week_blocks_are_monday_weeks():
    # 2025-10-05 is a Sunday, 2025-10-06 a Monday
    b = st.entry_week_blocks(np.array([ms("2025-10-05"), ms("2025-10-06"), ms("2025-10-12"), ms("2025-10-13")]))
    assert b.tolist() == [0, 1, 1, 2]


def test_overlap_merged_blocks_chain_weeks():
    # one long trip spanning three weeks merges them: the disclosed reason for entry-week blocks (ADR-0131)
    o = np.array([ms("2025-10-06"), ms("2025-10-14"), ms("2025-10-21")])
    c = np.array([ms("2025-10-25"), ms("2025-10-15"), ms("2025-10-22")])
    assert st.week_blocks(o, c).tolist() == [0, 0, 0]
    assert st.entry_week_blocks(o).tolist() == [0, 1, 2]


def test_block_bootstrap_seeded_and_block_wise():
    v = np.array([1.0, 1.0, 3.0])
    b = np.array([0, 0, 1])
    a = st.block_bootstrap(v, b, 500, np.random.default_rng(7))
    again = st.block_bootstrap(v, b, 500, np.random.default_rng(7))
    assert np.array_equal(a, again)
    # each draw is one of: both blocks 0 (1.0), both 1 (3.0), one each (5/3): blocks are never split
    assert set(np.round(a, 6)) <= {1.0, 3.0, round(5 / 3, 6)}


def trips_frame(rows):
    return pl.DataFrame(rows, schema={"trader": pl.String, "coin": pl.String, "trip": pl.Int64, "open_ms": pl.Int64,
                                      "close_ms": pl.Int64, "net": pl.Float64, "pnl": pl.Float64}, orient="row")


def weekly_trips(trader, nets, start="2025-09-01"):
    t0 = ms(start)
    return [(trader, "BTC", i, t0 + i * 7 * DAY, t0 + i * 7 * DAY + 3600_000, n, n * 1000) for i, n in enumerate(nets)]


def test_key_minimums_and_lower_bound():
    r = rules()
    t = trips_frame(weekly_trips("0x" + "a" * 40, [0.01] * 12) + weekly_trips("0x" + "b" * 40, [0.01] * 5))
    k = S.address_keys(t, r, date(2025, 11, 19))
    a = k.filter(pl.col("trader").str.starts_with("0xa")).row(0, named=True)
    b = k.filter(pl.col("trader").str.starts_with("0xb")).row(0, named=True)
    assert a["key_status"] == "ok" and a["key"] == pytest.approx(0.01)
    assert b["key_status"] == "too_few_trips" and b["key"] is None


def test_single_event_flag():
    r = rules()
    nets = [-0.002] * 11 + [0.5]  # one huge week makes the key positive; without it the bound is negative
    k = S.address_keys(trips_frame(weekly_trips("0x" + "c" * 40, nets)), r, date(2025, 11, 19)).row(0, named=True)
    if k["key"] > 0:
        assert k["single_event"] and k["key_ex_best"] <= 0
    assert k["best_block_share"] > 1  # the best week carries more than the total


def test_key_reproducible_and_independent_of_other_addresses():
    r = rules()
    one = trips_frame(weekly_trips("0x" + "d" * 40, list(np.linspace(-0.01, 0.03, 12))))
    two = pl.concat([one, trips_frame(weekly_trips("0x" + "e" * 40, [0.02] * 12))])
    k1 = S.address_keys(one, r, date(2025, 11, 5))
    k2 = S.address_keys(two, r, date(2025, 11, 5)).filter(pl.col("trader") == "0x" + "d" * 40)
    assert k1.equals(k2)


# ------------------------------------------------------------------------------------------------ clusters and walk


def test_ward_separates_groups():
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(0, 0.1, (5, 3)), rng.normal(5, 0.1, (4, 3))])
    labels = st.ward(st.standardise(x), 2)
    assert len(set(labels[:5])) == 1 and len(set(labels[5:])) == 1 and labels[0] != labels[5]


def test_average_linkage_threshold():
    d = np.array([[0, 0.1, 0.9], [0.1, 0, 0.8], [0.9, 0.8, 0]])
    assert st.average_linkage(d, 0.5).tolist() == [0, 0, 1]
    assert st.average_linkage(d, 0.05).tolist() == [0, 1, 2]


def walk_inputs():
    t = ["0x" + c * 40 for c in "abcdef"]
    cands = pl.DataFrame({"trader": t, "selectable": [True] * 6, "behaviour_cluster": ["b0", "b0", "b1", "b1", "b2",
                                                                                        "b2"],
                          "key": [0.05, 0.04, 0.03, 0.02, 0.01, 0.005]})
    pairs = pl.DataFrame({"trader_a": [t[0], t[0]], "trader_b": [t[2], t[4]], "corr": [0.9, None],
                          "overlap": [0.1, 0.7], "common_days": [30, 5]})
    return t, cands, pairs


def test_walk_order_thresholds_and_k():
    t, cands, pairs = walk_inputs()
    w = S.walk(cands, pairs, rules(max_k=3))
    # within-cluster rank first: a (b0 #1), c (b1 #1), e (b2 #1), then b, d, f
    assert w["trader"].to_list() == [t[0], t[2], t[4], t[1], t[3], t[5]]
    dec = dict(zip(w["trader"], w["decision"], strict=True))
    assert dec[t[0]] == "selected"
    assert dec[t[2]] == "rejected"  # correlation 0.9 with a
    assert dec[t[4]] == "rejected"  # overlap 0.7 with a (correlation unmeasured does not block)
    assert dec[t[1]] == "selected" and dec[t[3]] == "selected"
    assert dec[t[5]] == "rejected" and "basket full" in w.filter(pl.col("trader") == t[5])["reason"][0]


def test_copier_weaker_member():
    cl = pl.DataFrame({"trader": ["0xa", "0xb", "0xc"], "cluster_id": ["0xa", "0xa", "0xa"]})
    keys = pl.DataFrame({"trader": ["0xa", "0xb", "0xc"], "key": [0.01, 0.02, None]})
    w = dict(S.copier_weaker(cl, keys).select("trader", "copier_weaker").rows())
    assert w == {"0xa": True, "0xb": False, "0xc": True}


# ------------------------------------------------------------------------------------------------ baselines, stats


def test_random_k_seeded():
    pool = [f"0x{i:040x}" for i in range(8)]
    vals = {p: float(i) for i, p in enumerate(pool)}
    a = E.random_k(pool, vals, 3, 200, np.random.default_rng([1, 2, 3]))
    b = E.random_k(pool, vals, 3, 200, np.random.default_rng([1, 2, 3]))
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    assert all(len(set(r)) == 3 for r in a[0])  # without replacement
    assert E.random_k(pool[:2], vals, 3, 10, np.random.default_rng(0))[1].size == 0


def test_percentile_and_trimmed_mean():
    assert st.percentile_of(2.0, np.array([1.0, 2.0, 3.0, 4.0])) == pytest.approx(0.375)
    assert st.trimmed_mean(np.array([-100.0, 1, 2, 3, 100]), 0.2) == pytest.approx(2.0)


def test_clopper_pearson_plan_values():
    lo, hi = st.clopper_pearson(4, 5)
    assert lo == pytest.approx(0.2836, abs=1e-3) and hi == pytest.approx(0.9949, abs=1e-3)
    assert st.clopper_pearson(5, 5)[0] == pytest.approx(0.4782, abs=1e-3)
    assert st.clopper_pearson(5, 5, two_sided=False)[0] == pytest.approx(0.5493, abs=1e-3)


def test_min_trl_plan_scale():
    sr = 2 / np.sqrt(365)  # annualised 2, daily, normal
    n = st.min_track_record(sr, 0.0, 3.0)
    assert 240 < n < 260
    assert st.min_track_record(-0.1, 0, 3) is None
    assert st.min_track_record(sr / 2, 0, 3) > 3.9 * n


def test_spearman():
    assert st.spearman(np.array([1, 2, 3, 4]), np.array([10, 20, 30, 40])) == pytest.approx(1.0)
    assert st.spearman(np.array([1, 2]), np.array([1, 2])) is None


# ------------------------------------------------------------------------------------------------ capture (5b)


def capture_frame():
    rows = []
    for t, fol, ben in (("0xa", 80.0, 100.0), ("0xb", 30.0, 50.0), ("0xc", -5.0, 20.0)):
        gap = ben - fol
        parts = dict.fromkeys(PARTS, 0.0)
        parts["fees"] = gap * 0.25
        parts["half_spread"] = gap * 0.75
        rows.append({"trader": t, "follower_pnl": fol, "benchmark_pnl": ben, "gap": gap, "closure": 0.0,
                     "status": "ok", "leader_return": 0.01, **parts})
    return pl.DataFrame(rows)


def test_capture_group_ratio_closure_and_near_zero():
    cap = capture_frame()
    fee = pl.DataFrame({"trader": ["0xa", "0xb", "0xc"], "fee_rate_bps": [3.6, 3.6, 3.6]})
    turn = pl.DataFrame({"trader": ["0xa", "0xb", "0xc"], "benchmark_turnover": [1e4, 1e4, 1e4]})
    rows = E.capture_rows(cap, {"sleeve": ["0xa", "0xb", "0xc"], "basket": ["0xa", "0xb"],
                                "small": ["0xc"]}, fee, turn, 1000.0)
    b = rows.filter(pl.col("level") == "basket").row(0, named=True)
    assert b["capture_ratio"] == pytest.approx(110 / 150)
    assert sum(b[p] for p in PARTS) == pytest.approx(b["gap"])  # parts still sum to the gap
    assert b["capture_ratio_leader_fee"] == pytest.approx(110 / (150 - 2 * 3.6))
    small = rows.filter(pl.col("level") == "small").row(0, named=True)  # |20| < 1% x 1000 x 1? no: 10 -> ok
    assert small["status"] == "ok"
    tiny = E.capture_rows(cap, {"g": ["0xc"]}, fee, turn, 10_000.0).row(0, named=True)  # 20 < 100
    assert tiny["status"] == "not_meaningful" and tiny["capture_ratio"] is None
    med = E.capture_medians(rows.filter(pl.col("level") == "sleeve"))
    assert med["n_won"] == 3 and med["median_won"] == pytest.approx(0.6)


# ------------------------------------------------------------------------------------------------ freeze guard


def frozen_copy(tmp_path: Path) -> Context:
    for p in freeze.frozen_paths(ROOT):
        if p == freeze.SHORTLIST:
            continue
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / p, tmp_path / p)
    sl = tmp_path / freeze.SHORTLIST
    sl.parent.mkdir(parents=True, exist_ok=True)
    sl.write_text("trader,decision\n0xabc,selected\n", encoding="utf-8")
    (tmp_path / "provenance").mkdir(exist_ok=True)
    cfg = tmp_path / "config/decision_context.yaml"
    text = cfg.read_text(encoding="utf-8")
    if "\nfrozen: true" not in text:
        text = text.replace("\nfrozen: false", "\nfrozen: true", 1)
    cfg.write_text(text, encoding="utf-8")
    raw = yaml.safe_load(text)
    return Context(raw=raw, root=tmp_path)


def reload(ctx: Context) -> Context:
    return Context(raw=yaml.safe_load((ctx.root / "config/decision_context.yaml").read_text(encoding="utf-8")),
                   root=ctx.root)


AFTER = datetime(2025, 12, 4, tzinfo=UTC)
AT = datetime(2025, 12, 3, tzinfo=UTC)


def test_guard_without_freeze_refuses_after_holdout_start(tmp_path):
    ctx = frozen_copy(tmp_path)
    assert freeze.guard(ctx, AT) is None  # up to the holdout start: runs freely
    with pytest.raises(freeze.FreezeError, match="not frozen"):
        freeze.guard(ctx, AFTER)


def test_freeze_requires_frozen_flag(tmp_path):
    ctx = frozen_copy(tmp_path)
    raw = dict(ctx.raw)
    raw["frozen"] = False
    with pytest.raises(freeze.FreezeError, match="frozen: true"):
        freeze.write_freeze(Context(raw=raw, root=tmp_path), "rule_a")


def test_freeze_matches_then_rejects_edits(tmp_path):
    ctx = frozen_copy(tmp_path)
    _, h = freeze.write_freeze(ctx, "rule_a", now=datetime(2026, 11, 22, tzinfo=UTC))
    assert freeze.guard(ctx, AFTER) == h
    cfg = tmp_path / "config/decision_context.yaml"
    original = cfg.read_text(encoding="utf-8")
    # an edited threshold
    cfg.write_text(original.replace("max_corr: 0.5 ", "max_corr: 0.6 "), encoding="utf-8")
    with pytest.raises(freeze.FreezeError, match="changed config/decision_context.yaml"):
        freeze.guard(reload(ctx), AFTER)
    # a moved cutoff
    cfg.write_text(original.replace('cutoff: "2026-01-04T23:59:42.020Z"', 'cutoff: "2026-01-10T00:00:00Z"'),
                   encoding="utf-8")
    with pytest.raises(freeze.FreezeError, match="changed config/decision_context.yaml"):
        freeze.guard(reload(ctx), AFTER)
    cfg.write_text(original, encoding="utf-8")
    assert freeze.guard(reload(ctx), AFTER) == h
    # an edited shortlist or rule source
    (tmp_path / freeze.SHORTLIST).write_text("trader,decision\n0xdef,selected\n", encoding="utf-8")
    with pytest.raises(freeze.FreezeError, match="changed research/selection/shortlist"):
        freeze.guard(ctx, AFTER)


def test_freeze_file_tamper_detected(tmp_path):
    ctx = frozen_copy(tmp_path)
    path, _ = freeze.write_freeze(ctx, "rule_a")
    text = path.read_text(encoding="utf-8")
    first = next(ln for ln in text.splitlines() if ln[64:66] == "  ")
    path.write_text(text.replace(first, "0" * 64 + first[64:]), encoding="utf-8")
    with pytest.raises(freeze.FreezeError, match="freeze file edited"):
        freeze.guard(ctx, AFTER)


def test_selection_load_is_guarded(tmp_path):
    ctx = frozen_copy(tmp_path)
    with pytest.raises(freeze.FreezeError):
        S.load_origin(ctx, date(2025, 12, 10), pl.DataFrame(), pl.DataFrame(), rules())


# ------------------------------------------------------------------------------------------------ data tests


def origin_data(o: date, ctx=None) -> S.OriginData:
    from arkstream import copiers
    from arkstream.pipeline import load_inputs
    from arkstream.replay_market import midnight

    ctx = ctx or load_context()
    inp = load_inputs(ctx)
    cop = copiers.screen(inp.fills, midnight(o), ctx.raw["copiers"])["clusters"]
    return S.load_origin(ctx, o, inp.traders, cop, rules())


@pytest.mark.data
def test_follower_trips_reproduce_band_table():
    need(REPLAY / "origin=2025-11-19", "uv run python -m arkstream replay --frozen")
    ctx = load_context()
    o = date(2025, 11, 19)
    f, fund = S.load_ledger(ctx, o, "training", "base", S.training_end(o))
    trips = S.follower_trips(f, fund)
    uni = pl.read_parquet(S.window_dir(ctx, o, "training") / "universe.parquet").with_columns(
        pl.col("hold_band").fill_null("no_closed_trip"))
    mine = (trips.join(uni.select("trader", "hold_band"), on="trader").group_by("hold_band")
            .agg(completed=pl.len(), net_bps=pl.col("net").mean() * 1e4).sort("hold_band"))
    ref = pl.read_parquet(S.scenario_dir(ctx, o, "training", "base") / "band_break_even.parquet").sort("hold_band")
    j = ref.join(mine, on="hold_band", suffix="_m")
    assert j.height == ref.height
    assert (j["completed"] == j["completed_m"]).all()
    assert np.allclose(j["net_bps"], j["net_bps_m"], atol=1e-9)


@pytest.mark.data
def test_coin_daily_reproduces_replay_equity():
    need(REPLAY / "origin=2025-11-19", "uv run python -m arkstream replay --frozen")
    from arkstream import selection_coins as SC

    ctx = load_context()
    o, e = date(2025, 11, 19), date(2025, 12, 3)
    mine = SC.coin_daily(ctx, o, "test", "base", o, e, None)
    ref = pl.read_parquet(S.scenario_dir(ctx, o, "test", "base") / "daily_copy_twr.parquet",
                          columns=["trader", "day", "equity"])
    j = ref.join(mine, on=["trader", "day"], suffix="_m")
    assert j.height == ref.height == mine.height
    assert j["equity"].is_null().equals(j["equity_m"].is_null())
    assert (j["equity"] - j["equity_m"]).abs().max() < 1e-6


@pytest.mark.data
def test_selection_seeded_leak():
    """A test-window result planted in the ranking input is caught; forced through, it changes the shortlist."""
    need(REPLAY / "origin=2025-11-19", "uv run python -m arkstream replay --frozen")
    o = date(2025, 11, 19)
    data = origin_data(o)
    r = rules()
    clean = S.selected(S.select_origin(data, r))
    rejected = (S.select_origin(data, r)["decisions"].filter(pl.col("decision") != "selected")
                .sort("trader")["trader"][0])
    end = S.training_end(o)
    leak = pl.DataFrame([{**data.trips.row(0, named=True), "trader": rejected, "coin": "BTC", "trip": 10_000 + i,
                          "open_ms": end + i * 7 * DAY, "close_ms": end + i * 7 * DAY + 3600_000, "net": 5.0,
                          "pnl": 5e4} for i in range(12)], schema=data.trips.schema)
    from dataclasses import replace

    leaked = replace(data, trips=pl.concat([data.trips, leak]))
    with pytest.raises(S.LeakError):
        S.select_origin(leaked, r)
    forced = S.selected(S.select_origin(leaked, r, check=False))
    assert forced != clean and rejected in forced


@pytest.mark.data
def test_published_selection_matches_rule():
    """The published 3 Dec shortlist is the chosen rule at 3 Dec, recomputed."""
    need(ROOT / freeze.SHORTLIST, "uv run python -m arkstream select --evaluate")
    from arkstream import selection_coins as SC
    from arkstream.selection_run import FROZEN, ctx_for

    ctx = load_context()
    chosen = ctx.raw["selection"]["rule"]
    tree = S.Rules.from_config(ctx.raw, chosen).replay_dir
    need(ROOT / tree, "uv run python -m arkstream replay --coin-filter")
    o = date(2025, 12, 3)
    data = origin_data(o, ctx_for(ctx, tree))
    data.coin_set = SC.coin_set(ctx_for(ctx, FROZEN), o, rules())
    t = S.select_origin(data, S.Rules.from_config(ctx.raw, chosen))
    published = pl.read_csv(ROOT / freeze.SHORTLIST)
    assert sorted(published.filter(pl.col("decision") == "selected")["trader"]) == S.selected(t)
