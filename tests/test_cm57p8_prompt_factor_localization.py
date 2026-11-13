"""Deterministic CM-57P8 prompt-factor localization tests."""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel
from scripts import cm57p8_prompt_factor_localization as p8

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan, _PlannerWirePlan
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


@dataclass
class Backend:
    """Return one fixed plan and record forwarded provider requests."""

    plan: SemanticPlan = field(
        default_factory=lambda: SemanticPlan(
            summary="test",
            section_tasks=(SectionTask(goal="test section", capability_ids=("section.log_plot",)),),
        )
    )
    requests: list[StructuredGenerationRequest] = field(default_factory=list)
    response_models: list[type[BaseModel]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the fixed plan after recording the request."""
        self.requests.append(request)
        self.response_models.append(response_model)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.plan),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker execution."""
        raise AssertionError(f"Unexpected worker request: {request!r}")


def _synthetic_rows(
    reference_values: dict[str, bool],
    *,
    schema_values: dict[str, list[bool]] | None = None,
) -> list[dict[str, object]]:
    """Build bounded rows for localization decision tests."""
    rows = []
    for attempt in range(2):
        arms = {}
        for arm in p8.ARMS:
            plan_available = True
            if schema_values and arm in schema_values:
                plan_available = schema_values[arm][attempt]
            arms[arm] = {
                "final_plan_available": plan_available,
                "final_classification": "PLANNER_CONTRACT_OK"
                if plan_available
                else "PLANNER_SCHEMA_FAILURE",
                "reference": {
                    "expected_reference_required": False,
                    "final_plan_available": plan_available,
                    "actual_reference_present": reference_values.get(arm, False)
                    if plan_available
                    else None,
                    "unexpected_reference": reference_values.get(arm, False)
                    if plan_available
                    else None,
                    "missing_required_reference": False if plan_available else None,
                },
            }
        rows.append(
            {"case_id": p8.PROTECTED_REFERENCE_TARGET, "attempt_index": attempt, "arms": arms}
        )
    return rows


def _schema_rows(
    patterns: dict[str, tuple[bool, bool, bool]],
) -> list[dict[str, object]]:
    """Build two stable attempts for the schema localization targets."""
    rows = []
    for case_id in sorted(p8.SCHEMA_TARGETS):
        pattern = patterns[case_id]
        for attempt in range(2):
            available = {
                "P": False,
                "R": pattern[0],
                "C": pattern[1],
                "RC": pattern[2],
            }
            arms = {
                arm: {
                    "final_plan_available": available[arm],
                    "final_classification": "PLANNER_CONTRACT_OK"
                    if available[arm]
                    else "PLANNER_SCHEMA_FAILURE",
                    "reference": {
                        "expected_reference_required": True,
                        "final_plan_available": available[arm],
                        "actual_reference_present": None,
                        "unexpected_reference": None,
                        "missing_required_reference": None,
                    },
                }
                for arm in p8.ARMS
            }
            rows.append({"case_id": case_id, "attempt_index": attempt, "arms": arms})
    return rows


def _patch_historical_planner_hash(
    monkeypatch: pytest.MonkeyPatch,
    planner_hash: str | None = None,
) -> None:
    """Simulate only the planner bytes used by the closed P8 evaluation."""
    real_artifact_sha256 = p8.artifact_sha256
    planner_path = (p8.REPO_ROOT / "src/wellplot/agent/code_mode/planner.py").resolve()
    expected = planner_hash or p8.EXPECTED_PLANNER_SOURCE_SHA256

    def historical_artifact_sha256(path: Path) -> str:
        if Path(path).resolve() == planner_path:
            return expected
        return real_artifact_sha256(path)

    monkeypatch.setattr(p8, "artifact_sha256", historical_artifact_sha256)


def _decision_row(*, infrastructure_failure: bool = False, program_calls: int = 0) -> dict:
    """Build one minimal row for top-level decision tests."""
    return {
        "arms": {
            arm: {
                "provider_infrastructure_failure": infrastructure_failure,
                "program_call_count": program_calls,
            }
            for arm in p8.ARMS
        }
    }


def _patch_decision_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reference_classification: str,
    schema_classification: str,
    reference_reproduced: bool = True,
    schema_reproduced: bool = True,
    population_complete: bool = True,
    population_reasons: list[str] | None = None,
) -> None:
    """Patch only deterministic decision inputs for top-level label tests."""
    monkeypatch.setattr(
        p8,
        "population_integrity",
        lambda *args, **kwargs: (population_complete, population_reasons or []),
    )
    monkeypatch.setattr(
        p8,
        "historical_anchor_reproduction",
        lambda *args, **kwargs: {
            "all": {"checked": 0, "mismatches": [], "reproduced": True},
            "reference": {"checked": 0, "mismatches": [], "reproduced": reference_reproduced},
            "schema": {"checked": 0, "mismatches": [], "reproduced": schema_reproduced},
        },
    )
    monkeypatch.setattr(
        p8,
        "_reference_localization",
        lambda *args, **kwargs: {"classification": reference_classification},
    )
    monkeypatch.setattr(
        p8,
        "_schema_localization",
        lambda *args, **kwargs: {"classification": schema_classification},
    )


def test_manifest_resolves_exactly_twelve_p7_cases_without_request_text() -> None:
    """The manifest selects exposed P7 cases and does not duplicate prose."""
    payload = json.loads(p8.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 12
    assert all("request" not in case for case in payload["cases"])
    cases = p8.load_manifest()
    assert len(cases) == 12
    assert {case["case_id"] for case in cases} == {item["case_id"] for item in payload["cases"]}


def test_manifest_and_frozen_contract_hashes_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P7 corpus, raw evidence, prompts, schema, and production bytes are frozen."""
    _patch_historical_planner_hash(monkeypatch)
    contract = p8.verify_frozen_contract()
    assert contract["manifest_version"] == p8.MANIFEST_VERSION
    assert contract["p7_raw_sha256"] == p8.EXPECTED_P7_RAW_SHA256
    assert contract["production_schema_sha256"] == p8.EXPECTED_SCHEMA_SHA256
    assert contract["historical_anchor_derivation"] == "FROZEN_FROM_VERIFIED_P7_RAW"


def test_p7_raw_derivation_rejects_wrong_sha(tmp_path: Path) -> None:
    """Anchor derivation fails closed if the supplied P7 raw bytes drift."""
    raw = tmp_path / "p7.jsonl"
    raw.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exact verified P7 raw evidence SHA"):
        p8.derive_historical_anchors(raw)


def test_factor_prompts_change_only_the_frozen_system_suffix() -> None:
    """P/R/C/RC use the exact four frozen prompt compositions."""
    assert p8.composed_prompt("P") == p8._PLANNER_SYSTEM_PROMPT
    assert p8.composed_prompt("R") == (
        p8._PLANNER_SYSTEM_PROMPT + "\n" + p8.REPORT_BOUNDARY_INSTRUCTION
    )
    assert p8.composed_prompt("C") == (
        p8._PLANNER_SYSTEM_PROMPT + "\n" + p8.SECTION_COMPOSITION_INSTRUCTION
    )
    assert p8.composed_prompt("RC") == p8.p4.composed_prompt("RC")
    assert p8.PROMPT_SHA256 == {
        "P": p8.EXPECTED_BASE_PROMPT_SHA256,
        "R": p8.EXPECTED_R_PROMPT_SHA256,
        "C": p8.EXPECTED_C_PROMPT_SHA256,
        "RC": p8.EXPECTED_RC_PROMPT_SHA256,
    }


@pytest.mark.parametrize("arm", p8.ARMS)
def test_prompt_backend_preserves_non_system_request_fields(arm: p8.Arm) -> None:
    """Prompt substitution does not alter request payload or response model."""
    delegate = Backend()
    wrapper = p8.PromptFactorBackend(delegate=delegate, arm=arm)
    original = StructuredGenerationRequest(
        system_prompt=p8._PLANNER_SYSTEM_PROMPT,
        user_prompt="bounded request",
        timeout_seconds=5.0,
        temperature=0.0,
        max_output_tokens=100,
    )
    asyncio.run(wrapper.generate_structured(original, response_model=SemanticPlan))
    forwarded = delegate.requests[0]
    assert forwarded.user_prompt == original.user_prompt
    assert forwarded.timeout_seconds == original.timeout_seconds
    assert forwarded.temperature == original.temperature
    assert forwarded.max_output_tokens == original.max_output_tokens
    assert forwarded.system_prompt == p8.composed_prompt(arm)
    assert delegate.response_models == [SemanticPlan]


def test_p8_does_not_use_nonempty_report_or_invariant_schema() -> None:
    """Every factor uses the production SemanticPlan response model."""
    assert p8._schema_sha256() == p8.EXPECTED_SCHEMA_SHA256
    assert "NonEmptyReportSemanticPlan" not in p8.canonical_json(p8._frozen_provenance())
    assert "InvariantSemanticPlanner" not in p8.canonical_json(p8._frozen_provenance())


def test_reference_projection_is_unavailable_without_a_plan() -> None:
    """Terminal planner outcomes cannot manufacture semantic reference facts."""
    case = {"expected_sections": [["section.log_plot", "track.reference"]]}
    projection = p8._reference_projection(None, case)
    assert projection["expected_reference_required"] is True
    assert projection["final_plan_available"] is False
    assert projection["unexpected_reference"] is None
    assert projection["missing_required_reference"] is None


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ((False, True, True), "REFERENCE_SECTION_COMPOSITION_SUFFICIENT"),
        ((True, False, True), "REFERENCE_REPORT_BOUNDARY_SUFFICIENT"),
        ((False, False, True), "REFERENCE_RC_INTERACTION_REQUIRED"),
        ((True, True, True), "REFERENCE_MULTIPLE_FACTORS_SUFFICIENT"),
    ],
)
def test_reference_localization_classifies_all_stable_patterns(
    pattern: tuple[bool, bool, bool], expected: str
) -> None:
    """The protected target supports all four frozen reference labels."""
    rows = _synthetic_rows({"P": False, "R": pattern[0], "C": pattern[1], "RC": pattern[2]})
    result = p8._reference_localization(
        rows,
        (),
        {"reference": {"reproduced": True}},
    )
    assert result["classification"] == expected
    assert result["stable"] is True


def test_reference_localization_rejects_unstable_factor() -> None:
    """Attempt disagreement is not interpreted as a stable reference effect."""
    rows = _synthetic_rows({"P": False, "R": False, "C": True, "RC": True})
    rows[1]["arms"]["C"]["reference"]["unexpected_reference"] = False
    result = p8._reference_localization(
        rows,
        (),
        {"reference": {"reproduced": True}},
    )
    assert result["classification"] == "REFERENCE_FACTOR_UNSTABLE"


def test_reference_localization_is_inconclusive_when_its_anchors_drift() -> None:
    """Reference localization is gated only by its own historical anchors."""
    rows = _synthetic_rows({"P": False, "R": False, "C": True, "RC": True})
    result = p8._reference_localization(
        rows,
        (),
        {"reference": {"reproduced": False}},
    )
    assert result["classification"] == "INCONCLUSIVE_REFERENCE_LOCALIZATION"


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ((False, True, True), "SCHEMA_SECTION_COMPOSITION_SUFFICIENT"),
        ((True, False, True), "SCHEMA_REPORT_BOUNDARY_SUFFICIENT"),
        ((False, False, True), "SCHEMA_RC_INTERACTION_REQUIRED"),
        ((True, True, True), "SCHEMA_MULTIPLE_FACTORS_SUFFICIENT"),
    ],
)
def test_schema_localization_classifies_all_stable_patterns(
    pattern: tuple[bool, bool, bool], expected: str
) -> None:
    """The schema targets support all four frozen factor labels."""
    patterns = dict.fromkeys(p8.SCHEMA_TARGETS, pattern)
    result = p8._schema_localization(
        _schema_rows(patterns),
        {"schema": {"reproduced": True}},
    )
    assert result["classification"] == expected
    assert result["stable"] is True


def test_schema_localization_accepts_case_dependent_stabilization() -> None:
    """Different stable patterns are valid case-dependent evidence."""
    case_ids = sorted(p8.SCHEMA_TARGETS)
    patterns = {
        case_ids[0]: (False, True, True),
        case_ids[1]: (True, False, True),
    }
    result = p8._schema_localization(
        _schema_rows(patterns),
        {"schema": {"reproduced": True}},
    )
    assert result["classification"] == "SCHEMA_STABILIZATION_CASE_DEPENDENT"
    assert result["stable"] is True


def test_schema_localization_rejects_unstable_factor() -> None:
    """Attempt disagreement is not interpreted as stable schema evidence."""
    patterns = dict.fromkeys(p8.SCHEMA_TARGETS, (False, True, True))
    rows = _schema_rows(patterns)
    rows[1]["arms"]["C"]["final_plan_available"] = False
    result = p8._schema_localization(rows, {"schema": {"reproduced": True}})
    assert result["classification"] == "SCHEMA_FACTOR_UNSTABLE"
    assert result["stable"] is False


def test_schema_localization_is_inconclusive_when_its_anchors_drift() -> None:
    """Schema localization is gated only by its own historical anchors."""
    patterns = dict.fromkeys(p8.SCHEMA_TARGETS, (False, True, True))
    result = p8._schema_localization(
        _schema_rows(patterns),
        {"schema": {"reproduced": False}},
    )
    assert result["classification"] == "INCONCLUSIVE_SCHEMA_LOCALIZATION"


def test_positive_reference_controls_mark_missing_required_tracks() -> None:
    """Required reference selection is reported separately from over-selection."""
    row = {
        "case_id": "p7-depth-conductivity-06",
        "attempt_index": 0,
        "arms": {arm: {"reference": {"missing_required_reference": arm == "C"}} for arm in p8.ARMS},
    }
    controls = p8.positive_reference_controls([row])
    assert (
        controls["p7-depth-conductivity-06"]["C"]["reference_positive_control_regression"] is True
    )
    assert (
        controls["p7-depth-conductivity-06"]["P"]["reference_positive_control_regression"] is False
    )


def test_decision_accepts_case_dependent_schema_localization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case-dependent schema evidence remains interpretable and complete."""
    _patch_decision_inputs(
        monkeypatch,
        reference_classification="REFERENCE_MULTIPLE_FACTORS_SUFFICIENT",
        schema_classification="SCHEMA_STABILIZATION_CASE_DEPENDENT",
    )
    result = p8.decision([_decision_row()], ())
    assert result["decision"] == "PROMPT_FACTOR_LOCALIZATION_COMPLETE"


@pytest.mark.parametrize(
    ("reference_reproduced", "schema_reproduced", "expected"),
    [
        (False, True, "PROMPT_FACTOR_LOCALIZATION_PARTIAL"),
        (True, False, "PROMPT_FACTOR_LOCALIZATION_PARTIAL"),
    ],
)
def test_decision_allows_one_localized_axis_when_the_other_anchor_drifts(
    monkeypatch: pytest.MonkeyPatch,
    reference_reproduced: bool,
    schema_reproduced: bool,
    expected: str,
) -> None:
    """One valid mechanism axis is sufficient for a partial result."""
    reference_classification = (
        "REFERENCE_MULTIPLE_FACTORS_SUFFICIENT"
        if reference_reproduced
        else "INCONCLUSIVE_REFERENCE_LOCALIZATION"
    )
    schema_classification = (
        "SCHEMA_MULTIPLE_FACTORS_SUFFICIENT"
        if schema_reproduced
        else "INCONCLUSIVE_SCHEMA_LOCALIZATION"
    )
    _patch_decision_inputs(
        monkeypatch,
        reference_classification=reference_classification,
        schema_classification=schema_classification,
        reference_reproduced=reference_reproduced,
        schema_reproduced=schema_reproduced,
    )
    result = p8.decision([_decision_row()], ())
    assert result["decision"] == expected


@pytest.mark.parametrize(
    ("row", "population_complete", "expected"),
    [
        (
            _decision_row(),
            False,
            "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION",
        ),
        (
            _decision_row(infrastructure_failure=True),
            True,
            "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION",
        ),
        (
            _decision_row(program_calls=1),
            True,
            "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION",
        ),
    ],
)
def test_decision_fails_closed_for_population_infrastructure_or_worker_corruption(
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, object],
    population_complete: bool,
    expected: str,
) -> None:
    """Global integrity failures cannot yield a localization decision."""
    _patch_decision_inputs(
        monkeypatch,
        reference_classification="REFERENCE_MULTIPLE_FACTORS_SUFFICIENT",
        schema_classification="SCHEMA_MULTIPLE_FACTORS_SUFFICIENT",
        population_complete=population_complete,
        population_reasons=["synthetic_corruption"] if not population_complete else [],
    )
    result = p8.decision([row], ())
    assert result["decision"] == expected


def test_population_integrity_rejects_worker_program_calls() -> None:
    """The P8 population cannot contain worker/program execution."""
    case = p8.load_manifest()[0]
    row = {
        "case_id": case["case_id"],
        "attempt_index": 0,
        "arms": {
            arm: {
                "program_call_count": 1,
                "prompt_sha256": p8.PROMPT_SHA256[arm],
                "response_schema_sha256": p8.EXPECTED_SCHEMA_SHA256,
            }
            for arm in p8.ARMS
        },
    }
    complete, reasons = p8.population_integrity([row], (case,))
    assert complete is False
    assert "worker_program_call" in reasons


def test_live_rejects_nonempty_output_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pre-existing evidence file aborts before checkout/provider work."""
    output = tmp_path / "evidence.jsonl"
    output.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(p8, "OUTPUT_PATH", output)
    monkeypatch.setattr(
        p8,
        "_provider_configuration",
        lambda args: pytest.fail("provider constructed before output guard"),
    )
    args = SimpleNamespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="non-empty evidence path"):
        asyncio.run(p8._run_live(args, p8.BASELINE_SHA))


def test_live_rejects_checkout_drift_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reviewed-checkout failure aborts before provider construction."""
    monkeypatch.setattr(p8, "OUTPUT_PATH", tmp_path / "evidence.jsonl")
    monkeypatch.setattr(
        p8,
        "verify_reviewed_checkout",
        lambda checkpoint: (_ for _ in ()).throw(RuntimeError("synthetic checkout drift")),
    )
    monkeypatch.setattr(
        p8,
        "_provider_configuration",
        lambda args: pytest.fail("provider constructed before checkout guard"),
    )
    args = SimpleNamespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="synthetic checkout drift"):
        asyncio.run(p8._run_live(args, p8.BASELINE_SHA))


def test_terminal_schema_failure_is_not_infrastructure_failure() -> None:
    """Invalid structured output remains a studied schema outcome."""
    assert (
        p8._provider_classification(
            type("Error", (), {"category": p8.ProviderFailureCategory.INVALID_RESPONSE})()
        )
        == "PLANNER_SCHEMA_FAILURE"
    )


def test_population_and_decision_fail_closed_on_empty_or_wrong_checkpoint() -> None:
    """Incomplete populations cannot yield a localization decision."""
    cases = p8.load_manifest()
    complete, reasons = p8.population_integrity([], cases, expected_checkpoint=p8.BASELINE_SHA)
    assert complete is False
    assert "wrong_row_count" in reasons
    result = p8.decision([], cases, expected_checkpoint=p8.BASELINE_SHA)
    assert result["decision"] == "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION"


def test_prelive_report_constructs_no_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default CLI contract is provider-free and bounded."""
    _patch_historical_planner_hash(monkeypatch)
    report = p8.prelive_report()
    assert report["provider_calls"] == 0
    assert report["worker_program_calls"] == 0
    assert report["live_inference"] == "NOT_STARTED"
    assert report["shared_rows"] == 24


def test_historical_planner_drift_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P8 rejects an incorrect historical planner hash."""
    _patch_historical_planner_hash(monkeypatch, "0" * 64)

    with pytest.raises(RuntimeError, match="CM-57P8 frozen artifact drifted"):
        p8.prelive_report()


def test_p8_revision_preflight_qualifies_two_fresh_planner_processes() -> None:
    """Both committed planner blobs load canonically with the same wire schema."""
    report = p8.p8_revision_preflight()

    identities = report["isolated_arm_identity_processes"]
    assert report["provider_calls"] == 0
    assert report["holdout_access"] == "NOT_ACCESSED"
    assert identities["P-current"]["pid"] != identities["C1"]["pid"]
    assert identities["P-current"]["planner_module"] == "wellplot.agent.code_mode.planner"
    assert identities["C1"]["planner_module"] == "wellplot.agent.code_mode.planner"
    assert identities["P-current"]["planner_sha256"] == p8.P8_EXPECTED_PLANNER_SHA256["P-current"]
    assert identities["C1"]["planner_sha256"] == p8.P8_EXPECTED_PLANNER_SHA256["C1"]
    assert identities["P-current"]["wire_schema_sha256"] == identities["C1"]["wire_schema_sha256"]
    assert identities["P-current"]["prompt_sha256"] == p8.P8_EXPECTED_PROMPT_SHA256["P-current"]
    assert identities["C1"]["prompt_sha256"] == p8.P8_EXPECTED_PROMPT_SHA256["C1"]


def test_p8_b01_smoke_preflight_uses_approved_las_without_provider_calls() -> None:
    """The smoke case is B01, source-bound, and metadata-only before inference."""
    report = p8.p8_smoke_preflight()

    assert report["status"] == "P8_B01_SMOKE_PROVIDER_FREE_PREFLIGHT_PASS"
    assert report["case_id"] == "B01"
    assert report["request_sha256"] == p8.P8_SMOKE_REQUEST_SHA256
    assert report["source_asset_identity"]["sha256"] == (
        "7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9"
    )
    assert report["numeric_sample_apis_invoked"] is False
    assert report["provider_calls"] == 0
    assert report["model_calls"] == 0
    assert report["holdout_access"] == "NOT_ACCESSED"
    assert report["logical_invocations"] == 2
    assert report["physical_generation_cap_total"] == 4
    assert report["semantic_scoring"] == "NOT_PERFORMED"


def test_p8_smoke_trace_stops_only_after_schema_valid_wire() -> None:
    """The smoke stop sentinel is raised at production wire validation only."""
    trace: list[dict[str, object]] = []
    p8._capture_planner_trace(
        {"event": "PLANNER_GENERATION_ENTER", "attempt": 1},
        trace,
        stop_after_schema_valid_wire=True,
    )
    with pytest.raises(p8._P8SchemaValidWireCaptured):
        p8._capture_planner_trace(
            {
                "event": "PLANNER_GENERATION_PASS",
                "attempt": 1,
                "response_schema": "_PlannerWirePlan",
            },
            trace,
            stop_after_schema_valid_wire=True,
        )

    assert [event["event"] for event in trace] == [
        "PLANNER_GENERATION_ENTER",
        "PLANNER_GENERATION_PASS",
    ]
    assert trace[-1]["response_schema"] == "_PlannerWirePlan"


def test_p8_smoke_downstream_counter_contract_fails_closed() -> None:
    """A smoke result is valid only when every downstream count stays zero."""
    child = {
        "smoke": {
            "numeric_sample_apis_invoked": False,
            "downstream_stage_calls": dict.fromkeys(
                (
                    "report_worker",
                    "section_worker",
                    "reconciliation",
                    "execution",
                    "persistence",
                    "rendering",
                    "preview",
                    "scientific_grading",
                ),
                0,
            ),
        }
    }
    assert p8._p8_smoke_downstream_zero(child)
    child["smoke"]["downstream_stage_calls"]["persistence"] = 1
    assert not p8._p8_smoke_downstream_zero(child)


def test_p8_smoke_child_command_selects_one_arm_and_guards_internal_entry(
    tmp_path: Path,
) -> None:
    """The B01 child uses a fresh process and its own arm-scoped raw-I/O path."""
    raw_io = tmp_path / "B01" / "C1" / "model-io.jsonl"
    command, env = p8._p8_smoke_child_command("C1", raw_io)

    assert command[0] == p8.sys.executable
    assert command[1] == str(Path(p8.__file__).resolve())
    assert "--p8-smoke-child-b01" in command
    assert command[command.index("--p8-arm") + 1] == "C1"
    assert command[command.index("--p8-raw-io") + 1] == str(raw_io)
    assert env[p8.P8_REVISION_ARM_ENV] == "C1"
    assert env["WELLPLOT_P8_SMOKE_CHILD"] == "B01"


def test_p8_smoke_readiness_checks_exact_model_without_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness accepts the frozen model from both non-generative endpoints."""
    import httpx

    class FakeResponse:
        status_code = 200

        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = json.dumps(payload).encode()

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self) -> list[bytes]:
            return [self.payload]

    class FakeClient:
        def __init__(self, *, timeout: float, headers: dict[str, str]) -> None:
            assert timeout == 10.0
            assert headers == {"Authorization": "Bearer synthetic-secret"}

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def stream(self, method: str, url: str) -> FakeResponse:
            assert method == "GET"
            if url.endswith("/v1/models"):
                return FakeResponse({"data": [{"id": p8.FROZEN_MODEL, "object": "model"}]})
            return FakeResponse(
                {
                    "model_alias": p8.FROZEN_MODEL,
                    "default_generation_settings": {"n_ctx": 65536},
                    "total_slots": 1,
                    "is_sleeping": False,
                }
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = p8._p8_live_readiness(p8._p8_project_config(), "synthetic-secret")

    assert result["/v1/models"]["model_ids"] == [p8.FROZEN_MODEL]
    assert result["/props"]["model_alias"] == p8.FROZEN_MODEL
    assert result["/props"]["context_tokens"] == 65536


def test_p8_smoke_child_cannot_be_invoked_without_coordinator_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The internal B01 child CLI refuses direct invocation without its guard."""
    monkeypatch.delenv("WELLPLOT_P8_SMOKE_CHILD", raising=False)

    with pytest.raises(SystemExit, match="only be launched by its coordinator"):
        p8.main(
            [
                "--p8-smoke-child-b01",
                "--p8-arm",
                "C1",
                "--p8-raw-io",
                str(tmp_path / "model-io.jsonl"),
            ]
        )


def test_p8_raw_io_capture_enforces_record_and_file_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw provider bodies remain private and bounded per record and arm."""
    path = tmp_path / "private" / "model-io.jsonl"
    path.parent.mkdir(mode=0o700)
    monkeypatch.setattr(p8, "P8_RAW_IO_RECORD_LIMIT", 64)
    monkeypatch.setattr(p8, "P8_RAW_IO_FILE_LIMIT", 12)

    p8._append_private_json_line(path, {"ok": 1})
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(RuntimeError, match="artifact exceeds its private custody limit"):
        p8._append_private_json_line(path, {"ok": 2})

    monkeypatch.setattr(p8, "P8_RAW_IO_RECORD_LIMIT", 5)
    with pytest.raises(RuntimeError, match="record exceeds its private custody limit"):
        p8._append_private_json_line(path, {"long": "record"})


def test_p8_preflight_freezes_exact_12_by_2_pairs_without_holdout_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canary planning enumerates 24 unique pairs and never opens B01 holdout."""
    from scripts import a10_semantic_corpus_adapter as adapter

    read_fixtures: list[str] = []
    original = adapter._load_fixture

    def recording_load(root: Path, spec: adapter.CorpusSpec) -> list[dict[str, object]]:
        read_fixtures.append(spec.fixture)
        return original(root, spec)

    monkeypatch.setattr(adapter, "_load_fixture", recording_load)
    pairs = adapter.p8_pair_population(p8.REPO_ROOT)

    assert len(pairs) == 24
    assert len(set(pairs)) == 24
    assert len({case_id for case_id, _ in pairs}) == 12
    assert {arm for _, arm in pairs} == {"P-current", "C1"}
    assert adapter.HOLDOUT_FIXTURE not in read_fixtures


@pytest.mark.parametrize(
    ("logical_calls", "physical_calls", "valid"),
    [(0, 0, True), (2, 2, True), (3, 2, False), (1, 3, False)],
)
def test_p8_child_call_budget_is_fail_closed(
    logical_calls: int,
    physical_calls: int,
    valid: bool,
) -> None:
    """An arm allows one initial call and one native correction only."""
    child = {"call_count": logical_calls, "physical_attempt_count": physical_calls}
    if valid:
        p8._validate_p8_child_budget(child)
    else:
        with pytest.raises(RuntimeError, match="budget"):
            p8._validate_p8_child_budget(child)


def test_p8_arm_command_is_case_scoped_and_selects_revision_before_import(
    tmp_path: Path,
) -> None:
    """Each invocation is a new script process with one case/arm custody path."""
    custody = tmp_path / "case-a" / "C1" / "model-io.jsonl"

    command, env = p8._p8_child_command("case-a", "C1", custody)

    assert command[0] == p8.sys.executable
    assert command[1] == str(Path(p8.__file__).resolve())
    assert command[command.index("--p8-child-case") + 1] == "case-a"
    assert command[command.index("--p8-arm") + 1] == "C1"
    assert command[command.index("--p8-raw-io") + 1] == str(custody)
    assert env[p8.P8_REVISION_ARM_ENV] == "C1"
    assert "PromptFactorBackend" not in command


def test_retired_four_arm_live_route_cannot_construct_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The accepted two-arm comparison is the only exposed P8 live mode."""
    monkeypatch.setattr(
        p8,
        "_run_live",
        lambda *_args, **_kwargs: pytest.fail("retired four-arm live path was reached"),
    )

    with pytest.raises(SystemExit, match="prompt-factor live mode is retired"):
        p8.main(["--live-authorized", "--authorized-checkpoint", "0" * 40])


def test_p8_scorer_receives_only_completed_child_wire_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The historical scorer is invoked after a child result exists."""
    from scripts import a10_semantic_corpus_adapter as adapter

    case = adapter.load_corpus_index(p8.REPO_ROOT).canary_cases[0]
    child = {
        "wire_plan": {
            "version": "wellplot.semantic-plan.v2",
            "summary": "Synthetic P8 scoring fixture",
            "report_task": None,
            "section_tasks": [
                {
                    "goal": "Section",
                    "capability_ids": ["track.depth"],
                    "existing_section_hint": None,
                    "scope_ref": "section-a",
                    "operations": [
                        {
                            "local_ref": "section",
                            "scope_ref": "section-a",
                            "verb": "CREATE",
                            "object_kind": "section",
                            "semantic_ref": "section-object",
                        }
                    ],
                }
            ],
            "unresolved_requirements": [],
            "unresolved_semantics": [],
        },
        "terminal": {"kind": "success"},
        "raw_io_relative_path": "case/C1/model-io.jsonl",
    }
    seen: list[object] = []
    original = adapter.score_plan

    def record_score(received_case: object, plan: object) -> object:
        seen.append(plan)
        return original(received_case, plan)

    monkeypatch.setattr(adapter, "score_plan", record_score)
    p8._score_p8_child(case, child)

    assert len(seen) == 1
    assert seen[0].__class__.__name__ == "_PlannerWirePlan"


def test_p8_coordinator_runs_24_isolated_children_then_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every pair completes in its own child before downstream historical scoring."""
    from scripts import a10_semantic_corpus_adapter as adapter

    index = adapter.load_corpus_index(p8.REPO_ROOT)
    pairs = tuple((case.case_id, arm) for case in index.canary_cases for arm in ("P-current", "C1"))
    identity_reports = {
        arm: {
            "arm": arm,
            "revision": p8.P8_ARM_REVISIONS[arm],
            "planner_sha256": p8.P8_EXPECTED_PLANNER_SHA256[arm],
            "planner_module": "wellplot.agent.code_mode.planner",
            "module_origin": "test-frozen-origin",
            "wire_schema_sha256": p8.P8_EXPECTED_SCHEMA_SHA256,
            "prompt_sha256": p8.P8_EXPECTED_PROMPT_SHA256[arm],
            "pid": 1 if arm == "P-current" else 2,
        }
        for arm in ("P-current", "C1")
    }
    monkeypatch.setattr(p8, "_verify_p8_revision_arms", lambda: identity_reports)
    monkeypatch.setattr(adapter, "verify_planner_revision_closure", lambda _root: {"ok": True})
    monkeypatch.setattr(adapter, "load_corpus_index", lambda _root: index)
    monkeypatch.setattr(adapter, "p8_pair_population", lambda _root: pairs)
    monkeypatch.setattr(p8, "_p8_credential_available", lambda: True)
    config_fingerprint = p8._p8_project_config().fingerprint_sha256

    section_plan = {
        "version": "wellplot.semantic-plan.v2",
        "summary": "Synthetic paired score input",
        "report_task": None,
        "section_tasks": [
            {
                "goal": "Section",
                "capability_ids": ["track.depth"],
                "existing_section_hint": None,
                "scope_ref": "section-a",
                "operations": [
                    {
                        "local_ref": "section",
                        "scope_ref": "section-a",
                        "verb": "CREATE",
                        "object_kind": "section",
                        "semantic_ref": "section-object",
                    }
                ],
            }
        ],
        "unresolved_requirements": [],
        "unresolved_semantics": [],
    }
    wire_plan = _PlannerWirePlan.model_validate(section_plan).model_dump(mode="json")
    completed_pairs: set[tuple[str, str]] = set()
    score_events: list[str] = []
    process_counter = 100

    def fake_child(command: list[str], **_kwargs: object) -> SimpleNamespace:
        nonlocal process_counter
        case_id = command[command.index("--p8-child-case") + 1]
        arm = command[command.index("--p8-arm") + 1]
        raw_io_path = Path(command[command.index("--p8-raw-io") + 1])
        raw_io_path.write_text('{"event":"synthetic"}\n', encoding="utf-8")
        raw_io_path.chmod(0o600)
        process_counter += 1
        child = {
            "case_id": case_id,
            "arm": arm,
            "request_sha256": next(
                case.request_sha256 for case in index.canary_cases if case.case_id == case_id
            ),
            "planner_identity": {**identity_reports[arm], "pid": process_counter},
            "project_config_fingerprint_sha256": config_fingerprint,
            "call_count": 1,
            "physical_attempt_count": 1,
            "wire_plan": wire_plan,
            "wire_plans": [wire_plan],
            "terminal": {"kind": "success"},
            "raw_io_relative_path": str(raw_io_path.relative_to(p8.REPO_ROOT)),
        }
        completed_pairs.add((case_id, arm))
        return SimpleNamespace(returncode=0, stdout=json.dumps(child), stderr="")

    monkeypatch.setattr(p8.subprocess, "run", fake_child)
    monkeypatch.setattr(
        p8.subprocess,
        "check_output",
        lambda *_args, **_kwargs: str(p8.REPO_ROOT).encode(),
    )
    real_score = adapter.score_plan

    def assert_downstream_score(case: object, plan: object) -> object:
        assert any(case_id == case.case_id for case_id, _arm in completed_pairs)
        score_events.append(case.case_id)
        return real_score(case, plan)

    monkeypatch.setattr(adapter, "score_plan", assert_downstream_score)

    evaluation_parent = p8.REPO_ROOT / "workspace/evaluations" / f".p8-test-{uuid4().hex}"
    output_dir = evaluation_parent / "result"
    evaluation_parent.mkdir(mode=0o700)
    try:
        summary = p8._run_p8_revision_comparison(
            SimpleNamespace(
                p8_output_dir=str(output_dir),
            )
        )
        assert summary["population"] == {
            "cases": 12,
            "arms": ["P-current", "C1"],
            "planner_invocations": 24,
        }
        assert len(completed_pairs) == 24
        assert len(set(summary["case_child_pids"])) == 24
        assert len(score_events) == 48
        assert (output_dir / "SHA256SUMS").is_file()
        assert summary["holdout_access"] == "NOT_ACCESSED"
    finally:
        shutil.rmtree(evaluation_parent)
