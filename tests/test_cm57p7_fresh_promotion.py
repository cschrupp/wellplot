"""Provider-free tests for the CM-57P7 promotion harness."""

from __future__ import annotations

import asyncio
import copy
import json
from argparse import Namespace
from collections import Counter
from pathlib import Path

import pytest
from scripts import cm57p7_fresh_promotion as p7


def _cases() -> tuple[dict[str, object], ...]:
    return p7.load_case_definitions()


def _patch_historical_planner_hash(
    monkeypatch: pytest.MonkeyPatch,
    planner_hash: str | None = None,
) -> None:
    """Simulate only the planner bytes used by the closed P7 evaluation."""
    real_artifact_sha256 = p7.artifact_sha256
    planner_path = (p7.REPO_ROOT / "src/wellplot/agent/code_mode/planner.py").resolve()
    expected = planner_hash or p7.EXPECTED_PLANNER_SOURCE_SHA256

    def historical_artifact_sha256(path: Path) -> str:
        if Path(path).resolve() == planner_path:
            return expected
        return real_artifact_sha256(path)

    monkeypatch.setattr(p7, "artifact_sha256", historical_artifact_sha256)


def _synthetic_row(
    case: dict[str, object], *, checkpoint: str = p7.BASELINE_SHA
) -> dict[str, object]:
    """Build a bounded, all-success row for integrity tests."""
    facts = {
        "report_task_present": bool(case["expected_report_capabilities"]),
        "report_capability_ids": list(case["expected_report_capabilities"]),
        "report_presence_correct": True,
        "report_capabilities_exact": True,
        "section_task_count": len(case["expected_sections"]),
        "section_count_correct": True,
        "section_multiset_exact": True,
        "parent_closure_valid": True,
        "unresolved_correct": True,
        "duplicate_capability_type": False,
        "unresolved_requirements_count": 0,
    }
    result = {
        "prompt_sha256": "",
        "response_schema_sha256": "",
        "provider_calls": 1,
        "program_calls": 0,
        "final_planner_success": True,
        "final_contract_ok": True,
        "provider_infrastructure_failure": False,
        "final_classification": "PLANNER_CONTRACT_OK",
        "final_work_unit_facts": facts,
    }
    result_by_arm = {
        arm: {
            **result,
            "prompt_sha256": p7._prompt_sha256(arm),
            "response_schema_sha256": p7._schema_sha256(arm),
        }
        for arm in p7.ARMS
    }
    return {
        **p7.frozen_provenance(),
        "authorized_checkpoint": checkpoint,
        "case_id": case["case_id"],
        "family": case["family"],
        "attempt_index": 0,
        "request_sha256": p7.sha256_text(str(case["request"])),
        "expected_report_capabilities": list(case["expected_report_capabilities"]),
        "expected_sections": [list(section) for section in case["expected_sections"]],
        "expected_unresolved_count": 0,
        "arms": result_by_arm,
    }


def test_fresh_corpus_has_required_shape_and_family_distribution() -> None:
    """Require the fresh corpus to contain four cases in each family."""
    cases = _cases()
    assert len(cases) == 24
    assert Counter(case["family"] for case in cases) == Counter(dict.fromkeys(p7.FAMILIES, 4))
    assert len({case["case_id"] for case in cases}) == 24


def test_fresh_requests_are_disjoint_and_provider_safe() -> None:
    """Reject reused, path-bearing, or internal request text."""
    cases = _cases()
    previous = p7.p5.load_case_definitions()
    old_requests = {p7._normalized_request(str(case["request"])) for case in previous}
    assert not old_requests.intersection(
        p7._normalized_request(str(case["request"])) for case in cases
    )
    serialized = json.dumps(cases, sort_keys=True)
    assert "/" not in serialized
    assert "SectionTask" not in serialized
    assert "SemanticPlan" not in serialized
    assert all(case["expected_unresolved_count"] == 0 for case in cases)


def test_gold_is_checked_against_builtin_registry() -> None:
    """Validate every report and section gold entry against the registry."""
    cases = _cases()
    registry = p7.create_builtin_registry()
    for case in cases:
        p7.p5._validate_report_gold(case["expected_report_capabilities"], registry, case["case_id"])
        for section in case["expected_sections"]:
            p7.p5._validate_section_gold(section, registry, case["case_id"])


def test_arm_identity_and_schema_contract_are_frozen() -> None:
    """Lock the four arm order and their prompt/schema identities."""
    assert p7.ARMS == ("P", "RC", "RCV", "RCS")
    assert p7._schema_sha256("P") == p7.EXPECTED_PRODUCTION_SCHEMA_SHA256
    assert p7._schema_sha256("RCV") == p7.EXPECTED_PRODUCTION_SCHEMA_SHA256
    assert p7._schema_sha256("RCS") == p7.EXPECTED_NONEMPTY_SCHEMA_SHA256
    assert p7._prompt_sha256("P") == p7.EXPECTED_BASE_PROMPT_SHA256
    assert p7._prompt_sha256("RC") == p7.EXPECTED_RC_PROMPT_SHA256


def test_all_arm_paths_run_without_provider_calls() -> None:
    """Exercise P, RC, RCV, and RCS with only the deterministic fake backend."""
    case = _cases()[4]

    async def run() -> list[dict[str, object]]:
        results = []
        for arm in p7.ARMS:
            backend = p7.p5._DeterministicBackend(invalid_first=True)
            result = await p7.run_arm(
                case,
                arm=arm,
                delegate=backend,
                registry=p7.create_builtin_registry(),
            )
            assert result["program_calls"] == 0
            results.append(result)
        return results

    results = asyncio.run(run())
    assert all(result["final_planner_success"] for result in results)
    assert all(result["provider_calls"] == 2 for result in results)


def test_population_integrity_fails_closed_for_missing_population() -> None:
    """Treat an incomplete evidence population as invalid."""
    complete, reasons = p7.population_integrity([], _cases(), expected_checkpoint=p7.BASELINE_SHA)
    assert not complete
    assert "wrong_row_count" in reasons


def test_population_integrity_fails_closed_for_malformed_arm_data() -> None:
    """Report malformed arm data instead of raising while validating it."""
    case = _cases()[0]
    row = _synthetic_row(case)
    row["arms"] = None
    complete, reasons = p7.population_integrity([row], (case,), expected_checkpoint=p7.BASELINE_SHA)
    assert not complete
    assert "arm_set_mismatch" in reasons


def test_population_integrity_rejects_program_calls() -> None:
    """Reject any row that reaches a worker/program boundary."""
    case = _cases()[0]
    row = _synthetic_row(case)
    row["arms"]["P"]["program_calls"] = 1
    complete, reasons = p7.population_integrity([row], (case,), expected_checkpoint=p7.BASELINE_SHA)
    assert not complete
    assert "worker_program_call" in reasons


def test_population_integrity_rejects_prompt_or_schema_drift() -> None:
    """Reject arm prompt and response-schema provenance drift."""
    case = _cases()[0]
    row = _synthetic_row(case)
    row["arms"]["RC"]["prompt_sha256"] = p7.EXPECTED_BASE_PROMPT_SHA256
    row["arms"]["RCS"]["response_schema_sha256"] = p7.EXPECTED_PRODUCTION_SCHEMA_SHA256
    complete, reasons = p7.population_integrity([row], (case,), expected_checkpoint=p7.BASELINE_SHA)
    assert not complete
    assert "RC_prompt_mismatch" in reasons
    assert "RCS_schema_mismatch" in reasons


def test_decision_labels_are_candidate_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    """Select validator-only and schema-only labels independently."""
    cases = _cases()
    rows = [_synthetic_row(case) for case in cases]
    monkeypatch.setattr(p7, "population_integrity", lambda *args, **kwargs: (True, []))
    monkeypatch.setattr(p7, "_activation_cases", lambda *args, **kwargs: ({"activation"}, []))
    monkeypatch.setattr(
        p7,
        "_repeatability",
        lambda *args, **kwargs: {"stable": 24, "unstable": 0, "unavailable": 0},
    )

    def viability(*args: object, **kwargs: object) -> dict[str, object]:
        candidate = str(args[2])
        return {"viable": candidate == "RCV"}

    monkeypatch.setattr(p7, "_candidate_viability", viability)
    assert p7.decision(rows, cases) == "PROMOTION_VALIDATOR_ONLY_VALIDATED"

    monkeypatch.setattr(
        p7,
        "_candidate_viability",
        lambda *args, **kwargs: {"viable": str(args[2]) == "RCS"},
    )
    assert p7.decision(rows, cases) == "PROMOTION_SCHEMA_ONLY_VALIDATED"


@pytest.mark.parametrize(
    ("validator", "schema", "expected"),
    [
        (True, True, "PROMOTION_BOTH_VALIDATED"),
        (False, True, "PROMOTION_SCHEMA_ONLY_VALIDATED"),
        (True, False, "PROMOTION_VALIDATOR_ONLY_VALIDATED"),
        (False, False, "PROMOTION_NO_CANDIDATE_VALIDATED"),
    ],
)
def test_decision_supports_all_complete_population_labels(
    monkeypatch: pytest.MonkeyPatch,
    validator: bool,
    schema: bool,
    expected: str,
) -> None:
    """Exercise each non-inconclusive promotion label."""
    cases = _cases()
    rows = [_synthetic_row(case) for case in cases]
    monkeypatch.setattr(p7, "population_integrity", lambda *args, **kwargs: (True, []))
    monkeypatch.setattr(
        p7,
        "_activation_cases",
        lambda *args, **kwargs: ({"activation"}, []),
    )
    monkeypatch.setattr(
        p7,
        "_repeatability",
        lambda *args, **kwargs: {"stable": 24, "unstable": 0, "unavailable": 0},
    )

    def viability(*args: object, **kwargs: object) -> dict[str, object]:
        values = {"RCV": validator, "RCS": schema}
        return {"viable": values[str(args[2])]}

    monkeypatch.setattr(p7, "_candidate_viability", viability)
    assert p7.decision(rows, cases) == expected


def test_decision_is_inconclusive_for_provider_infrastructure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make provider infrastructure failures dominate candidate scoring."""
    cases = _cases()
    rows = [_synthetic_row(case) for case in cases]
    rows[0]["arms"]["RCV"]["provider_infrastructure_failure"] = True
    monkeypatch.setattr(p7, "population_integrity", lambda *args, **kwargs: (True, []))
    assert p7.decision(rows, cases) == "INCONCLUSIVE_PROMOTION_EVALUATION"


def test_decision_is_inconclusive_for_unstable_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not score candidates when P or RC changes between attempts."""
    cases = _cases()
    rows = [_synthetic_row(case) for case in cases]
    monkeypatch.setattr(p7, "population_integrity", lambda *args, **kwargs: (True, []))
    monkeypatch.setattr(
        p7,
        "_repeatability",
        lambda rows, arm: (
            {"stable": 23, "unstable": 1, "unavailable": 0}
            if arm == "P"
            else {"stable": 24, "unstable": 0, "unavailable": 0}
        ),
    )
    assert p7.decision(rows, cases) == "INCONCLUSIVE_PROMOTION_EVALUATION"


def test_duplicate_property_is_evaluated_as_no_duplicate_correctness() -> None:
    """Count a newly introduced duplicate as a P-to-candidate regression."""
    case = _cases()[0]
    row = _synthetic_row(case)
    row = copy.deepcopy(row)
    row["arms"]["RCV"]["final_work_unit_facts"] = copy.deepcopy(
        row["arms"]["RCV"]["final_work_unit_facts"]
    )
    row["arms"]["RCV"]["final_work_unit_facts"]["duplicate_capability_type"] = True
    transition = p7._field_transition([row], "P", "RCV", "no_duplicate_capability_type")
    assert transition["CORRECT_TO_WRONG"] == 1


def test_candidate_gain_requires_four_cases_and_two_families() -> None:
    """Require the stable gain threshold and family spread for viability."""
    cases = _cases()
    rows = []
    for case in cases:
        for attempt in range(p7.ATTEMPTS):
            row = _synthetic_row(case)
            row["attempt_index"] = attempt
            row["arms"]["P"]["final_contract_ok"] = False
            rows.append(row)
    viable = p7._candidate_viability(rows, cases, "RCV", set())
    assert viable["viable"]
    assert len(viable["stable_gains"]) == 24

    first_cases = {case["case_id"] for case in cases[:3]}
    for row in rows:
        if row["case_id"] not in first_cases:
            row["arms"]["RCV"]["final_contract_ok"] = False
    not_viable = p7._candidate_viability(rows, cases, "RCV", set())
    assert not not_viable["viable"]


def test_activation_requires_both_report_families() -> None:
    """Do not validate candidates without both report activation families."""
    cases = _cases()
    rows = []
    for case in cases:
        for attempt in range(p7.ATTEMPTS):
            row = _synthetic_row(case)
            row["attempt_index"] = attempt
            row["arms"]["RC"]["final_work_unit_facts"]["report_task_present"] = True
            row["arms"]["RC"]["final_work_unit_facts"]["report_capability_ids"] = []
            row["arms"]["RC"]["final_classification"] = "REPORT_CAPABILITY_MISMATCH"
            rows.append(row)
    activated, reasons = p7._activation_cases(rows, cases)
    assert len(activated) == 8
    assert reasons == []
    mixed_only = [row for row in rows if row["family"] == "MIXED_REPORT_SECTION"]
    activated, reasons = p7._activation_cases(mixed_only, cases)
    assert activated
    assert reasons == ["insufficient_rc_activation"]


def test_activation_recovery_ignores_unrelated_section_failure() -> None:
    """Score the report invariant even when section work remains wrong."""
    case = _cases()[0]
    row = _synthetic_row(case)
    row["arms"]["RCV"]["final_contract_ok"] = False
    row["arms"]["RCV"]["final_classification"] = "SECTION_WORK_UNIT_MISMATCH"
    assert p7._activation_report_recovered(row, "RCV")
    row["arms"]["RCV"]["final_work_unit_facts"]["report_capabilities_exact"] = False
    assert not p7._activation_report_recovered(row, "RCV")


@pytest.mark.parametrize(
    "label",
    ["INCONCLUSIVE_PROMOTION_EVALUATION", "PROMOTION_NO_CANDIDATE_VALIDATED"],
)
def test_efficiency_is_not_applicable_before_candidate_viability(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> None:
    """Do not report call efficiency for inconclusive/no-candidate outcomes."""
    cases = _cases()
    rows = [_synthetic_row(case) for case in cases]
    monkeypatch.setattr(p7, "decision", lambda *args, **kwargs: label)
    summary = p7.summarize_population(rows, cases)
    assert summary["efficiency"]["RCV_vs_RCS"] == "NOT_APPLICABLE"


def test_provider_base_is_a_frozen_live_guard() -> None:
    """Require the provider request contract artifact in P7 provenance."""
    provenance = p7.frozen_provenance()
    assert provenance["provider_base_sha256"] == p7.EXPECTED_PROVIDER_BASE_SHA256
    assert len(provenance["provider_base_sha256"]) == 64


def test_prelive_report_is_provider_free(monkeypatch: pytest.MonkeyPatch) -> None:
    """Require the pre-live report to declare zero provider and worker calls."""
    _patch_historical_planner_hash(monkeypatch)
    report = p7.prelive_report()
    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["worker_program_calls"] == 0
    assert report["future_population"]["planner_executions"] == 192


def test_no_live_summary_or_provider_object_is_created_by_default() -> None:
    """Keep the provider-free checkpoint free of live evidence artifacts."""
    assert not (
        p7.REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P7-live-summary.json"
    ).exists()
    assert p7.SemanticPlan is not None


def test_prelive_does_not_construct_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provider construction outside the provider-free pre-live path."""
    _patch_historical_planner_hash(monkeypatch)
    monkeypatch.setattr(
        p7.p5,
        "_provider_configuration",
        lambda args: pytest.fail("provider construction occurred during pre-live checks"),
    )
    assert p7.prelive_report()["provider_calls"] == 0


def test_historical_planner_drift_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P7 rejects an incorrect historical planner hash."""
    _patch_historical_planner_hash(monkeypatch, "0" * 64)

    with pytest.raises(RuntimeError, match="CM-57P7 frozen artifact drifted"):
        p7.prelive_report()


def test_live_path_rejects_nonempty_output_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Protect the future population from append/resume behavior."""
    output = tmp_path / "evidence.jsonl"
    output.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(p7, "OUTPUT_PATH", output)
    monkeypatch.setattr(
        p7.p5,
        "_provider_configuration",
        lambda args: pytest.fail("provider construction occurred after output drift"),
    )
    args = Namespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="Refusing to append"):
        asyncio.run(p7._run_live(args, p7.BASELINE_SHA))
