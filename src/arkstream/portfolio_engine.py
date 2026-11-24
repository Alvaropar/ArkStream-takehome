"""Phase 5 portfolio engine (P5-3): one event loop over the sleeves of a scheme (ADRs 0087-0089).

Pure logic, no file I/O; `portfolio_replay` builds the inputs from the frozen trees and writes the outputs.

* **Targets** (ADR-0087 item 2-3): sleeve base `B_{i,c} = k_i q_{i,c}` on the wallet's tradable coins, S1 scale
  `s1_i = min(1, 1.5 × denominator / G_i)` with `G_i = k_i Σ |q| mark` on the full priced book (ADR-0034), target
  `T_{i,c} = s_i λ_i B_{i,c}`, and the U\\* target of the same leg `s1_i B_{i,c}` logged beside it (F6).
* **λ solver** (ADR-0088 item 3): from 1 at each leader-driven update; per-sleeve S1, S2, P2-sleeve; then P1,
  P2-total, P3, P4, P5 (budget form) with one common factor on the contributing sleeves; repeated to a fixed point
  (1e-12 relative, at most 50 passes; no convergence -> the sleeves of a breached limit go to 0, logged as a fault).
  Hourly checks can only lower `λ` (S2, P5) and set the passive P4 reduce-only flag (item 4). G\\* (option C) runs
  S1 and the `L_gray` stress cap on the remaining budget.
* **Execution** (ADR-0087 items 4-8): per coin, sleeve deltas `Δ_i = T_i - held_i - pending_i`; offsetting parts
  crossed internally at the decision mark at no cost; the net part is one physical IOC allocated pro rata to
  `|Δ_i|`; deadband `max(10, 2% |T_c|)`; participation budget per coin per 4h bar summed over sleeves; minimum 10
  USDC; stale signals (> 30 s at decision) not executed; the 15-minute sweep executes residuals.
* **Pricing** (ADR-0087 item 10, the frozen tradable stack's cost model): the trigger leg of a leader batch uses the
  tree's reference price at acknowledgement (tape or parameterised drift, sweep anchor); every other leg (resizes,
  sweeps, state actions) is priced at the decision mark times the tape factor of the same signal when the tree has
  one, else the parameterised drift of ADR-0029 for its delay (`market.drift`); then half-spread, square-root
  impact and fee as in `replay_orders.execute`. FLATTEN orders use stress costs.
* **States** (ADR-0089): NORMAL < HALVED < REDUCE_ONLY < FLATTEN < PAUSED < EXITED per sleeve, capped by the scheme
  state (P6 ladder); REDUCE_ONLY keeps the held legs' shape with a scale that can only fall, a sign flip gives 0.
* **Cost runs B and C** (ADRs 0098-0099), all off by default (run A): `pricer` re-prices every order the frozen model
  prices (the cost rebuild, O2 fill completeness); `risk_market` is the market the stress limits and the gray loss
  cap read (C's daily refit); `shadow_market` logs C1 and O2 on that model without acting on them. C1 always
  compares with `market`, the frozen model.
"""

from __future__ import annotations

import bisect
import heapq
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

BPS = 10_000.0
MINUTE = 60_000
HOUR = 3_600_000
DAY = 86_400_000
BAR = 4 * HOUR
STATES = ("NORMAL", "HALVED", "REDUCE_ONLY", "FLATTEN", "PAUSED", "EXITED")
RANK = {s: i for i, s in enumerate(STATES)}
MAJORS = ("BTC", "ETH")
EPS = 1e-12


# ---------------------------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class Leg:
    """One coin of a leader signal (a row of the frozen tree): the leader's position visible at the decision."""

    coin: str
    pos: float
    tradable: bool  # inside the wallet's tradable set and the price check (target 0 otherwise)
    priced: bool  # passes the price check: counts in the S1 gross (ADR-0034, the full priced book)
    ref_px: float | None = None  # the tree's reference at acknowledgement (trigger legs only)
    reason: str = ""  # the tree's pricing failure for this leg ('' = priced)
    tape_factor: float | None = None  # b1 / b0 of the same signal (direct coins), sign-independent
    half_bps: float | None = None  # the tree's half-spread (configured or the Corwin-Schultz estimate)
    mid_px: float | None = None  # the tree's mid at the leader fill (the trigger leg's cost anchor, mid_L)


@dataclass(frozen=True)
class Signal:
    t: int  # decision time (ms)
    trader: str
    coin: str  # trigger coin
    event_ms: int
    ack_ms: int
    legs: tuple[Leg, ...]
    e_ref: float | None  # frozen reference equity at the latest review (ADR-0052)
    review_reduce_only: bool = False
    forced: bool = False  # ADR-0046: liquidation or ADL batch (L5)
    batch: int = 0


class Market(Protocol):
    def mark(self, coin: str, t: int) -> float | None: ...

    def bar(self, coin: str, t: int) -> tuple[int | None, float | None, float | None, float | None]: ...

    def drift(self, coin: str, t: int, trader: str, regime: str, delay_ms: int, bucket: str) -> float | None: ...

    def half_spread(self, coin: str, t: int, regime: str) -> float: ...

    def funding(self, coin: str, hour: int) -> tuple[float | None, float | None]: ...

    def shock(self, coin: str, long: bool) -> float: ...

    def beta(self, coin: str) -> float: ...

    def bucket(self, volume: float | None) -> str: ...


@dataclass(frozen=True)
class Costs:
    """One scenario (execution.yaml): delays in ms, cost regime, fee, half-spread floors, impact multiple."""

    name: str
    regime: str
    delay_ms: int
    delay_thin_ms: int | None
    fee_bps: float
    half_majors: float
    half_other: float
    impact_mult: float  # 0 none, 1 linear, 3 3x_base (square-root model, ADR-0033)
    sqrt_y: float
    thin_volume_usdc: float
    receive_ms: int
    debounce_ms: int


@dataclass(frozen=True)
class Rules:
    kind: str  # "S" (scheme), "U" (unconstrained twin), "G" (capital book, option C)
    D: float
    allocations: dict[str, float]
    gross_x: float = 1.5
    s2_share: float = 0.25
    s3: tuple[float, float] = (-0.10, -0.15)
    p2_major: float = 0.25
    p2_other_sleeve: float = 0.10
    p2_other_total: float = 0.20
    p3_x: float = 0.5
    p4_share: float = 0.15
    p4_release: float = 0.90
    p5_usdc: float = 1200.0
    ladder: tuple[float, float, float] = (-0.05, -0.10, -0.15)
    l_gray: float = 750.0
    halved_scale: float = 0.5
    deadband_min: float = 10.0
    deadband_share: float = 0.02
    min_notional: float = 10.0
    participation: float = 0.005
    sweep_ms: int = 15 * MINUTE
    stale_ms: int = 30_000
    twap_minutes: int = 60
    twap_volume_usdc: float = 1_000_000.0
    review_days: int = 14
    triggers: bool = True
    cap_denominator: str = "fixed"  # fixed | min_nav (ADR-0095 item 2 variant)
    max_passes: int = 50
    rel_tol: float = 1e-12
    stress_costs: Costs | None = None  # exit costs and FLATTEN orders
    portfolio_limits: bool = True  # False: a one-sleeve population copy (S1, S3, states, triggers; ADR-0095 item 1)

    @property
    def limited(self) -> bool:
        return self.kind == "S"

    @property
    def stateful(self) -> bool:
        return self.kind in ("S", "G")


@dataclass
class TriggerSeries:
    """Point-in-time leader series for L1-L4 (each sorted by time; value known at its time)."""

    drawdown: list[tuple[int, float]] = field(default_factory=list)  # leader index drawdown from its HWM (<= 0)
    drawdown_limit: float | None = None  # 1.5 x the pre-origin max drawdown (negative)
    leverage: list[tuple[int, float]] = field(default_factory=list)
    leverage_limit: float | None = None  # 2 x the pre-origin p95
    equity: list[tuple[int, float]] = field(default_factory=list)  # snapshot equity
    outflow: list[tuple[int, float, float]] = field(default_factory=list)  # (t, outflow USDC >= 0, equity before)
    last_fill_ms: int | None = None  # last leader fill before the window


# ---------------------------------------------------------------------------------------------- risk quantities
def exit_bps(market: Market, costs: Costs, coin: str, t: int, trader: str, notional: float) -> float | None:
    """Stress-scenario shortfall per side (bps) for closing `notional` in one order now (ADR-0088 item 2)."""
    if notional <= 0:
        return 0.0
    _, bar_vol, vol_daily, sigma = market.bar(coin, t)
    delay = costs.delay_ms if costs.delay_thin_ms is None or (bar_vol or 0) >= costs.thin_volume_usdc else (
        costs.delay_thin_ms)
    d = market.drift(coin, t, trader, costs.regime, delay, market.bucket(bar_vol))
    half = market.half_spread(coin, t, costs.regime)
    impact = 0.0
    if costs.impact_mult:
        if not vol_daily or vol_daily <= 0 or sigma is None:
            return None
        y = market.impact_y(coin, t) if hasattr(market, "impact_y") else costs.sqrt_y  # C's refit (ADR-0099 item 8)
        impact = costs.impact_mult * BPS * y * sigma * math.sqrt(notional / vol_daily)
    return half + costs.fee_bps + max(d or 0.0, 0.0) + impact


def stress_loss(positions: dict[str, float], marks: dict[str, float], market: Market, costs: Costs | None, t: int,
                trader: str) -> float:
    """Shock every position at once (fall for longs, rise for shorts) plus the stress exit cost (ADR-0088)."""
    total = 0.0
    for coin in sorted(positions):
        q = positions[coin]
        m = marks.get(coin)
        if abs(q) < EPS or m is None:
            continue
        notional = abs(q) * m
        total += notional * market.shock(coin, q > 0)
        if costs is not None:
            e = exit_bps(market, costs, coin, t, trader, notional)
            total += notional * (e if e is not None else 0.0) / BPS
    return total


def largest_factor(f, limit: float, hi: float = 1.0, iters: int = 60) -> float:
    """Largest x in [0, hi] with f(x) <= limit, for f non-decreasing in x (bisection)."""
    if f(hi) <= limit + 1e-9:
        return hi
    if f(0.0) > limit + 1e-9:
        return 0.0
    lo = 0.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) <= limit:
            lo = mid
        else:
            hi = mid
    return lo


# ---------------------------------------------------------------------------------------------- the solver
@dataclass
class SolveResult:
    lam: dict[str, float]
    set_by: dict[str, str]
    passes: int
    converged: bool
    p5_binding: list[str]
    fault: str = ""


def solve(rules: Rules, base: dict[str, dict[str, float]], s1: dict[str, float], marks: dict[str, float],
          market: Market, t: int, nav: dict[str, float], loss_to_date: float = 0.0,
          include_p4: bool = True, start: dict[str, float] | None = None,
          only: tuple[str, ...] | None = None) -> SolveResult:
    """Whole-sleeve limit scales (ADR-0088 item 3; G\\*: ADR-0088 item 7 option C, ADR-0090 item 6).

    `base[i][c]` are the uncapped scaled legs k_i q_{i,c} on tradable coins; `s1[i]` the S1 scale. `start` (hourly
    checks) bounds every λ from above; `only` restricts the limits checked (hourly: S2, P5, cap)."""
    traders = sorted(base)
    lam = {i: min(s1.get(i, 1.0), (start or {}).get(i, 1.0)) for i in traders}
    set_by = {i: ("S1" if s1.get(i, 1.0) < 1 - EPS else "none") for i in traders}
    if start:
        for i in traders:
            if start.get(i, 1.0) < s1.get(i, 1.0) - EPS:
                set_by[i] = "previous"
    stress = rules.stress_costs
    p5_binding: list[str] = []

    def use(name: str) -> bool:
        return only is None or name in only

    def notional(i: str, c: str) -> float:
        m = marks.get(c)
        return abs(base[i].get(c, 0.0)) * m if m is not None else 0.0

    def cut(i: str, value: float, name: str) -> None:
        if value < lam[i] - EPS * max(1.0, lam[i]):
            lam[i] = max(value, 0.0)
            set_by[i] = name

    def net(c: str, scale: dict[str, float]) -> float:
        return sum(scale[i] * base[i].get(c, 0.0) for i in traders)

    def coins() -> list[str]:
        return sorted({c for i in traders for c in base[i]})

    if rules.kind == "U" or (rules.kind == "S" and not rules.portfolio_limits):
        return SolveResult(lam, set_by, 0, True, [])
    if rules.kind == "G":
        budget = max(rules.l_gray - max(loss_to_date, 0.0), 0.0)
        for i in traders:
            cut(i, largest_factor(lambda x, i=i: stress_loss({c: x * q for c, q in base[i].items()}, marks, market,
                                                             stress, t, i), budget, lam[i]), "L_gray")
        return SolveResult(lam, set_by, 1, True, [])

    D = rules.D
    passes = 0
    converged = False
    while passes < rules.max_passes:
        passes += 1
        before = dict(lam)
        # per-sleeve limits: S2, the per-sleeve part of P2
        for i in traders:
            if use("S2") and nav.get(i) is not None:
                cut(i, largest_factor(lambda x, i=i: stress_loss({c: x * q for c, q in base[i].items()}, marks,
                                                                 market, stress, t, i),
                                      rules.s2_share * max(nav[i], 0.0), lam[i]), "S2")
            if use("P2"):
                worst = max((notional(i, c) for c in base[i] if c not in MAJORS), default=0.0)
                if worst > 0:
                    cut(i, rules.p2_other_sleeve * D / worst, "P2_sleeve")

        def common(name: str, contrib: list[str], fn, limit: float) -> None:
            """One common factor on the contributing sleeves, the largest that restores the limit."""
            if not contrib:
                return

            def at(f: float) -> float:
                return fn({i: (f * lam[i] if i in contrib else lam[i]) for i in traders})

            if at(1.0) <= limit + 1e-9:
                return
            f = largest_factor(at, limit)
            for i in contrib:
                cut(i, f * lam[i], name)

        if use("P1"):
            common("P1", [i for i in traders if any(notional(i, c) > 0 for c in base[i])],
                   lambda sc: sum(sc[i] * notional(i, c) for i in traders for c in base[i]), rules.gross_x * D)
        if use("P2"):
            for c in coins():
                m = marks.get(c)
                if m is None:
                    continue
                n = net(c, lam)
                if abs(n) < EPS:
                    continue
                contrib = [i for i in traders if base[i].get(c, 0.0) * n > 0]
                limit = (rules.p2_major if c in MAJORS else rules.p2_other_total) * D
                common("P2_total", contrib, lambda sc, c=c, m=m: abs(net(c, sc)) * m, limit)
        if use("P3"):
            def beta_net(sc: dict[str, float]) -> float:
                return sum(net(c, sc) * marks[c] * market.beta(c) for c in coins() if c in marks)

            b = beta_net(lam)
            if abs(b) > EPS:
                contrib = [i for i in traders if b * sum(
                    base[i].get(c, 0.0) * marks[c] * market.beta(c) for c in base[i] if c in marks) > 0]
                common("P3", contrib, lambda sc: abs(beta_net(sc)), rules.p3_x * D)
        if use("P4") and include_p4:
            def book_stress(sc: dict[str, float]) -> float:
                return stress_loss({c: net(c, sc) for c in coins()}, marks, market, stress, t, traders[0])

            netted = {c: net(c, lam) for c in coins()}
            contrib = [i for i in traders if any(base[i].get(c, 0.0) * netted[c] > 0 for c in base[i])]
            common("P4", contrib, book_stress, rules.p4_share * D)
        if use("P5"):
            for c in coins():
                if marks.get(c) is None:
                    continue

                def coin_stress(sc: dict[str, float], c: str = c) -> float:
                    return stress_loss({c: net(c, sc)}, marks, market, stress, t, traders[0])

                if coin_stress(lam) > rules.p5_usdc + 1e-9:
                    p5_binding.append(c)
                    n = net(c, lam)
                    common("P5", [i for i in traders if base[i].get(c, 0.0) * n > 0], coin_stress, rules.p5_usdc)
        change = max((abs(lam[i] - before[i]) / max(before[i], EPS) for i in traders), default=0.0)
        if change <= rules.rel_tol:
            converged = True
            break
    if not converged:
        for i in traders:
            lam[i], set_by[i] = 0.0, "no_convergence"
        return SolveResult(lam, set_by, passes, False, sorted(set(p5_binding)), "solver_no_convergence")
    return SolveResult(lam, set_by, passes, True, sorted(set(p5_binding)))


# ---------------------------------------------------------------------------------------------- the engine
@dataclass
class Sleeve:
    trader: str
    allocation: float
    book: dict[str, float] = field(default_factory=dict)  # leader positions known at the latest decision
    tradable: dict[str, bool] = field(default_factory=dict)
    priced: dict[str, bool] = field(default_factory=dict)
    e_ref: float | None = None
    review_reduce_only: bool = False
    held: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    pending: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    cash: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    lam: float = 1.0
    s1: float = 1.0
    lam_by: str = "none"
    state: str = "NORMAL"
    state_reason: str = ""
    ro_scale: float = 1.0  # REDUCE_ONLY common scale (can only fall)
    hwm: float = 0.0
    nav: float = 0.0
    last_fill_ms: int | None = None
    last_signal: Signal | None = None
    flatten_start: dict[str, float] = field(default_factory=dict)
    nontradable_hours: list[tuple[int, float, float]] = field(default_factory=list)  # (t, outside, total) notional
    shortfalls: list[tuple[int, float, float]] = field(default_factory=list)  # (t, realised bps, stress model bps)
    shadow_shortfalls: list[tuple[int, float, float]] = field(default_factory=list)  # C: the updated stress model
    shadow_active: bool = False
    cleared: set[str] = field(default_factory=set)
    active: set[str] = field(default_factory=set)  # trigger conditions true at the previous check
    u_gross: float = 0.0  # the U* twin's target gross at the latest update (exposure weight of λ)

    @property
    def k(self) -> float | None:
        return min(self.allocation / self.e_ref, 1.0) if self.e_ref and self.e_ref > 0 else None


@dataclass
class Result:
    orders: list[dict]
    fills: list[dict]
    decisions: list[dict]
    hourly: list[dict]
    events: list[dict]
    faults: list[str]
    intents: list[dict]
    cost_records: list[dict] = field(default_factory=list)  # runs B and C (ADR-0099 item 10)


class Engine:
    def __init__(self, rules: Rules, costs: Costs, market: Market, start: int, end: int,
                 triggers: dict[str, TriggerSeries] | None = None, reviews: list[int] | None = None,
                 resume_at_review: bool = True, feed_gaps: dict[str, list[tuple[int, int]]] | None = None,
                 light: bool = False, risk_market: Market | None = None, pricer=None,
                 shadow_market: Market | None = None):
        self.rules, self.costs, self.market, self.start, self.end = rules, costs, market, start, end
        # ADR-0099 item 9: the stress limits and the gray loss cap read `risk_market` (run C: the daily refit);
        # C1 and O2 read `market` (the frozen model) in every run
        self.risk_market: Market = risk_market if risk_market is not None else market
        self.pricer = pricer  # runs B and C: the cost rebuild (ADR-0099 items 1-6)
        self.shadow_market = shadow_market  # run C: shadow C1 and O2, logged, never acted on
        self.cost_records: list[dict] = []
        self._records: dict[int, dict] = {}
        self.sleeves = {i: Sleeve(i, a) for i, a in sorted(rules.allocations.items())}
        for s in self.sleeves.values():
            s.hwm = s.nav = s.allocation
        self.triggers = triggers or {}
        self.reviews = sorted(reviews or [start])
        self.resume_at_review = resume_at_review
        self.light = light  # population runs: no per-decision log, a short hourly row
        self.usable_hours: dict[str, int] = defaultdict(int)
        self.max_stress_book: dict[str, tuple[float, int, dict[str, float], dict[str, float]]] = {}
        self.feed_gaps = feed_gaps or {}  # C3 fault injection: (start, end) of a leader feed outage per sleeve
        self.c3_stale_ms = 60_000
        self.scheme_state = "NORMAL"
        self.scheme_reason = ""
        self.scheme_hwm = sum(r for r in rules.allocations.values())
        self.start_nav = self.scheme_hwm
        self.p4_passive = False
        self.loss_cap_hit = False
        self.budget: dict[tuple[str, int], float] = defaultdict(float)
        self.queue: list[tuple] = []
        self.serial = 0
        self.orders: list[dict] = []
        self.fills: list[dict] = []
        self.decisions: list[dict] = []
        self.hourly: list[dict] = []
        self.events: list[dict] = []
        self.intents: list[dict] = []
        self.faults: list[str] = []
        self.last_mark: dict[str, float] = {}
        self._times: dict[int, list[int]] = {}

    # -- helpers
    def push(self, t: int, prio: int, kind: str, payload: object) -> None:
        self.serial += 1
        heapq.heappush(self.queue, (t, prio, self.serial, kind, payload))

    def mark(self, coin: str, t: int) -> float | None:
        m = self.market.mark(coin, t)
        if m is not None:
            self.last_mark[coin] = m
            return m
        return self.last_mark.get(coin)

    def log(self, t: int, kind: str, trader: str, **kw: object) -> None:
        self.events.append({"t": t, "event": kind, "trader": trader, **kw})

    def effective_state(self, s: Sleeve) -> str:
        return max((s.state, self.scheme_state), key=lambda x: RANK[x]) if self.rules.stateful else "NORMAL"

    def set_state(self, s: Sleeve, state: str, t: int, reason: str, value: float | None = None) -> None:
        if state == s.state:
            return
        up = RANK[state] > RANK[s.state]
        if state == "REDUCE_ONLY" and s.state != "REDUCE_ONLY":
            s.ro_scale = 1.0
        if state == "FLATTEN":
            s.flatten_start = {c: q + s.pending[c] for c, q in s.held.items()}
        self.log(t, "state_firing" if up else "state_release", s.trader, state_from=s.state, state_to=state,
                 reason=reason, value=value)
        s.state, s.state_reason = state, reason

    def set_scheme(self, state: str, t: int, reason: str, value: float | None = None) -> None:
        if state == self.scheme_state:
            return
        if state == "FLATTEN":
            for s in self.sleeves.values():
                s.flatten_start = {c: q + s.pending[c] for c, q in s.held.items()}
        if state == "REDUCE_ONLY":
            for s in self.sleeves.values():
                s.ro_scale = 1.0
        self.log(t, "scheme_firing" if RANK[state] > RANK[self.scheme_state] else "scheme_release", "scheme",
                 state_from=self.scheme_state, state_to=state, reason=reason, value=value)
        self.scheme_state, self.scheme_reason = state, reason

    def marks_for(self, coins: set[str], t: int) -> dict[str, float]:
        out = {}
        for c in sorted(coins):
            m = self.mark(c, t)
            if m is not None:
                out[c] = m
        return out

    def base_vectors(self, t: int) -> tuple[dict[str, dict[str, float]], dict[str, float], dict[str, float]]:
        base: dict[str, dict[str, float]] = {}
        s1: dict[str, float] = {}
        coins = {c for s in self.sleeves.values() for c in s.book} | {c for s in self.sleeves.values() for c in s.held}
        marks = self.marks_for(coins, t)
        for i, s in self.sleeves.items():
            k = s.k
            if k is None:
                base[i], s1[i] = {}, 0.0
                continue
            gross = sum(abs(q) * marks[c] for c, q in s.book.items() if s.priced.get(c) and c in marks) * k
            denom = s.allocation
            if self.rules.cap_denominator == "min_nav":
                denom = min(s.allocation, max(s.nav, 0.0))
            s1[i] = min(1.0, self.rules.gross_x * denom / gross) if gross > 0 else 1.0
            base[i] = {c: k * q for c, q in sorted(s.book.items()) if s.tradable.get(c) and abs(q) > EPS}
        return base, s1, marks

    def feed_frozen(self, trader: str, t: int) -> bool:
        """C3: the leader feed silent for more than 60 s while the sleeve holds a position (fault injection only)."""
        s = self.sleeves[trader]
        holding = any(abs(q) > EPS for q in s.held.values())
        return holding and any(a + self.c3_stale_ms <= t < b for a, b in self.feed_gaps.get(trader, []))

    def exit_cost(self, t: int, trader: str | None = None) -> float:
        total = 0.0
        if self.rules.stress_costs is None:
            return 0.0
        for s in self.sleeves.values():
            if trader is not None and s.trader != trader:
                continue
            for c, q in s.held.items():
                m = self.mark(c, t)
                if m is None or abs(q) < EPS:
                    continue
                e = exit_bps(self.risk_market, self.rules.stress_costs, c, t, s.trader, abs(q) * m)
                total += abs(q) * m * (e or 0.0) / BPS
        return total

    def loss_to_date(self, t: int) -> float:
        nav = sum(s.nav for s in self.sleeves.values())
        return max(self.start_nav - nav, 0.0)

    # -- targets
    def targets(self, t: int, base, s1, lam, reason: str) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for i, s in self.sleeves.items():
            st = self.effective_state(s)
            raw = {c: lam[i] * q for c, q in base[i].items()}
            u = {c: s1[i] * q for c, q in base[i].items()}
            if s.review_reduce_only and st == "NORMAL":
                st = "REDUCE_ONLY"
            scalar = 0.0
            ro_legs: list[str] = []
            if st == "NORMAL":
                scalar = 1.0
            elif st == "HALVED":
                scalar = self.rules.halved_scale
            elif st == "REDUCE_ONLY":
                held = {c: s.held[c] + s.pending[c] for c in set(s.held) | set(raw)}
                scale = s.ro_scale
                for c, h in held.items():
                    if abs(h) < EPS:
                        continue
                    r = raw.get(c, 0.0)
                    if abs(r) < EPS:
                        continue
                    if r * h < 0:
                        scale = 0.0
                        break
                    scale = min(scale, abs(h) / abs(r))
                s.ro_scale = scale
                scalar = scale
                ro_legs = [c for c in raw if abs(held.get(c, 0.0)) < EPS]
            targets = {c: scalar * q for c, q in raw.items()}
            for c in ro_legs:
                targets[c] = 0.0
            # every leg held but no longer in the base (leader flat, coin not tradable) goes to 0
            for c in s.held:
                targets.setdefault(c, 0.0)
            out[i] = targets
            ratio = scalar * lam[i] / s1[i] if s1.get(i) else 0.0
            s.u_gross = sum(abs(q) * (self.last_mark.get(c) or 0.0) for c, q in u.items())
            for c, q in sorted(u.items()):
                if c in ro_legs:
                    continue
                if abs(targets.get(c, 0.0) - ratio * q) > 1e-9 * max(abs(q), 1e-12):
                    self.faults.append(f"F6 shape broken {i} {c} at {t}")
            if self.light:
                continue
            tmarks = self.marks_for(set(targets), t)
            t_stress = stress_loss(targets, tmarks, self.risk_market, self.rules.stress_costs, t, i)
            self.decisions.append({
                "t": t, "trader": i, "reason": reason, "state": st, "lambda": lam[i], "lambda_set_by": s.lam_by,
                "s1": s1.get(i, 0.0), "state_scalar": scalar, "u_ratio": ratio, "reduce_only_legs": len(ro_legs),
                "legs": len(u),
                "target_gross": sum(abs(q) * (self.last_mark.get(c) or 0.0) for c, q in targets.items()),
                "u_gross": sum(abs(q) * (self.last_mark.get(c) or 0.0) for c, q in u.items()),
                "target_stress": t_stress,
                "stress_budget": (max(self.rules.l_gray - self.loss_to_date(t), 0.0) if self.rules.kind == "G"
                                  else self.rules.s2_share * max(s.nav, 0.0)),
            })
        return out

    # -- orders
    def price(self, coin: str, t: int, q: float, trader: str, sig: Signal | None, flatten: bool
              ) -> tuple[float | None, float, float, float, str, int, str, float]:
        """(fill px, fee, impact bps, half bps, reason, ack ms, price source, cost anchor) for an order of q at t."""
        costs = self.rules.stress_costs if flatten and self.rules.stress_costs else self.costs
        _, bar_vol, vol_daily, sigma = self.market.bar(coin, t)
        thin = costs.delay_thin_ms is not None and (bar_vol is None or bar_vol < costs.thin_volume_usdc)
        delay = costs.delay_thin_ms if thin and costs.delay_thin_ms is not None else costs.delay_ms
        m = self.mark(coin, t)
        if m is None:
            return None, 0.0, 0.0, 0.0, "missing_mark", t, "", 0.0
        anchor = m
        leg = next((g for g in sig.legs if g.coin == coin), None) if sig is not None else None
        trigger = (sig is not None and coin == sig.coin and leg is not None and not flatten and costs is self.costs
                   and (leg.ref_px is not None or bool(leg.reason)))
        ack = sig.ack_ms if trigger and sig is not None else t + max(delay - costs.receive_ms - costs.debounce_ms, 0)
        if trigger and leg is not None:
            if leg.reason:
                return None, 0.0, 0.0, 0.0, leg.reason, ack, "tree", m
            ref = leg.ref_px
            anchor = leg.mid_px if leg.mid_px else m
            half = leg.half_bps if leg.half_bps is not None else self.market.half_spread(coin, t, costs.regime)
            source = "tree_trigger"
        else:
            half = self.market.half_spread(coin, t, costs.regime)
            if leg is not None and leg.tape_factor is not None and not flatten:
                ref, source = m * leg.tape_factor, "tape_factor"
            else:
                d = self.market.drift(coin, t, trader, costs.regime, delay, self.market.bucket(bar_vol))
                if d is None:
                    return None, 0.0, 0.0, 0.0, "no_drift_cell", ack, "parameterised", m
                ref, source = m * (1 + math.copysign(1, q) * d / BPS), "parameterised"
        if ref is None or ref <= 0:
            return None, 0.0, 0.0, 0.0, "invalid_scenario_price", ack, source, m
        impact = 0.0
        if costs.impact_mult:
            if not vol_daily or vol_daily <= 0 or sigma is None:
                return None, 0.0, 0.0, half, "missing_sqrt_inputs", ack, source, m
            impact = costs.impact_mult * BPS * costs.sqrt_y * sigma * math.sqrt(abs(q) * ref / vol_daily)
        px = ref * (1 + math.copysign(1, q) * (half + impact) / BPS)
        fee = abs(q) * px * costs.fee_bps / BPS
        return px, fee, impact, half, "", ack, source, anchor

    def execute(self, t: int, targets: dict[str, dict[str, float]], sig: Signal | None, reason: str) -> None:
        coins = sorted({c for tg in targets.values() for c in tg})
        for c in coins:
            m = self.mark(c, t)
            if m is None:
                continue
            deltas = {}
            flatten = False
            for i, s in self.sleeves.items():
                if i not in targets or c not in targets[i]:
                    continue
                st = self.effective_state(s)
                if st in ("PAUSED", "EXITED") and abs(s.held[c] + s.pending[c]) < EPS:
                    continue
                d = targets[i][c] - s.held[c] - s.pending[c]
                frozen_feed = self.rules.stateful and self.feed_frozen(i, t)
                if (self.p4_passive and self.rules.limited) or frozen_feed:
                    cur = s.held[c] + s.pending[c]
                    if abs(cur + d) > abs(cur) + EPS or (cur * (cur + d) < 0):
                        d = -cur if cur * (cur + d) < 0 else 0.0
                        self.log(t, "C3_freeze_increase" if frozen_feed else "p4_reduce_only_block", i, coin=c)
                if st in ("FLATTEN", "PAUSED", "EXITED"):
                    flatten = True
                    start = s.flatten_start.get(c, s.held[c])
                    _, bar_vol, _, _ = self.market.bar(c, t)
                    if bar_vol is not None and bar_vol < self.rules.twap_volume_usdc and abs(start) > EPS:
                        slices = max(self.rules.twap_minutes * MINUTE // self.rules.sweep_ms, 1)
                        step = abs(start) / slices
                        if abs(d) > step:
                            d = math.copysign(step, d)
                if abs(d) * m >= 1e-9:
                    deltas[i] = d
            if not deltas:
                continue
            if sig is not None and c == sig.coin:
                # ADR-0090 item 4: the sized intent of the trigger leg, after λ and the state, before any minimum
                self.intents.append({"t": t, "trader": sig.trader, "coin": c, "notional": abs(sum(deltas.values())) * m,
                                     "sleeve_notional": abs(deltas.get(sig.trader, 0.0)) * m})
            total_target = sum(targets[i].get(c, 0.0) for i in targets)
            net = sum(deltas.values())
            pos = sum(d for d in deltas.values() if d > 0)
            neg = -sum(d for d in deltas.values() if d < 0)
            cross = min(pos, neg)
            band = max(self.rules.deadband_min, self.rules.deadband_share * abs(total_target) * m)
            physical = abs(net) * m >= band
            if cross * m >= self.rules.deadband_min and (physical or cross > 0):
                # internal cross at the decision mark, no cost (ADR-0087 item 4)
                for i, d in deltas.items():
                    side_total = pos if d > 0 else neg
                    part = d * cross / side_total if side_total > 0 else 0.0
                    if abs(part) < EPS:
                        continue
                    s = self.sleeves[i]
                    s.held[c] += part
                    s.cash -= part * m
                    deltas[i] = d - part
                    self.fills.append({"trader": i, "coin": c, "decision_ms": t, "ack_ms": t, "quantity": part,
                                       "fill_px": m, "fee": 0.0, "anchor_px": m, "status": "filled",
                                       "kind": "internal_cross", "reason": reason, "impact_bps": 0.0,
                                       "half_bps": 0.0, "physical_id": -1})
                self.log(t, "internal_cross", "scheme", coin=c, quantity=cross, notional=cross * m)
            if not physical:
                continue
            q = sum(deltas.values())
            if abs(q) < EPS:
                continue
            bar_id, bar_vol, _, _ = self.market.bar(c, t)
            status = "submitted"
            clip = 0.0
            if bar_vol is None or bar_vol <= 0:
                status = "missing_participation_volume"
            else:
                key = (c, t // BAR)
                left = self.rules.participation * bar_vol - self.budget[key]
                if abs(q) * m > left:
                    clip = abs(q) * m - max(left, 0.0)
                    q = math.copysign(max(left, 0.0) / m, q)
            if status == "submitted" and abs(q) * m < self.rules.min_notional:
                status = "below_minimum" if clip == 0 else "participation_exhausted"
            trigger_trader = sig.trader if sig is not None else sorted(deltas)[0]
            px, fee, impact, half, why, ack, source, anchor = (None, 0.0, 0.0, 0.0, "", t, "", m)
            record = None
            if status == "submitted":
                px, fee, impact, half, why, ack, source, anchor = self.price(c, t, q, trigger_trader, sig, flatten)
                if self.pricer is not None and px is not None and not why:
                    # ADR-0099 item 6: the rebuild prices only what the frozen model prices
                    record = self.pricer.price(self, c, t, q, trigger_trader, sig, flatten, px, impact, half, ack,
                                               source, anchor)
                    px, fee, impact, half, ack = (record["px"], record["fee"], record["impact_bps"],
                                                  record["half_bps"], record["ack_ms"])
                    if record["status"] != "filled":
                        why = record["status"]  # rejected_o2: the engine's failure path (ADR-0099 item 5)
                    if record.get("shadow_o2_reject"):
                        self.log(t, "shadow_o2_reject", trigger_trader, coin=c, value=record["shortfall_bps"])
                if px is not None and abs(q) * px < self.rules.min_notional:
                    status = "below_minimum_at_ack"
                elif ack >= self.end:
                    status = "after_window"
            oid = len(self.orders)
            if record is not None:
                record.update(physical_id=oid, decision_ms=t, coin=c, quantity=q, reason=reason, flatten=flatten,
                              order_status=status if status != "submitted" else (why or "filled"))
                self.cost_records.append(record)
                self._records[oid] = record
            shares = {i: d / sum(deltas.values()) for i, d in deltas.items()} if abs(sum(deltas.values())) > EPS else {}
            self.orders.append({"physical_id": oid, "coin": c, "decision_ms": t, "ack_ms": ack, "quantity": q,
                                "mark": m, "anchor_px": anchor, "fill_px": px, "fee": fee, "impact_bps": impact,
                                "half_bps": half,
                                "status": status if status != "submitted" else (why or "filled"),
                                "reason": reason, "source": source, "clip_usdc": clip, "flatten": flatten,
                                "sleeves": len(deltas), "bar_id": bar_id})
            if clip > 0:
                self.log(t, "participation_clip", "scheme", coin=c, clipped_usdc=clip)
            if status != "submitted":
                continue
            self.budget[(c, t // BAR)] += abs(q) * m
            alloc = {i: q * w for i, w in shares.items()}
            for i, a in alloc.items():
                self.sleeves[i].pending[c] += a
            self.push(ack, 0, "ack", (oid, c, alloc, px, fee, why, t, anchor, impact, half, reason))

    def on_ack(self, payload) -> None:
        oid, c, alloc, px, fee, why, t, m, impact, half, reason = payload
        total = sum(abs(a) for a in alloc.values())
        for i, a in sorted(alloc.items()):
            s = self.sleeves[i]
            s.pending[c] -= a
            if abs(s.pending[c]) < EPS:
                s.pending[c] = 0.0
            if why or px is None:
                continue
            f = fee * abs(a) / total if total > 0 else 0.0
            s.held[c] += a
            if abs(s.held[c]) < 1e-10:
                s.held[c] = 0.0
            s.cash -= a * px + f
            s.fees += f
            ack = self.orders[oid]["ack_ms"]
            self.fills.append({"trader": i, "coin": c, "decision_ms": t, "ack_ms": ack, "quantity": a,
                               "fill_px": px, "fee": f, "anchor_px": m, "status": "filled", "kind": "physical",
                               "reason": reason, "impact_bps": impact, "half_bps": half, "physical_id": oid})
            if self.rules.stress_costs is not None:
                model = exit_bps(self.market, self.rules.stress_costs, c, t, i, abs(a) * m)
                realised = math.copysign(1, a) * (px / m - 1) * BPS + self.costs.fee_bps
                if model is not None:
                    s.shortfalls.append((ack, realised, model))
                if self.shadow_market is not None:
                    shadow = exit_bps(self.shadow_market, self.rules.stress_costs, c, t, i, abs(a) * m)
                    if shadow is not None:
                        s.shadow_shortfalls.append((ack, realised, shadow))
        if self.pricer is not None and not why and px is not None and oid in self._records:
            self.pricer.filled(self._records[oid])

    # -- the decision paths
    def update(self, t: int, sig: Signal | None, reason: str) -> None:
        """A leader-driven target update (or a state change): λ from 1, every limit, then the orders."""
        self.value(t)
        base, s1, marks = self.base_vectors(t)
        navs = {i: s.nav for i, s in self.sleeves.items()}
        res = solve(self.rules, base, s1, marks, self.risk_market, t, navs, self.loss_to_date(t),
                    include_p4=sig is not None)
        if res.fault:
            self.faults.append(f"{res.fault} at {t}")
            self.log(t, "engine_fault", "scheme", reason=res.fault)
        for i, s in self.sleeves.items():
            s.lam, s.lam_by, s.s1 = res.lam[i], res.set_by[i], s1[i]
        if res.p5_binding:
            self.log(t, "p5_binding", "scheme", coins=",".join(res.p5_binding))
        lam = {i: s.lam for i, s in self.sleeves.items()}
        self.execute(t, self.targets(t, base, s1, lam, reason), sig, reason)

    def recheck(self, t: int, reason: str) -> None:
        """Hourly / sweep: targets at the current λ (hourly: S2, P5 or the cap can only lower it)."""
        base, s1, marks = self.base_vectors(t)
        lam = {i: min(s.lam, s1[i]) for i, s in self.sleeves.items()}
        if reason == "hourly" and self.rules.kind in ("S", "G"):
            navs = {i: s.nav for i, s in self.sleeves.items()}
            only = ("S2", "P5") if self.rules.kind == "S" else None
            res = solve(self.rules, base, s1, marks, self.risk_market, t, navs, self.loss_to_date(t),
                        include_p4=False, start=lam, only=only)
            for i, s in self.sleeves.items():
                if res.lam[i] < lam[i] - EPS:
                    s.lam, s.lam_by = res.lam[i], res.set_by[i] + "_hourly"
                    self.log(t, "hourly_scale", i, limit=res.set_by[i], value=res.lam[i])
                lam[i] = s.lam
            if self.rules.kind == "S":
                netted: dict[str, float] = defaultdict(float)
                for i in base:
                    for c, q in base[i].items():
                        netted[c] += lam[i] * q
                usage = stress_loss(dict(netted), marks, self.risk_market, self.rules.stress_costs, t,
                                    sorted(base)[0] if base else "")
                limit = self.rules.p4_share * self.rules.D
                if usage > limit + 1e-9 and not self.p4_passive:
                    self.p4_passive = True
                    self.log(t, "p4_passive_breach", "scheme", value=usage)
                elif self.p4_passive and usage < self.rules.p4_release * limit:
                    self.p4_passive = False
                    self.log(t, "p4_passive_release", "scheme", value=usage)
        self.execute(t, self.targets(t, base, s1, lam, reason), None, reason)

    # -- valuation, states and triggers
    def value(self, t: int) -> None:
        for s in self.sleeves.values():
            gross = 0.0
            hold = 0.0
            for c, q in s.held.items():
                if abs(q) < EPS:
                    continue
                m = self.mark(c, t)
                if m is None:
                    continue
                hold += q * m
                gross += abs(q) * m
            s.nav = s.allocation + s.cash + hold
            s.hwm = max(s.hwm, s.nav)

    def accrue_funding(self, hour: int) -> None:
        for s in self.sleeves.values():
            for c, q in sorted(s.held.items()):
                if abs(q) < EPS:
                    continue
                proxy, rate = self.market.funding(c, hour)
                if proxy is None or rate is None:
                    continue
                pay = -q * proxy * rate
                s.cash += pay
                s.funding += pay

    def latest(self, series: list, t: int):
        key = id(series)
        times = self._times.get(key)
        if times is None or len(times) != len(series):
            times = self._times[key] = [row[0] for row in series]
        i = bisect.bisect_right(times, t) - 1
        return series[i] if i >= 0 else None

    def check_triggers(self, s: Sleeve, t: int) -> None:
        tr = self.triggers.get(s.trader)
        fire: list[tuple[str, str, float | None]] = []
        if tr is not None:
            dd = self.latest(tr.drawdown, t)
            if dd is not None and tr.drawdown_limit is not None and dd[1] < tr.drawdown_limit:
                fire.append(("REDUCE_ONLY", "L1", dd[1]))
            lev = self.latest(tr.leverage, t)
            if lev is not None and tr.leverage_limit is not None and lev[1] > tr.leverage_limit:
                fire.append(("REDUCE_ONLY", "L2", lev[1]))
            eq = self.latest(tr.equity, t)
            if eq is not None and s.e_ref and eq[1] < 0.7 * s.e_ref:
                fire.append(("REDUCE_ONLY", "L3", eq[1] / s.e_ref))
            lo = bisect.bisect_right(self._outflow_times(tr), t - DAY)
            hi = bisect.bisect_right(self._outflow_times(tr), t)
            out = tr.outflow[lo:hi]
            if out:
                eq0 = out[0][2]
                share = sum(o[1] for o in out) / eq0 if eq0 and eq0 > 0 else None
                if share is not None and share > 0.5:
                    fire.append(("REDUCE_ONLY", "L4", share))
            last = s.last_fill_ms if s.last_fill_ms is not None else tr.last_fill_ms
            if last is not None and t - last > 14 * DAY:
                fire.append(("NORMAL", "L7", (t - last) / DAY))  # released at the review, no state of its own
        # L6: trailing 7-day share of leader notional-hours outside the tradable set
        # (pinned: measured only once the run holds the full trailing 7 days of the leader book)
        while s.nontradable_hours and s.nontradable_hours[0][0] <= t - 7 * DAY:
            s.nontradable_hours.pop(0)
        tot = sum(h[2] for h in s.nontradable_hours)
        out_share = sum(h[1] for h in s.nontradable_hours) / tot if tot > 0 else 0.0
        if t - self.start >= 7 * DAY and out_share > 0.10:
            fire.append(("REDUCE_ONLY", "L6", out_share))
        # C1: rolling 14-day median realised shortfall against the stress model's for the same orders
        while s.shortfalls and s.shortfalls[0][0] <= t - 14 * DAY:
            s.shortfalls.pop(0)
        recent = [x for x in s.shortfalls if x[0] <= t]
        if len(recent) >= 5:
            real = sorted(x[1] for x in recent)[len(recent) // 2]
            model = sorted(x[2] for x in recent)[len(recent) // 2]
            if real > model:
                fire.append(("REDUCE_ONLY", "C1", real - model))
        if self.shadow_market is not None:  # run C: C1 on the updated stress model, logged only (ADR-0099 item 9)
            while s.shadow_shortfalls and s.shadow_shortfalls[0][0] <= t - 14 * DAY:
                s.shadow_shortfalls.pop(0)
            sh = [x for x in s.shadow_shortfalls if x[0] <= t]
            on = False
            if len(sh) >= 5:
                real_s = sorted(x[1] for x in sh)[len(sh) // 2]
                model_s = sorted(x[2] for x in sh)[len(sh) // 2]
                on = real_s > model_s
                if on and not s.shadow_active:
                    self.log(t, "shadow_trigger_on", s.trader, trigger="C1", value=real_s - model_s)
            s.shadow_active = on
        active = {name for _, name, _ in fire}
        for _state, name, value in fire:
            if name not in s.active:  # a firing: the condition turns on (ADR-0089 item 3), whatever the state
                self.log(t, "trigger_on", s.trader, trigger=name, value=value)
        s.active = active
        s.cleared = {"L1", "L2", "L3", "L4", "L6", "C1"} - active
        for state, name, value in fire:
            if RANK[s.state] < RANK[state]:
                self.set_state(s, state, t, name, value)

    def _outflow_times(self, tr: TriggerSeries) -> list[int]:
        return self.latest_times(tr.outflow)

    def latest_times(self, series: list) -> list[int]:
        key = id(series)
        times = self._times.get(key)
        if times is None or len(times) != len(series):
            times = self._times[key] = [row[0] for row in series]
        return times

    def hourly_check(self, t: int) -> None:
        self.accrue_funding(t // HOUR)
        self.value(t)
        if self.rules.stateful:
            for s in self.sleeves.values():
                # L6 bookkeeping on the leader book
                outside = total = 0.0
                for c, q in s.book.items():
                    m = self.mark(c, t)
                    if m is None or abs(q) < EPS:
                        continue
                    total += abs(q) * m
                    if not s.tradable.get(c):
                        outside += abs(q) * m
                s.nontradable_hours.append((t, outside, total))
                dd = s.nav / s.hwm - 1 if s.hwm > 0 else 0.0
                if self.rules.kind == "S":
                    if dd <= self.rules.s3[1] and RANK[s.state] < RANK["FLATTEN"]:
                        self.set_state(s, "FLATTEN", t, "S3", dd)
                    elif dd <= self.rules.s3[0] and RANK[s.state] < RANK["REDUCE_ONLY"]:
                        self.set_state(s, "REDUCE_ONLY", t, "S3", dd)
                if self.rules.triggers:
                    self.check_triggers(s, t)
                if s.state == "FLATTEN" and all(abs(s.held[c]) < EPS and abs(s.pending[c]) < EPS for c in s.held):
                    self.set_state(s, "PAUSED", t, s.state_reason or "flattened")
            nav = sum(s.nav for s in self.sleeves.values())
            self.scheme_hwm = max(self.scheme_hwm, nav)
            dd = nav / self.scheme_hwm - 1
            h1, h2, h3 = self.rules.ladder
            if not self.rules.portfolio_limits:
                pass
            elif dd <= h3 and RANK[self.scheme_state] < RANK["FLATTEN"]:
                self.set_scheme("FLATTEN", t, "P6", dd)
            elif dd <= h2 and RANK[self.scheme_state] < RANK["REDUCE_ONLY"]:
                self.set_scheme("REDUCE_ONLY", t, "P6", dd)
            elif dd <= h1 and RANK[self.scheme_state] < RANK["HALVED"]:
                self.set_scheme("HALVED", t, "P6", dd)
            if self.rules.kind == "G" and not self.loss_cap_hit:
                loss = self.start_nav - nav + self.exit_cost(t)
                if loss >= self.rules.l_gray:
                    self.loss_cap_hit = True
                    self.set_scheme("FLATTEN", t, "L_gray_loss_cap", loss)
            if self.scheme_state == "FLATTEN" and all(
                    abs(s.held[c]) < EPS and abs(s.pending[c]) < EPS for s in self.sleeves.values() for c in s.held):
                self.set_scheme("EXITED", t, self.scheme_reason or "flattened")
        self.recheck(t, "hourly")
        self.value(t)
        for s in self.sleeves.values():
            if s.k is not None:
                self.usable_hours[s.trader] += 1
            if self.light:
                self.hourly.append({"t": t, "trader": s.trader, "nav": s.nav, "state": self.effective_state(s)})
                continue
            held_marks = self.marks_for(set(s.held), t)
            held_stress = stress_loss(dict(s.held), held_marks, self.risk_market, self.rules.stress_costs, t,
                                      s.trader)
            if held_stress > self.max_stress_book.get(s.trader, (-1.0,))[0]:
                book = {c: q for c, q in s.held.items() if abs(q) > EPS}
                self.max_stress_book[s.trader] = (held_stress, t, book, {c: held_marks[c] for c in book
                                                                          if c in held_marks})
            self.hourly.append({
                "t": t, "trader": s.trader, "nav": s.nav, "hwm": s.hwm, "lambda": s.lam, "lambda_set_by": s.lam_by,
                "state": self.effective_state(s), "gross": sum(abs(q) * (self.last_mark.get(c) or 0.0)
                                                               for c, q in s.held.items()),
                "funding": s.funding, "fees": s.fees, "scheme_state": self.scheme_state,
                "p4_passive": self.p4_passive, "exit_cost": self.exit_cost(t, s.trader), "u_gross": s.u_gross,
                "held_stress": held_stress,
            })

    def review(self, t: int) -> None:
        """ADR-0089 item 5: resume only at a review once the trigger cleared (modelled as yes, labelled)."""
        if not self.resume_at_review:
            return
        nav = sum(s.nav for s in self.sleeves.values())
        dd = nav / self.scheme_hwm - 1 if self.scheme_hwm > 0 else 0.0
        h1, h2, _ = self.rules.ladder
        if (self.scheme_state == "HALVED" and dd > h1) or (self.scheme_state == "REDUCE_ONLY" and dd > h2):
            self.set_scheme("NORMAL", t, "review_resume_modelled", dd)
        for s in self.sleeves.values():
            if s.state in ("REDUCE_ONLY", "HALVED", "PAUSED") and s.state_reason in s.cleared | {"S3"}:
                dd = s.nav / s.hwm - 1 if s.hwm > 0 else 0.0
                if s.state_reason != "S3" or dd > self.rules.s3[0]:
                    self.set_state(s, "NORMAL", t, "review_resume_modelled")

    def on_signal(self, sig: Signal) -> None:
        s = self.sleeves[sig.trader]
        for leg in sig.legs:
            s.book[leg.coin] = leg.pos
            s.tradable[leg.coin] = leg.tradable
            s.priced[leg.coin] = leg.priced
        s.e_ref = sig.e_ref
        s.review_reduce_only = sig.review_reduce_only
        s.last_fill_ms = sig.event_ms
        s.last_signal = sig
        if sig.t - sig.event_ms > self.rules.stale_ms:
            self.log(sig.t, "stale_signal", sig.trader, coin=sig.coin, age_ms=sig.t - sig.event_ms)
            return
        if sig.forced and self.rules.triggers and self.rules.stateful:
            self.log(sig.t, "trigger_on", sig.trader, trigger="L5", value=1.0)
            if RANK[s.state] < RANK["FLATTEN"]:
                self.set_state(s, "FLATTEN", sig.t, "L5")
        self.update(sig.t, sig, "signal")

    def run(self, signals: list[Signal]) -> Result:
        for sig in sorted(signals, key=lambda x: (x.t, x.trader, x.coin, x.batch)):
            if self.start <= sig.t < self.end:
                self.push(sig.t, 2, "signal", sig)
        t = self.start
        while t < self.end:
            self.push(t, 1, "hour", None)
            t += HOUR
        t = self.start + self.rules.sweep_ms
        while t < self.end:
            self.push(t, 3, "sweep", None)
            t += self.rules.sweep_ms
        for r in self.reviews:
            if self.start < r < self.end:
                self.push(r, 1, "review", None)
        while self.queue:
            t, _, _, kind, payload = heapq.heappop(self.queue)
            if t >= self.end:
                continue
            if kind == "ack":
                self.on_ack(payload)
            elif kind == "hour":
                self.hourly_check(t)
            elif kind == "review":
                self.review(t)
            elif kind == "signal":
                self.on_signal(payload)  # type: ignore[arg-type]
            elif kind == "sweep":
                self.value(t)
                self.recheck(t, "sweep")
        self.value(self.end - 1)
        return Result(self.orders, self.fills, self.decisions, self.hourly, self.events, self.faults, self.intents,
                      self.cost_records)
