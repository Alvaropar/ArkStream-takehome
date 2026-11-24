"""Check 3: verify the data the holdout run depends on, not only the hashed code (read-only; no holdout data computed).

1. The current freeze (`provenance/HOLDOUT_FREEZE.txt`): every listed file's SHA-256 and the combined hash.
2. Raw inputs and reference prices: `provenance/CHECKSUMS.txt`, `data/reference/prices/MANIFEST.yaml`.
3. Downloaded references: Binance kline zips (`data/reference/binance/CHECKSUMS.txt`, under data/lake/_raw), aggTrades
   and the Hyperliquid funding / candles / user-funding MANIFEST.csv files.
4. Pre-Phase 4 outputs: `provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt` (the unfiltered frozen replay and its inputs).
5. Coverage gap: every file under the trees the holdout path reads (`research/replay_coinfilter`, `research/selection`,
   `research/leader/origin=2025-12-03`) that no manifest above lists, hashed now into
   `research/audit/unmanifested_inputs.txt`, and the shared inputs the coin-filter tree copied from the frozen tree
   compared byte for byte.
6. The software environment (Python, package versions, uv.lock hash, POLARS_MAX_THREADS).

Writes `research/audit/holdout_inputs_verification.md`. Usage: uv run python scripts/verify_holdout_inputs.py
"""

import sys

sys.path.insert(0, "src")
import csv
import hashlib
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from pathlib import Path

import yaml

from arkstream import freeze
from arkstream.config import load_context

ROOT = Path(".").resolve()
OUT = ROOT / "research/audit"
HOLDOUT_TREES = ["research/replay_coinfilter", "research/selection", "research/leader/origin=2025-12-03"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def check(entries: list[tuple[Path, str, int | None]]) -> tuple[int, list[str]]:
    """(path, expected sha256, expected bytes or None) -> (n ok, problems)."""
    def one(e):
        p, want, size = e
        if not p.exists():
            return f"missing: {p.relative_to(ROOT).as_posix()}"
        if size is not None and p.stat().st_size != size:
            return f"size differs: {p.relative_to(ROOT).as_posix()}"
        return None if sha(p) == want else f"sha256 differs: {p.relative_to(ROOT).as_posix()}"
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, entries))
    bad = [r for r in res if r]
    return len(res) - len(bad), bad


def sums_file(path: str, base: Path = ROOT) -> list[tuple[Path, str, int | None]]:
    out = []
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        out.append((base / parts[2], parts[0], int(parts[1])))
    return out


def manifest_csv(path: str, base: str) -> list[tuple[Path, str, int | None]]:
    with open(ROOT / path, encoding="utf-8", newline="") as fh:
        return [(ROOT / base / r["file"], r["sha256"], int(r["bytes"])) for r in csv.DictReader(fh)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = ["# Holdout input verification (Check 3)", ""]
    listed: set[str] = set()

    # 1. freeze
    ff = (ROOT / freeze.FREEZE_FILE).read_text(encoding="utf-8").splitlines()
    rec = [ln for ln in ff if len(ln) > 66 and ln[64:66] == "  "]
    recorded_hash = next(ln.split(": ")[1] for ln in ff if ln.startswith("freeze_hash:"))
    cur = freeze.digest_lines(ROOT)
    changed = sorted(set(rec) ^ set(cur))
    report += ["## 1. Current freeze", f"- recorded freeze_hash `{recorded_hash}`, files {len(rec)}",
               f"- recomputed combined hash `{freeze.combined(cur)}` over {len(cur)} files",
               f"- matches: **{freeze.combined(cur) == recorded_hash and not changed}**"]
    report += [f"  - differs: `{c[66:]}`" for c in changed[:20]]
    listed |= {ln[66:] for ln in rec}

    # 2-4. manifests
    groups = {
        "raw inputs and reference prices (provenance/CHECKSUMS.txt)": sums_file("provenance/CHECKSUMS.txt"),
        "reference prices (data/reference/prices/MANIFEST.yaml)": [
            (ROOT / "data/reference/prices" / f["path"], f["sha256"], int(f["bytes"]))
            for f in yaml.safe_load(
                (ROOT / "data/reference/prices/MANIFEST.yaml").read_text(encoding="utf-8"))["files"]],
        "Binance kline zips (data/reference/binance/CHECKSUMS.txt)": sums_file(
            "data/reference/binance/CHECKSUMS.txt", ROOT / "data/lake/_raw"),
        "Binance aggTrades (MANIFEST.csv)": manifest_csv("data/reference/binance/aggtrades/MANIFEST.csv",
                                                         "data/reference/binance/aggtrades"),
        "Hyperliquid funding (MANIFEST.csv)": manifest_csv("data/reference/hyperliquid/funding/MANIFEST.csv",
                                                           "data/reference/hyperliquid"),
        "Hyperliquid 4h candles (MANIFEST.csv)": manifest_csv("data/reference/hyperliquid/candles_4h/MANIFEST.csv",
                                                              "data/reference/hyperliquid"),
        "Hyperliquid user funding (MANIFEST.csv)": manifest_csv(
            "data/reference/hyperliquid/user_funding/MANIFEST.csv", "data/reference/hyperliquid"),
        "pre-Phase 4 outputs (provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt)": sums_file(
            "provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt"),
    }
    report += ["", "## 2-4. Manifests", "| Manifest | Files | OK | Problems |", "| --- | ---: | ---: | --- |"]
    manifest_hashes = []
    for name, entries in groups.items():
        ok, bad = check(entries)
        problems = "; ".join(bad[:5]) + (" ..." if len(bad) > 5 else "") or "none"
        report.append(f"| {name} | {len(entries)} | {ok} | {problems} |")
        for p, _, _ in entries:
            try:
                listed.add(p.relative_to(ROOT).as_posix())
            except ValueError:
                pass
        print(name, len(entries), ok, len(bad), flush=True)
    for m in ["provenance/CHECKSUMS.txt", "data/reference/prices/MANIFEST.yaml", "data/reference/binance/CHECKSUMS.txt",
              "data/reference/binance/aggtrades/MANIFEST.csv", "data/reference/hyperliquid/funding/MANIFEST.csv",
              "data/reference/hyperliquid/candles_4h/MANIFEST.csv",
              "data/reference/hyperliquid/user_funding/MANIFEST.csv", "provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt"]:
        manifest_hashes.append(f"{sha(ROOT / m)}  {m}")
    report += ["", "Manifest file hashes (to record beside the freeze hash):", "```", *manifest_hashes, "```"]

    # 5. coverage gap
    tree_files = sorted(p.relative_to(ROOT).as_posix() for t in HOLDOUT_TREES for p in (ROOT / t).rglob("*")
                        if p.is_file())
    gap = [f for f in tree_files if f not in listed]
    with ThreadPoolExecutor(8) as ex:
        gap_lines = list(ex.map(lambda f: f"{sha(ROOT / f)}  {(ROOT / f).stat().st_size:>12}  {f}", gap))
    (OUT / "unmanifested_inputs.txt").write_text(
        "# files under the holdout path's input trees listed in no manifest; hashed by verify_holdout_inputs.py\n"
        "# sha256  bytes  path\n" + "\n".join(gap_lines) + "\n", encoding="utf-8")
    from arkstream.replay_coinfilter import SHARED
    same = {n: sha(ROOT / "research/replay_coinfilter" / n) == sha(ROOT / "research/replay_frozen" / n)
            for n in SHARED}
    by_tree = {t: sum(f.startswith(t + "/") for f in gap) for t in HOLDOUT_TREES}
    report += ["", "## 5. Coverage gap", f"- files under {', '.join(f'`{t}`' for t in HOLDOUT_TREES)}: "
               f"{len(tree_files)}; in no manifest: **{len(gap)}** ({by_tree})",
               f"- hashed now into `research/audit/unmanifested_inputs.txt` "
               f"(sha256 `{sha(OUT / 'unmanifested_inputs.txt')}`)",
               "- shared inputs copied from the frozen tree, identical byte for byte: "
               + ", ".join(f"`{n}` {'yes' if v else '**NO**'}" for n, v in same.items())]

    # 6. environment
    pk = ["polars", "numpy", "pyarrow", "pyyaml", "scipy"]
    vers = []
    for p in pk:
        try:
            vers.append(f"{p} {metadata.version(p)}")
        except metadata.PackageNotFoundError:
            pass
    report += ["", "## 6. Environment", f"- Python {platform.python_version()} ({platform.platform()})",
               f"- {', '.join(vers)}", f"- uv.lock sha256 `{sha(ROOT / 'uv.lock')}`",
               f"- POLARS_MAX_THREADS={os.environ.get('POLARS_MAX_THREADS', '(unset)')} "
               "(the replay reruns were byte-identical at 8)",
               f"- config cutoff `{load_context().raw['cutoff']}`"]
    (OUT / "holdout_inputs_verification.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
