"""Focused provider-free tests for the CM-57P5 holdout harness."""

from __future__ import annotations

import asyncio
import json
from argparse import Namespace
from pathlib import Path

import pytest
from scripts import cm57p5_fresh_holdout as p5

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.capabilities import create_builtin_registry


@pytest.fixture()
def cases() -> tuple[dict[str, object], ...]:
    """Load the frozen P5 corpus through the harness validator."""
    return p5.load_case_definitions()


def _patch_historical_planner_hash(
    monkeypatch: pytest.MonkeyPatch,
    planner_hash: str | None = None,
) -> None:
    """Simulate only the planner bytes used by the closed P5 evaluation."""
    real_artifact_sha256 = p5.artifact_sha256
    planner_path = (p5.REPO_ROOT / "src/wellplot/agent/code_mode/planner.py").resolve()
    expected = planner_hash or p5.EXPECTED_PLANNER_SOURCE_SHA256

    def historical_artifact_sha256(path: Path) -> str:
        if Path(path).resolve() == planner_path:
            return expected
        return real_artifact_sha256(path)

    monkeypatch.setattr(p5, "artifact_sha256", historical_artifact_sha256)


def test_fresh_corpus_has_exact_family_distribution_and_frozen_hash(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Verify the exact six-family holdout shape and corpus hash."""
    assert len(cases) == 24
    assert {case["family"] for case in cases} == set(p5.FAMILIES)
    assert all(sum(case["family"] == other["family"] for other in cases) == 4 for case in cases)
    assert len({case["case_id"] for case in cases}) == 24
    assert len({case["request"] for case in cases}) == 24
    assert p5.artifact_sha256(p5.CASE_PATH) == p5.EXPECTED_HOLDOUT_SHA256


def test_fresh_requests_are_path_free_and_do_not_leak_planner_vocabulary(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Reject paths, internal IDs, evaluator terms, and historical requests."""
    corpus_text = p5.CASE_PATH.read_text(encoding="utf-8")
    assert not p5.PATH_RE.search(corpus_text)
    for case in cases:
        request = str(case["request"])
        assert not any(term in request for term in p5.CAPABILITY_IDS)
        assert not any(term in request for term in p5.FORBIDDEN_REQUEST_TERMS)
    historical_hashes = p5._cm57c_request_hashes()
    assert not {p5.sha256_text(str(case["request"])) for case in cases} & historical_hashes


def test_fixed_source_summary_is_path_free_and_frozen() -> None:
    """Verify the shared source summary is deterministic and redacted."""
    source_summary = p5.canonical_json(p5.FIXED_SOURCE_SUMMARY)
    assert p5._fixed_source_summary_sha() == p5.EXPECTED_SOURCE_SUMMARY_SHA256
    assert not p5.PATH_RE.search(source_summary)
    assert "candidate_id" not in source_summary


def test_holdout_gold_is_unchanged_from_r1_review_baseline() -> None:
    """Ensure R1 request wording changes did not alter any expected gold."""
    baseline_path = f"{p5.BASELINE_SHA}:tests/fixtures/typed_worker/cm57p5_fresh_holdout.json"
    baseline_payload = json.loads(p5._git_output("show", baseline_path))
    current_payload = json.loads(p5.CASE_PATH.read_text(encoding="utf-8"))

    def gold_projection(payload: dict[str, object]) -> list[tuple[object, ...]]:
        return [
            (
                case["case_id"],
                case["family"],
                tuple(case["expected_report_capabilities"]),
                tuple(tuple(section) for section in case["expected_sections"]),
                case["expected_unresolved_count"],
            )
            for case in payload["cases"]
        ]

    assert gold_projection(current_payload) == gold_projection(baseline_payload)


def test_section_multiset_is_order_independent_and_preserves_duplicates(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Verify section order is irrelevant while multiplicity remains material."""
    registry = create_builtin_registry()
    case = cases[13]
    plan = SemanticPlan(
        summary="reordered independent panels",
        section_tasks=(
            SectionTask(
                goal="image",
                capability_ids=("section.log_plot", "track.array", "binding.raster"),
            ),
            SectionTask(
                goal="curve",
                capability_ids=("binding.curve", "track.normal", "section.log_plot"),
            ),
        ),
    )
    assert p5.final_contract_ok(p5._facts(plan, case, registry))

    duplicate_case = cases[12]
    duplicate_plan = SemanticPlan(
        summary="two identical panels",
        section_tasks=(
            SectionTask(
                goal="one",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
            SectionTask(
                goal="two",
                capability_ids=("binding.curve", "track.normal", "section.log_plot"),
            ),
        ),
    )
    assert p5.final_contract_ok(p5._facts(duplicate_plan, duplicate_case, registry))

    missing_plan = duplicate_plan.model_copy(
        update={"section_tasks": duplicate_plan.section_tasks[:1]}
    )
    missing_facts = p5._facts(missing_plan, duplicate_case, registry)
    assert not missing_facts["section_multiset_exact"]
    assert not p5.final_contract_ok(missing_facts)


def test_mixed_report_and_section_gold_requires_all_work_units(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Require report and all independent section work units in mixed gold."""
    registry = create_builtin_registry()
    case = cases[18]
    complete = SemanticPlan(
        summary="report and two panels",
        report_task=ReportTask(goal="report", capability_ids=("report.standard",)),
        section_tasks=(
            SectionTask(
                goal="curve",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
            SectionTask(
                goal="image",
                capability_ids=("section.log_plot", "track.array", "binding.raster"),
            ),
        ),
    )
    assert p5.final_contract_ok(p5._facts(complete, case, registry))
    merged = complete.model_copy(update={"section_tasks": (complete.section_tasks[0],)})
    assert not p5.final_contract_ok(p5._facts(merged, case, registry))
    empty_report = complete.model_copy(
        update={"report_task": ReportTask(goal="empty", capability_ids=())}
    )
    assert not p5.final_contract_ok(p5._facts(empty_report, case, registry))


def test_independent_sections_must_not_be_merged_into_one_task(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Reject one task that merges two independently expected sections."""
    registry = create_builtin_registry()
    case = cases[13]
    merged = SemanticPlan(
        summary="merged independent panels",
        section_tasks=(
            SectionTask(
                goal="merged curve and image",
                capability_ids=(
                    "section.log_plot",
                    "track.normal",
                    "binding.curve",
                    "track.array",
                    "binding.raster",
                ),
            ),
        ),
    )
    facts = p5._facts(merged, case, registry)
    assert not p5.final_contract_ok(facts)
    assert p5.classify_facts(facts) == "SECTION_COUNT_MISMATCH"


def test_multiplicity_distinguishes_within_task_duplicates_from_independent_tasks(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Distinguish repeated types in one task from repeated independent tasks."""
    registry = create_builtin_registry()
    case = cases[20]
    valid = SemanticPlan(
        summary="two curves",
        section_tasks=(
            SectionTask(
                goal="one panel",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
        ),
    )
    assert p5.final_contract_ok(p5._facts(valid, case, registry))
    invalid = valid.model_copy(
        update={
            "section_tasks": (
                SectionTask(
                    goal="bad duplicate type",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "binding.curve",
                        "binding.curve",
                    ),
                ),
            )
        }
    )
    facts = p5._facts(invalid, case, registry)
    assert facts["duplicate_capability_type"]
    assert not p5.final_contract_ok(facts)


def test_decision_precedence_covers_validated_regression_partial_no_gain_and_inconclusive(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Exercise every frozen holdout decision precedence branch."""
    rows = p5._synthetic_rows(cases)
    assert p5.decision(rows, cases, expected_checkpoint=p5.BASELINE_SHA) == (
        "HOLDOUT_GENERALIZATION_VALIDATED"
    )

    rows[0]["arms"]["RC"]["final_contract_ok"] = False
    assert p5.decision(rows, cases, expected_checkpoint=p5.BASELINE_SHA) == (
        "HOLDOUT_GENERALIZATION_REGRESSION"
    )

    rows[0]["arms"]["RC"]["final_contract_ok"] = True
    rows[0]["arms"]["P"]["final_contract_ok"] = False
    rows[1]["arms"]["P"]["final_contract_ok"] = False
    rows[1]["arms"]["RC"]["final_contract_ok"] = False
    assert p5.decision(rows, cases, expected_checkpoint=p5.BASELINE_SHA) == (
        "HOLDOUT_GENERALIZATION_PARTIAL"
    )

    for row in rows:
        row["arms"]["P"]["final_contract_ok"] = False
        row["arms"]["RC"]["final_contract_ok"] = False
    assert p5.decision(rows, cases, expected_checkpoint=p5.BASELINE_SHA) == (
        "HOLDOUT_GENERALIZATION_NO_GAIN"
    )

    rows[0]["arms"]["RC"]["provider_infrastructure_failure"] = True
    assert p5.decision(rows, cases, expected_checkpoint=p5.BASELINE_SHA) == (
        "INCONCLUSIVE_HOLDOUT_EVALUATION"
    )


def test_production_path_equivalence_self_test_is_provider_free(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Run actual P and RC path checks without constructing a provider."""
    asyncio.run(p5._production_path_equivalence_self_test(cases[4]))
    assert p5.sha256_text(p5.RC_PROMPT) == p5.EXPECTED_RC_PROMPT_SHA256


def test_population_rejects_prompt_and_corpus_provenance_drift(
    cases: tuple[dict[str, object], ...],
) -> None:
    """Reject changed prompt and corpus provenance in a complete population."""
    rows = p5._synthetic_rows(cases)
    rows[0]["arms"]["RC"]["prompt_sha256"] = "drift"
    rows[1]["corpus_sha256"] = "drift"
    complete, reasons = p5.population_integrity(
        rows,
        cases,
        expected_checkpoint=p5.BASELINE_SHA,
    )
    assert not complete
    assert "RC_prompt_mismatch" in reasons
    assert "corpus_sha256_mismatch" in reasons


def test_nonempty_evidence_path_is_rejected_before_provider_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject existing evidence before the provider configuration boundary."""
    output = tmp_path / "existing.jsonl"
    output.write_text("retained evidence\n", encoding="utf-8")
    monkeypatch.setattr(p5, "OUTPUT_PATH", output)
    constructed = False

    def fail_if_constructed(_args: Namespace) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("provider construction must not occur")

    monkeypatch.setattr(p5, "_provider_configuration", fail_if_constructed)
    args = Namespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="non-empty evidence path"):
        asyncio.run(p5._run_live(args, p5.BASELINE_SHA))
    assert not constructed


def _patch_reviewed_checkout_bytes(
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: str,
    drifted_path: str,
) -> None:
    """Make the reviewed-checkout guard see one deliberately drifted file."""
    monkeypatch.setattr(p5, "current_checkout_sha", lambda: checkpoint)

    def fake_git_output(*arguments: str) -> bytes:
        if len(arguments) == 2 and arguments[0] == "show":
            _, relative_path = arguments[1].split(":", 1)
            if relative_path == drifted_path:
                return b"drift"
            return (p5.REPO_ROOT / relative_path).read_bytes()
        raise AssertionError(f"Unexpected Git command in guard test: {arguments!r}")

    monkeypatch.setattr(p5, "_git_output", fake_git_output)


@pytest.mark.parametrize(
    "drifted_path",
    [
        "scripts/cm57p5_fresh_holdout.py",
        "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json",
    ],
)
def test_live_gate_rejects_harness_or_corpus_drift_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drifted_path: str,
) -> None:
    """Abort before provider construction when a reviewed byte guard drifts."""
    monkeypatch.setattr(p5, "OUTPUT_PATH", tmp_path / "evidence.jsonl")
    checkpoint = "a" * 40
    _patch_reviewed_checkout_bytes(monkeypatch, checkpoint, drifted_path)
    constructed = False

    def fail_if_constructed(_args: Namespace) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("provider construction must not occur")

    monkeypatch.setattr(p5, "_provider_configuration", fail_if_constructed)
    args = Namespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="guarded artifact drifted"):
        asyncio.run(p5._run_live(args, checkpoint))
    assert not constructed


@pytest.mark.parametrize(
    ("drift_kind", "expected_message"),
    [
        ("prompt", "Production planner prompt drifted"),
        ("source", "source summary bytes drifted"),
        ("controls", "execution controls drifted"),
    ],
)
def test_live_gate_rejects_prompt_source_or_control_drift_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
    expected_message: str,
) -> None:
    """Abort before provider construction when frozen contract values drift."""
    _patch_historical_planner_hash(monkeypatch)
    monkeypatch.setattr(p5, "OUTPUT_PATH", tmp_path / "evidence.jsonl")
    monkeypatch.setattr(p5, "verify_reviewed_checkout", lambda _checkpoint: None)
    if drift_kind == "prompt":
        monkeypatch.setattr(p5, "EXPECTED_BASE_PROMPT_SHA256", "drift")
    elif drift_kind == "source":
        monkeypatch.setitem(p5.FIXED_SOURCE_SUMMARY, "version", "drift")
    else:
        monkeypatch.setattr(p5, "PLANNER_TEMPERATURE", 1.0)

    constructed = False

    def fail_if_constructed(_args: Namespace) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("provider construction must not occur")

    monkeypatch.setattr(p5, "_provider_configuration", fail_if_constructed)
    args = Namespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match=expected_message):
        asyncio.run(p5._run_live(args, p5.BASELINE_SHA))
    assert not constructed


def test_historical_planner_drift_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P5 rejects an incorrect historical planner hash."""
    _patch_historical_planner_hash(monkeypatch, "0" * 64)

    with pytest.raises(RuntimeError, match="Production planner bytes drifted"):
        p5.prelive_report()
