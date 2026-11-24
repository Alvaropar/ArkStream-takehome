"""Download Hyperliquid public history from the REST info endpoint: hourly funding and 4h candles.

    python -m arkstream_fetch.fetch_hyperliquid --dry-run                 # plan only, no network
    python -m arkstream_fetch.fetch_hyperliquid                           # funding, all coins in coins.csv
    python -m arkstream_fetch.fetch_hyperliquid --kind candles_4h         # 4h candles (price check, ADR-0008)

Source: `POST https://api.hyperliquid.xyz/info` (public, no key), docs
hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint (read 2026-11-19). History
comes only from this endpoint (ADR-0008). Requests:

* funding: `{"type": "fundingHistory", "coin", "startTime", "endTime"}`; at most 500 rows per response,
  paginated with the last row's `time` + 1 as the next `startTime`.
* user_funding: `{"type": "userFunding", "user", "startTime", "endTime"}`, for a few leaders given with
  `--coins <address>...`, as a check of the funding convention only (never an input); paginated like funding.
* candles_4h: `{"type": "candleSnapshot", "req": {"coin", "interval": "4h", "startTime", "endTime"}}`; one
  request per coin (972 bars for the range; the endpoint keeps the latest 5,000 bars per interval).

Coins come from `data/reference/hyperliquid/coins.csv` (the core perps traded in eligible fills, written by
`python -m arkstream funding --coins`). Range: 2025-07-27T00:00Z to CUTOFF, read from
config/decision_context.yaml (never hard-coded).

Rules (same as fetch_aggtrades):

* **Raw responses saved unchanged**, one file per request: `<out>/<kind>/<COIN>/<COIN>-<startTime>.json`,
  with the request body, bytes, SHA-256, row count and first/last time in `<out>/<kind>/MANIFEST.csv`.
  The manifest is rewritten after every file, so an interruption loses at most one request.
* **Resumable.** A page in place whose bytes and SHA-256 match its manifest row is reused without any network
  call, and pagination continues from it. A page file without a manifest row is discarded and re-fetched.
* **Only api.hyperliquid.xyz/info is contacted** (POST, read-only info requests). Bounded retries with
  exponential backoff (429 and 5xx retried); a rate limiter keeps at least `--interval-s` (default 1.2 s)
  between requests: at weight ~20-45 per request that is under 1,200 per minute.
* Windows-safe renames (`_replace` from fetch_aggtrades); standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from arkstream_fetch.fetch_aggtrades import _replace

ALLOWED_HOST = "api.hyperliquid.xyz"
INFO_URL = f"https://{ALLOWED_HOST}/info"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "reference" / "hyperliquid"
DEFAULT_COINS = DEFAULT_OUT / "coins.csv"
CONFIG = ROOT / "config" / "decision_context.yaml"
START = datetime(2025, 7, 27, tzinfo=UTC)
PAGE_ROWS = 500
KINDS = ("funding", "candles_4h", "user_funding")
MANIFEST = "MANIFEST.csv"
FIELDS = ["coin", "start_ms", "end_ms", "file", "bytes", "sha256", "rows", "first_time_ms", "last_time_ms",
          "request", "retrieved_on"]
_COIN_RE = re.compile(r"^[A-Za-z0-9]+$")  # core perps only; a HIP-3 name ("xyz:AAPL") is refused
_USER_RE = re.compile(r"^0x[0-9a-f]{40}$")


def read_cutoff(config: Path = CONFIG) -> datetime:
    """CUTOFF from config/decision_context.yaml (`cutoff: "..."`), without a YAML dependency."""
    m = re.search(r'^cutoff:\s*"?([0-9T:.\-]+)Z?"?', config.read_text(encoding="utf-8"), re.M)
    if not m:
        raise ValueError(f"{config}: no cutoff line")
    return datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC)


def ms(t: datetime) -> int:
    return int(round(t.timestamp() * 1000))


# ------------------------------------------------------------------------------------------------ http

class Http(Protocol):
    def post(self, url: str, body: dict[str, Any]) -> bytes: ...


def _check_url(url: str) -> None:
    if url != INFO_URL:
        raise ValueError(f"refusing to contact {url}: only {INFO_URL} is allowed")


class UrllibHttp:
    """Standard-library POST with a minimum interval between requests, bounded retries and backoff."""

    def __init__(self, interval_s: float = 1.2, retries: int = 5, backoff_s: float = 5.0, timeout_s: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.interval_s, self.retries, self.backoff_s, self.timeout_s = interval_s, retries, backoff_s, timeout_s
        self.sleep, self.clock, self._last = sleep, clock, -1e18
        self.requests = 0

    def _wait(self) -> None:
        dt = self.clock() - self._last
        if dt < self.interval_s:
            self.sleep(self.interval_s - dt)
        self._last = self.clock()

    def post(self, url: str, body: dict[str, Any]) -> bytes:
        _check_url(url)
        data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        last: Exception | None = None
        for attempt in range(self.retries):
            self._wait()
            self.requests += 1
            try:
                req = urllib.request.Request(url, data=data, method="POST", headers={
                    "Content-Type": "application/json", "User-Agent": "arkstream-fetch/1"})
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:  # noqa: S310 (host checked)
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504):
                    raise ConnectionError(f"{url} {body}: HTTP {e.code}") from e
                last = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
            self.sleep(self.backoff_s * 2 ** attempt)
        raise ConnectionError(f"{url} {body}: gave up after {self.retries} attempts: {last}")


# ------------------------------------------------------------------------------------------------ requests

def request_body(kind: str, coin: str, start_ms: int, end_ms: int) -> dict[str, Any]:
    """`coin` is the key of the series: a coin, or for user_funding a leader address (lower-case hex)."""
    if kind == "user_funding":
        if not _USER_RE.match(coin):
            raise ValueError(f"{coin!r}: not a lower-case 0x address")
        return {"type": "userFunding", "user": coin, "startTime": start_ms, "endTime": end_ms}
    if not _COIN_RE.match(coin):
        raise ValueError(f"{coin!r}: not a core-perp coin name")
    if kind == "funding":
        return {"type": "fundingHistory", "coin": coin, "startTime": start_ms, "endTime": end_ms}
    if kind == "candles_4h":
        return {"type": "candleSnapshot", "req": {"coin": coin, "interval": "4h", "startTime": start_ms,
                                                  "endTime": end_ms}}
    raise ValueError(f"unknown kind {kind}")


def row_time(kind: str, row: dict[str, Any]) -> int:
    return int(row["t"] if kind == "candles_4h" else row["time"])


@dataclass(frozen=True)
class Page:
    coin: str
    start_ms: int

    def rel(self, kind: str) -> str:
        return f"{kind}/{self.coin}/{self.coin}-{self.start_ms}.json"


def read_manifest(out: Path, kind: str) -> dict[tuple[str, int], dict[str, str]]:
    p = out / kind / MANIFEST
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as fh:
        return {(r["coin"], int(r["start_ms"])): r for r in csv.DictReader(fh)}


def write_manifest(out: Path, kind: str, rows: dict[tuple[str, int], dict[str, str]]) -> None:
    d = out / kind
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (MANIFEST + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow({f: rows[k].get(f, "") for f in FIELDS})
    _replace(tmp, d / MANIFEST)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _valid(out: Path, row: dict[str, str]) -> bool:
    p = out / row["file"]
    return p.exists() and p.stat().st_size == int(row["bytes"]) and _sha(p.read_bytes()) == row["sha256"]


def _save(out: Path, rel: str, raw: bytes) -> None:
    t = out / rel
    t.parent.mkdir(parents=True, exist_ok=True)
    part = t.with_name(t.name + ".part")
    part.write_bytes(raw)
    _replace(part, t)


def next_start(kind: str, rows: list[dict[str, Any]], end_ms: int) -> int | None:
    """Start of the next page, or None when this coin is complete."""
    if kind == "candles_4h" or len(rows) < PAGE_ROWS:
        return None
    nxt = row_time(kind, rows[-1]) + 1
    return nxt if nxt <= end_ms else None


def fetch_coin(kind: str, coin: str, start_ms: int, end_ms: int, out: Path, http: Http | None,
               man: dict[tuple[str, int], dict[str, str]], log: Callable[[str], None]) -> dict[str, int]:
    """Walk one coin's pages from start_ms; reuse verified pages, fetch the rest. Returns counts."""
    n = {"reused": 0, "fetched": 0, "rows": 0}
    st: int | None = start_ms
    while st is not None:
        pg = Page(coin, st)
        row = man.get((coin, st))
        if row and int(row["end_ms"]) == end_ms and _valid(out, row):
            rows = json.loads((out / row["file"]).read_bytes())
            n["reused"] += 1
        else:
            if http is None:
                raise ConnectionError(f"{coin} page {st} not on disk and no network allowed")
            body = request_body(kind, coin, st, end_ms)
            raw = http.post(INFO_URL, body)
            rows = json.loads(raw)
            if not isinstance(rows, list):
                raise ValueError(f"{coin} {st}: unexpected response {raw[:200]!r}")
            _save(out, pg.rel(kind), raw)
            ts = [row_time(kind, r) for r in rows]
            man[(coin, st)] = {
                "coin": coin, "start_ms": str(st), "end_ms": str(end_ms), "file": pg.rel(kind),
                "bytes": str(len(raw)), "sha256": _sha(raw), "rows": str(len(rows)),
                "first_time_ms": str(min(ts)) if ts else "", "last_time_ms": str(max(ts)) if ts else "",
                "request": json.dumps(body, separators=(",", ":"), sort_keys=True),
                "retrieved_on": datetime.now(UTC).date().isoformat()}
            write_manifest(out, kind, man)
            n["fetched"] += 1
        n["rows"] += len(rows)
        st = next_start(kind, rows, end_ms)
    return n


def read_coins(path: Path) -> list[str]:
    with open(path, newline="", encoding="utf-8") as fh:
        coins = sorted({r["coin"] for r in csv.DictReader(fh)})
    lower = [c.lower() for c in coins]
    if len(set(lower)) != len(lower):
        raise ValueError("two coins differ only by case; folder names would collide on Windows")
    return coins


def run(kind: str, coins: list[str], out: Path, http: Http | None, end: datetime,
        log: Callable[[str], None] = print) -> dict[str, list[str]]:
    if end > read_cutoff():
        raise ValueError(f"end {end} is after the research cutoff; refusing")
    s, e = ms(START), ms(end)
    man = read_manifest(out, kind)
    res: dict[str, list[str]] = {"done": [], "failed": []}
    for i, c in enumerate(coins, 1):
        try:
            n = fetch_coin(kind, c, s, e, out, http, man, log)
            res["done"].append(c)
            log(f"[{i}/{len(coins)}] {kind} {c}: {n['rows']} rows, {n['fetched']} fetched, {n['reused']} reused")
        except (ConnectionError, ValueError) as ex:
            res["failed"].append(c)
            log(f"[{i}/{len(coins)}] FAILED {kind} {c}: {ex}")
    return res


def dry_run(kind: str, coins: list[str], out: Path, end: datetime, log: Callable[[str], None] = print) -> dict:
    """No network: pages already verified on disk, and the expected request count for the rest."""
    man = read_manifest(out, kind)
    have = {c for (c, st), r in man.items() if st == ms(START) and _valid(out, r)}
    per = (-(-(ms(end) - ms(START)) // 3_600_000) // PAGE_ROWS + 1) if kind == "funding" else 1
    todo = [c for c in coins if c not in have]
    log(f"{kind}: {len(coins)} coins, {START.isoformat()} .. {end.isoformat()}; first page on disk for "
        f"{len(have)}; about {len(todo) * per} requests left (~{len(todo) * per * 1.3 / 60:.0f} min at 1.2 s)")
    return {"coins": len(coins), "have": len(have), "requests": len(todo) * per}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_hyperliquid", description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", choices=KINDS, default="funding")
    ap.add_argument("--coins", nargs="+", default=None, help="default: every coin in --coins-file")
    ap.add_argument("--coins-file", type=Path, default=DEFAULT_COINS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--interval-s", type=float, default=1.2, help="minimum seconds between requests")
    ap.add_argument("--dry-run", action="store_true", help="no network: show what is on disk and what is left")
    a = ap.parse_args(argv)
    coins = sorted(a.coins) if a.coins else read_coins(a.coins_file)
    end = read_cutoff()
    if a.dry_run:
        dry_run(a.kind, coins, a.out, end)
        return 0
    res = run(a.kind, coins, a.out, UrllibHttp(interval_s=a.interval_s), end)
    print({k: len(v) for k, v in res.items()})
    if res["failed"]:
        print("failed (rerun to retry; verified pages are kept):", ", ".join(res["failed"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
