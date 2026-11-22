"""Download Binance USD-M monthly 1m kline zips, verified against Binance's published checksums.

    python -m arkstream_fetch.fetch_klines --dry-run --offline   # plan only: no network, nothing written
    python -m arkstream_fetch.fetch_klines --dry-run             # plan with sizes (HEAD requests only)
    python -m arkstream_fetch.fetch_klines                       # seed, verify, download, resume

Source: https://data.binance.vision/data/futures/um/monthly/klines/<SYM>/1m/<SYM>-1m-<YYYY-MM>.zip and its
published `<file>.zip.CHECKSUM` (sha256). Files go to `data/reference/binance/klines/<SYM>/`, the .CHECKSUM beside
each zip, and every verified file is recorded in `data/reference/binance/klines/MANIFEST.csv` (symbol, month, file,
bytes, sha256, published_sha256, source, retrieved_on, verified_on). `python -m arkstream refprices --from-zips
data/reference/binance/klines` then rebuilds the kline lake and the reference prices from these files alone.

Rules (the same as fetch_aggtrades, whose download helpers this module reuses):

* **Nothing unverified is kept.** Each zip is hashed while written to a `.part` file and moved into place only if
  its SHA-256 equals the published checksum; a mismatch is refused, reported and the run exits non-zero.
* **Resumable.** A zip in place whose size and SHA-256 match its manifest row is reused with no network call.
* **Seeds first.** Zips fetched earlier (by default the lake's `data/lake/_raw/data/futures/um/monthly/klines`)
  are copied into place and verified again against the published checksum. The seed folder is only read.
* **Not published is not a failure.** A month Binance does not publish (404: the contract was not listed yet)
  is reported as `not_published`.
* **Cutoff.** Months after the research cutoff month (2026-01) are refused. Only data.binance.vision is contacted;
  standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from arkstream_fetch.fetch_aggtrades import (
    ChecksumMismatch,
    Http,
    UrllibHttp,
    _file_chunks,
    _place,
    _replace,
    _safe_len,
    _today,
    parse_checksum,
    sha256_file,
)

BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"
CUTOFF_MONTH = "2026-01"  # month of the research cutoff (config/decision_context.yaml: the last fill)
DEFAULT_START, DEFAULT_END = "2025-07", "2026-01"  # reference price coverage (A13)
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "reference" / "binance" / "klines"
DEFAULT_SEED = ROOT / "data" / "lake" / "_raw" / "data" / "futures" / "um" / "monthly" / "klines"
DEFAULT_SYMBOLS_FILE = ROOT / "data" / "reference" / "binance" / "binance_um_symbols.txt"
MANIFEST = "MANIFEST.csv"
FIELDS = ["symbol", "month", "file", "bytes", "sha256", "published_sha256", "source", "retrieved_on", "verified_on"]


@dataclass(frozen=True)
class Item:
    symbol: str
    month: str  # YYYY-MM

    @property
    def name(self) -> str:
        return f"{self.symbol}-1m-{self.month}.zip"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.symbol}/1m/{self.name}"

    def target(self, out: Path) -> Path:
        return out / self.symbol / self.name

    def seed(self, seed_dir: Path) -> Path:
        return seed_dir / self.symbol / "1m" / self.name


def months(start: str, end: str) -> list[str]:
    if end > CUTOFF_MONTH:
        raise ValueError(f"end month {end} is after the research cutoff month {CUTOFF_MONTH}; refusing")
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    y, m = map(int, start.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def items(symbols: Iterable[str], start: str, end: str) -> list[Item]:
    ms = months(start, end)
    return [Item(s, m) for s in sorted(set(symbols)) for m in ms]


def read_symbols(path: Path) -> list[str]:
    return [s.strip() for s in path.read_text(encoding="utf-8").splitlines() if s.strip() and not s.startswith("#")]


def read_manifest(out: Path) -> dict[tuple[str, str], dict[str, str]]:
    p = out / MANIFEST
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as fh:
        return {(r["symbol"], r["month"]): r for r in csv.DictReader(fh)}


def write_manifest(out: Path, rows: dict[tuple[str, str], dict[str, str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / (MANIFEST + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(rows):
            w.writerow({f: rows[k].get(f, "") for f in FIELDS})
    _replace(tmp, out / MANIFEST)


@dataclass
class Plan:
    reuse: list[Item] = field(default_factory=list)
    verify: list[Item] = field(default_factory=list)
    seed: list[Item] = field(default_factory=list)
    download: list[Item] = field(default_factory=list)


def plan(todo: list[Item], out: Path, seed_dir: Path | None, rehash: bool = True) -> Plan:
    man = read_manifest(out)
    p = Plan()
    for it in todo:
        t = it.target(out)
        row = man.get((it.symbol, it.month))
        if t.exists():
            if row and int(row["bytes"]) == t.stat().st_size and (not rehash or sha256_file(t) == row["sha256"]):
                p.reuse.append(it)
            else:
                p.verify.append(it)
        elif seed_dir is not None and it.seed(seed_dir).exists():
            p.seed.append(it)
        else:
            p.download.append(it)
    return p


def run(todo: list[Item], out: Path, seed_dir: Path | None, http: Http,
        log: Callable[[str], None] = print) -> dict[str, list[str]]:
    """Execute the plan. Returns {'reused','verified','seeded','downloaded','not_published','failed'} names."""
    p = plan(todo, out, seed_dir)
    man = read_manifest(out)
    res: dict[str, list[str]] = {k: [] for k in ("reused", "verified", "seeded", "downloaded", "not_published",
                                                  "failed")}
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
                _replace(t, tmp)
                try:
                    n, got = _place(it, out, _file_chunks(tmp), published)
                finally:
                    if tmp.exists():
                        tmp.unlink()
                source, retrieved = "existing", man.get((it.symbol, it.month), {}).get("retrieved_on", "")
            elif kind == "seeded":
                assert seed_dir is not None
                n, got = _place(it, out, _file_chunks(it.seed(seed_dir)), published)
                source, retrieved = "seed", ""
            else:
                n, got = _place(it, out, http.stream(it.url), published)
                source, retrieved = "download", _today()
            t.with_name(t.name + ".CHECKSUM").write_text(text, encoding="utf-8")
            man[(it.symbol, it.month)] = {
                "symbol": it.symbol, "month": it.month, "file": f"{it.symbol}/{it.name}", "bytes": str(n),
                "sha256": got, "published_sha256": published, "source": source, "retrieved_on": retrieved,
                "verified_on": _today()}
            write_manifest(out, man)  # after every file, so an interruption loses at most one
            res[kind].append(it.name)
            log(f"[{i}/{len(work)}] {kind:10s} {it.symbol}/{it.name} {n / 1e6:8.1f} MB")
        except FileNotFoundError:
            res["not_published"].append(it.name)
            log(f"[{i}/{len(work)}] not published {it.symbol}/{it.name} (404)")
        except (ChecksumMismatch, ValueError, ConnectionError) as e:
            res["failed"].append(it.name)
            log(f"[{i}/{len(work)}] FAILED     {it.symbol}/{it.name}: {e}")
    return res


def dry_run(todo: list[Item], out: Path, seed_dir: Path | None, http: Http | None,
            log: Callable[[str], None] = print) -> dict[str, int]:
    """Count files by action and the expected size; HEAD requests only (http=None: no network at all)."""
    p = plan(todo, out, seed_dir, rehash=False)
    sizes = {it.name: _safe_len(http, it.url) for it in p.download} if http is not None else {}
    seed_bytes = sum(it.seed(seed_dir).stat().st_size for it in p.seed) if seed_dir else 0
    have_bytes = sum(it.target(out).stat().st_size for it in p.reuse + p.verify)
    dl_bytes = sum(v for v in sizes.values() if v is not None)
    log(f"kline plan: {len(todo)} files, {len({it.symbol for it in todo})} symbols, "
        f"{min(it.month for it in todo)} .. {max(it.month for it in todo)}")
    log(f"  already in place and verified (reuse): {len(p.reuse):5d}")
    log(f"  in place, not yet verified:            {len(p.verify):5d}  {have_bytes / 1e9:6.2f} GB in place")
    log(f"  copy from seed folder, then verify:    {len(p.seed):5d}  {seed_bytes / 1e9:6.2f} GB")
    log(f"  download (or not published):           {len(p.download):5d}  {dl_bytes / 1e9:6.2f} GB known")
    log(f"  target: {out}")
    return {"files": len(todo), "reuse": len(p.reuse), "verify": len(p.verify), "seed": len(p.seed),
            "download": len(p.download), "seed_bytes": seed_bytes, "download_bytes": dl_bytes}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_klines", description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbols", nargs="+", default=None, help="default: data/reference/binance/binance_um_symbols.txt")
    ap.add_argument("--start", default=DEFAULT_START, help="YYYY-MM")
    ap.add_argument("--end", default=DEFAULT_END, help="YYYY-MM")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED, help="read-only folder of earlier zips")
    ap.add_argument("--no-seed", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    ap.add_argument("--offline", action="store_true", help="with --dry-run: no HEAD requests")
    a = ap.parse_args(argv)
    for m in (a.start, a.end):
        date.fromisoformat(m + "-01")  # validates YYYY-MM
    todo = items(a.symbols or read_symbols(DEFAULT_SYMBOLS_FILE), a.start, a.end)
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
