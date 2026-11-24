"""Phase 5 step P5-5: S*, U* and G* on the four development test windows, 200 random pairs, and the stress tests
(ADR-0095 items 5-6), with the pass criteria F2a, F2b, F3 and F5.

Every table carries the label "selection in-sample on these windows; machinery test, not skill" (ADR-0086 item 3).

* **Configurations** (ADR-0086 item 5): S* (both sleeves at 10k, every limit, state and trigger), U* (S1 and
  execution only) and G* (the hand-off alone at the gray size, option C, the cap on the remaining budget). The
  risk-rule variants chosen at P5-4 (`variant_decision.json`) apply to all three.
* **The gray size** (ADR-0090 items 4, 6): G* is run at 2,500 and 5,000 in base; the count share of its trigger-leg
  intents under 10 USDC after `λ`, pooled over the four windows, decides (> 10% -> 5,000); the chosen size is then run
  in every scenario.
* **α** excludes funding (ADR-0084): the Phase 4 v2 residual on the origin's published factors and betas.
* **Random pairs**: 200 per window, two distinct A/B addresses with at least one signal, seed
  [20251203, origin ordinal], S* rules, base.
* **Stress at the limits** (ADR-0095 item 6, pinned): each sleeve's held book at its hour of largest stress usage in
  the base runs, scaled up until the first limit binds (the solver at a scale of 1,000), then every coin's shock at
  once and a one-order exit at stress costs and severe delays (60 s / 300 s).
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from arkstream import portfolio_engine as PE
from arkstream import portfolio_replay as PR

C = pl.col
DEFAULT_OUT = "research/portfolio_replay"
LABEL = PR.LABEL
CRASH = (date(2025, 10, 10), date(2025, 10, 11))


def variant_overrides(ctx) -> tuple[dict, bool, dict]:
    path = ctx.root / "research/phase5_population/variant_decision.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    over: dict = {}
    if d["cap_denominator"]["adopted"]:
        over["cap_denominator"] = "min_nav"
    return over, bool(d["eref_at_review"]["adopted"]), d


def num(v) -> float:
    """A polars scalar (mean, max, sum) as a float; 0 when empty."""
    return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else 0.0


def alpha_market(ctx, origin: date):
    from arkstream.selection_v2_market import coin_returns
    from arkstream.selection_v2_stats import Market

    sv = ctx.root / "research/selection_v2" / f"origin={origin}"
    marks = pl.read_parquet(ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / "valuation_marks.parquet")
    members = pl.read_parquet(sv / "coins.parquet").filter("tradable")["coin"].to_list()
    return Market(origin, sorted(members), coin_returns(marks), pl.read_parquet(sv / "factors.parquet"),
                  pl.read_parquet(sv / "betas.parquet"), False), marks


def alpha_of(ledger: pl.DataFrame, fund: pl.DataFrame, marks, market, start, end, traders) -> dict[str, float | None]:
    from arkstream.selection_v2_market import coin_days, residual_coin_days, trader_days

    if ledger.height == 0:
        empty: dict[str, float | None] = {t: None for t in traders}
        empty["combined"] = None
        return empty
    cd = coin_days(ledger, fund, marks, start, end)
    rc = residual_coin_days(cd, market.betas, market.factors, market.returns, False)
    td = trader_days(rc, traders, start, end, 10.0)
    out: dict[str, float | None] = {}
    ex = td.filter("exposed")
    for tr in traders:
        g = ex.filter(C("trader") == tr)
        G = float(g["G"].sum())
        out[tr] = float(g["U"].sum()) / G * PE.BPS if G > 0 else None
    G = float(ex["G"].sum())
    out["combined"] = float(ex["U"].sum()) / G * PE.BPS if G > 0 else None
    return out


def max_drawdown(nav: list[float], start: float) -> float:
    peak, worst = start, 0.0
    for v in nav:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1 if peak > 0 else 0.0)
    return worst


def summarize(win, config: str, scenario: str, rules: PE.Rules, fr: dict[str, pl.DataFrame], daily: pl.DataFrame,
              alpha: dict, eng: PE.Engine) -> list[dict]:
    rows = []
    hourly, events, fills, orders = fr["hourly"], fr["events"], fr["fills"], fr["orders"]
    allocs = rules.allocations
    scopes = [*sorted(allocs), "combined"]
    for scope in scopes:
        traders = sorted(allocs) if scope == "combined" else [scope]
        alloc = sum(allocs[t] for t in traders)
        d = daily.filter(C("trader").is_in(traders)).group_by("day").agg(
            C("equity").sum(), C("funding").sum(), C("fees").sum(), C("execution_cost").sum(),
            C("gross").sum()).sort("day")
        eq = d["equity"].to_list()
        prev = [alloc, *eq[:-1]]
        rets = [e / p - 1 if p and e is not None else None for e, p in zip(eq, prev, strict=True)]
        h = hourly.filter(C("trader").is_in(traders)).group_by("t").agg(C("nav").sum(), C("gross").sum(),
                                                                       C("exit_cost").sum()).sort("t")
        hs = hourly.filter(C("trader").is_in(traders))
        f = fills.filter(C("trader").is_in(traders)) if fills.height else fills
        phys = f.filter(C("kind") == "physical") if f.height else f
        notional = float((phys["quantity"].abs() * phys["fill_px"]).sum()) if phys.height else 0.0
        gross_fill = phys["quantity"].abs() * phys["fill_px"] if phys.height else None
        half = num((gross_fill * phys["half_bps"]).sum()) / PE.BPS if gross_fill is not None else 0.0
        imp = num((gross_fill * phys["impact_bps"]).sum()) / PE.BPS if gross_fill is not None else 0.0
        fee = float(phys["fee"].sum()) if phys.height else 0.0
        slip = float((phys["quantity"] * (phys["fill_px"] - phys["anchor_px"])).sum()) if phys.height else 0.0
        ev = events.filter(C("trader").is_in([*traders, "scheme"])) if events.height else events

        def count(name: str, ev: pl.DataFrame = ev) -> int:
            return int((ev["event"] == name).sum()) if ev.height else 0

        cross = float(ev.filter(C("event") == "internal_cross")["notional"].sum()) if (
            ev.height and "notional" in ev.columns and scope == "combined") else 0.0
        clips = ev.filter(C("event") == "participation_clip") if ev.height else ev
        state_hours = hs.group_by("state").len() if hs.height else hs
        lam_by = hs.group_by("lambda_set_by").len() if hs.height else hs
        n_h = max(hs.height, 1)
        loss_path = [alloc - nv + x for nv, x in zip(h["nav"].to_list(), h["exit_cost"].to_list(), strict=True)]
        row = {
            "origin": win.origin, "config": config, "scenario": scenario, "scope": scope, "allocation": alloc,
            "final_nav": eq[-1] if eq else None,
            "raw_return": (eq[-1] / alloc - 1) if eq and eq[-1] is not None else None,
            "alpha_bps_day_ex_funding": alpha.get(scope),
            "funding_usdc": float(d["funding"].sum()), "fees_usdc": float(d["fees"].sum()),
            "max_drawdown_hourly": max_drawdown(h["nav"].to_list(), alloc) if h.height else None,
            "max_drawdown_usdc": -max_drawdown(h["nav"].to_list(), alloc) * alloc if h.height else None,
            "max_loss_incl_exit_usdc": max(loss_path) if loss_path else None,
            "worst_day": min((r for r in rets if r is not None), default=None),
            "daily_returns": json.dumps([r for r in rets if r is not None]),
            "utilisation": num(h["gross"].mean()) / alloc if h.height else None,
            "lambda_tw_mean": num(hs["lambda"].mean()) if hs.height and "lambda" in hs.columns else None,
            "lambda_exposure_weighted": (num((hs["lambda"] * hs["u_gross"]).sum()) / num(hs["u_gross"].sum())
                                         if hs.height and num(hs["u_gross"].sum()) > 0 else None),
            "u_gross_mean": num(hs["u_gross"].mean()) if hs.height else None,
            "lambda_set_by": json.dumps({str(a): round(b / n_h, 4) for a, b in lam_by.rows()}, sort_keys=True)
            if hs.height else "{}",
            "state_hours": json.dumps({str(a): b for a, b in state_hours.rows()}, sort_keys=True)
            if hs.height else "{}",
            "firings": json.dumps(
                {str(k): int(v) for k, v in (ev.filter(C("event").is_in(["state_firing", "scheme_firing"]))
                                             .group_by("reason").len().rows() if ev.height else [])},
                sort_keys=True),
            "trigger_on": json.dumps({str(k): int(v) for k, v in (ev.filter(C("event") == "trigger_on")
                                                                  .group_by("trigger").len().rows()
                                                                  if ev.height and "trigger" in ev.columns else [])},
                                     sort_keys=True),
            "p5_binding_updates": count("p5_binding"), "p4_passive_breaches": count("p4_passive_breach"),
            "internal_cross_usdc": cross, "participation_clips": clips.height,
            "clipped_usdc": float(clips["clipped_usdc"].sum()) if clips.height else 0.0,
            "flatten_orders": int(orders.filter(C("flatten") & (C("status") == "filled")).height)
            if orders.height and scope == "combined" else 0,
            "sweep_orders": int(orders.filter((C("reason") == "sweep") & (C("status") == "filled")).height)
            if orders.height and scope == "combined" else 0,
            "physical_fills": phys.height, "traded_usdc": notional,
            "cost_half_spread_bps": half / notional * PE.BPS if notional else None,
            "cost_impact_bps": imp / notional * PE.BPS if notional else None,
            "cost_fee_bps": fee / notional * PE.BPS if notional else None,
            "cost_drift_bps": (slip - half - imp) / notional * PE.BPS if notional else None,
            "engine_faults": len(eng.faults), "label": LABEL,
        }
        if config.startswith("G"):
            dec = fr["decisions"]
            over = dec.filter(C("target_stress") > C("stress_budget") + 1e-6) if dec.height else dec
            row["cap_breaches_at_update"] = over.height
            row["max_stress_to_budget"] = num((dec["target_stress"] / dec["stress_budget"].clip(1e-9)).max()
                                              ) if dec.height else None
            row["loss_cap_hit"] = bool(eng.loss_cap_hit)
            it = fr["intents"]
            row["intents"] = it.height
            row["sub_minimum_intents"] = int((it["sleeve_notional"] < rules.min_notional).sum()) if it.height else 0
        rows.append(row)
    return rows


class Runner:
    def __init__(self, ctx, out: Path):
        from arkstream import drift, hlprices
        from arkstream.replay_cap import impact_bars

        self.ctx, self.out = ctx, out
        dr = drift.DriftRules.from_config(ctx.raw)
        self.stop = PR.midnight(dr.holdout_start)
        from arkstream.freeze import guard

        guard(ctx, self.stop)
        self.costs, self.ex = PR.costs_by_scenario(ctx)
        candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), self.stop)
        self.bars = impact_bars(candles, self.stop, self.ex["square_root"]["volatility_bars"])
        from arkstream import replay_gray

        self.sleeves = list(replay_gray.sleeves(ctx))
        hand = pl.read_parquet(ctx.root / "research/selection_v2/origin=2025-12-03/eligible.parquet")
        self.handoff = sorted(hand["trader"].to_list())
        self.t10 = ctx.root / ctx.raw["selection_v2"]["tradable_dir"]
        self.over, self.eref_hwm, self.variant = variant_overrides(ctx)
        self.stress = self.costs["stress"]

    def tree(self, size: float) -> Path:
        return self.t10 if size == 10000 else self.ctx.root / "research/replay_gray" / f"sleeve={int(size)}"

    def signals(self, win, size: float, scenario: str, traders: list[str]) -> list[PE.Signal]:
        from arkstream.phase5_population import hwm_signals, previous_reference

        sigs = PR.signals_from_orders(PR.tree_orders(self.tree(size), win.origin, "test", scenario, traders))
        out = []
        prev = previous_reference(self.ctx, win.origin, traders, win.start - timedelta(days=14)) if (
            self.eref_hwm) else {}
        for tr in traders:
            s = sigs.get(tr, [])
            out += hwm_signals(s, prev.get(tr)) if self.eref_hwm else s
        return out

    def run_one(self, data, win, config: str, scenario: str, size: float, traders: list[str]):
        kind = {"S": "S", "U": "U", "G": "G"}[config]
        alloc = {t: float(size) for t in traders}
        rules = PR.scheme_rules(self.ctx, kind, alloc, self.stress, **self.over)
        eng = PE.Engine(rules, self.costs[scenario], data.market, PR.ms(win.start), PR.ms(win.end),
                        triggers=data.triggers, reviews=PR.review_times(win.start, win.end, rules.review_days))
        res = eng.run(self.signals(win, size, scenario, traders))
        return rules, eng, res

    def window(self, win, scenarios, gray_sizes, write=True) -> list[dict]:
        data = PR.WindowData(self.ctx, win, self.sleeves,
                             [self.t10, *[self.tree(g) for g in gray_sizes]], self.bars, self.costs, self.ex)
        market, marks = alpha_market(self.ctx, win.origin)
        rows = []
        plan = [(c, sc, 10000.0, self.sleeves) for sc in scenarios for c in ("S", "U")]
        plan += [("G", sc, float(g), self.handoff) for sc in scenarios for g in gray_sizes]
        for config, scenario, size, traders in plan:
            rules, eng, res = self.run_one(data, win, config, scenario, size, traders)
            fr = PR.frames(res)
            daily, fund, ledger = PR.daily_book(fr["fills"], rules.allocations, marks, data.funding, win.start,
                                                win.end)
            alpha = alpha_of(ledger, fund, marks, market, win.start.date(), win.end.date(), sorted(rules.allocations))
            tag = config if config != "G" else f"G{int(size)}"
            if write:
                folder = self.out / f"origin={win.origin}" / f"config={tag}" / f"scenario={scenario}"
                PR.write_run(folder, {**fr, "daily": daily})
                (folder / "max_stress_book.json").write_text(json.dumps(
                    {k: {"stress": v[0], "t": v[1], "book": v[2], "marks": v[3]}
                     for k, v in eng.max_stress_book.items()}, sort_keys=True) + "\n", encoding="utf-8")
            for r in summarize(win, tag, scenario, rules, fr, daily, alpha, eng):
                rows.append(r)
        return rows


def subminimum(rows: list[dict], size: int) -> dict:
    g = [r for r in rows if r["config"] == f"G{size}" and r["scenario"] == "base" and r["scope"] != "combined"]
    n = sum(r["intents"] for r in g)
    k = sum(r["sub_minimum_intents"] for r in g)
    filled = sum(r["physical_fills"] for r in g)
    return {"size": size, "intents": n, "sub_minimum": k, "share": k / n if n else None,
            "filled_per_week": filled / (len(g) * 2) if g else None}


def random_pairs(runner: Runner, wins, n_pairs: int = 200) -> pl.DataFrame:
    from arkstream.phase5_population import universe

    rows = []
    for win in wins:
        traders = universe(runner.t10, win.origin, "test")
        sigs = PR.signals_from_orders(PR.tree_orders(runner.t10, win.origin, "test", "base", traders))
        usable = sorted(t for t in traders if any(s.e_ref for s in sigs.get(t, [])))
        rng = np.random.default_rng([20251203, win.origin.toordinal()])
        data = PR.WindowData(runner.ctx, win, usable, [runner.t10], runner.bars, runner.costs, runner.ex)
        seen: set[tuple[str, str]] = set()
        k = 0
        while k < n_pairs:
            a, b = (usable[i] for i in rng.choice(len(usable), size=2, replace=False))
            pair = tuple(sorted((a, b)))
            if pair in seen:
                continue
            seen.add(pair)  # type: ignore[arg-type]
            k += 1
            alloc = {t: 10000.0 for t in pair}
            rules = PR.scheme_rules(runner.ctx, "S", alloc, runner.stress, **runner.over)
            eng = PE.Engine(rules, runner.costs["base"], data.market, PR.ms(win.start), PR.ms(win.end),
                            triggers=data.triggers, reviews=PR.review_times(win.start, win.end, rules.review_days))
            res = eng.run([s for t in pair for s in sigs.get(t, [])])
            h = pl.DataFrame(res.hourly)
            nav = h.group_by("t").agg(C("nav").sum()).sort("t")["nav"].to_list()
            lam = h.group_by("trader").agg(C("lambda").mean(), (C("lambda_set_by").str.starts_with("P2")).mean()
                                           .alias("p2_share"))
            ev = pl.DataFrame(res.events) if res.events else pl.DataFrame({"event": []}, schema={"event": pl.String})
            rows.append({"origin": win.origin, "a": pair[0], "b": pair[1],
                         "raw_return": sum(eng.sleeves[t].nav for t in pair) / 20000 - 1,
                         "max_drawdown": max_drawdown(nav, 20000.0),
                         "lambda_mean": num(lam["lambda"].mean()),
                         "lambda_min_sleeve": num(lam["lambda"].min()),
                         "p2_set_share": num(lam["p2_share"].mean()),
                         "p5_binding_updates": int((ev["event"] == "p5_binding").sum()),
                         "ladder_events": int((ev["event"] == "scheme_firing").sum()),
                         "state_firings": int((ev["event"] == "state_firing").sum()),
                         "faults": len(res.faults), "label": LABEL})
        print(f"{win.origin} random pairs: {k}", flush=True)
    return pl.DataFrame(rows)


def at_limits(runner: Runner, rows_books: dict, wins) -> list[dict]:
    """ADR-0095 item 6.2 (pinned): max permitted exposure in each sleeve's worst-stress shape, joint shock, exit."""
    sev = runner.costs["severe"]
    stress = runner.stress
    severe_exit = PE.Costs(name="severe_exit", regime="stress", delay_ms=sev.delay_ms,
                           delay_thin_ms=sev.delay_thin_ms,
                           fee_bps=stress.fee_bps, half_majors=stress.half_majors, half_other=stress.half_other,
                           impact_mult=stress.impact_mult, sqrt_y=stress.sqrt_y,
                           thin_volume_usdc=stress.thin_volume_usdc, receive_ms=stress.receive_ms,
                           debounce_ms=stress.debounce_ms)
    out = []
    for win in wins:
        data = PR.WindowData(runner.ctx, win, runner.sleeves, [runner.t10], runner.bars, runner.costs, runner.ex)
        for config, size, traders in (("S", 10000.0, runner.sleeves), ("G", None, runner.handoff)):
            key = (win.origin, config)
            books = rows_books.get(key)
            if not books:
                continue
            alloc = {t: float(size or books["size"]) for t in traders}
            rules = PR.scheme_rules(runner.ctx, config, alloc, stress, **runner.over)
            t = max(books[tr]["t"] for tr in traders if tr in books) if any(tr in books for tr in traders) else None
            if t is None:
                continue
            base = {tr: ({c: q * 1000.0 for c, q in books[tr]["book"].items()} if tr in books else {})
                    for tr in traders}
            marks: dict[str, float] = {}
            for tr in traders:
                marks.update(books.get(tr, {}).get("marks", {}))
            s1 = {}
            for tr in traders:
                gross = sum(abs(q) * marks.get(c, 0.0) for c, q in base[tr].items())
                s1[tr] = min(1.0, rules.gross_x * alloc[tr] / gross) if gross > 0 else 1.0
            res = PE.solve(rules, base, s1, marks, data.market, t, dict(alloc), 0.0)
            book: dict[str, float] = {}
            for tr in traders:
                for c, q in base[tr].items():
                    book[c] = book.get(c, 0.0) + res.lam[tr] * q
            shock = sum(abs(q) * marks[c] * data.market.shock(c, q > 0) for c, q in book.items() if c in marks)
            exit_cost = 0.0
            for c, q in book.items():
                if c not in marks:
                    continue
                e = PE.exit_bps(data.market, severe_exit, c, t, traders[0], abs(q) * marks[c])
                exit_cost += abs(q) * marks[c] * (e or 0.0) / PE.BPS
            loss = shock + exit_cost
            D = rules.D
            limit = 0.165 * D if config == "S" else rules.l_gray
            out.append({"origin": win.origin, "config": config, "t": t, "gross_usdc": sum(
                abs(q) * marks.get(c, 0.0) for c, q in book.items()), "lambda": json.dumps(res.lam),
                "set_by": json.dumps(res.set_by), "shock_loss": shock, "exit_cost_severe": exit_cost, "loss": loss,
                "limit": limit, "loss_share_of_D": loss / D, "pass": loss <= limit + 1e-9,
                "criterion": "F2a" if config == "S" else "F2b", "label": LABEL})
    return out


def digest(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*.parquet")):
        h.update(str(p.relative_to(folder)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def run(ctx, out: Path | None = None, pairs: bool = True) -> Path:
    out = Path(out) if out else ctx.root / DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner(ctx, out)
    wins = PR.dev_windows(ctx)
    # 1. the gray size: G* at both sizes in base, decided on the sub-minimum share after lambda
    rows = []
    for win in wins:
        rows += runner.window(win, ("base",), (2500, 5000), write=False)
    shares = {g: subminimum(rows, g) for g in (2500, 5000)}
    s25 = shares[2500]["share"] or 0.0
    gray = 5000 if s25 > 0.10 else 2500
    sizing = {"rule": "ADR-0090 items 4 and 6: count share of G* trigger-leg intents under 10 USDC after lambda, "
              "four development test windows pooled, base; > 0.10 -> 5,000", "shares": shares, "chosen": gray}
    (out / "gray_size.json").write_text(json.dumps(sizing, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"gray size {gray}: {shares}", flush=True)
    # 2. every configuration in every scenario
    rows = []
    for win in wins:
        rows += runner.window(win, PR.SCENARIOS, (gray,))
        print(f"{win.origin} pair runs written", flush=True)
    summary = pl.DataFrame(rows, infer_schema_length=None)
    summary.write_csv(out / "pair_summary.csv")
    # 3. stress at the limits on the base runs' worst-stress books
    books: dict = {}
    for win in wins:
        for config, tag in (("S", "S"), ("G", f"G{gray}")):
            path = out / f"origin={win.origin}" / f"config={tag}" / "scenario=base" / "max_stress_book.json"
            if path.is_file():
                b = json.loads(path.read_text(encoding="utf-8"))
                b["size"] = gray
                books[(win.origin, config)] = b
    pl.DataFrame(at_limits(runner, books, wins), infer_schema_length=None).write_csv(out / "stress_at_limits.csv")
    # 3b. historical stress: 10-11 Oct inside the 8 Oct window (F3)
    pl.DataFrame(historical_crash(out, wins[0].origin, ["S", "U", f"G{gray}"]), infer_schema_length=None).write_csv(
        out / "stress_historical.csv")
    # 4. context: 200 random pairs per window
    if pairs:
        random_pairs(runner, wins).write_csv(out / "random_pairs.csv")
    return out


def historical_crash(out: Path, origin: date, configs: list[str], scenarios=("base", "severe")) -> list[dict]:
    """F3 (ADR-0095 item 6.1): the 10-11 Oct path inside the 8 Oct window. The ladder acts as designed when every
    hour at or below a ladder step is in that step's state or a more restrictive one (S*: P6 on the scheme NAV;
    G*: P6 and the loss cap on the live book), and no update put the G* book above its stress budget."""
    rows = []
    lo, hi = PR.ms(PR.midnight(CRASH[0])), PR.ms(PR.midnight(CRASH[1]) + timedelta(days=1))
    for config in configs:
        for scenario in scenarios:
            folder = out / f"origin={origin}" / f"config={config}" / f"scenario={scenario}"
            if not (folder / "hourly.parquet").is_file():
                continue
            h = pl.read_parquet(folder / "hourly.parquet")
            ev = pl.read_parquet(folder / "events.parquet")
            orders = pl.read_parquet(folder / "orders.parquet")
            nav = h.group_by("t").agg(C("nav").sum(), C("exit_cost").sum(), C("scheme_state").first()).sort("t")
            alloc = float(h.filter(C("t") == h["t"].min())["nav"].sum())
            peak, consistent, worst = alloc, True, 0.0
            ladder = ((-0.15, "FLATTEN"), (-0.10, "REDUCE_ONLY"), (-0.05, "HALVED"))
            for t, v, _x, st in nav.rows():
                peak = max(peak, v)
                dd = v / peak - 1
                if lo <= t < hi:
                    worst = min(worst, dd)
                if config == "U":
                    continue
                for level, state in ladder:
                    # the state is set at the same hourly check that measures the drawdown
                    if dd <= level and PE.RANK[st] < PE.RANK[state]:
                        consistent = False
            crash = nav.filter((C("t") >= lo) & (C("t") < hi))
            loss_exit = max((alloc - v + x for _, v, x, _ in crash.rows()), default=0.0)
            in_crash = ev.filter((C("t") >= lo) & (C("t") < hi) & C("event").str.contains("firing|release"))
            fl = orders.filter(C("flatten") & (C("status") == "filled") & (C("decision_ms") >= lo)
                               & (C("decision_ms") < hi))
            exit_cost = num((fl["quantity"].abs() * (fl["fill_px"] - fl["mark"]).abs() + fl["fee"]).sum()) if (
                fl.height) else 0.0
            dec_path = folder / "decisions.parquet"
            breaches = 0
            if config.startswith("G") and dec_path.is_file():
                d = pl.read_parquet(dec_path)
                breaches = d.filter(C("target_stress") > C("stress_budget") + 1e-6).height
            rows.append({"origin": origin, "config": config, "scenario": scenario,
                         "crash_max_drawdown": worst, "crash_max_drawdown_usdc": -worst * alloc,
                         "crash_max_loss_incl_exit_usdc": loss_exit, "crash_state_events": in_crash.height,
                         "crash_events": json.dumps([f"{e['event']}:{e['state_to']}:{e['reason']}"
                                                     for e in in_crash.iter_rows(named=True)]),
                         "flatten_fills": fl.height, "flatten_cost_usdc": exit_cost,
                         "ladder_consistent": consistent if config != "U" else None,
                         "cap_breaches_at_update": breaches if config.startswith("G") else None,
                         "label": LABEL})
    return rows
