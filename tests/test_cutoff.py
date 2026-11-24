"""The cutoff selection and the cutoff deliverables (ADR-0100): the cutoff origin and context, the guards, the P5-8
order, the first-failed-gate rule and the allocations."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from arkstream import cutoff
from arkstream.config import load_context, research_dir
from arkstream.freeze import FreezeError, holdout_start

OBS = "0x971fc0c9becffd708c52a195b8a87c27359e77fa"


def tmp_ctx(tmp_path: Path):
    ctx = load_context()
    shutil.copytree(ctx.root / "config", tmp_path / "config", dirs_exist_ok=True)
    return type(ctx)(raw=ctx.raw, root=tmp_path)


def test_cutoff_origin_is_the_last_midnight_before_the_cutoff():
    ctx = load_context()
    assert cutoff.cutoff_origin(ctx) == date(2026, 1, 4)
    assert cutoff.midnight(cutoff.cutoff_origin(ctx)) <= ctx.cutoff


def test_cutoff_context_extends_the_origins_and_keeps_the_real_holdout_start(tmp_path):
    from arkstream import drift

    ctx = tmp_ctx(tmp_path)
    out = tmp_path / "research/cutoff"
    c = cutoff.cutoff_context(ctx, date(2026, 1, 4), out)
    dr = drift.DriftRules.from_config(c.raw)
    assert dr.origin_dates[-1] == date(2026, 1, 4) and len(dr.origin_dates) == 6
    assert dr.est_end == date(2026, 1, 3) and dr.holdout_start == date(2026, 1, 4)
    assert holdout_start(c.raw).date() == date(2025, 12, 3)  # every guard inside still needs the freeze
    assert research_dir(c, "leader") == out / "leader" and research_dir(ctx, "leader") == tmp_path / "research/leader"
    assert ctx.raw["drift"]["origins"][-1] != "2026-01-04"  # the real configuration is untouched
    from arkstream.freeze import guard

    with pytest.raises(FreezeError):
        guard(c, cutoff.midnight(date(2026, 1, 4)))


def test_cutoff_selection_is_refused_without_the_freeze(tmp_path):
    with pytest.raises(FreezeError):
        cutoff.run(tmp_ctx(tmp_path))
    assert not (tmp_path / cutoff.OUT).exists()  # nothing ran before the guard


def test_cutoff_selection_waits_for_run_a(tmp_path, monkeypatch):
    import arkstream.freeze as F

    monkeypatch.setattr(F, "guard", lambda ctx, t: "hash")
    with pytest.raises(RuntimeError, match="run_A.json"):
        cutoff.run(tmp_ctx(tmp_path))
    assert not (tmp_path / cutoff.OUT).exists()


def test_deliverables_wait_for_the_decision_entry(tmp_path, monkeypatch):
    import arkstream.freeze as F

    monkeypatch.setattr(F, "guard", lambda ctx, t: "hash")
    with pytest.raises(RuntimeError, match="decision_A.json"):
        cutoff.deliverables(tmp_ctx(tmp_path))
    with pytest.raises(FreezeError):
        monkeypatch.undo()
        cutoff.deliverables(tmp_ctx(tmp_path / "x"))


def test_resume_is_refused_outside_check_mode(tmp_path):
    with pytest.raises(ValueError, match="check mode only"):
        cutoff.run(tmp_ctx(tmp_path), resume=True)


def test_decision_stage_waits_for_run_a_and_the_cutoff_selection(tmp_path):
    from arkstream import holdout

    ctx = tmp_ctx(tmp_path)
    spec = holdout.holdout_spec(ctx)
    cf = tmp_path / "cutoff_handoff.json"
    with pytest.raises(RuntimeError, match="run_A.json"):
        holdout.stage_decision(ctx, spec, tmp_path, None, cf)
    (tmp_path / "run_A.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="cutoff selection"):
        holdout.stage_decision(ctx, spec, tmp_path, None, cf)


def test_holdout_stages_are_named_and_guarded(tmp_path):
    from arkstream import holdout

    with pytest.raises(ValueError, match="unknown stage"):
        holdout.run(tmp_ctx(tmp_path), stage="all")
    with pytest.raises(FreezeError):
        holdout.run(tmp_ctx(tmp_path), stage="decision")


def test_training_window_needs_a_configured_origin():
    from arkstream.replay_sensitivity import run_sensitivities

    with pytest.raises(ValueError, match="invalid single training window"):
        run_sensitivities(load_context(), training=date(2025, 12, 10))


# ---------------------------------------------------------------------------------------------- deliverables
def test_first_failed_gate_follows_the_pinned_order():
    ok = {"grade": "A", "s2": True, "category": "E1", "duplicate_decision": "kept",
          **{g: "pass" for g in cutoff.S3_ORDER}}
    assert cutoff.first_failed_gate(ok) == "none"
    assert cutoff.first_failed_gate({**ok, "grade": "C"}) == "S1_grade_C"
    assert cutoff.first_failed_gate({**ok, "s2": False, "gates_failed": ["g3_coverage", "g5"]}) == "S2_g3_coverage"
    assert cutoff.first_failed_gate({**ok, "sel_break_even": "fail", "sel_copier": "fail"}) == "S3_sel_break_even_fail"
    assert cutoff.first_failed_gate({**ok, "sel_direction": "unmeasured"}) == "S3_sel_direction_unmeasured"
    assert cutoff.first_failed_gate({**ok, "category": "E0"}) == "category_E0"
    assert cutoff.first_failed_gate({**ok, "duplicate_decision": "near_duplicate"}) == "near_duplicate"
    assert cutoff.first_failed_gate({"grade": None}) == "S1_grade_none"


def selection(tmp_path: Path, origin: date, rows: list[tuple[str, str, float, float]], m_constant: bool) -> Path:
    sel = tmp_path / "selection_v2"
    d = sel / f"origin={origin}"
    d.mkdir(parents=True)
    pl.DataFrame(rows, schema={"trader": pl.String, "category": pl.String, "m": pl.Float64, "alpha": pl.Float64},
                 orient="row").write_parquet(d / "eligible.parquet")
    ms = [0.0] * 5 if m_constant else [0.1, 0.2, 0.3, 0.4, 0.5]
    pl.DataFrame({"m": ms}).write_parquet(d / "evidence.parquet")
    return sel


def test_allocations_paper_and_gray(tmp_path):
    ctx = tmp_ctx(tmp_path)
    o = date(2026, 1, 4)
    sel = selection(tmp_path, o, [("0xa", "E1", 0.0, 0.9), ("0xb", "E2", 0.0, 0.1), ("0xc", "E1", 0.0, 0.5)],
                    m_constant=True)
    paper = cutoff.target_allocations(ctx, o, sel, "NO-GO")
    assert paper.filter(pl.col("role") == "hand-off")["deployed_usdc"].sum() == 0
    assert paper.filter(pl.col("role") == "reserve")["deployed_usdc"][0] == 100000.0
    assert paper.filter(pl.col("role") == "observation")["trader"].to_list() == [OBS]
    gray = cutoff.target_allocations(ctx, o, sel, "CONDITIONAL GO")
    live = gray.filter(pl.col("protocol") == "gray")["trader"].to_list()
    assert live == ["0xb", "0xa"]  # E2 first, then E1 by own alpha (m constant), at most two
    assert gray.filter(pl.col("role") == "reserve")["deployed_usdc"][0] == 95000.0
    assert gray["ordering_statistic"][0] == "alpha"
    assert gray.filter(pl.col("trader") == "0xc")["protocol"][0] == "paper"


def test_a_cutoff_address_that_cannot_be_replayed_has_d2b_unmeasured(tmp_path):
    from arkstream import holdout

    ctx = load_context()
    spec = holdout.holdout_spec(ctx)
    hand = ["0x2cd9f4645b14bf968212c7c108213eaeb193946e"]
    done, unmeasured = holdout.cutoff_reruns(ctx, spec, [*hand, "0xnot_in_the_3_dec_universe"], hand, tmp_path)
    assert done == [] and unmeasured == ["0xnot_in_the_3_dec_universe"]
    assert not (tmp_path / "replay_gray_cutoff").exists()  # nothing built, nothing read past 3 Dec


def test_decision_entry_fails_d2b_for_an_unmeasured_cutoff_address(tmp_path):
    from arkstream import holdout

    ctx = load_context()
    spec = holdout.check_spec(ctx)
    tables = {
        "h1_engine": pl.DataFrame({"clean": [True]}),
        "h2_risk": pl.DataFrame({"config": ["S", "S", "G2500", "G2500"], "scenario": ["base", "stress"] * 2,
                                 "within_limit": [True] * 4, "cap_breaches_at_update": [0] * 4}),
        "h3_costs": pl.DataFrame({"measured": [True], "within_p90": [True]}),
        "h5_cross_section": pl.DataFrame({"test": ["d4"], "group": ["alpha"], "value": [0.1],
                                          "note": ["threshold -0.14"]}),
    }
    (tmp_path / "window_report").mkdir()
    ok = holdout.decision_entry(ctx, spec, tmp_path, tables, True, [], None)
    assert json.loads(ok.read_text(encoding="utf-8"))["decision"] == "CONDITIONAL GO"
    bad = holdout.decision_entry(ctx, spec, tmp_path, tables, True, ["0xnew"], None)
    d = json.loads(bad.read_text(encoding="utf-8"))
    assert d["D2b"] is False and d["decision"] == "NO-GO" and d["d2b_unmeasured_cutoff_addresses"] == ["0xnew"]
