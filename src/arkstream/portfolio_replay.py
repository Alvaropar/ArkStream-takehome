"""Phase 5 portfolio replay (P5-3 / P5-5): S*, U* and G* through `portfolio_engine` on the development windows.

Inputs, all published and point in time:
* **leader signals and trigger-leg prices**: the frozen tradable trees' `follower_orders` per scenario (10k:
  `research/replay_tradable`, gray sizes: `research/replay_gray/sleeve=<size>`, P5-1). Each signal is a leader batch
  at its decision time with every leg of the tree's plan (the leader's visible position per coin, the tradable flag,
  the trigger leg's reference at acknowledgement, the frozen `E_ref` and its review flag, the forced flag);
* **market**: approved minute marks (decision marks, hourly checks), Hyperliquid 4h bars (participation budget,
  thin-coin delay, square-root impact), the tree's drift cells and hold bands (ADR-0029 parameters), the spread
  estimates, the risk model of P5-2 (shocks, betas), funding rates and proxies from the tree's own funding entries;
* **leader series** for the triggers (L1-L4) from the next origin's Phase 2 tables, each value used only from its
  own time on.

The holdout is never read here (`freeze.guard` at the holdout start); the window runner refuses any window that
ends after it.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from arkstream.portfolio_engine import (
    DAY,
    HOUR,
    MAJORS,
    Costs,
    Engine,
    Leg,
    Result,
    Rules,
    Signal,
    TriggerSeries,
)
from arkstream.replay_orders import EXCLUDED, Parameters, resolve_scenarios
from arkstream.replay_sensitivity import canonical

C = pl.col
MODEL = "part_ns_sweep_frozen"
SCENARIOS = ("optimistic", "base", "stress", "severe")
DEFAULT_OUT = "research/portfolio_replay"
IMPACT = {"none": 0.0, "linear": 1.0, "3x_base": 3.0}
LABEL = "selection in-sample on these windows; machinery test, not skill"


def ms(t: datetime) -> int:
    return int(round(t.timestamp() * 1000))


def midnight(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), UTC)


# ---------------------------------------------------------------------------------------------- configuration
def costs_by_scenario(ctx) -> tuple[dict[str, Costs], dict]:
    from arkstream.config import load_yaml

    ex = load_yaml("execution.yaml", ctx.root / "config")
    scenarios = resolve_scenarios(ex["scenarios"])
    rules = dict(ex["replay"])
    out = {}
    for name, s in scenarios.items():
        out[name] = Costs(
            name=name, regime=s["costs"], delay_ms=int(s["delay_ms"]),
            delay_thin_ms=None if s.get("delay_thin_ms") is None else int(s["delay_thin_ms"]),
            fee_bps=float(s["fee_bps"]), half_majors=float(s["half_spread_bps"]["majors"]),
            half_other=float(s["half_spread_bps"]["other"]), impact_mult=IMPACT[s["impact"]],
            sqrt_y=float(rules["square_root"]["y"]), thin_volume_usdc=float(rules["thin_volume_usdc"]),
            receive_ms=int(rules["receive_ms"]), debounce_ms=int(rules["debounce_ms"]))
    return out, rules


def scheme_rules(ctx, kind: str, allocations: dict[str, float], stress: Costs, **overrides) -> Rules:
    from arkstream.config import load_yaml

    r = load_yaml("risk.yaml", ctx.root / "config")
    lim, eng, gray = r["limits"], r["engine"], r["gray"]
    D = float(r["scheme"]["notional_D_usdc"]) if kind != "G" else sum(allocations.values())
    if kind != "G" and len(allocations) != 2:
        D = sum(allocations.values())  # a one-sleeve population copy is its own scheme
    ladder = r["drawdown_ladder"]
    kw = dict(
        kind=kind, D=D, allocations=dict(allocations), gross_x=float(lim["S1_sleeve_gross_x"]),
        s2_share=float(lim["S2_sleeve_stress_of_nav"]),
        s3=(float(lim["S3_sleeve_drawdown"]["reduce_only"]), float(lim["S3_sleeve_drawdown"]["flatten_pause"])),
        p2_major=float(lim["P2_net_per_coin"]["BTC"]),
        p2_other_sleeve=float(lim["P2_net_per_coin"]["other_per_sleeve"]),
        p2_other_total=float(lim["P2_net_per_coin"]["other_total"]), p3_x=float(lim["P3_net_btc_beta_x"]),
        p4_share=float(lim["P4_portfolio_stress"]), p4_release=float(lim["P4_passive_release"]),
        p5_usdc=float(lim["P5_coin_share"]) * float(lim["P4_portfolio_stress"]) * D,
        ladder=(float(ladder["halve_new_risk"]), float(ladder["reduce_only"]), float(ladder["flatten"])),
        l_gray=float(gray["loss_cap_usdc"]), halved_scale=float(r["states"]["halved_scale"]),
        deadband_min=float(eng["deadband"]["min_usdc"]), deadband_share=float(eng["deadband"]["share_of_target"]),
        min_notional=float(lim["O3_min_notional_usdc"]), participation=float(eng["participation_per_coin_bar"]),
        sweep_ms=int(eng["sweep_minutes"]) * 60_000, stale_ms=int(eng["stale_signal_s"]) * 1000,
        twap_minutes=int(r["states"]["flatten"]["twap_max_minutes"]),
        twap_volume_usdc=float(r["states"]["flatten"]["twap_below_4h_volume_usdc"]),
        review_days=int(r["states"]["review_days"]), max_passes=int(r["solver"]["max_passes"]),
        rel_tol=float(r["solver"]["repeat_until_rel_change"]), stress_costs=stress,
    )
    kw.update(overrides)
    return Rules(**kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------- market
class TreeMarket:
    """The engine's market view for one window (see the module docstring)."""

    def __init__(self, minute_marks, bars: pl.DataFrame, params: Parameters, bands: pl.DataFrame,
                 spreads: pl.DataFrame, funding: pl.DataFrame, shocks: pl.DataFrame, betas: pl.DataFrame,
                 costs: dict[str, Costs], vintage: date, edges, labels):
        self.mm = minute_marks
        self.params, self.vintage = params, vintage
        self.costs = {c.regime: c for c in costs.values()}
        self.edges, self.labels = [float(e) for e in edges], labels
        self.bars: dict[str, tuple[list[int], list]] = {}
        for (coin,), g in bars.sort("coin", "bar_ms").group_by("coin", maintain_order=True):
            self.bars[coin] = (g["bar_ms"].to_list(), list(zip(g["bar_volume_usdc"].to_list(),
                                                                g["volume_daily"].to_list(),
                                                                g["sigma_daily"].to_list(), strict=True)))
        self.band = {tr: b for tr, b in bands.filter(C("origin") == vintage).select("trader", "band").rows()}
        self.spread: dict[str, tuple[list[int], list[float]]] = {}
        for (coin,), g in spreads.sort("coin", "known_at").group_by("coin", maintain_order=True):
            self.spread[coin] = ([ms(x) for x in g["known_at"].to_list()], g["cs_half_bps"].to_list())
        self.fund = {(c, h): (p, r) for c, h, p, r in funding.select("coin", "hour", "proxy", "funding_rate").rows()}
        self.shock_down = dict(shocks.select("coin", "shock_down").rows())
        self.shock_up = dict(shocks.select("coin", "shock_up").rows())
        self.max_down = max(self.shock_down.values()) if self.shock_down else 0.5
        self.max_up = max(self.shock_up.values()) if self.shock_up else 0.5
        self.betas = dict(betas.select("coin", "beta_btc").rows())
        self.prior = float(betas["prior_btc"][0]) if betas.height else 1.0
        self.cache: dict[tuple, float | None] = {}

    def mark(self, coin: str, t: int) -> float | None:
        return self.mm.at(coin, t)

    def bar(self, coin: str, t: int):
        b = self.bars.get(coin)
        if b is None:
            return None, None, None, None
        i = bisect.bisect_right(b[0], t) - 1
        if i < 0 or t - b[0][i] > 4 * HOUR - 1:
            return None, None, None, None
        return b[0][i], *b[1][i]

    def bucket(self, volume: float | None) -> str:
        if volume is None:
            return "unknown"
        for edge, label in zip(self.edges, self.labels[:-1], strict=True):
            if volume < edge:
                return label
        return self.labels[-1]

    def drift(self, coin: str, t: int, trader: str, regime: str, delay_ms: int, bucket: str) -> float | None:
        band = self.band.get(trader, "no_closed_trip")
        key = (coin, regime, band, delay_ms, bucket)
        if key not in self.cache:
            period = "stress" if regime == "stress" else "development"
            v, _, _, _ = self.params.lookup(self.vintage, period, coin, band, delay_ms,
                                            conservative=regime == "base", bucket=bucket)
            self.cache[key] = v
        return self.cache[key]

    def half_spread(self, coin: str, t: int, regime: str) -> float:
        c = self.costs[regime]
        configured = c.half_majors if coin in MAJORS else c.half_other
        s = self.spread.get(coin)
        if s is None:
            return configured
        i = bisect.bisect_right(s[0], t) - 1
        cs = s[1][i] if i >= 0 else None
        return max(configured, cs) if cs is not None else configured

    def funding(self, coin: str, hour: int):
        return self.fund.get((coin, hour), (None, None))

    def shock(self, coin: str, long: bool) -> float:
        if long:
            return float(self.shock_down.get(coin, self.max_down))
        return float(self.shock_up.get(coin, self.max_up))

    def beta(self, coin: str) -> float:
        return float(self.betas.get(coin, self.prior))


# ---------------------------------------------------------------------------------------------- signals
def signals_from_orders(orders: pl.DataFrame) -> dict[str, list[Signal]]:
    """One Signal per tree signal: the trigger row plus its resize legs (ADR-0034 plan)."""
    o = orders.with_columns(
        tradable=(C("outcome") == "pass") & ~C("not_tradable").fill_null(True),
        priced=C("outcome") == "pass",
        tape=pl.when(C("b0").is_not_null() & C("b1").is_not_null() & (C("b0") > 0)).then(C("b1") / C("b0")),
        pricing=pl.when(C("price_reason").is_in(list(EXCLUDED))).then(pl.lit("")).otherwise(
            C("price_reason").fill_null("")),
    ).sort("trader", "signal", "resize_leg", "coin")
    out: dict[str, list[Signal]] = {}
    cols = ["trader", "signal", "coin", "resize_leg", "pos_after", "tradable", "priced", "ref_px", "pricing", "tape",
            "half_bps", "mid_L", "decision_ms", "event_ms", "ack_ms", "sizing_equity", "reduce_only", "forced",
            "trigger_coin"]
    for (trader, _sig), g in o.select(cols).group_by("trader", "signal", maintain_order=True):
        rows = g.rows(named=True)
        trig = next((r for r in rows if not r["resize_leg"]), None)
        if trig is None:
            continue
        legs = tuple(
            Leg(coin=r["coin"], pos=float(r["pos_after"] or 0.0), tradable=bool(r["tradable"]),
                priced=bool(r["priced"]), ref_px=r["ref_px"] if not r["resize_leg"] else None,
                reason=r["pricing"] if not r["resize_leg"] else "", tape_factor=r["tape"],
                half_bps=r["half_bps"] if not r["resize_leg"] else None,
                mid_px=r["mid_L"] if not r["resize_leg"] else None)
            for r in rows)
        out.setdefault(str(trader), []).append(Signal(
            t=int(trig["decision_ms"]), trader=str(trader), coin=trig["coin"], event_ms=int(trig["event_ms"]),
            ack_ms=int(trig["ack_ms"]), legs=legs, e_ref=trig["sizing_equity"],
            review_reduce_only=bool(trig["reduce_only"]), forced=bool(trig["forced"] or False),
            batch=int(_sig)))
    return out


def tree_orders(tree: Path, origin: date, window: str, scenario: str, traders: list[str]) -> pl.DataFrame:
    path = tree / f"origin={origin}" / f"window={window}" / f"scenario={canonical(scenario, MODEL)}" / (
        "follower_orders.parquet")
    return pl.read_parquet(path).filter(C("trader").is_in(traders))


def funding_table(trees: list[Path], origin: date, window: str) -> pl.DataFrame:
    """(coin, hour) -> proxy, rate, known_ms from the trees' own base funding entries (identical across traders)."""
    parts = []
    for tree in trees:
        path = tree / f"origin={origin}" / f"window={window}" / f"scenario={canonical('base', MODEL)}" / (
            "funding_payments.parquet")
        if path.is_file():
            parts.append(pl.read_parquet(path, columns=["coin", "hour", "proxy", "funding_rate", "known_ms"]))
    f = pl.concat(parts).filter(C("funding_rate").is_not_null() & C("proxy").is_not_null())
    return f.unique(["coin", "hour"], keep="first").sort("coin", "hour")


# ---------------------------------------------------------------------------------------------- triggers
def trigger_series(ctx, origin: date, series_origin: date, traders: list[str], start: datetime | None = None
                   ) -> dict[str, TriggerSeries]:
    """L1-L4 inputs: thresholds from the origin's Phase 2 evidence (history before it), values from the Phase 2 tables
    at `series_origin` (>= the window end), each known from its own timestamp."""
    lead = ctx.root / "research/leader"
    ev = pl.read_parquet(lead / f"origin={origin}" / "evidence.parquet").filter(C("trader").is_in(traders))
    rules = ctx.raw["leader"]
    from arkstream.config import load_yaml

    trig = load_yaml("risk.yaml", ctx.root / "config")["triggers"]
    twr = pl.read_parquet(lead / f"origin={series_origin}" / "daily_twr.parquet",
                          columns=["trader", "ts", "equity", "prev_equity", "d_net_deposit", "index_end", "usable"]
                          ).filter(C("trader").is_in(traders)).sort("trader", "ts")
    hourly = pl.read_parquet(lead / f"origin={series_origin}" / "book_hourly.parquet",
                             columns=["trader", "hour_end", "leverage"]).filter(C("trader").is_in(traders))
    del rules
    out = {}
    for tr in sorted(traders):
        e = ev.filter(C("trader") == tr)
        maxdd = e["twr_max_dd"][0] if e.height else None
        p95 = e["leverage_p95"][0] if e.height else None
        last = e["last_fill_ts"][0] if e.height else None
        t = twr.filter(C("trader") == tr)
        idx = t.filter(C("index_end").is_not_null())
        peak = idx["index_end"].cum_max()
        dd = (idx["index_end"] / peak - 1).to_list()
        times = [ms(x) for x in idx["ts"].to_list()]
        h = hourly.filter((C("trader") == tr) & C("leverage").is_not_null()).sort("hour_end")
        flows = t.filter(C("d_net_deposit") < 0)
        out[tr] = TriggerSeries(
            drawdown=list(zip(times, dd, strict=True)),
            drawdown_limit=float(trig["L1_leader_drawdown_x_hist_max"]) * float(maxdd) if maxdd is not None else None,
            leverage=[(ms(a), float(b)) for a, b in h.select("hour_end", "leverage").rows()],
            leverage_limit=float(trig["L2_leader_leverage_x_p95"]) * float(p95) if p95 else None,
            equity=[(ms(a), float(b)) for a, b in t.filter(C("equity").is_not_null()).select("ts", "equity").rows()],
            outflow=[(ms(a), float(-b), float(c) if c is not None else 0.0)
                     for a, b, c in flows.select("ts", "d_net_deposit", "prev_equity").rows()],
            # the last fill before the window only when it is known at the window start (never a later one)
            last_fill_ms=ms(last) if last is not None and (start is None or last <= start) else None,
        )
    return out


# ---------------------------------------------------------------------------------------------- windows
@dataclass
class WindowInputs:
    origin: date
    window: str
    start: datetime
    end: datetime
    series_origin: date


def dev_windows(ctx, kind: str = "test") -> list[WindowInputs]:
    from arkstream import drift

    dr = drift.DriftRules.from_config(ctx.raw)
    origins = list(dr.origin_dates)
    out = []
    for i, o in enumerate(origins):
        if o >= dr.holdout_start:
            continue
        if kind == "test":
            out.append(WindowInputs(o, "test", midnight(o), midnight(origins[i + 1]), origins[i + 1]))
    return out


class WindowData:
    """Everything shared by the configurations and scenarios of one window."""

    def __init__(self, ctx, win: WindowInputs, traders: list[str], trees: list[Path], bars: pl.DataFrame,
                 costs: dict[str, Costs], ex_rules: dict):
        from arkstream import risk_model
        from arkstream.replay_cap import MinuteMarks
        from arkstream.replay_market import bucket_labels

        self.win = win
        tree0 = trees[0]
        coins = set()
        for tree in trees:
            o = tree_orders(tree, win.origin, win.window, "base", traders)
            coins |= set(o["coin"].unique().to_list())
        self.coins = sorted(coins)
        self.minute = MinuteMarks.load(ctx.path("reference_prices_dir"), win.start, win.end, self.coins)
        params = Parameters.from_rules(pl.read_parquet(tree0 / "drift_cells.parquet"), ex_rules)
        bands = pl.read_parquet(tree0 / "drift_hold_bands.parquet")
        spreads = pl.read_parquet(tree0 / "spread_estimates.parquet")
        rm = risk_model.load(ctx.root / risk_model.DEFAULT_OUT, win.origin)
        funding = funding_table(trees, win.origin, win.window)
        edges = ex_rules["stress_fallback"]["bucket_edges_usdc"]
        self.market = TreeMarket(self.minute, bars.filter(C("coin").is_in(self.coins)), params, bands, spreads,
                                 funding, rm["stress_shocks"], rm["betas"], costs, win.origin, edges,
                                 bucket_labels(edges))
        self.funding = funding
        self.triggers = trigger_series(ctx, win.origin, win.series_origin, traders, win.start)


def review_times(start: datetime, end: datetime, days: int = 14) -> list[int]:
    """ADR-0052 / ADR-0089: reviews at the window start and every 14 days after it, before the end."""
    out, r = [], start
    while r < end:
        out.append(ms(r))
        r += timedelta(days=days)
    return out


def run_config(data: WindowData, rules: Rules, costs: Costs, signals: list[Signal], reviews: list[int] | None = None
               ) -> Result:
    eng = Engine(rules, costs, data.market, ms(data.win.start), ms(data.win.end), triggers=data.triggers,
                 reviews=reviews or review_times(data.win.start, data.win.end, rules.review_days))
    return eng.run(signals)


# ---------------------------------------------------------------------------------------------- outputs
EVENT_SCHEMA = {"t": pl.Int64, "event": pl.String, "trader": pl.String, "coin": pl.String, "reason": pl.String,
                "trigger": pl.String, "state_from": pl.String, "state_to": pl.String, "value": pl.Float64,
                "limit": pl.String, "quantity": pl.Float64, "notional": pl.Float64, "clipped_usdc": pl.Float64,
                "age_ms": pl.Int64, "coins": pl.String}


def events_frame(events: list[dict]) -> pl.DataFrame:
    """Every event with the fixed EVENT_SCHEMA (absent fields null)."""
    rows: list[dict[str, object]] = [{k: e.get(k) for k in EVENT_SCHEMA} for e in events]
    for r in rows:
        for k in ("value", "quantity", "notional", "clipped_usdc"):
            v = r[k]
            if isinstance(v, (int, float)):
                r[k] = float(v)
    return pl.DataFrame(rows, schema=EVENT_SCHEMA, orient="row") if rows else pl.DataFrame(schema=EVENT_SCHEMA)


def frames(res: Result) -> dict[str, pl.DataFrame]:
    def df(rows: list[dict], schema: dict | None = None) -> pl.DataFrame:
        return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame(schema=schema or {})

    return {
        "orders": df(res.orders),
        "fills": df(res.fills),
        "decisions": df(res.decisions),
        "hourly": df(res.hourly),
        "events": events_frame(res.events),
        "intents": df(res.intents),
    }


def daily_book(fills: pl.DataFrame, allocations: dict[str, float], marks: pl.DataFrame, funding: pl.DataFrame,
               start: datetime, end: datetime) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Per sleeve: the replay's own daily valuation (`value_book`) of the engine's virtual fills."""
    from arkstream.replay_book import value_book

    parts_d, parts_f, parts_l = [], [], []
    for trader, alloc in sorted(allocations.items()):
        f = fills.filter(C("trader") == trader) if fills.height else fills
        orders = (f.with_row_index("oid").with_columns(batch=C("oid").cast(pl.Int64), oid=C("oid").cast(pl.Int64))
                  if f.height else pl.DataFrame(schema={"trader": pl.String, "coin": pl.String,
                                                        "quantity": pl.Float64, "fill_px": pl.Float64,
                                                        "fee": pl.Float64, "ack_ms": pl.Int64,
                                                        "decision_ms": pl.Int64, "batch": pl.Int64,
                                                        "oid": pl.Int64, "status": pl.String,
                                                        "anchor_px": pl.Float64}))
        universe = pl.DataFrame({"trader": [trader]})
        daily, fund, ledger = value_book(orders, universe, marks, funding, start, end, alloc)
        parts_d.append(daily)
        parts_f.append(fund)
        parts_l.append(ledger)
    return pl.concat(parts_d, how="diagonal_relaxed"), pl.concat(parts_f, how="diagonal_relaxed"), pl.concat(
        parts_l, how="diagonal_relaxed")


def es95(values: list[float]) -> float | None:
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:
        return None
    n = max(1, math.ceil(0.05 * len(v)))
    return sum(v[:n]) / n


def time_weighted(hourly: pl.DataFrame, trader: str, col: str) -> float | None:
    h = hourly.filter(C("trader") == trader)
    v = h[col].mean() if h.height else None
    return float(v) if isinstance(v, (int, float)) else None


def write_run(folder: Path, tables: dict[str, pl.DataFrame]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        t.write_parquet(folder / f"{name}.parquet", compression="zstd", statistics=True)


def timedelta_days(n: int) -> timedelta:
    return timedelta(days=n)


def day_of(t_ms: int) -> int:
    return t_ms // DAY
