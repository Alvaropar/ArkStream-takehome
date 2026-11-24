"""Distribution functions for Phase 4 v2 without scipy: Student t CDF and quantile, chi-square survival, the normal
CDF and quantile (stdlib `statistics.NormalDist`), Fisher-z correlation bounds and Spearman's rank correlation.

The incomplete beta and gamma functions use the continued fractions of Numerical Recipes (Lentz's method); they are
accurate to about 1e-12 over the ranges used here (tested against tabulated values)."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

_N = NormalDist()
EPS = 1e-15
TINY = 1e-300


def norm_cdf(x: float) -> float:
    return _N.cdf(x)


def norm_ppf(q: float) -> float:
    return _N.inv_cdf(q)


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > TINY else TINY)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > TINY else TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > TINY else TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > TINY else TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > TINY else TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1.0 - x) / b


def t_cdf(x: float, df: float) -> float:
    if not math.isfinite(df) or df > 1e7:
        return norm_cdf(x)
    tail = 0.5 * betainc(df / 2.0, 0.5, df / (df + x * x))
    return 1.0 - tail if x > 0 else tail


def t_ppf(q: float, df: float) -> float:
    """Quantile of Student's t by bisection on the CDF (monotone), to 1e-12."""
    if not 0 < q < 1:
        raise ValueError("q must be in (0, 1)")
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def _gammq_cf(a: float, x: float) -> float:
    b = x + 1.0 - a
    c = 1.0 / TINY
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > TINY else TINY)
        c = b + an / c
        c = c if abs(c) > TINY else TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def _gammp_series(a: float, x: float) -> float:
    ap, s = a, 1.0 / a
    term = s
    for _ in range(10000):
        ap += 1.0
        term *= x / ap
        s += term
        if abs(term) < abs(s) * EPS:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def gammaincc(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x)."""
    if x <= 0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gammp_series(a, x)
    return _gammq_cf(a, x)


def chi2_sf(x: float, df: float) -> float:
    return gammaincc(df / 2.0, x / 2.0)


def fisher_bounds(r: float, n: int, level: float = 0.95) -> tuple[float | None, float | None]:
    """Two-sided Fisher-z interval of a Pearson correlation on n pairs (null under 4 pairs or |r| = 1)."""
    if n < 4 or not math.isfinite(r) or abs(r) >= 1:
        return None, None
    z, se = math.atanh(r), 1.0 / math.sqrt(n - 3)
    k = norm_ppf(0.5 + level / 2.0)
    return math.tanh(z - k * se), math.tanh(z + k * se)


def rank_average(x: np.ndarray) -> np.ndarray:
    """Ranks 1..n with ties at their average rank."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    sx = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sx[j + 1] == sx[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    """Spearman's rho (Pearson on average ranks); null under 3 pairs or when either side is constant."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < 3:
        return None
    rx, ry = rank_average(x), rank_average(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def pearson(x: np.ndarray, y: np.ndarray, min_n: int = 3) -> float | None:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < min_n or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])
