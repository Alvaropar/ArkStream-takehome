"""Rerun the whole project in a few commands, from the unzipped package or a clone.

    uv run python scripts/rerun.py check               # ~1 min: checksums, freeze, decision entry, protocol
    uv run python scripts/rerun.py fetch               # the public Binance data the package does not ship (~11 GB)
    uv run python scripts/rerun.py rebuild             # every development output (~2-3 h), then the comparisons
    uv run python scripts/rerun.py holdout --confirm   # the holdout and the cutoff, compared with the shipped record
    uv run python scripts/rerun.py reports             # the English and Chinese Word reports and their figures
    uv run python scripts/rerun.py all --confirm       # rebuild, holdout and reports in one go

Options: --list prints a stage's steps, --dry-run prints its commands without running them, --from N resumes a stage
at step N. POLARS_MAX_THREADS is set to 8 (the published runs) unless it is already set.

`holdout` rewrites the published record in research/holdout/ and research/cutoff/, so it asks for --confirm: run it
in a copy. Before running it snapshots that record, and afterwards compares the new files with it (the "written"
timestamp inside the two JSON entries is ignored). The holdout commands also refuse to start unless the freeze holds,
which includes the environment recorded at the freeze: Python 3.12.15 (pinned in .python-version), the locked package
versions and POLARS_MAX_THREADS=8.

Standard library only; each step is one of the commands listed in VERIFY.md.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
FREEZE_HASH = "62eba6dab41bf74838957d355538796fd59f30876317691219600755687b6648"
DECISION_SHA = "cb3dd576b3880ddfdf7459fd8dc97297fb93bfe249082cb15c731448586e7c2f"
AGG_SYMBOLS = ["BTCUSDT", "ETHUSDT", "HYPEUSDT", "SOLUSDT", "BNBUSDT", "AAVEUSDT", "EIGENUSDT"]
RECORD = ("research/holdout", "research/cutoff")
RECORD_SUFFIXES = (".csv", ".json", ".md")
SNAPSHOT = ROOT / ".rerun" / "record_before.json"


@dataclass
class Step:
    label: str
    run: list[str] | Callable[[], bool]
    minutes: float = 1
    skip: Callable[[], str | None] = field(default=lambda: None)  # a reason to skip, or None


def ark(*args: str) -> list[str]:
    return [PY, "-m", "arkstream", *args]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _freeze():
    sys.path.insert(0, str(ROOT / "src"))
    from arkstream import freeze

    return freeze


# ------------------------------------------------------------------------------------------------------ checks
def check_package() -> bool:
    problems = _load("package_submission").check(ROOT / "MANIFEST.sha256", ROOT)
    print("\n".join(problems[:20]) if problems else "every file listed in MANIFEST.sha256 matches")
    return not problems


def check_freeze() -> bool:
    freeze = _freeze()
    _, env, h = freeze.read_freeze(ROOT)
    ok = freeze.combined(freeze.digest_lines(ROOT) + env) == h == FREEZE_HASH
    print(f"freeze holds: {ok}  {h}")
    return ok


def check_decision() -> bool:
    got = hashlib.sha256((ROOT / "research/holdout/decision_A.json").read_bytes()).hexdigest()
    print(f"decision_A.json sha256 {got} ({'matches' if got == DECISION_SHA else 'DIFFERS from ' + DECISION_SHA})")
    return got == DECISION_SHA


def compare_published() -> bool:
    """The rebuilt development outputs against the published lists; the freeze must still hold."""
    pkg = _load("package_submission")
    ok = True
    problems = pkg.check(ROOT / "provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt", ROOT)
    print(f"PRE_PHASE4_OUTPUT_CHECKSUMS.txt: {len(problems)} problem(s)")
    print("\n".join(f"  {p}" for p in problems[:20]))
    ok &= not problems
    # CHECKSUMS.txt also lists the two package originals, which are not shipped (data/raw holds byte copies).
    problems = [p for p in pkg.check(ROOT / "provenance/CHECKSUMS.txt", ROOT) if "笔试题" not in p]
    print(f"CHECKSUMS.txt (raw inputs, reference prices): {len(problems)} problem(s)")
    print("\n".join(f"  {p}" for p in problems[:20]))
    ok &= not problems
    problems = _freeze().check_output_manifest(ROOT)
    print(f"HOLDOUT_OUTPUT_MANIFEST.txt (the trees the holdout reads): {len(problems)} problem(s)")
    print("\n".join(f"  {p}" for p in problems[:20]))
    ok &= not problems
    return check_freeze() and ok


# ------------------------------------------------------------------------------------------------------ holdout
def _record_files() -> dict[str, str]:
    out = {}
    for top in RECORD:
        for p in sorted((ROOT / top).rglob("*")):
            if p.is_file() and (p.suffix in RECORD_SUFFIXES or p.name == "eligible.parquet"):
                data = p.read_bytes()
                if p.suffix == ".json":  # the run time stamp is the one field a rerun cannot reproduce
                    obj = json.loads(data)
                    if isinstance(obj, dict):
                        obj.pop("written", None)
                    data = json.dumps(obj, sort_keys=True).encode()
                out[p.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    return out


def snapshot_record() -> bool:
    if SNAPSHOT.is_file():
        print(f"keeping the earlier snapshot {SNAPSHOT.relative_to(ROOT)}")
        return True
    files = _record_files()
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(files, indent=1), encoding="utf-8")
    print(f"snapshot of the shipped record: {len(files)} files -> {SNAPSHOT.relative_to(ROOT)}")
    return True


def check_environment() -> bool:
    freeze = _freeze()
    frozen = freeze.parse_env(freeze.read_freeze(ROOT)[1])
    now = dict(freeze.environment(ROOT))
    diff = [f"{k}: frozen {frozen.get(k)}, now {now.get(k)}" for k in sorted(set(frozen) | set(now))
            if k not in freeze.ENV_NOT_COMPARED and frozen.get(k) != now.get(k)]
    if diff:
        print("the environment differs from the freeze, so the holdout commands will refuse:\n  " + "\n  ".join(diff))
        print("fix: uv python install 3.12.15, then uv sync (the lock pins the packages); POLARS_MAX_THREADS=8")
    else:
        print(f"environment matches the freeze (Python {platform.python_version()}, locked packages, 8 threads)")
    return not diff


def check_trees() -> bool:
    """The development trees the holdout reads must be the frozen ones (rebuild writes them)."""
    problems = _freeze().check_output_manifest(ROOT)
    if problems:
        print(f"{len(problems)} difference(s) from provenance/HOLDOUT_OUTPUT_MANIFEST.txt, e.g.:\n  "
              + "\n  ".join(problems[:10]))
        print("run `uv run python scripts/rerun.py rebuild` first")
    else:
        print("the development trees match provenance/HOLDOUT_OUTPUT_MANIFEST.txt")
    return not problems


def compare_record() -> bool:
    before = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    after = _record_files()
    same = [f for f in before if after.get(f) == before[f]]
    differ = [f for f in before if f in after and after[f] != before[f]]
    missing = [f for f in before if f not in after]
    new = [f for f in after if f not in before]
    print(f"record files: {len(same)} identical, {len(differ)} differ, {len(missing)} missing, {len(new)} new")
    for name, lst in (("differs", differ), ("missing", missing), ("new", new)):
        for f in lst[:30]:
            print(f"  {name}  {f}")
    return not (differ or missing)


# ------------------------------------------------------------------------------------------------------ inputs
KLINES = ROOT / "data/reference/binance/klines"
LAKE = ROOT / "data/lake"
LAKE_KLINES = LAKE / "venue=binance" / "dataset=binance.um.klines"
AGG = ROOT / "data/reference/binance/aggtrades"


def lake_built() -> bool:
    return LAKE_KLINES.is_dir() and any(LAKE_KLINES.rglob("*.parquet"))


def check_inputs() -> bool:
    """The rebuild needs the Binance data that the package does not ship (the fetch stage downloads it)."""
    ok = True
    zips = list(KLINES.rglob("*.zip")) if KLINES.is_dir() else []
    if lake_built():
        print("kline lake: built (data/lake)")
    elif zips:
        print(f"kline lake: not built yet; {len(zips)} kline zips found, step 2 builds it")
    else:
        print("kline lake: missing, and no kline zips in data/reference/binance/klines (Phase 2 reads the lake)")
        ok = False
    lines = (AGG / "MANIFEST.csv").read_text(encoding="utf-8").splitlines()
    col = lines[0].split(",").index("file")
    listed = [ln.split(",")[col] for ln in lines[1:] if ln]
    missing = [f for f in listed if not (AGG / f).is_file()]
    print(f"aggTrades: {len(listed) - len(missing)} of {len(listed)} files listed in MANIFEST.csv are present")
    ok &= not missing
    if not ok:
        print("run `uv run python scripts/rerun.py fetch` first")
    return ok


def lake_ready() -> str | None:
    return "the kline lake is already built" if lake_built() else None


# ------------------------------------------------------------------------------------------------------ frozen files
REGENERATED = "provenance/CHECKSUMS.txt"  # `ingest` rewrites it from the input files present


def frozen_bytes() -> dict[str, bytes]:
    freeze = _freeze()
    try:
        paths = freeze.frozen_paths(ROOT)
    except freeze.FreezeError:
        paths = [ln[66:] for ln in freeze.read_freeze(ROOT)[0]]
    return {p: (ROOT / p).read_bytes() for p in paths if (ROOT / p).is_file()}


def _entries(data: bytes | None) -> set[str]:
    lines = (data or b"").decode("utf-8").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def keep_frozen(before: dict[str, bytes]) -> bool:
    """No step may change a frozen file. The one known rewrite is checked and undone: `ingest` rewrites
    provenance/CHECKSUMS.txt without the two package originals, which the package does not ship (data/raw holds byte
    copies); every line it writes must be in the published file."""
    after = frozen_bytes()
    ok = True
    for p, old in before.items():
        new = after.get(p)
        if new == old:
            continue
        if p == REGENERATED and new is not None and _entries(new) <= _entries(old):
            (ROOT / p).write_bytes(old)
            print(f"  {p}: the input files present match the published checksums; the published file is kept")
        else:
            print(f"  a frozen file changed: {p} (the freeze would no longer hold)")
            ok = False
    return ok


# ------------------------------------------------------------------------------------------------------ stages


def no_manifest() -> str | None:
    return None if (ROOT / "MANIFEST.sha256").is_file() else "no MANIFEST.sha256 here (a clone, not the package)"


def report_cmd() -> list[str]:
    py = os.environ.get("ARKSTREAM_REPORT_PYTHON")  # any Python with python-docx, matplotlib, pandas and pyarrow
    if py:
        return [py, "scripts/build_report.py"]
    # python-docx stays out of uv.lock: the lock's hash is part of the frozen environment.
    return ["uv", "run", "--group", "figures", "--with", "python-docx==1.2.0", "python", "scripts/build_report.py"]


STAGES: dict[str, list[Step]] = {
    "check": [
        Step("Package checksums (MANIFEST.sha256)", check_package, 1, no_manifest),
        Step("Freeze hash", check_freeze, 0.2),
        Step("Decision entry checksum", check_decision, 0.1),
        Step("Protocol parameters against config/risk.yaml", [PY, "scripts/check_protocol_parameters.py"], 0.2),
    ],
    "fetch": [
        Step("Binance 1-minute klines (1.9 GB, 1,270 files)", [PY, "-m", "arkstream_fetch.fetch_klines"], 20),
        Step("Binance aggTrades, 7 coins (9.3 GB, 833 files)",
             [PY, "-m", "arkstream_fetch.fetch_aggtrades", "--symbols", *AGG_SYMBOLS], 60),
    ],
    "rebuild": [
        Step("Inputs present (kline lake or zips, aggTrades)", check_inputs, 0.2),
        Step("Ingest the raw files", ark("ingest"), 1),
        Step("Kline lake and reference prices from the kline zips",
             ark("refprices", "--from-zips", "data/reference/binance/klines"), 3, lake_ready),
        Step("Milestone 1 at the cutoff", ark("build"), 0.5),
        Step("Audit: headline counts", ark("audit"), 0.5),
        Step("Funding and price check", ark("funding"), 1),
        Step("Drift cells per origin", ark("drift"), 2),
        Step("Leader evidence per origin", ark("leader"), 4),
        Step("Copy replay, frozen sizing", ark("replay", "--frozen"), 17),
        Step("Copy replay with the v1 coin filter (record)", ark("replay", "--coin-filter"), 9),
        Step("v1 selection walk-forward (record)", ark("select", "--evaluate"), 1),
        Step("Copy replay on every priced coin", ark("replay", "--allpriced"), 15),
        Step("Copy replay on each trader's tradable coins", ark("replay", "--tradable"), 13),
        Step("Selection v2 at every origin", ark("select-v2"), 3),
        Step("Gray sleeves at 2,500 and 5,000", ark("replay", "--gray"), 3),
        Step("Risk model per origin", ark("phase5", "risk-model"), 2),
        Step("Trigger calibration on all A/B copies", ark("phase5", "population"), 10),
        Step("Two-sleeve books on the test windows", ark("phase5", "pair"), 10),
        Step("Window report on the development windows", ark("phase5", "report"), 2),
        Step("Rebuilt-cost runs B and C (development)", ark("phase5", "cost-runs"), 10),
        Step("Holdout entry point on 19 Nov - 3 Dec", ark("phase5", "holdout", "--check"), 10),
        Step("Cutoff selection code at 3 Dec", ark("phase5", "cutoff", "--check"), 20),
        Step("Unit and data tests", [PY, "-m", "pytest", "-q"], 10),
        Step("Compare with the published checksums", compare_published, 2),
    ],
    "holdout": [
        Step("Environment against the freeze", check_environment, 0.1),
        Step("Development trees against the frozen output manifest", check_trees, 1),
        Step("Snapshot the shipped record", snapshot_record, 0.5),
        Step("Run A on the holdout (3 Dec - 4 Jan)", ark("phase5", "holdout", "--stage", "a"), 15),
        Step("Cutoff selection at 4 Jan", ark("phase5", "cutoff"), 25),
        Step("Decision entry D1-D5", ark("phase5", "holdout", "--stage", "decision"), 10),
        Step("Runs B and C on the holdout", ark("phase5", "holdout", "--stage", "bc"), 10),
        Step("Cutoff deliverables", ark("phase5", "cutoff", "--deliverables"), 1),
        Step("Compare with the shipped record", compare_record, 0.5),
    ],
    "reports": [
        Step("Word reports (English and Chinese) and figures", report_cmd(), 1),
    ],
}
STAGES["all"] = STAGES["rebuild"] + STAGES["holdout"] + STAGES["reports"]


def describe(step: Step) -> str:
    if callable(step.run):
        return f"(in-process: {step.run.__name__})"
    return " ".join(("python" if a == PY else a) for a in step.run)


def run_stage(name: str, start: int, dry: bool) -> int:
    steps = STAGES[name]
    total = sum(s.minutes for s in steps[start - 1:])
    print(f"== {name}: steps {start}-{len(steps)} of {len(steps)}, about {total:.0f} min "
          f"(POLARS_MAX_THREADS={os.environ['POLARS_MAX_THREADS']})")
    results = []
    for i, step in enumerate(steps, start=1):
        if i < start:
            continue
        print(f"\n[{name} {i}/{len(steps)}] {step.label}  (~{step.minutes:g} min)\n  {describe(step)}", flush=True)
        reason = step.skip()
        if reason:
            print(f"  skipped: {reason}")
            results.append((i, step.label, "skipped", 0.0))
            continue
        if dry:
            continue
        t0 = time.time()
        if callable(step.run):
            ok = bool(step.run())
        else:
            before = frozen_bytes()
            ok = subprocess.run(step.run, cwd=ROOT).returncode == 0
            ok = keep_frozen(before) and ok
        dt = (time.time() - t0) / 60
        results.append((i, step.label, "ok" if ok else "FAILED", dt))
        if not ok:
            confirm = " --confirm" if name in ("holdout", "all") else ""
            print(f"\n{name} stopped at step {i}. Fix the cause, then resume with: "
                  f"uv run python scripts/rerun.py {name} --from {i}{confirm}")
            break
    if not dry:
        print(f"\n== {name} summary")
        for i, label, status, dt in results:
            print(f"  {i:>2}. {status:<8} {dt:6.1f} min  {label}")
    return 0 if all(r[2] != "FAILED" for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rerun", description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", choices=list(STAGES))
    ap.add_argument("--from", dest="start", type=int, default=1, help="resume the stage at this step")
    ap.add_argument("--dry-run", action="store_true", help="print the commands without running them")
    ap.add_argument("--list", action="store_true", help="list the stage's steps")
    ap.add_argument("--confirm", action="store_true", help="allow holdout/all to rewrite the published record")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("POLARS_MAX_THREADS", "8")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if a.list:
        for i, s in enumerate(STAGES[a.stage], start=1):
            print(f"{i:>2}. {s.label}  (~{s.minutes:g} min)\n    {describe(s)}")
        return 0
    if a.stage in ("holdout", "all") and not (a.confirm or a.dry_run):
        print("holdout rewrites research/holdout/ and research/cutoff/ (the published record). Run it in a copy and "
              "add --confirm.")
        return 2
    if a.stage == "reports" and not os.environ.get("ARKSTREAM_REPORT_PYTHON") and not shutil.which("uv"):
        print("the reports stage needs uv on PATH, or ARKSTREAM_REPORT_PYTHON set to a Python with python-docx")
        return 2
    return run_stage(a.stage, a.start, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
