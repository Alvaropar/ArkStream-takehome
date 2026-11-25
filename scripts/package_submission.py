"""Build the submission zip from an explicit include list and write MANIFEST.sha256 for everything inside.

    uv run python scripts/package_submission.py                  # -> dist/arkstream_submission.zip (+ manifest)
    uv run python scripts/package_submission.py --list           # print what would be packed; write nothing
    uv run python scripts/package_submission.py --check FILE     # verify a list of `sha256  bytes  path` lines

What is shipped: the Word reports for reviewers, code, config, tests, scripts, decision/, provenance/, the small
verified inputs (data/raw, data/reference/prices, hyperliquid, binance without the aggTrades and kline zips, latency)
and the small
research summaries, including Phase 4 v2 and Phase 5 (the holdout report, the decision entry, the cutoff deliverables
and the 3 Dec shortlist the freeze hashes). What is not: the aggTrades and kline zips, the kline lake, data/processed
and the large replay, leader, selection and portfolio Parquet trees; VERIFY.md gives the commands that regenerate
them and the provenance/ lists to compare with.

The zip is deterministic: entries sorted by path, fixed timestamps and permissions, one compression level, so the
same tree always gives the same bytes. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "arkstream"
STAMP = (2026, 1, 1, 0, 0, 0)
INCLUDE = [
    "README.md", "VERIFY.md", "Makefile", "pyproject.toml", "uv.lock", ".python-version", ".gitignore",
    # the short reports for reviewers, English and Chinese (scripts/build_report.py)
    "ArkStream_Assignment_Report.docx", "ArkStream_Assignment_Report_zh-CN.docx",
    "src/**", "config/**", "tests/**", "scripts/**", "decision/**", "provenance/**",
    "data/raw/**", "data/reference/prices/**", "data/reference/hyperliquid/**", "data/reference/binance/**",
    "data/reference/latency/**",
    "research/DATA_DICTIONARY.md", "research/quality_report.parquet", "research/quality_evidence.parquet",
    "research/cards/**", "research/hyperliquid/**", "research/drift/**",
    "research/leader/gate_counts.csv", "research/leader/origin=*/gate_counts.csv",
    "research/leader/origin=*/summary.md",
    "research/replay/*.csv", "research/replay/summary.md", "research/replay/leader_size/*.csv",
    "research/replay_sizing/*.csv", "research/replay_sizing/summary.md", "research/replay_sizing/leader_size/*.csv",
    "research/replay_sizing/origin=*/summary.md",
    "research/replay_frozen/*.csv", "research/replay_frozen/leader_size/*.csv",
    "research/replay_frozen/capture_summary.parquet", "research/replay_frozen/capture_daily.parquet",
    "research/replay_frozen/market_relative.parquet",
    "research/copy_daily_twr_training.csv", "research/leader_book_daily_twr_training.csv",
    # The two shortlists, the only Parquet files git tracks under research/: the 3 Dec one is hashed by the freeze
    # (freeze.SHORTLIST), so the reviewer's freeze check needs it; the 4 Jan one is the cutoff hand-off.
    "research/selection_v2/origin=2025-12-03/eligible.parquet",
    "research/cutoff/selection_v2/origin=2026-01-04/eligible.parquet",
]
# Phase 4 v2 and Phase 5 (ADRs 0066-0102): the small text outputs, by folder and type. Together with the lines above
# this is the research/ set a git clone has. The large Parquet trees are rebuilt with the commands in VERIFY.md.
PHASE_4_5 = {
    "audit": ("csv", "log", "md", "txt"),
    "cost_runs": ("csv",),
    "cutoff": ("csv", "json", "md"),            # the deliverables, the hand-off, the 4 Jan selection summaries
    "cutoff_check": ("csv", "json", "md"),
    "holdout": ("csv", "json", "md"),           # decision_A.json, the window report, runs B and C
    "holdout_check": ("csv", "json", "md"),
    "latency": ("csv", "md"),
    "phase5_population": ("csv", "json"),
    "portfolio_replay": ("csv", "json"),
    "replay": ("md",),
    "replay_allpriced": ("csv",),
    "replay_coinfilter": ("csv",),
    "replay_gray": ("csv",),
    "replay_tradable": ("csv",),
    "risk_model": ("json",),
    "selection": ("csv",),
    "selection_v2": ("csv",),
    "split_orders": ("csv", "md"),
    "window_report": ("csv", "json"),
}
INCLUDE += [f"research/{folder}/**/*.{ext}" for folder, exts in PHASE_4_5.items() for ext in exts]
EXCLUDE = [
    "data/reference/binance/aggtrades/*/*",  # the zips; aggtrades/MANIFEST.csv is kept
    "data/reference/binance/klines/*/*",     # the zips; klines/MANIFEST.csv is kept
    "*/__pycache__/*", "*.pyc", "*.part",
]
CHUNK = 1 << 20


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while b := fh.read(CHUNK):
            h.update(b)
    return h.hexdigest()


def finished_latency_run(rel: str, root: Path) -> bool:
    """A latency recording is shipped only once it is complete: its folder holds run.json and MANIFEST.csv (the
    rule `arkstream.latency` uses to find runs). A run still being recorded, or an aborted one, is left out."""
    parts = rel.split("/")
    if len(parts) < 6 or parts[:4] != ["data", "reference", "latency", "hyperliquid"]:
        return True
    run = root.joinpath(*parts[:5])
    return (run / "run.json").is_file() and (run / "MANIFEST.csv").is_file()


def selected(root: Path = ROOT) -> list[Path]:
    """Every file matched by INCLUDE and not by EXCLUDE, sorted by relative path. A missing include fails."""
    files: set[Path] = set()
    for pattern in INCLUDE:
        hits = [p for p in (root.glob(pattern[:-3] + "/**/*") if pattern.endswith("/**") else root.glob(pattern))
                if p.is_file()]
        if not hits:
            raise FileNotFoundError(f"include pattern matched nothing: {pattern}")
        files.update(hits)
    keep = [p for p in files if not any(fnmatch.fnmatch(p.relative_to(root).as_posix(), x) for x in EXCLUDE)
            and finished_latency_run(p.relative_to(root).as_posix(), root)]
    return sorted(keep, key=lambda p: p.relative_to(root).as_posix())


def manifest_lines(files: list[Path], root: Path = ROOT) -> list[str]:
    return [f"{sha256_file(p)}  {p.stat().st_size:>12d}  {p.relative_to(root).as_posix()}" for p in files]


def build(out: Path, root: Path = ROOT) -> tuple[Path, int]:
    files = selected(root)
    lines = manifest_lines(files, root)
    manifest = ("# sha256  bytes  path (relative to the unzipped arkstream/ folder)\n" + "\n".join(lines) + "\n")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            info = zipfile.ZipInfo(f"{PREFIX}/{p.relative_to(root).as_posix()}", date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(p, "rb") as src, z.open(info, "w") as dst:
                while b := src.read(CHUNK):
                    dst.write(b)
        info = zipfile.ZipInfo(f"{PREFIX}/MANIFEST.sha256", date_time=STAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        z.writestr(info, manifest)
    tmp.replace(out)
    # newline="\n": the copy beside the zip must be byte-identical to the one inside it (Windows would write CRLF).
    out.with_name("MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    return out, len(files)


def check(listing: Path, root: Path = ROOT) -> list[str]:
    """Problems found verifying `sha256  bytes  path` lines (comments skipped) against files under root."""
    problems = []
    for line in listing.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, size, rel = line.split(maxsplit=2)
        p = root / rel
        if not p.is_file():
            problems.append(f"missing  {rel}")
        elif p.stat().st_size != int(size) or sha256_file(p) != digest:
            problems.append(f"differs  {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="package_submission", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "arkstream_submission.zip")
    ap.add_argument("--list", action="store_true", help="print the files that would be packed")
    ap.add_argument("--check", type=Path, default=None, help="verify a checksum list against the working tree")
    ap.add_argument("--root", type=Path, default=ROOT, help="tree to check (default: this project)")
    a = ap.parse_args(argv)
    if a.check:
        problems = check(a.check, a.root)
        print("\n".join(problems) if problems else f"{a.check}: every listed file matches")
        return 1 if problems else 0
    if a.list:
        files = selected()
        print("\n".join(p.relative_to(ROOT).as_posix() for p in files))
        print(f"{len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB", file=sys.stderr)
        return 0
    out, n = build(a.out)
    print(f"wrote {out} ({n} files, {out.stat().st_size / 1e6:.1f} MB) and {out.with_name('MANIFEST.sha256')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
