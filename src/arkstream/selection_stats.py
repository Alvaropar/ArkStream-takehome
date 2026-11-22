"""Phase 4 statistics, numpy and the standard library only (plan "Decision gates": no SciPy).

* `entry_week_blocks` / `block_bootstrap`: the ranking key's lower bound (ADR-0131), calendar-week blocks by entry
  week (trades opened in the same week stay together); `week_blocks` is the literal overlap-merged alternative,
  kept for the disclosure in ADR-0131 (one multi-week trip chains every week into one block);
* `ward`: Ward hierarchical clustering on standardised features (ADR-0132), Lance-Williams updates;
* `average_linkage`: hierarchical clustering on a distance matrix (co-movement, ADR-0132);
* `clopper_pearson`, `min_track_record`: the plan's exact interval on wins and Bailey and Lopez de Prado's MinTRL
  (ADR-0133), the beta quantile by bisection on the binomial CDF, the normal quantile from `statistics.NormalDist`;
* `spearman`, `trimmed_mean`, `percentile_of`: robust summaries used by the walk-forward and the diagnostics.

Every function is deterministic: seeds are explicit and ties break on input order.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

DAY_MS = 86_400_000
WEEK_OFFSET_DAYS = 3  # 1970-01-01 is a Thursday: (day + 3) // 7 counts Monday-aligned calendar weeks


def week_of(ms: np.ndarray) -> np.ndarray:
    """Monday-aligned UTC calendar week index of epoch milliseconds."""
    return (np.asarray(ms, dtype=np.int64) // DAY_MS + WEEK_OFFSET_DAYS) // 7


def week_blocks(open_ms: np.ndarray, close_ms: np.ndarray) -> np.ndarray:
    """Block id per trip: calendar weeks, merged where a trip spans several weeks so that trades overlapping in time
    stay in one block (merged intervals of [open week, close week]). Ids are 0..n_blocks-1 in time order."""
    w0, w1 = week_of(open_ms), week_of(close_ms)
    n = len(w0)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    order = np.lexsort((w1, w0))
    block = np.empty(n, dtype=np.int64)
    current, reach = -1, None
    for i in order:
        if reach is None or w0[i] > reach:
            current += 1
            reach = w1[i]
        else:
            reach = max(reach, w1[i])
        block[i] = current
    return block


def entry_week_blocks(open_ms: np.ndarray) -> np.ndarray:
    """Block id per trip: the calendar week the trip opened in (ADR-0131). Ids are 0..n_blocks-1 in time order. A
    trip is one observation in one block however long it is held, so a long-held position does not chain weeks."""
    w = week_of(open_ms)
    if len(w) == 0:
        return np.zeros(0, dtype=np.int64)
    return np.unique(w, return_inverse=True)[1].astype(np.int64)


def block_bootstrap(values: np.ndarray, blocks: np.ndarray, draws: int, rng: np.random.Generator) -> np.ndarray:
    """Means of `values` (one per trip) over `draws` resamples of whole blocks with replacement (as many blocks as
    observed). Each mean is trip-weighted: the sum of the drawn trips' values over their count."""
    values = np.asarray(values, dtype=float)
    nb = int(blocks.max()) + 1 if len(blocks) else 0
    if nb == 0:
        return np.zeros(0)
    sums = np.bincount(blocks, weights=values, minlength=nb)
    counts = np.bincount(blocks, minlength=nb).astype(float)
    pick = rng.integers(0, nb, size=(draws, nb))
    return sums[pick].sum(axis=1) / counts[pick].sum(axis=1)


def quantile(x: np.ndarray, q: float) -> float:
    """Linear-interpolation quantile (numpy's default), as a float."""
    return float(np.quantile(np.asarray(x, dtype=float), q))


def standardise(x: np.ndarray) -> np.ndarray:
    """Column z-scores; a constant column becomes 0."""
    mu = x.mean(axis=0)
    sd = x.std(axis=0)
    sd[sd == 0] = 1.0
    return (x - mu) / sd


def _cut(merges: list[tuple[int, int]], n: int, k: int) -> np.ndarray:
    """Labels 0..k-1 after applying the first n - k merges, numbered by each cluster's first member."""
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in merges[: max(n - k, 0)]:
        ra, rb = find(a), find(b)
        parent[max(ra, rb)] = min(ra, rb)
    roots = [find(i) for i in range(n)]
    order: dict[int, int] = {}
    for r in roots:
        order.setdefault(r, len(order))
    return np.array([order[r] for r in roots], dtype=np.int64)


def ward(x: np.ndarray, k: int) -> np.ndarray:
    """Ward clustering of the rows of `x` (already standardised) into at most k clusters. Lance-Williams update on
    squared Euclidean distances; ties take the first pair in row order."""
    n = x.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    d = ((x[:, None, :] - x[None, :, :]) ** 2).sum(axis=2)
    size = np.ones(n)
    active = np.ones(n, dtype=bool)
    rep = list(range(n))  # the original row a cluster slot stands for (its smallest member)
    merges: list[tuple[int, int]] = []
    big = np.inf
    for _ in range(n - 1):
        m = np.where(active[:, None] & active[None, :], d, big)
        np.fill_diagonal(m, big)
        flat = int(np.argmin(m))
        i, j = divmod(flat, n)
        if i > j:
            i, j = j, i
        merges.append((rep[i], rep[j]))
        si, sj = size[i], size[j]
        for h in np.flatnonzero(active):
            if h in (i, j):
                continue
            sh = size[h]
            d[i, h] = d[h, i] = ((si + sh) * d[i, h] + (sj + sh) * d[j, h] - sh * d[i, j]) / (si + sj + sh)
        size[i] = si + sj
        active[j] = False
        rep[i] = min(rep[i], rep[j])
    return _cut(merges, n, k)


def average_linkage(dist: np.ndarray, threshold: float) -> np.ndarray:
    """Average-linkage clustering on a symmetric distance matrix, merging while the closest pair is below
    `threshold`. Labels numbered by first member."""
    n = dist.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    d = dist.astype(float).copy()
    size = np.ones(n)
    active = np.ones(n, dtype=bool)
    rep = list(range(n))
    merges: list[tuple[int, int]] = []
    for _ in range(n - 1):
        m = np.where(active[:, None] & active[None, :], d, np.inf)
        np.fill_diagonal(m, np.inf)
        flat = int(np.argmin(m))
        i, j = divmod(flat, n)
        if not m[i, j] < threshold:
            break
        if i > j:
            i, j = j, i
        merges.append((rep[i], rep[j]))
        for h in np.flatnonzero(active):
            if h in (i, j):
                continue
            d[i, h] = d[h, i] = (size[i] * d[i, h] + size[j] * d[j, h]) / (size[i] + size[j])
        size[i] += size[j]
        active[j] = False
        rep[i] = min(rep[i], rep[j])
    return _cut(merges, n, n - len(merges))


def rank(x: np.ndarray) -> np.ndarray:
    """Average ranks (1-based), ties averaged."""
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="stable")
    r = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        r[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    """Spearman rank correlation over pairs where both are finite; None with fewer than 3 pairs or no spread."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return None
    ra, rb = rank(a[ok]), rank(b[ok])
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def trimmed_mean(x: np.ndarray, share: float) -> float | None:
    """Mean after dropping floor(share * n) values from each end; None when empty."""
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0:
        return None
    cut = int(math.floor(share * len(x)))
    core = x[cut : len(x) - cut] if len(x) - 2 * cut > 0 else x
    return float(core.mean())


def percentile_of(value: float, draws: np.ndarray) -> float:
    """Mid-rank percentile of `value` in `draws`: share below plus half the share equal."""
    draws = np.asarray(draws, dtype=float)
    return float(((draws < value).sum() + 0.5 * (draws == value).sum()) / len(draws))


def _binom_cdf(k: int, n: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 1.0 if k >= n else 0.0
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1)))


def _beta_quantile_int(q: float, a: int, b: int) -> float:
    """Quantile of Beta(a, b) for positive integers: P(Beta(a, b) <= x) = P(Bin(a + b - 1, x) >= a)."""
    n = a + b - 1
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        cdf = 1 - _binom_cdf(a - 1, n, mid)
        if cdf < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, alpha: float = 0.05, two_sided: bool = True) -> tuple[float, float]:
    """Exact binomial interval for k successes in n trials (two-sided at 1 - alpha, or one-sided lower bound with the
    upper bound 1)."""
    if n <= 0:
        return (0.0, 1.0)
    a = alpha / 2 if two_sided else alpha
    lo = 0.0 if k == 0 else _beta_quantile_int(a, k, n - k + 1)
    hi = 1.0 if (k == n or not two_sided) else _beta_quantile_int(1 - a, k + 1, n - k)
    return (lo, hi)


def min_track_record(sr: float, skew: float, kurt: float, sr_star: float = 0.0, alpha: float = 0.05) -> float | None:
    """Minimum track record length in observations (Bailey and Lopez de Prado, 2012), per-period Sharpe `sr`,
    skewness and (non-excess) kurtosis of the returns. None when sr <= sr_star (no length suffices)."""
    if not sr > sr_star:
        return None
    z = NormalDist().inv_cdf(1 - alpha)
    return float(1 + (1 - skew * sr + (kurt - 1) / 4 * sr**2) * (z / (sr - sr_star)) ** 2)


def moments(x: np.ndarray) -> tuple[float, float, float] | None:
    """Per-period Sharpe (mean / population sd), skewness and kurtosis (non-excess); None if fewer than 3 points or
    no spread."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std() == 0:
        return None
    m, s = x.mean(), x.std()
    z = (x - m) / s
    return float(m / s), float((z**3).mean()), float((z**4).mean())
