"""Provider-free tests for A10's read-only historical corpus adapter."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from scripts import a10_semantic_corpus_adapter as adapter
from scripts import nlp_d5_live_semantic_qualification as live_qualification

from wellplot.agent.code_mode.planner import (
    UnresolvedSemantic,
    _PlannerWirePlan,
    _PlannerWireReportTask,
    _PlannerWireSectionTask,
)
from wellplot.capabilities.builtins import create_builtin_registry

REPO_ROOT = Path(__file__).resolve().parents[1]


def _case(case_id: str) -> adapter.AdaptedCase:
    index = adapter.load_corpus_index(REPO_ROOT)
    return next(case for case in index.cases if case.case_id == case_id)


def _section_plan(
    capabilities: tuple[str, ...],
    *,
    scope: str = "section-a",
    unresolved: tuple[UnresolvedSemantic, ...] = (),
) -> _PlannerWirePlan:
    return _PlannerWirePlan.model_validate(
        {
            "version": "wellplot.semantic-plan.v2",
            "summary": "Synthetic scorer fixture",
            "report_task": None,
            "section_tasks": [
                {
                    "goal": "Synthetic section",
                    "capability_ids": list(capabilities),
                    "existing_section_hint": None,
                    "scope_ref": scope,
                    "operations": [
                        {
                            "local_ref": "create-section",
                            "scope_ref": scope,
                            "verb": "CREATE",
                            "object_kind": "section",
                            "semantic_ref": "section-object",
                        }
                    ],
                }
            ],
            "unresolved_requirements": [],
            "unresolved_semantics": [item.model_dump(mode="json") for item in unresolved],
        }
    )


def test_index_preserves_all_historical_cases_and_joins_p8() -> None:
    """P8 role metadata resolves to its P7 source without copied requests."""
    index = adapter.load_corpus_index(REPO_ROOT)

    assert len(index.cases) == 96
    assert len({case.request.encode("utf-8") for case in index.cases}) == 96
    assert len(index.canary_cases) == 12
    assert len({case.case_id for case in index.canary_cases}) == 12
    assert all(
        case.source_fixture.endswith("cm57p7_fresh_promotion.json") for case in index.canary_cases
    )
    assert all(case.protected_role for case in index.canary_cases)
    assert all(
        case.source_blob_sha256 == adapter.CORPORA[1].blob_sha256 for case in index.canary_cases
    )
    p8_rows = json.loads((REPO_ROOT / adapter.P8_FIXTURE).read_text())["cases"]
    assert all("request" not in row for row in p8_rows)


def test_p8_join_fails_closed_for_missing_duplicate_and_hash_mismatch() -> None:
    """Missing P7 source, duplicate joins, and altered hashes are rejected."""
    p7 = {
        "known": {
            "case_id": "known",
            "family": "REPORT_ONLY",
            "request": "request",
            "expected_report_capabilities": ["report.standard"],
            "expected_sections": [],
            "expected_unresolved_count": 0,
        }
    }
    gold = {
        key: p7["known"][key]
        for key in (
            "family",
            "expected_report_capabilities",
            "expected_sections",
            "expected_unresolved_count",
        )
    }
    row = {
        "case_id": "known",
        "request_sha256": adapter._sha256(b"request"),
        "gold_sha256": adapter._canonical_json_sha256(gold),
        "role": "PROTECTED_REFERENCE_TARGET",
    }

    with pytest.raises(adapter.CorpusIntegrityError, match="no unique P7 source"):
        adapter._join_p8_rows({}, {"cases": [row]})
    with pytest.raises(adapter.CorpusIntegrityError, match="request hash mismatch"):
        adapter._join_p8_rows(p7, {"cases": [{**row, "request_sha256": "0" * 64}]})
    with pytest.raises(adapter.CorpusIntegrityError, match="duplicate P8"):
        adapter._join_p8_rows(p7, {"cases": [row, row]})


def test_b01_holdout_is_matched_by_exact_request_bytes() -> None:
    """The frozen holdout classification uses exact request bytes and digest."""
    result = adapter.audit_holdout_request(REPO_ROOT)

    assert result["match_count"] == 1
    assert result["matches"][0]["request_sha256"] == (
        "404a98eb0f9e40014aaf8312e53aea8a3267ea076963bff7420f1827196d7517"
    )
    assert result["disposition"] == "EXPOSED_DIAGNOSTIC_CASE"
    assert result["fresh_holdout_count"] == 52


@pytest.mark.parametrize(
    ("boundary", "detail", "historical"),
    [
        ("transport", "TRANSPORT", "PROVIDER_OR_STRUCTURED"),
        ("structured_decode", "STRUCTURED_DECODE", "PROVIDER_OR_STRUCTURED"),
        ("provider_schema", "PROVIDER_SCHEMA", "PROVIDER_OR_STRUCTURED"),
        ("pydantic_validation", "PYDANTIC_VALIDATION", "PLANNER_STRUCTURAL"),
        ("planner_semantic", "PLANNER_SEMANTIC", "SEMANTIC"),
        ("host_resolution", "HOST_RESOLUTION", "TARGET_GROUNDING"),
        ("host_safety", "HOST_SAFETY", "HOST_SAFETY"),
        (None, "NO_DIVERGENCE", "NONE"),
    ],
)
def test_first_divergence_uses_earliest_observed_stage(
    boundary: str | None, detail: str, historical: str
) -> None:
    """Observed stage failures map to the existing D5 taxonomy in order."""
    boundaries = {
        name: ("FAIL" if name == boundary else "PASS")
        for name in (
            "transport",
            "structured_decode",
            "provider_schema",
            "pydantic_validation",
            "planner_semantic",
            "host_resolution",
            "host_safety",
        )
    }

    assert adapter.classify_first_divergence(boundaries) == (detail, historical)


def test_first_divergence_does_not_report_downstream_failures() -> None:
    """The earliest failed boundary wins over later failed stages."""
    assert adapter.classify_first_divergence(
        {
            "transport": "PASS",
            "structured_decode": "PASS",
            "provider_schema": "FAIL",
            "pydantic_validation": "FAIL",
            "planner_semantic": "FAIL",
            "host_resolution": "FAIL",
            "host_safety": "FAIL",
        }
    ) == ("PROVIDER_SCHEMA", "PROVIDER_OR_STRUCTURED")


def test_historical_gold_capabilities_still_exist_in_builtin_registry() -> None:
    """Every historical capability expectation remains in the production registry."""
    index = adapter.load_corpus_index(REPO_ROOT)
    expected = {
        capability
        for case in index.cases
        for capability in (
            *case.expected_report_capabilities,
            *(item for section in case.expected_sections for item in section),
        )
    }
    registry = create_builtin_registry()

    assert expected == {
        "annotation.typed",
        "binding.curve",
        "binding.raster",
        "report.standard",
        "section.log_plot",
        "track.annotation",
        "track.array",
        "track.normal",
        "track.reference",
    }
    assert all(registry.contains(capability) for capability in expected)


def test_known_valid_historical_semantics_score_pass_without_inventing_ops() -> None:
    """A hand-authored valid current plan passes only frozen semantic dimensions."""
    case = _case("p7-lone-porosity-05")
    plan = _section_plan(case.expected_sections[0])

    result = adapter.score_plan(case, plan)

    assert result.passed
    assert result.disposition == "PLANNER_PLAN"
    assert result.operation_observations[0].object_kind == "section"
    assert result.operation_observations[0].verb == "CREATE"
    assert result.operation_target_comparison == "UNSCORABLE_NO_HISTORICAL_OPERATION_GOLD"
    assert result.source_identity_comparison == "UNSCORABLE_NO_HISTORICAL_SOURCE_GOLD"


def test_report_presence_regression_is_detected() -> None:
    """An extra section in place of required report work fails scoring."""
    case = _case("p7-dossier-brief-01")
    plan = _section_plan(("section.log_plot", "track.normal", "binding.curve"))

    result = adapter.score_plan(case, plan)

    assert not result.passed
    assert "report_work_ownership_mismatch" in result.findings


def test_section_count_regression_is_detected() -> None:
    """A plan with too few sections fails the historical section-count invariant."""
    case = _case("p7-acoustic-comparison-19")
    plan = _section_plan(("section.log_plot", "track.normal", "binding.curve"))

    result = adapter.score_plan(case, plan)

    assert not result.passed
    assert "section_count_mismatch" in result.findings


@pytest.mark.parametrize(
    ("capabilities", "expected_finding"),
    [
        (("section.log_plot", "track.normal"), "section_capability_set_mismatch"),
        (
            ("section.log_plot", "track.normal", "binding.curve", "track.array"),
            "section_capability_set_mismatch",
        ),
    ],
)
def test_missing_and_extra_capabilities_are_detected(
    capabilities: tuple[str, ...],
    expected_finding: str,
) -> None:
    """Missing and invented capability IDs both fail the capability-set check."""
    case = _case("p7-lone-porosity-05")
    result = adapter.score_plan(case, _section_plan(capabilities))

    assert not result.passed
    assert expected_finding in result.findings


def test_wrong_report_section_ownership_is_detected() -> None:
    """Unexpected report work on a section-only case is rejected."""
    case = _case("p7-lone-porosity-05")
    section_plan = _section_plan(case.expected_sections[0])
    report = _PlannerWireReportTask.model_validate(
        {
            "goal": "Unexpected report work",
            "operations": [
                {
                    "local_ref": "report-title",
                    "scope_ref": "report",
                    "verb": "CREATE",
                    "object_kind": "report_field",
                    "semantic_ref": "title",
                }
            ],
        }
    )
    plan = section_plan.model_copy(update={"report_task": report})

    result = adapter.score_plan(case, plan)

    assert not result.passed
    assert "report_work_ownership_mismatch" in result.findings


def test_safe_unresolved_and_planner_terminal_failure_are_distinct() -> None:
    """Expected unresolved semantics remain distinct from planner failure."""
    base_case = _case("p7-lone-porosity-05")
    case = replace(base_case, expected_unresolved_count=1)
    unresolved = UnresolvedSemantic(
        local_ref="ambiguity-1",
        scope_ref="section-a",
        question="Which candidate should be used?",
        candidate_clues=("candidate A", "candidate B"),
    )

    safe_plan = _section_plan(case.expected_sections[0], unresolved=(unresolved,))
    safe = adapter.score_plan(case, safe_plan)
    terminal = adapter.score_plan(case, None)

    assert safe.passed
    assert safe.disposition == "UNRESOLVED_SAFE"
    assert not terminal.passed
    assert terminal.disposition == "PLANNER_TERMINAL_FAILURE"


def test_operation_scope_mismatch_is_detected_even_for_constructed_wire_plan() -> None:
    """The scorer independently checks ownership even for constructed DTOs."""
    case = _case("p7-lone-porosity-05")
    task = _PlannerWireSectionTask.model_validate(
        {
            "goal": "Synthetic section",
            "capability_ids": list(case.expected_sections[0]),
            "existing_section_hint": None,
            "scope_ref": "section-a",
            "operations": [
                {
                    "local_ref": "section-create",
                    "scope_ref": "section-b",
                    "verb": "CREATE",
                    "object_kind": "section",
                    "semantic_ref": "section-object",
                }
            ],
        }
    )
    invalid = _PlannerWirePlan.model_construct(
        version="wellplot.semantic-plan.v2",
        summary="Constructed to exercise scorer boundary",
        report_task=None,
        section_tasks=(task,),
        unresolved_requirements=(),
        unresolved_semantics=(),
    )

    result = adapter.score_plan(case, invalid)

    assert not result.passed
    assert "section_operation_scope_mismatch" in result.findings


def test_schema_probe_pairs_isolate_the_five_targeted_keywords() -> None:
    """Each requested synthetic object violates its constrained schema only."""
    probes = live_qualification._schema_behavior_probes()

    assert [probe.feature for probe in probes] == [
        "minItems",
        "pattern",
        "root_anyOf",
        "root_allOf",
        "not",
    ]
    for probe in probes:
        constrained = probe.constrained_model.model_json_schema()
        control = probe.control_model.model_json_schema()
        value = dict(probe.prompt_value)

        assert list(Draft202012Validator(constrained).iter_errors(value))
        assert not list(Draft202012Validator(control).iter_errors(value))


@pytest.mark.parametrize(
    ("constrained_value", "expected"),
    [
        ({"items": []}, "NOT_ENFORCED_BY_DEPLOYED_DECODER"),
        ({"items": [1]}, "ENFORCED_BY_DEPLOYED_DECODER"),
    ],
)
def test_schema_probe_classification_uses_matching_control(
    constrained_value: dict[str, object], expected: str
) -> None:
    """A matching control distinguishes decoder enforcement from compliance."""
    probe = live_qualification._schema_behavior_probes()[0]
    observation = live_qualification._classify_schema_probe_pair(
        probe,
        constrained_content=json.dumps(constrained_value),
        constrained_http_status=200,
        control_content=json.dumps(dict(probe.prompt_value)),
        control_http_status=200,
    )

    assert observation.classification == expected
    assert observation.control_matches_request


def test_schema_probe_classifies_rejection_and_inconclusive_separately() -> None:
    """Schema rejection and a failed behavioral control are distinct outcomes."""
    probe = live_qualification._schema_behavior_probes()[1]
    rejected = live_qualification._classify_schema_probe_pair(
        probe,
        constrained_content=None,
        constrained_http_status=422,
        control_content=None,
        control_http_status=None,
    )
    inconclusive = live_qualification._classify_schema_probe_pair(
        probe,
        constrained_content=json.dumps({"code": "A7"}),
        constrained_http_status=200,
        control_content=json.dumps({"code": "A7"}),
        control_http_status=200,
    )

    assert rejected.classification == "BACKEND_REJECTS_SCHEMA"
    assert inconclusive.classification == "INCONCLUSIVE_MODEL_BEHAVIOR"


def test_schema_probe_local_validation_records_json_schema_and_pydantic() -> None:
    """The exact constrained response is checked against both local contracts."""
    probe = live_qualification._schema_behavior_probes()[0]
    payload, errors, pydantic_valid = live_qualification._schema_probe_local_validation(
        '{"items": []}', probe.constrained_model
    )

    assert payload == {"items": []}
    assert errors == ("items:minItems",)
    assert pydantic_valid


def test_schema_probe_call_ledger_caps_physical_calls_at_ten() -> None:
    """The existing smoke ledger permits ten single-attempt probe calls only."""
    ledger = live_qualification.D5SmokeCallLedger(mode=live_qualification.SMOKE_SCHEMA_PROBE_KIND)

    for expected_index in range(1, 11):
        index = ledger.reserve()
        assert index == expected_index
        assert ledger.physical_attempt(index) == 1

    assert ledger.logical_calls == 10
    assert ledger.physical_attempts == 10
    with pytest.raises(live_qualification.D5CallCapExceeded):
        ledger.reserve()
