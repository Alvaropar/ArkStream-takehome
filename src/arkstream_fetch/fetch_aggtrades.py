"""Download Binance USD-M daily aggTrades zips, verified against Binance's published checksums.

    python -m arkstream_fetch.fetch_aggtrades --dry-run     # plan only: file count and expected size
    python -m arkstream_fetch.fetch_aggtrades               # seed, verify, download, resume

Source: https://data.binance.vision/data/futures/um/daily/aggTrades/<SYM>/<SYM>-aggTrades-<YYYY-MM-DD>.zip
and its published `<file>.zip.CHECKSUM` (sha256). Files go to
`data/reference/binance/aggtrades/<SYM>/`, with the .CHECKSUM beside each zip, and every verified file is
recorded in `data/reference/binance/aggtrades/MANIFEST.csv` (symbol, date, file, bytes, sha256, the
published sha256, source, retrieved_on, verified_on).

Rules:

* **Nothing unverified is kept.** Each zip is hashed while it is written to a `.part` file and moved into
  place only if its SHA-256 equals the published checksum. A mismatch is refused: the `.part` is deleted,
  the file is reported, and the run exits non-zero.
* **Resumable.** A file already in place whose size and SHA-256 match its manifest row is reused without
  any network call. A zip in place without a manifest row is verified against the published checksum
  before it is accepted. Interrupted downloads leave only `.part` files, which are discarded.
* **Seeds first.** Zips already fetched earlier (by default `data/lake/_raw/data/futures/um/daily/aggTrades`,
  checked against Binance's checksums when they were fetched) are copied into place and verified again
  against the published checksum, so they are never downloaded twice. The seed folder is only read.
* **Cutoff.** Dates after the research cutoff (2026-01-04) are refused.
* Bounded retries with backoff; only data.binance.vision is contacted; standard library only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

BASE_URL = "https://data.binance.vision/data/futures/um/daily/aggTrades"
ALLOWED_HOST = "data.binance.vision"
CUTOFF_DATE = date(2026, 1, 4)  # research cutoff date (config/decision_context.yaml: the last fill)
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "HYPEUSDT", "SOLUSDT")
DEFAULT_START, DEFAULT_END = date(2025, 9, 8), date(2026, 1, 4)  # history for the 8 Oct origin
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "reference" / "binance" / "aggtrades"
DEFAULT_SEED = ROOT / "data" / "lake" / "_raw" / "data" / "futures" / "um" / "daily" / "aggTrades"
MANIFEST = "MANIFEST.csv"
FIELDS = ["symbol", "date", "file", "bytes", "sha256", "published_sha256", "source", "retrieved_on", "verified_on"]
CHUNK = 1 << 20


class ChecksumMismatch(Exception):
    pass


# ------------------------------------------------------------------------------------------------ http

class Http(Protocol):
    def get_text(self, url: str) -> str: ...
    def content_length(self, url: str) -> int | None: ...
    def stream(self, url: str) -> Iterator[bytes]: ...


def _check_url(url: str) -> None:
    if not url.startswith(f"https://{ALLOWED_HOST}/"):
        raise ValueError(f"refusing to contact {url}: only {ALLOWED_HOST} is allowed")


class UrllibHttp:
    """Standard-library HTTP with bounded retries and exponential backoff."""

    def __init__(self, retries: int = 3, backoff_s: float = 2.0, timeout_s: float = 60.0):
        self.retries, self.backoff_s, self.timeout_s = retries, backoff_s, timeout_s

    def _open(self, url: str, method: str = "GET"):
        _check_url(url)
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, method=method, headers={"User-Agent": "arkstream-fetch/1"})
                return urllib.request.urlopen(req, timeout=self.timeout_s)  # noqa: S310 (host checked)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise FileNotFoundError(url) from e
                last = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
            time.sleep(self.backoff_s * 2 ** attempt)
        raise ConnectionError(f"{url}: gave up after {self.retries} attempts: {last}")

    def get_text(self, url: str) -> str:
        with self._open(url) as r:
            return r.read().decode("utf-8")

    def content_length(self, url: str) -> int | None:
        with self._open(url, "HEAD") as r:
            v = r.headers.get("Content-Length")
            return int(v) if v else None

    def stream(self, url: str) -> Iterator[bytes]:
        with self._open(url) as r:
            while block := r.read(CHUNK):
                yield block


# ------------------------------------------------------------------------------------------------ plan

@dataclass(frozen=True)
class Item:
    symbol: str
    day: date

    @property
    def name(self) -> str:
        return f"{self.symbol}-aggTrades-{self.day.isoformat()}.zip"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.symbol}/{self.name}"

    def target(self, out: Path) -> Path:
        return out / self.symbol / self.name


def items(symbols: Iterable[str], start: date, end: date) -> list[Item]:
    if end > CUTOFF_DATE:
        raise ValueError(f"end date {end} is after the research cutoff {CUTOFF_DATE}; refusing")
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return [Item(s, d) for s in symbols for d in days]


def read_manifest(out: Path) -> dict[tuple[str, str], dict[str, str]]:
    p = out / MANIFEST
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as fh:
        return {(r["symbol"], r["date"]): r for r in csv.DictReader(fh)}


def _replace(src: Path, dst: Path, tries: int = 10, wait_s: float = 0.1,
             sleep: Callable[[float], None] = time.sleep) -> None:
    """os.replace that waits out a brief lock. On Windows another program (antivirus, search indexer, an
    editor or file preview showing the file) can hold `dst` open for a moment, and the rename then fails
    with PermissionError. Retry with backoff (about 10 s in all), then raise with the path named."""
    for k in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if k == tries - 1:
                raise PermissionError(f"{dst}: still locked by another program after {tries} tries; close any "
                                      f"program that has it open and rerun (verified files are kept)") from None
            sleep(wait_s * 2 ** min(k, 5))


def write_manifest(out: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / (MANIFEST + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(rows):
            w.writerow({f: rows[k].get(f, "") for f in FIELDS})
    _replace(tmp, out / MANIFEST)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while b := fh.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def parse_checksum(text: str, name: str) -> str:
    """Binance .CHECKSUM: '<sha256>  <file name>'."""
    parts = text.split()
    if len(parts) < 2 or len(parts[0]) != 64 or parts[1].lstrip("*") != name:
        raise ValueError(f"unexpected CHECKSUM content for {name}: {text[:120]!r}")
    return parts[0].lower()


def seed_dates(seed_dir: Path) -> dict[str, str]:
    """When each seed zip was fetched and verified (the lake fetcher's record), keyed by file name."""
    db = seed_dir.parents[4] / "_verified.sqlite" if len(seed_dir.parents) > 4 else None
    if not db or not db.exists():
        return {}
    try:
        with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as c:
            rows = c.execute("select key, verified_at from verified where key like '%aggTrades%'").fetchall()
    except sqlite3.Error:
        return {}
    return {Path(k).name: v[:10] for k, v in rows}


@dataclass
class Plan:
    reuse: list[Item] = field(default_factory=list)     # in place, matches manifest: no network
    verify: list[Item] = field(default_factory=list)    # in place, not in manifest: verify against CHECKSUM
    seed: list[Item] = field(default_factory=list)      # copy from the seed folder, then verify
    download: list[Item] = field(default_factory=list)


def plan(todo: list[Item], out: Path, seed_dir: Path | None, rehash: bool = True) -> Plan:
    man = read_manifest(out)
    pl_ = Plan()
    for it in todo:
        t = it.target(out)
        row = man.get((it.symbol, it.day.isoformat()))
        if t.exists():
            if row and int(row["bytes"]) == t.stat().st_size and (not rehash or sha256_file(t) == row["sha256"]):
                pl_.reuse.append(it)
            else:
                pl_.verify.append(it)
        elif seed_dir is not None and (seed_dir / it.symbol / it.name).exists():
            pl_.seed.append(it)
        else:
            pl_.download.append(it)
    return pl_


# ------------------------------------------------------------------------------------------------ run

def _today() -> str:
    return datetime.now(UTC).date().isoformat()


class Placeable(Protocol):
    """Anything with a file name and a target path under the output folder (aggTrades days, kline months)."""

    @property
    def name(self) -> str: ...
    def target(self, out: Path) -> Path: ...


def _place(it: Placeable, out: Path, chunks: Iterable[bytes], published: str) -> tuple[int, str]:
    """Write chunks to <target>.part, hashing as it goes; move into place only on a checksum match."""
    t = it.target(out)
    t.parent.mkdir(parents=True, exist_ok=True)
    part = t.with_name(t.name + ".part")
    h, n = hashlib.sha256(), 0
    try:
        with open(part, "wb") as fh:
            for b in chunks:
                h.update(b)
                n += len(b)
                fh.write(b)
        got = h.hexdigest()
        if got != published:
            raise ChecksumMismatch(f"{it.name}: sha256 {got} != published {published}")
        _replace(part, t)
    finally:
        if part.exists():
            part.unlink()
    return n, got


def _file_chunks(p: Path) -> Iterator[bytes]:
    with open(p, "rb") as fh:
        while b := fh.read(CHUNK):
            yield b


def run(todo: list[Item], out: Path, seed_dir: Path | None, http: Http,
        log: Callable[[str], None] = print) -> dict[str, list[str]]:
    """Execute the plan. Returns {'reused','verified','seeded','downloaded','failed'} file names."""
    p = plan(todo, out, seed_dir)
    man = read_manifest(out)
    seeded_on = seed_dates(seed_dir) if seed_dir else {}
    res: dict[str, list[str]] = {k: [] for k in ("reused", "verified", "seeded", "downloaded", "failed")}
    res["reused"] = [it.name for it in p.reuse]
    work = [("verified", it) for it in p.verify] + [("seeded", it) for it in p.seed] + \
           [("downloaded", it) for it in p.download]
    for i, (kind, it) in enumerate(work, 1):
        try:
            text = http.get_text(it.url + ".CHECKSUM")
            published = parse_checksum(text, it.name)
            t = it.target(out)
            if kind == "verified":
                tmp = t.with_name(t.name + ".existing")
                _replace(t, tmp)  # re-verify through the same .part path; restore nothing on mismatch
                try:
                    n, got = _place(it, out, _file_chunks(tmp), published)
                finally:
                    if tmp.exists():
                        tmp.unlink()
                source, retrieved = "existing", man.get((it.symbol, it.day.isoformat()), {}).get("retrieved_on", "")
            elif kind == "seeded":
                assert seed_dir is not None
                n, got = _place(it, out, _file_chunks(seed_dir / it.symbol / it.name), published)
                source, retrieved = "seed", seeded_on.get(it.name, "")
            else:
                n, got = _place(it, out, http.stream(it.url), published)
                source, retrieved = "download", _today()
            t.with_name(t.name + ".CHECKSUM").write_text(text, encoding="utf-8")
            man[(it.symbol, it.day.isoformat())] = {
                "symbol": it.symbol, "date": it.day.isoformat(), "file": f"{it.symbol}/{it.name}", "bytes": str(n),
                "sha256": got, "published_sha256": published, "source": source, "retrieved_on": retrieved,
                "verified_on": _today()}
            write_manifest(out, man)  # after every file, so an interruption loses at most one
            res[kind].append(it.name)
            log(f"[{i}/{len(work)}] {kind:10s} {it.symbol}/{it.name} {n / 1e6:8.1f} MB")
        except FileNotFoundError:
            res["failed"].append(it.name)
            log(f"[{i}/{len(work)}] FAILED     {it.symbol}/{it.name}: not published (404)")
        except (ChecksumMismatch, ValueError, ConnectionError) as e:
            res["failed"].append(it.name)
            log(f"[{i}/{len(work)}] FAILED     {it.symbol}/{it.name}: {e}")
    return res


def dry_run(todo: list[Item], out: Path, seed_dir: Path | None, http: Http | None,
            log: Callable[[str], None] = print, workers: int = 8) -> dict[str, int]:
    """Count files by action and the expected size. Reads sizes with HEAD requests only (nothing is
    downloaded or written); pass http=None to skip the network and leave download sizes unknown."""
    p = plan(todo, out, seed_dir, rehash=False)
    sizes: dict[str, int | None] = {}
    if http is not None and p.download:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for it, n in zip(p.download, ex.map(lambda x: _safe_len(http, x.url), p.download), strict=True):
                sizes[it.name] = n
    seed_bytes = sum((seed_dir / it.symbol / it.name).stat().st_size for it in p.seed) if seed_dir else 0
    have_bytes = sum(it.target(out).stat().st_size for it in p.reuse + p.verify)
    dl_known = [v for v in sizes.values() if v is not None]
    missing = [k for k, v in sizes.items() if v is None]
    dl_bytes = sum(dl_known)
    total = have_bytes + seed_bytes + dl_bytes
    syms = sorted({it.symbol for it in todo})
    log(f"aggTrades plan: {len(todo)} files ({', '.join(syms)}), "
        f"{min(it.day for it in todo)} .. {max(it.day for it in todo)}")
    log(f"  already in place and verified (reuse): {len(p.reuse):4d}")
    log(f"  in place, not yet verified:            {len(p.verify):4d}  {have_bytes / 1e9:6.2f} GB in place")
    log(f"  copy from seed folder, then verify:    {len(p.seed):4d}  {seed_bytes / 1e9:6.2f} GB")
    log(f"  download:                              {len(p.download):4d}  {dl_bytes / 1e9:6.2f} GB"
        + (f"  ({len(missing)} sizes unknown: {', '.join(missing[:5])})" if missing else ""))
    log(f"  expected total on disk:                      {total / 1e9:6.2f} GB")
    log(f"  target: {out}")
    return {"files": len(todo), "reuse": len(p.reuse), "verify": len(p.verify), "seed": len(p.seed),
            "download": len(p.download), "download_bytes": dl_bytes, "seed_bytes": seed_bytes,
            "total_bytes": total, "unknown_sizes": len(missing)}


def _safe_len(http: Http, url: str) -> int | None:
    try:
        return http.content_length(url)
    except (FileNotFoundError, ConnectionError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_aggtrades", description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    ap.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    ap.add_argument("--end", type=date.fromisoformat, default=DEFAULT_END)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED, help="read-only folder of earlier zips")
    ap.add_argument("--no-seed", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print file count and expected size; write nothing")
    ap.add_argument("--offline", action="store_true", help="with --dry-run: no HEAD requests")
    a = ap.parse_args(argv)
    todo = items(a.symbols, a.start, a.end)
    seed = None if a.no_seed or not a.seed_dir.exists() else a.seed_dir
    if a.dry_run:
        dry_run(todo, a.out, seed, None if a.offline else UrllibHttp())
        return 0
    res = run(todo, a.out, seed, UrllibHttp())
    print({k: len(v) for k, v in res.items()})
    if res["failed"]:
        print("failed (rerun to retry; verified files are kept):", ", ".join(res["failed"][:20]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

