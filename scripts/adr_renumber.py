"""One-time ADR renumbering (2026-11-23, ADR-0085 after it): chronological numbers, superseded ADRs archived.

It ran once and is kept as the record of the rewrite rules. The archive it created was deleted the same day, so it
refuses to run again.

The 84 ADRs in force get the numbers 0001-0084 in the order they were decided (by date, then by the order of work on
that date). The 18 that no longer carry a decision used by the current study move to `decision/adr/archive/` as
`A<old number>-<slug>.md` (ID `ADR-A<old number>`); the parts of them still in force were first copied into the ADRs
that replace them.

Every reference in the current materials is rewritten: `ADR-0110`, `ADRs 0110-0122, 0150-0152`, `ADR-0116/0119`,
`ADRs 0139 and 0141`, `ADR-0020..0027`, and markdown links to ADR files (relative paths recomputed). In a range,
archived members are dropped when the range still has members in force. Not rewritten (they keep the old numbers;
see `decision/adr/RENUMBERING.md`): generated outputs under `research/`, the checksum and before/after records and the
void freeze under `provenance/`, `data/`, and the latency session's files.

Usage:
  uv run python scripts/adr_renumber.py            # dry run: counts, unknown IDs, archived references, bare numbers
  uv run python scripts/adr_renumber.py --apply    # rewrite, then move the files (refuses if already done)
  uv run python scripts/adr_renumber.py --files PATH...   # later: rewrite old numbers in the named files only
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = "decision/adr"

# The order of the ADRs in force, old numbers; the position gives the new number (1-based).
ORDER: dict[str, list[str]] = {
    "2026-11-19": ["0001", "0002", "0003", "0004", "0005", "0008", "0009", "0010", "0011", "0012", "0013", "0014",
                   "0020", "0021", "0022", "0023", "0024", "0025", "0026", "0040", "0041", "0042", "0060", "0061",
                   "0062", "0063", "0064", "0065"],
    "2026-11-20": ["0080", "0081", "0082", "0083", "0084", "0085", "0086", "0088", "0043", "0044", "0045", "0100",
                   "0101", "0102", "0103", "0110", "0111", "0112", "0113", "0114", "0115"],
    "2026-11-21": ["0117", "0118", "0119", "0120", "0121", "0122", "0104", "0105", "0150", "0151", "0152", "0160",
                   "0161", "0162"],
    "2026-11-22": ["0046", "0047", "0048"],
    "2026-11-23": ["0049", "0050", "0052", "0142", "0143", "0144", "0145", "0146", "0147", "0170", "0171", "0172",
                   "0173", "0174", "0175", "0176", "0177", "0053"],
}
# Archived: superseded or promoted, with the parts still in force copied into the ADR named here (old numbers).
ARCHIVED: dict[str, str] = {
    "0006": "an action (redundant aggTrades copies deleted), no rule in force",
    "0007": "superseded by ADR-0041",
    "0027": "replaced by ADR-0049 (gate 1 keeps the 20-trip minimum)",
    "0051": "superseded by ADRs 0143-0144; the NAV-key definition kept in ADR-0172 for the reported IC",
    "0087": "promoted to the sizing rule by ADR-0043, which now carries its mechanics",
    "0116": "promoted to the sizing rule by ADR-0119, which now carries its mechanics",
    "0130": "Phase 4 v1 gates; superseded by ADR-0145 (the unchanged gates copied there) and ADR-0049",
    "0131": "Phase 4 v1 trip key; superseded by ADRs 0143-0144; definition kept in ADR-0172",
    "0132": "Phase 4 v1 walk and basket; superseded by ADR-0146; the clusters copied into ADR-0144",
    "0133": "Phase 4 v1 baselines; superseded by ADR-0147 (seed and draws copied there)",
    "0134": "Phase 4 v1 market-relative basket report; superseded by ADR-0143",
    "0135": "Phase 4 v1 diagnostics; the gate audit is restated in ADRs 0147 and 0173",
    "0136": "Phase 4 v1 coin filter; superseded by ADR-0145",
    "0137": "Phase 4 v1 variant choice; superseded by ADR-0147",
    "0138": "Phase 4 v1 rule and shortlist; superseded by ADR-0142",
    "0139": "void freeze; the mechanism is restated in ADR-0047",
    "0140": "Phase 4 v1 executable coin filter; superseded by ADR-0145",
    "0141": "void freeze; the mechanism is restated in ADR-0047",
}
OLD_IN_FORCE = [o for day in ORDER.values() for o in day]
NEW = {old: f"{i + 1:04d}" for i, old in enumerate(OLD_IN_FORCE)}
ARCH = {old: f"A{old}" for old in ARCHIVED}
DATE_OF = {old: day for day, olds in ORDER.items() for old in olds}

# Rewritten: current materials. Excluded: generated outputs, hash records, the void freeze, the latency session.
INCLUDE = ("decision/", "src/", "tests/", "scripts/", "config/", "Makefile", "README.md", "VERIFY.md",
           "ArkStream Hyperliquid Pilot", "provenance/expected_counts.yaml", "provenance/trial_log.md")
EXCLUDE = ("src/arkstream/latency.py", "src/arkstream_fetch/hl_ws_latency.py", "tests/test_hl_ws_latency.py",
           "scripts/adr_renumber.py",
           "decision/phase-5-methodology-1.md")  # being written while the renumbering ran; rewrite with --files

RSEP = r"(?:\s*(?:\.\.|–|—|-)\s*|\s+to\s+)"
ITEM = re.compile(rf"(\d{{4}})(?:({RSEP})(\d{{4}}))?\b")
SINGLE = re.compile(r"(\d{4})()()\b")
# Separators may wrap onto the next line of a blockquote (`> `) or a comment (`# `).
_NL = r"\n[ \t]*(?:(?:>|#)[ \t]*)*"
_W0 = rf"(?:[ \t]*(?:{_NL})?)"
_W1 = rf"(?:[ \t]+(?:{_NL})?|[ \t]*{_NL})"
LSEP = re.compile(rf"{_W0},{_W1}and{_W1}|{_W0},{_W0}|{_W0}/{_W0}|{_W0}\+{_W0}|{_W1}and{_W1}|{_W1}or{_W1}")
PREFIX = re.compile(rf"\bADR(s?)(-|[ \t]+|[ \t]*{_NL})(?=\d{{4}}\b)")
LINKTEXT = re.compile(r"\[(\d{4})\](?=\((?:[^)\s]*/)?(\d{4})-[a-z0-9][a-z0-9\-]*\.md\))")
STRAY = re.compile(r"(?<![\w./:#-])(\d{4})(?![\w.:/])")
LINK = re.compile(r"(?P<pre>(?:[A-Za-z0-9_.\-]+/)*)(?P<num>\d{4})-(?P<slug>[a-z0-9][a-z0-9\-]*)\.md")


MOVED = not (ROOT / ADR_DIR / "0130-selection-gates.md").exists()


def adr_files() -> dict[str, str]:
    """Old number -> old file name: read from the folder before the move, derived from the new names after it."""
    out = {}
    if not MOVED:
        for p in sorted((ROOT / ADR_DIR).glob("[0-9][0-9][0-9][0-9]-*.md")):
            out[p.name[:4]] = p.name
        return out
    old_of = {new: old for old, new in NEW.items()}
    for p in sorted((ROOT / ADR_DIR).glob("[0-9][0-9][0-9][0-9]-*.md")):
        if p.name[:4] in old_of:
            out[old_of[p.name[:4]]] = f"{old_of[p.name[:4]]}{p.name[4:]}"
    for p in sorted((ROOT / ADR_DIR / "archive").glob("A[0-9][0-9][0-9][0-9]-*.md")):
        out[p.name[1:5]] = p.name[1:]
    for old in ARCHIVED:  # deleted with the archive: no file is left to link to
        out.setdefault(old, f"{old}-deleted.md")
    return out


FILES = adr_files()
KNOWN = set(NEW) | set(ARCH)


def new_name(old: str) -> str:
    """The file's path relative to decision/adr after the move."""
    slug = FILES[old][5:]
    return f"{NEW[old]}-{slug}" if old in NEW else f"archive/{ARCH[old]}-{slug}"


def compress(ids: list[str], rsep: str) -> list[str]:
    ids = sorted(set(ids))
    runs: list[list[str]] = []
    for x in ids:
        if runs and int(x) == int(runs[-1][-1]) + 1:
            runs[-1].append(x)
        else:
            runs.append([x])
    out = []
    for r in runs:
        if len(r) >= 3:
            out.append(f"{r[0]}{rsep}{r[-1]}")
        else:
            out.extend(r)
    return out


class Log:
    def __init__(self) -> None:
        self.unknown: list[str] = []
        self.archived_refs: list[str] = []
        self.links: list[str] = []
        self.count = 0
        self.spans: list[tuple[int, int]] = []


def render_item(a: str, rsep: str | None, b: str | None) -> list[str] | None:
    """New ID pieces for one item; None if unknown."""
    if not b:
        if a in NEW:
            return [NEW[a]]
        if a in ARCH:
            return [ARCH[a]]
        return None
    members = [o for o in sorted(KNOWN) if a <= o <= b]
    if not members:
        return None
    act = [NEW[o] for o in members if o in NEW]
    rs = rsep.strip() if rsep and rsep.strip() in ("..", "–", "—", "-") else "-"
    if act:
        return compress(act, rs)
    arch = [ARCH[o] for o in members]
    return [f"{arch[0]}{rs}{arch[-1]}"] if len(arch) > 1 else arch


def valid_cont(m: re.Match[str]) -> bool:
    a, b = m.group(1), m.group(3)
    if not b:
        return a in KNOWN
    return "0001" <= a <= "0199" and "0001" <= b <= "0199" and a <= b


def rewrite_ids(text: str, where: str, log: Log) -> str:
    out, pos = [], 0
    for pm in PREFIX.finditer(text):
        if pm.start() < pos:
            continue
        first = ITEM.match(text, pm.end())
        if not first:
            continue
        if first.group(3) is not None and not valid_cont(first):
            first = SINGLE.match(text, pm.end())
            assert first is not None
        items = [("", first)]
        end = first.end()
        while True:
            sm = LSEP.match(text, end)
            if not sm:
                break
            im = ITEM.match(text, sm.end())
            if not im or not valid_cont(im):
                break
            items.append((sm.group(0), im))
            end = im.end()
        pieces_per = [render_item(m.group(1), m.group(2), m.group(3)) for _, m in items]
        line = text[max(0, text.rfind("\n", 0, pm.start()) + 1): text.find("\n", end) if "\n" in text[end:] else None]
        if any(p is None for p in pieces_per):
            log.unknown.append(f"{where}: {text[pm.start():end]}  | {line.strip()[:160]}")
            continue
        n_ids = sum(len(p) for p in pieces_per)
        has_range = any(any(not x.lstrip("A").isdigit() for x in p) for p in pieces_per)
        seps = [s for s, _ in items[1:]]
        orig = pm.group(0)
        if n_ids == 1 and not has_range:
            prefix = "ADR-" if pm.group(1) or pm.group(2) == "-" else orig
        elif pm.group(1) == "" and pm.group(2) == "-" and not has_range and all(s.strip() == "/" for s in seps) \
                and len(seps) == n_ids - 1:
            prefix = "ADR-"
        else:
            prefix = orig if pm.group(1) else "ADRs "
        body = ", ".join(pieces_per[0])
        for (sep, _), pieces in zip(items[1:], pieces_per[1:], strict=True):
            body += sep + ", ".join(pieces)
        new = prefix + body
        if any(x.startswith("A") for p in pieces_per for x in p):
            log.archived_refs.append(f"{where}: {text[pm.start():end]} -> {new}")
        out.append(text[pos:pm.start()])
        out.append(new)
        log.spans.append((pm.start(), end))
        pos = end
        log.count += 1
    out.append(text[pos:])
    return "".join(out)


def new_location(rel: str) -> str:
    """Where a file will live after the move (only ADR files move)."""
    d, name = posixpath.split(rel)
    if d == ADR_DIR and name[:4] in FILES and FILES[name[:4]] == name:
        return posixpath.join(ADR_DIR, new_name(name[:4]))
    return rel


def rewrite_links(text: str, rel: str, log: Log) -> str:
    ref_old_dir = posixpath.dirname(rel)
    ref_new_dir = posixpath.dirname(new_location(rel))

    def sub(m: re.Match[str]) -> str:
        num, slug, pre = m.group("num"), m.group("slug"), m.group("pre")
        if FILES.get(num) != f"{num}-{slug}.md":
            return m.group(0)
        target_new = posixpath.join(ADR_DIR, new_name(num))
        from_file = posixpath.normpath(posixpath.join(ref_old_dir, pre)) if pre else ref_old_dir
        from_root = posixpath.normpath(pre) if pre else ""
        if from_file == ADR_DIR and (rel.endswith(".md") or not pre):
            out = posixpath.relpath(target_new, ref_new_dir)
        elif from_root == ADR_DIR:
            out = target_new
        elif not pre:
            out = posixpath.basename(target_new)
        else:
            out = pre + new_name(num)
            log.links.append(f"{rel}: unresolved prefix {m.group(0)} -> {out}")
        log.links.append(f"{rel}: {m.group(0)} -> {out}") if pre and from_root == ADR_DIR else None
        return out

    def sub_text(m: re.Match[str]) -> str:
        num = m.group(1)
        if num != m.group(2) or num not in FILES:
            return m.group(0)
        return f"[{NEW.get(num) or ARCH[num]}]"

    return LINK.sub(sub, LINKTEXT.sub(sub_text, text))


# After the rewrite no number in force exceeds 0084: a leftover 0085-0199 token is an old number missed.
BARE = re.compile(r"(?<![\w./-])0(?:08[5-9]|09\d|1\d\d)(?![\w])")


def keep_endings(original: str, new: str) -> str:
    """Give the rewritten text the original's line endings, line by line when the line count is unchanged."""
    old_lines, new_lines = original.split("\n"), new.split("\n")
    if len(old_lines) == len(new_lines):
        return "\n".join(n + ("\r" if o.endswith("\r") else "") for o, n in zip(old_lines, new_lines, strict=True))
    return new.replace("\n", "\r\n") if "\r\n" in original else new


def targets(only: list[str] | None) -> list[str]:
    if only:
        return [Path(p).resolve().relative_to(ROOT).as_posix() for p in only]
    ls = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                        capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    out = []
    for rel in sorted(set(ls)):
        if not rel or rel in EXCLUDE or not rel.startswith(INCLUDE) or rel == f"{ADR_DIR}/README.md":
            continue
        if not (ROOT / rel).is_file():
            continue
        out.append(rel)
    return out


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    only = args[args.index("--files") + 1:] if "--files" in args else None
    if MOVED and not only:
        sys.exit("the renumbering is done and the archive was deleted; only --files <path> still runs")
    if not only and MOVED:
        sys.exit("already renumbered (decision/adr/0130-selection-gates.md is gone); use --files for stragglers")
    assert len(NEW) == 84 and len(ARCH) == 18 and not set(NEW) & set(ARCH)
    assert set(NEW) | set(ARCH) == set(FILES), sorted(set(FILES) ^ (set(NEW) | set(ARCH)))
    for old, day in DATE_OF.items():
        if MOVED:
            break
        txt = (ROOT / ADR_DIR / FILES[old]).read_text(encoding="utf-8")
        m = re.search(r"^- Date: (\d{4}-\d{2}-\d{2})", txt, re.M)
        if not m or m.group(1) != day:
            print(f"date check: {old} is dated {m.group(1) if m else None}, grouped under {day}")
    log = Log()
    changed: dict[str, str] = {}
    per_file: dict[str, int] = {}
    bare: list[str] = []
    stray: list[str] = []
    originals: dict[str, str] = {}
    for rel in targets(only):
        p = ROOT / rel
        try:
            raw_text = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        originals[rel] = raw_text
        text = raw_text.replace("\r\n", "\n")
        if "ADR" not in text and not LINK.search(text):
            continue
        before = log.count
        new = rewrite_links(text, rel, log)
        linked = new
        log.spans = []
        new = rewrite_ids(linked, rel, log)
        start = 0
        for ln in linked.splitlines(keepends=True):
            if "ADR" in ln:
                for m in STRAY.finditer(ln):
                    a = start + m.start()
                    if m.group(1) in KNOWN and not any(x <= a < y for x, y in log.spans):
                        stray.append(f"{rel}: {m.group(1)} | {ln.strip()[:170]}")
            start += len(ln)
        per_file[rel] = log.count - before
        if new != text:
            changed[rel] = new
        for ln in new.splitlines():
            if BARE.search(ln):
                bare.append(f"{rel}: {ln.strip()[:170]}")
    print(f"files with changes: {len(changed)}; ID groups rewritten: {log.count}")
    for rel, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:25]:
        print(f"  {n:4d}  {rel}")
    print(f"\nunknown IDs ({len(log.unknown)}):")
    for u in log.unknown:
        print("  " + u)
    print(f"\nreferences to archived ADRs ({len(log.archived_refs)}):")
    for u in log.archived_refs:
        print("  " + u)
    print(f"\nlinks with a path prefix ({len(log.links)}):")
    for u in log.links:
        print("  " + u)
    print(f"\npossible bare numbers to check by hand ({len(bare)}):")
    for u in bare[:80]:
        print("  " + u)
    print(f"\nold numbers on ADR lines not rewritten ({len(stray)}):")
    for u in stray:
        print("  " + u)
    if not apply:
        print("\ndry run: nothing written")
        return
    for rel, text in changed.items():
        (ROOT / rel).write_bytes(keep_endings(originals[rel], text).encode("utf-8"))
    if only:
        return
    write_index()
    adr = ROOT / ADR_DIR
    (adr / "archive").mkdir(exist_ok=True)
    tmp = {}
    for old, name in FILES.items():
        t = adr / f"__renum_{name}"
        (adr / name).rename(t)
        tmp[old] = t
    for old, t in tmp.items():
        t.rename(adr / new_name(old))
    print(f"\nmoved {len(NEW)} ADRs in force and archived {len(ARCH)}")
    for old in ARCH:
        p = adr / new_name(old)
        text = p.read_text(encoding="utf-8")
        head, _, rest = text.partition("\n")
        why = rewrite_ids(ARCHIVED[old], "archive note", Log())
        note = (f"\n> **Archived on 2026-11-23** (ADR-{RENUM_ID}): {why}. It carries no decision used by the current "
                f"study and is kept as the record. Numbers: [RENUMBERING.md](../RENUMBERING.md).\n")
        p.write_text(head + "\n" + note + rest, encoding="utf-8", newline="")


# The index ---------------------------------------------------------------------------------------------------------
RENUM_ID = f"{len(NEW) + 1:04d}"
RENUM_FILE = f"{RENUM_ID}-adr-renumbering-and-archive.md"
DAY_TITLES = {
    "2026-11-19": "Set-up, data and Phase 2 leader evidence",
    "2026-11-20": "Phase 3 follower replay, no scale-up, the latency method and the point-in-time fixes",
    "2026-11-21": "Pre-Phase 4 fixes: frozen sizing, stress rules, measured latency",
    "2026-11-22": "Scope, the new Phase 5 and grading",
    "2026-11-23": "Phase 2 gate review, Phase 4 v2 and the renumbering",
}
# Reading guide, written with the OLD numbers and converted by the same rewrite; RENUM is the renumbering ADR.
GUIDE = [
    ("Process and scope", "ADR-0046 (scope: the gray-launch go/no-go), ADR-0047 (Phase 5 designed before the "
     "holdout; the freeze mechanism), ADR-0041 (the recruiter's answers), ADR-0042 (HIP-3 out)",
     "ADR-0001 (ADRs), ADR-0009 (addresses as assets), RENUM (this numbering)"),
    ("Milestone 1: data and prices", "ADR-0110 (point-in-time price check), ADR-0118 and ADR-0121 (clean, "
     "reproducible copy)", "ADRs 0002-0005, 0008, 0010-0014, 0040"),
    ("Phase 2: leader evidence", "ADR-0048 (grades A/B/C), ADR-0049 (gates in four categories), ADR-0050 "
     "(missing measurements never pass), ADR-0052 (gate 7 v2)",
     "ADRs 0020-0026 and 0060-0065 (returns, book valuation, trips, stress, leverage), ADR-0111 (return-source "
     "switch), ADR-0045 (worst-case drawdown), ADR-0113 (excluded-coin exposure, reported)"),
    ("Phase 3: follower replay", "ADR-0119 (frozen `E_ref` sizing), ADR-0043 (no scale-up), ADR-0150 and "
     "ADR-0161 (measured delays), ADR-0160 (alt drift), ADR-0122 (stress coverage), ADR-0162 (capture)",
     "ADRs 0080-0086 and 0088 (the copy model and costs), ADRs 0112, 0114, 0115, 0117, 0120, ADR-0044 and ADRs "
     "0100-0105 (how the delay was measured), ADRs 0151 and 0152"),
    ("Phase 4: qualification (v2)", "ADR-0142 (structure), ADR-0143 (holdings α), ADR-0053 (funding out of α), "
     "ADR-0144 (evidence and categories), ADR-0145 (tradable universe, S3 gates), ADR-0146 (duplicates), "
     "ADR-0147 (the IC rule and the evaluation)", "ADRs 0170-0177 (details pinned before computing)"),
    ("Phase 5: portfolio design", "ADR-0047 (scope and order)", "its ADRs come next"),
]


def rewrite_bare(s: str) -> str:
    """Bare numbers in the old index's status column (`Amended by 0060–0064`) -> new numbers."""
    tagged = re.sub(r"(?<![\w\-–.])(?=\d{4}\b)", "ADRs ", s)
    out = rewrite_ids(tagged, "index", Log())
    return re.sub(r"ADRs? ?-?(?=A?\d{4})", "", out)


def write_index() -> None:
    adr = ROOT / ADR_DIR
    old_readme = (adr / "README.md").read_text(encoding="utf-8")
    rows = {}
    for m in re.finditer(r"^\| \[(\d{4})\]\([^)]*\) \| (.*?) \| (.*?) \| (\d{4}-\d{2}-\d{2}) \|$", old_readme, re.M):
        rows[m.group(1)] = (rewrite_ids(m.group(2), "index", Log()), rewrite_bare(m.group(3)))
    missing = set(FILES) - set(rows)
    titles = {}
    for old, name in FILES.items():
        first = (adr / name).read_text(encoding="utf-8").splitlines()[0]
        titles[old] = first.split(":", 1)[1].strip()  # the file is already rewritten
    for old in missing:
        rows[old] = (titles[old], "Accepted")
    renum_link = f"[ADR-{RENUM_ID}]({RENUM_FILE})"

    def conv(s: str) -> str:
        return rewrite_ids(s, "guide", Log()).replace("RENUM", renum_link)

    def link(old: str) -> str:
        return f"[{NEW.get(old) or ARCH[old]}]({new_name(old)})"

    head = old_readme.split("## Template", 1)[1].split("## Index", 1)[0]
    out = [
        "# Architecture decision records",
        "",
        "One file per decision: `NNNN-short-title.md`. **Numbers follow the order in which the decisions were "
        "made.**",
        f"- They were renumbered once, on 2026-11-23 ({renum_link}). Every old number and its new one are in "
        "[RENUMBERING.md](RENUMBERING.md).",
        "- A changed decision gets a new ADR, and the old one's status line says what amended it.",
        "- An ADR that no longer carries any decision used by the study moves to [archive/](archive/) as "
        "`A<old number>-short-title.md` (ID `ADR-A<old number>`). The parts still in force are copied into the ADR "
        "that replaces it first.",
        "",
        "**When to write one.** Any choice that changes a result, a data source, a rule, a threshold, the scope or",
        "the layout of the project, and any choice another session or a reviewer would otherwise have to "
        "rediscover.",
        "Exploratory trials and their numbers go in `provenance/trial_log.md`; the ADR records what was decided and",
        "why, and points to the trials.",
        "",
        f"**Numbering.** A new ADR takes the next free number ({int(RENUM_ID) + 1:04d} onward). Sessions working in "
        "parallel reserve consecutive numbers from the next free one in their brief, so the numbers stay in "
        "decision order.",
        "",
        "## Template" + head.rstrip(),
        "",
        "## Where to start: the rules in force, by phase",
        "",
        "| Phase | Latest decisions (start here) | Definitions they build on |",
        "| --- | --- | --- |",
    ]
    for phase, latest, base in GUIDE:
        out.append(f"| {phase} | {conv(latest)} | {conv(base)} |")
    out += ["", "## Index (in decision order)", ""]
    for day, olds in ORDER.items():
        lo, hi = NEW[olds[0]], NEW[olds[-1]]
        if day == "2026-11-23":
            hi = RENUM_ID
        out += [f"### {day}: {DAY_TITLES[day]} ({lo}–{hi})", "", "| ADR | Decision | Status |", "| --- | --- | --- |"]
        for old in olds:
            dec, status = rows[old]
            out.append(f"| {link(old)} | {dec} | {status} |")
        if day == "2026-11-23":
            out.append(f"| [{RENUM_ID}]({RENUM_FILE}) | One-time renumbering in decision order; the 18 ADRs no "
                       "longer in force archived after their live parts were copied forward | Accepted |")
        out.append("")
    out += ["## Archive", "",
            "Kept as the record; none carries a decision used by the current study.", "",
            "| ADR | Decision | Why archived |", "| --- | --- | --- |"]
    for old in sorted(ARCH):
        out.append(f"| {link(old)} | {rows[old][0]} | {rewrite_ids(ARCHIVED[old], 'index', Log())} |")
    (adr / "README.md").write_text("\n".join(out) + "\n", encoding="utf-8", newline="")

    ren = [
        "# ADR renumbering of 2026-11-23",
        "",
        f"Decided in [ADR-{RENUM_ID}]({RENUM_FILE}); done by `scripts/adr_renumber.py`. Look up an old number here.",
        "",
        "**Where old numbers remain.** These were not rewritten, so their ADR numbers are the old ones:",
        "- generated outputs under `research/` (they change when regenerated);",
        "- the checksum records, the before/after folders and the void freeze under `provenance/`;",
        "- the latency session's files (`src/arkstream/latency.py`, `src/arkstream_fetch/hl_ws_latency.py`, "
        "`tests/test_hl_ws_latency.py`, `research/latency/`, `data/reference/latency/`). Rewrite them with "
        "`uv run python scripts/adr_renumber.py --files <path>` once that session is done;",
        "- `decision/phase-5-methodology-1.md` (Phase 5 revision 3), which was being written while the renumbering "
        "ran. Its planned ADRs 0180-0189 would become the next free numbers.",
        "",
        "The reserved number blocks quoted in `decision/briefs/` are the blocks as they were reserved. "
        "`ADR-0018 D11` in `decision/latency_study.md` is the Binance latency repo's own ADR.",
        "",
        "| Old | New | Decision |",
        "| --- | --- | --- |",
    ]
    for old in sorted(FILES):
        ren.append(f"| {old} | {link(old)} | {titles[old]} |")
    (adr / "RENUMBERING.md").write_text("\n".join(ren) + "\n", encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
