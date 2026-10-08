"""Provider-free tests for the D4 live-acceptance harness."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml
from pydantic import BaseModel
from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent.code_mode.enrichment import SemanticEnricher
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler
from wellplot.agent.code_mode.report_worker import ReportProgramCompiler
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.direct_notebook import DirectNotebookSession
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.agent.session import AgentSession, AgentSessionConfig
from wellplot.authoring import (
    _fill_element,
    authoring_document_to_logfile_mapping,
    load_authoring_document,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


class _Value(BaseModel):
    value: str = "ok"


class _Backend:
    """Provider-free backend that records delegation without raw payloads."""

    def __init__(self, *, program_text: str = "report = wp.report()") -> None:
        self.calls = 0
        self.program_text = program_text

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[_Value],
    ) -> StructuredGenerationResult[_Value]:
        del request, response_model
        self.calls += 1
        return StructuredGenerationResult(
            value=_Value(),
            metrics=ProviderMetrics(input_tokens=2, output_tokens=3, total_tokens=5),
        )

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        del request
        self.calls += 1
        return ProgramGenerationResult(
            text=self.program_text,
            metrics=ProviderMetrics(input_tokens=2, output_tokens=3, total_tokens=5),
        )


def _structured_request() -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        system_prompt="system",
        user_prompt="user",
        timeout_seconds=120.0,
        temperature=0.0,
        max_output_tokens=None,
    )


def _program_request() -> ProgramGenerationRequest:
    return ProgramGenerationRequest(
        system_prompt="system",
        user_prompt="user",
        timeout_seconds=120.0,
        temperature=None,
        max_output_tokens=None,
    )


def _authorization() -> d4.FrozenAuthorization:
    """Build an external-style authorization from the checked-out test fixture."""
    return d4.FrozenAuthorization(
        accepted_checkpoint=d4._git(REPO_ROOT, "rev-parse", "HEAD"),
        harness_source_sha256=d4.sha256_file(REPO_ROOT / d4.HARNESS_SOURCE_PATH),
        cases_fixture_sha256=d4.sha256_file(REPO_ROOT / d4.CASES_PATH),
        gold_fixture_sha256=d4.sha256_file(REPO_ROOT / d4.GOLD_PATH),
        uv_lock_sha256=d4.sha256_file(REPO_ROOT / d4.UV_LOCK_PATH),
        production_component_sha256=dict(d4.FROZEN_PRODUCTION_COMPONENT_SHA256),
        source_sha256={
            d4.SOURCE_RELATIVE.as_posix(): d4.SOURCE_SHA256,
            "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis": (
                "3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7"
            ),
            "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis": (
                "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640"
            ),
        },
    )


def _put(document: dict[str, object], path: str, value: object) -> None:
    """Set a JSON-pointer-like value in a synthetic canonical artifact."""
    parts = path.strip("/").split("/") if path.strip("/") else []
    current: object = document
    for index, part in enumerate(parts):
        part = part.replace("~1", "/").replace("~0", "~")
        last = index == len(parts) - 1
        if isinstance(current, dict):
            if last:
                current[part] = value
                return
            next_part = parts[index + 1]
            if part not in current:
                current[part] = [] if next_part.isdigit() else {}
            current = current[part]
        elif isinstance(current, list):
            position = int(part)
            while len(current) <= position:
                current.append({} if not last else None)
            if last:
                current[position] = value
                return
            if current[position] is None:
                current[position] = [] if parts[index + 1].isdigit() else {}
            current = current[position]
        else:
            raise AssertionError(f"cannot set {path}: {current!r}")


def _synthetic_artifact(assertions: list[Mapping[str, object]]) -> dict[str, object]:
    """Materialize just enough canonical structure for a gold assertion set."""
    document: dict[str, object] = {}
    for assertion in assertions:
        path = str(assertion["path"])
        if assertion.get("operator") in {"length", "length_at_least"}:
            _put(document, path, [{} for _ in range(int(assertion["value"]))])
        else:
            _put(document, path, assertion.get("value"))
    return document


def _verifier(required_ids: list[str], *, cbl: bool = False) -> dict[str, object]:
    """Create deterministic fake verifier evidence with explicit requirement status."""
    return {
        "acceptance_status" if cbl else "status": "PASS",
        "requirements": [{"id": item, "status": "PASS"} for item in required_ids],
    }


def test_population_hashes_and_canonical_seed_are_frozen() -> None:
    """Require the exact nine-turn schedule and canonical seed."""
    cases = d4.load_cases(REPO_ROOT)
    gold = d4.load_gold(REPO_ROOT)
    assert len(cases) == 9
    assert gold["canonical_las_seed"]["name"] == "D4 LAS Acceptance Seed"
    assert [case["turn_id"] for case in cases] == [
        "D4-C01:C01",
        "D4-L01:T1",
        "D4-L01:T2",
        "D4-L01:T3",
        "D4-L01:T4",
        "D4-L02:T1",
        "D4-L02:T2",
        "D4-L03:C01",
        "D4-L04:C01",
    ]
    assert all(case["request_sha256"] == d4.sha256_text(case["request"]) for case in cases)
    assert all(
        isinstance(case.get("contract"), dict)
        and case["contract"].get("kind") in {"cbl", "las", "safety"}
        for case in gold["cases"]
    )
    assert [case["contract"]["kind"] for case in gold["cases"]] == [
        "cbl",
        "las",
        "las",
        "las",
        "las",
        "safety",
        "las",
        "safety",
        "safety",
    ]


def test_d4_requests_are_not_the_d3_request() -> None:
    """Reject reuse of the accepted D3 request text."""
    cases = d4.load_cases(REPO_ROOT)
    d3_request = (REPO_ROOT / "tests/fixtures/agentic_cbl/frozen_prompt.txt").read_text()
    d3_request = d3_request.replace(
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis",
        "CBL_Main.dlis",
    ).replace(
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis",
        "CBL_Repeat.dlis",
    )
    d3_hash = d4.sha256_text(d3_request)
    assert all(case["request_sha256"] != d3_hash for case in cases)


def test_unseen_guard_rejects_every_known_d1_d3_request() -> None:
    """The guard covers the accepted request family, not only the D3 request."""
    cases = d4.load_cases(REPO_ROOT)
    known = next(iter(d4.accepted_d1_d3_request_hashes(REPO_ROOT)))
    reused = [dict(cases[0], request_sha256=known)]
    with pytest.raises(d4.PreflightError, match="accepted D1-D3"):
        d4.assert_unseen_requests(REPO_ROOT, reused)


def test_frozen_contract_attestation_binds_checkpoint_and_all_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A correct external authorization passes before campaign state creation."""
    authorization = _authorization()
    real_git = d4._git
    monkeypatch.setattr(
        d4,
        "_git",
        lambda repo, *args: "" if args == ("status", "--porcelain") else real_git(repo, *args),
    )
    observed = d4.verify_frozen_contract(REPO_ROOT, authorization)
    assert observed["accepted_checkpoint"] == authorization.accepted_checkpoint
    assert observed["cases_fixture_sha256"] == authorization.cases_fixture_sha256
    assert observed["gold_fixture_sha256"] == authorization.gold_fixture_sha256
    assert set(observed["production_component_sha256"]) == set(d4.PRODUCTION_COMPONENT_PATHS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accepted_checkpoint", "0" * 40),
        ("harness_source_sha256", "0" * 64),
        ("cases_fixture_sha256", "0" * 64),
        ("gold_fixture_sha256", "0" * 64),
        ("uv_lock_sha256", "0" * 64),
    ],
)
def test_frozen_contract_attestation_rejects_identity_drift(
    field: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checkpoint and every top-level artifact identity fail closed."""
    authorization = _authorization()
    values = replace(authorization, **{field: value})
    with pytest.raises(d4.PreflightError):
        d4.verify_frozen_contract(REPO_ROOT, values)


def test_frozen_contract_attestation_rejects_component_manifest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single production component mismatch blocks before provider construction."""
    authorization = _authorization()
    real_git = d4._git
    monkeypatch.setattr(
        d4,
        "_git",
        lambda repo, *args: "" if args == ("status", "--porcelain") else real_git(repo, *args),
    )
    components = dict(authorization.production_component_sha256)
    components["src/wellplot/agent/code_mode/planner.py"] = "0" * 64
    drifted = replace(authorization, production_component_sha256=components)
    with pytest.raises(d4.PreflightError, match="component"):
        d4.verify_frozen_contract(REPO_ROOT, drifted)


@pytest.mark.parametrize(
    "field",
    ["provider", "model", "openai_version", "sdk_max_retries"],
)
def test_frozen_contract_attestation_rejects_runtime_configuration_drift(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider/model and SDK controls are authorization inputs, not defaults."""
    authorization = _authorization()
    values: dict[str, object] = {
        "provider": "other" if field == "provider" else authorization.provider,
        "model": "other" if field == "model" else authorization.model,
        "openai_version": "0.0.0" if field == "openai_version" else authorization.openai_version,
        "sdk_max_retries": 99 if field == "sdk_max_retries" else authorization.sdk_max_retries,
    }
    real_git = d4._git
    monkeypatch.setattr(
        d4,
        "_git",
        lambda repo, *args: "" if args == ("status", "--porcelain") else real_git(repo, *args),
    )
    with pytest.raises(d4.PreflightError, match="drifted"):
        d4.verify_frozen_contract(REPO_ROOT, replace(authorization, **values))


def test_source_preflight_authenticates_real_las() -> None:
    """Authenticate the external LAS source when it is available locally."""
    try:
        result = d4.preflight_las_source(REPO_ROOT)
    except d4.PreflightError as error:
        pytest.skip(str(error))
    assert result.size == d4.SOURCE_SIZE
    assert result.sha256 == d4.SOURCE_SHA256
    assert result.required_channels_present is True
    assert result.forbidden_channels_absent is True
    assert {"GR", "CALI", "ILD", "ILM", "MSFL", "NPHI"}.issubset(result.channel_inventory)
    assert "RT" not in result.channel_inventory


def test_openai_retry_policy_is_provider_free() -> None:
    """Inspect the SDK retry contract without constructing a client."""
    evidence = d4.inspect_openai_retry_policy()
    assert evidence["version"] == "2.34.0"
    assert evidence["max_retries"] == 2
    assert evidence["physical_http_attempt_upper_bound"] == 135


def test_counting_backend_preserves_controls_and_records_bounded_metadata() -> None:
    """Record logical calls without retaining provider payloads."""
    delegate = _Backend()
    backend = d4.CountingBackend(delegate=delegate)

    async def run() -> None:
        await backend.generate_structured(_structured_request(), response_model=_Value)
        await backend.generate_program(_program_request())

    asyncio.run(run())
    assert delegate.calls == 2
    assert [call.operation for call in backend.calls] == ["structured", "program"]
    assert backend.calls[0].metrics == {
        "input_tokens": 2,
        "output_tokens": 3,
        "total_tokens": 5,
        "latency_ms": None,
    }
    assert not hasattr(backend.calls[0], "raw_provider_response")
    assert not hasattr(backend.calls[1], "raw_generated_program")


def test_call_46_is_rejected_before_delegation() -> None:
    """Reject the first call beyond the frozen logical-call ceiling."""
    delegate = _Backend()
    backend = d4.CountingBackend(delegate=delegate)

    async def run() -> None:
        for _ in range(d4.MAX_LOGICAL_CALLS):
            await backend.generate_structured(_structured_request(), response_model=_Value)
        with pytest.raises(d4.CallCapExceeded):
            await backend.generate_structured(_structured_request(), response_model=_Value)

    asyncio.run(run())
    assert delegate.calls == d4.MAX_LOGICAL_CALLS
    assert len(backend.calls) == d4.MAX_LOGICAL_CALLS


def test_campaign_state_is_durable_before_credentials() -> None:
    """Write STARTED state before invoking credential construction."""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        state_path = directory / "state.json"
        journal_path = directory / "journal.jsonl"
        events: list[str] = []

        def preflight() -> dict[str, str]:
            events.append("preflight")
            return {"current_checkout": "a" * 40}

        def credentials() -> object:
            events.append("credentials")
            assert state_path.is_file()
            return object()

        state, _ = d4.start_campaign(
            state_path=state_path,
            journal_path=journal_path,
            preflight=preflight,
            credential_factory=credentials,
        )
        assert events == ["preflight", "credentials"]
        assert state["status"] == "STARTED"
        assert json.loads(state_path.read_text())["status"] == "STARTED"


def test_campaign_custody_persists_calls_and_writes_bounded_jsonl() -> None:
    """Logical call count and journal evidence survive each call boundary."""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        state_path = directory / "state.json"
        journal_path = directory / "journal.jsonl"
        state, _ = d4.start_campaign(
            state_path=state_path,
            journal_path=journal_path,
            preflight=lambda: {"current_checkout": "a" * 40},
            credential_factory=lambda: object(),
        )
        custody = d4.CampaignCustody(
            state_path=state_path,
            journal=d4.CampaignJournal(journal_path),
            state=state,
        )
        backend = d4.CountingBackend(delegate=_Backend(), call_started=custody.record_call_started)

        async def run() -> None:
            await backend.generate_structured(_structured_request(), response_model=_Value)

        asyncio.run(run())
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted["logical_generation_calls"] == 1
        events = [json.loads(line) for line in journal_path.read_text().splitlines()]
        assert events[0]["event"] == "logical_call_started"
        assert events[0]["logical_generation_calls"] == 1
        assert "raw_structured_payload" not in events[0]
        custody.journal.close()


def test_campaign_journal_rejects_raw_generation_material_and_duplicate_creation() -> None:
    """The journal is exclusive and cannot persist provider/program payloads."""
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "journal.jsonl"
        journal = d4.CampaignJournal(path)
        with pytest.raises(d4.PreflightError, match="secret or raw"):
            journal.append({"raw_generated_program": "wp.report()"})
        journal.append({"event": "safe", "result_status": "PASS"})
        journal.close()
        with pytest.raises(d4.PreflightError, match="already exists"):
            d4.CampaignJournal(path).append({"event": "resume"})


def test_existing_campaign_artifacts_block_resume() -> None:
    """Reject both empty and non-empty previous campaign artifacts."""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        state_path = directory / "state.json"
        journal_path = directory / "journal.jsonl"
        state_path.write_text("", encoding="utf-8")
        with pytest.raises(d4.PreflightError, match="already exist"):
            d4.start_campaign(
                state_path=state_path,
                journal_path=journal_path,
                preflight=lambda: {"current_checkout": "a" * 40},
                credential_factory=lambda: pytest.fail("credentials accessed"),
            )


def test_evidence_redaction_rejects_secrets_and_raw_material() -> None:
    """Reject credentials and raw generation content in evidence."""
    assert d4.evidence_is_redacted({"case_id": "D4-L01", "metrics": {"total": 3}})
    assert not d4.evidence_is_redacted({"api_key": "secret"})
    assert not d4.evidence_is_redacted({"text": "Authorization: Bearer secret"})
    assert not d4.evidence_is_redacted({"raw_generated_program": "report = wp.report()"})


def test_provider_prompt_cannot_contain_evaluator_gold() -> None:
    """Gold contracts remain harness-owned and cannot enter provider context."""
    gold = d4.load_gold(REPO_ROOT)
    d4.assert_provider_prompt_excludes_gold("normal scientist context", gold)
    with pytest.raises(d4.PreflightError, match="gold"):
        d4.assert_provider_prompt_excludes_gold(d4.canonical_json(gold), gold)
    with pytest.raises(d4.PreflightError, match="evaluator"):
        d4.assert_provider_prompt_excludes_gold('{"expected_outcome":"DIRECT_CORRECT"}', gold)


def test_scientific_graders_cover_each_positive_case_contract() -> None:
    """Fake canonical artifacts exercise the CBL and all positive LAS contracts."""
    gold = d4.load_gold(REPO_ROOT)
    for expected in gold["cases"]:
        if expected["expected_outcome"] not in {"DIRECT_CORRECT", "CORRECT_AFTER_CLARIFICATION"}:
            continue
        contract = expected["contract"]
        before = _synthetic_artifact(contract.get("before_assertions", []))
        after = _synthetic_artifact(contract.get("after_assertions", []))
        if expected["turn_id"] == "D4-L02:T2":
            before = copy.deepcopy(after)
            _put(before, "/sections/0/tracks/1/bindings/0/scale/minimum", 0.0)
            _put(before, "/sections/0/tracks/1/bindings/0/scale/maximum", 100.0)
        required_ids = contract["required_verifier_requirements"]
        actual = {
            "outcome": expected["expected_outcome"],
            "canonical_before": before,
            "canonical_after": after,
            "persisted": True,
            "rendered": True,
            "verifier": _verifier(required_ids, cbl=expected["grader"] == "cbl"),
        }
        assert d4.grade_turn(actual, expected)["status"] == "PASS", expected["turn_id"]


def test_negative_scientific_graders_require_identity_and_reject_substitution() -> None:
    """Safe failures require byte/canonical identity and reject channel fallback."""
    gold = d4.load_gold(REPO_ROOT)
    for turn_id in ("D4-L02:T1", "D4-L03:C01", "D4-L04:C01"):
        expected = next(item for item in gold["cases"] if item["turn_id"] == turn_id)
        actual = {
            "outcome": expected["expected_outcome"],
            "changed": False,
            "pre_bytes_sha256": "same",
            "post_bytes_sha256": "same",
            "canonical_before": {"title": "same"},
            "canonical_after": {"title": "same"},
            "diagnostic_code": "safe.rejection",
            "intent_applied": False,
            "persisted": False,
            "rendered": False,
            "fallback_used": False,
            "substituted_channel": False,
            "prohibited_object_present": False,
            "created_channels": [],
        }
        assert d4.grade_turn(actual, expected)["status"] == "PASS", turn_id
        if turn_id == "D4-L04:C01":
            unsafe = {**actual, "created_channels": ["ILD"]}
            assert d4.grade_turn(unsafe, expected)["status"] == "FAIL"


def test_grader_does_not_mutate_acceptance_artifacts() -> None:
    """Grading is observational and leaves the supplied canonical artifacts intact."""
    expected = next(
        item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == "D4-L01:T1"
    )
    actual = {
        "outcome": "DIRECT_CORRECT",
        "canonical_before": {"title": "Original Well Log Report"},
        "canonical_after": {"title": "Formation Integrity Review"},
        "persisted": True,
        "rendered": True,
        "verifier": _verifier(expected["contract"]["required_verifier_requirements"]),
    }
    snapshot = copy.deepcopy(actual)
    d4.grade_turn(actual, expected)
    assert actual == snapshot


def test_terminal_decision_precedence_is_frozen() -> None:
    """Keep incomplete infrastructure separate from semantic failure."""
    passed = [{"grader_status": "PASS"} for _ in range(9)]
    assert d4.derive_terminal_decision(passed) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED"
    failed = [*passed[:-1], {"grader_status": "FAIL"}]
    assert d4.derive_terminal_decision(failed) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_FAILED"
    incomplete = passed[:-1]
    assert d4.derive_terminal_decision(incomplete) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"
    infra = [*passed[:-1], {"grader_status": "PASS", "infrastructure_failure": True}]
    assert d4.derive_terminal_decision(infra) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"


def test_turn_grader_requires_zero_mutation_for_safe_failures() -> None:
    """Require byte identity and actionable diagnostics for safe failure."""
    expected = {
        "turn_id": "D4-L03:C01",
        "expected_outcome": "SAFE_ACTIONABLE_FAILURE",
        "contract": {
            "kind": "safety",
            "required_false_flags": ["intent_applied", "persisted", "rendered"],
        },
    }
    safe = {
        "outcome": "SAFE_ACTIONABLE_FAILURE",
        "changed": False,
        "pre_bytes_sha256": "a",
        "post_bytes_sha256": "a",
        "diagnostic_code": "enrichment.source_missing",
        "canonical_before": {"title": "same"},
        "canonical_after": {"title": "same"},
        "intent_applied": False,
        "persisted": False,
        "rendered": False,
    }
    assert d4.grade_turn(safe, expected)["status"] == "PASS"
    unsafe = {**safe, "post_bytes_sha256": "b"}
    assert d4.grade_turn(unsafe, expected)["status"] == "FAIL"


_D4_REHEARSAL_LAS = """~Version Information
 VERS.                  2.0:   CWLS log ASCII standard - VERSION 2.0
 WRAP.                   NO:   One line per depth step
~Well Information
 WELL.             D4-REHEARSAL:   WELL NAME
~Curve Information
 DEPT.M                     :   Depth
 GR  .gAPI                  :   Gamma Ray
 CALI.in                    :   Caliper
 ILD .ohm.m                 :   Induction Resistivity
 NPHI.v/v                   :   Neutron Porosity
~ASCII Log Data
1000.0  50.0  8.6  100.0  0.20
1002.0  51.0  8.5  110.0  0.22
1004.0  52.0  8.4  120.0  0.24
"""


@dataclass
class _D4SessionPlanner:
    """Return deterministic semantic tasks through the real session facade."""

    calls: list[dict[str, object]]
    logical_calls: list[dict[str, str]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Map each frozen LAS request to its bounded production work unit."""
        self.calls.append(kwargs)
        self.logical_calls.append({"operation": "structured"})
        request = str(kwargs["request"])
        if request.startswith("Rename this report"):
            return SemanticPlan(
                summary="D4 report title revision",
                report_task=ReportTask(
                    goal="Rename the report.",
                    capability_ids=("report.standard",),
                    requirements=(request,),
                ),
                section_tasks=(
                    SectionTask(
                        goal="Preserve the plotted sections.",
                        capability_ids=("section.log_plot",),
                        existing_section_hint="Main Log",
                        requirements=("Preserve the plotted sections.",),
                    ),
                ),
            )
        section_hint = "Main Log – Upper" if "Main Log – Upper" in request else "Main Log"
        source_hints = ()
        if "missing_neutron.las" in request:
            source_hints = ("missing_neutron.las",)
        elif "30-23a-3 8117_d.las" in request:
            source_hints = ("30-23a-3 8117_d.las",)
        capability_ids = ("section.log_plot", "track.normal", "binding.curve")
        if "fill from" in request:
            capability_ids = (
                "section.log_plot",
                "track.normal",
                "binding.curve",
                "fill.curve",
            )
        return SemanticPlan(
            summary="D4 LAS revision",
            section_tasks=(
                SectionTask(
                    goal="Execute the requested LAS revision.",
                    capability_ids=capability_ids,
                    existing_section_hint=section_hint,
                    source_hints=source_hints,
                    requirements=(request,),
                ),
            ),
        )


@dataclass
class _D4SessionReportBackend:
    """Emit the deterministic D4 title operation through ReportProgramCompiler."""

    logical_calls: list[dict[str, str]]

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Return only the report title operation required by D4-L01:T1."""
        del request
        self.logical_calls.append({"operation": "program"})
        return ProgramGenerationResult(
            text='report = wp.report(title="Formation Integrity Review")\n',
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _D4SessionSectionBackend:
    """Emit deterministic section programs after inspecting real worker context."""

    logical_calls: list[dict[str, str]]

    @staticmethod
    def _payload(request: ProgramGenerationRequest) -> dict[str, object]:
        """Decode the production worker's bounded JSON context."""
        payload_start = request.user_prompt.index('{"capabilities":')
        payload = json.loads(request.user_prompt[payload_start:])
        assert isinstance(payload, dict)
        return payload

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Return one deterministic program for the requested LAS turn."""
        payload = self._payload(request)
        task = payload["section_task"]
        assert isinstance(task, dict)
        requirement = str(task["requirements"][0])
        context = payload["section_context"]
        assert isinstance(context, dict)
        sources = context["sources"]
        assert isinstance(sources, list) and sources
        source_channels = {
            channel["mnemonic"] for source in sources for channel in source["channels"]
        }
        self.logical_calls.append({"operation": "program"})
        if requirement == "Preserve the plotted sections.":
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "wp.update_section(section, title='Main Log')\n"
            )
        elif "set the Gamma Ray curve to a linear 5–125" in requirement:
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.target_track(section, track_id='gr')\n"
                "curve = wp.target_curve(track, binding_id='main.gr.GR.1')\n"
                "wp.update_curve(track, curve, scale_minimum=5, scale_maximum=125, "
                "scale_kind='linear', reverse=False)\n"
            )
        elif "Append a 30 mm normal track" in requirement:
            assert "ILD" in source_channels
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.track(section, id_hint='resistivity_qc', kind='normal', "
                "title='Resistivity QC', width_mm=30)\n"
                "wp.curve(track, channel='ILD', label='Resistivity QC', "
                "scale_minimum=0.2, scale_maximum=2000, scale_kind='log', reverse=False)\n"
            )
        elif "fill from the Gamma Ray curve" in requirement:
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.target_track(section, track_id='gr')\n"
                "curve = wp.target_curve(track, binding_id='main.gr.GR.1')\n"
                "wp.fill(track, curve, kind='to_lower_limit', id_hint='gr_fill', "
                "color='#f2e8a0', alpha=0.2)\n"
            )
        elif "Apply that 20–110" in requirement:
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.target_track(section, track_id='gr')\n"
                "curve = wp.target_curve(track, binding_id='main.gr.GR.1')\n"
                "wp.update_curve(track, curve, scale_minimum=20, scale_maximum=110, "
                "scale_kind='linear', reverse=False)\n"
            )
        else:
            assert "RT" in requirement
            assert "RT" not in source_channels
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.track(section, kind='normal', title='Resistivity Alias QC', "
                "width_mm=24)\n"
                "wp.curve(track, channel='RT', label='Resistivity Alias QC', "
                "scale_minimum=0.2, scale_maximum=2000, scale_kind='log', reverse=False)\n"
            )
        return ProgramGenerationResult(
            text=program,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _D4SessionHarness:
    """Compose the real DirectNotebookSession with deterministic worker doubles."""

    root: Path
    planner: _D4SessionPlanner
    report_backend: _D4SessionReportBackend
    section_backend: _D4SessionSectionBackend
    adapter: DirectNotebookSession

    @classmethod
    def create(cls, root: Path) -> _D4SessionHarness:
        """Build the unchanged production graph around deterministic backends."""
        calls: list[dict[str, str]] = []
        planner = _D4SessionPlanner(calls=[], logical_calls=calls)
        report_backend = _D4SessionReportBackend(logical_calls=calls)
        section_backend = _D4SessionSectionBackend(logical_calls=calls)
        registry = create_builtin_registry()
        dependencies = CodeModeGraphDependencies(
            planner=planner,  # type: ignore[arg-type]
            enricher=SemanticEnricher(
                loader=LogfileSourceLoader(),
                allowed_roots={"server": root},
            ),
            report_compiler=ReportProgramCompiler(backend=report_backend, registry=registry),
            section_compiler=ProgramSectionCompiler(backend=section_backend, registry=registry),
        )
        adapter = DirectNotebookSession(
            session=AgentSession(
                compiler=CodeModeCompileFacade(dependencies),
                config=AgentSessionConfig(timeout_seconds=10.0),
            ),
            provider="deterministic",
            model="d4-rehearsal-model",
            credential_source="none",
            server_root=root,
        )
        return cls(root, planner, report_backend, section_backend, adapter)

    @property
    def logical_calls(self) -> list[dict[str, str]]:
        """Return and retain the shared logical-call list used by all doubles."""
        return self.planner.logical_calls

    def take_calls(self) -> list[dict[str, str]]:
        """Take the calls emitted by the current production-session turn."""
        calls = list(self.logical_calls)
        self.logical_calls.clear()
        return calls


def _write_rehearsal_document(path: Path, payload: dict[str, object]) -> None:
    """Write a mutated canonical document through the real logfile adapter."""
    document = AuthoringDocumentSpec.model_validate(payload)
    mapping = authoring_document_to_logfile_mapping(document)
    channels = mapping["document"]["bindings"]["channels"]
    for section in document.sections:
        for track in section.tracks:
            for fill in getattr(track, "fills", ()):
                channel = next(
                    item
                    for item in channels
                    if item.get("id") == fill.binding_id
                    and item.get("track_id") == track.id
                    and item.get("section") == section.id
                )
                channel["fill"] = _fill_element(fill)
    path.write_text(
        yaml.safe_dump(mapping, sort_keys=False),
        encoding="utf-8",
    )


def test_campaign_runner_rehearses_all_nine_turns_and_real_las_verifier(
    tmp_path: Path,
) -> None:
    """Run the complete frozen sequence with durable evidence and real LAS grading."""
    state_path = tmp_path / "state.json"
    journal_path = tmp_path / "journal.jsonl"
    current_by_case: dict[str, Path] = {}
    order: list[str] = []

    class _RehearsalContext:
        """Expose only bounded fake execution metrics to the campaign runner."""

        provider_calls = 0
        endpoint_calls = 0
        model_calls = 0

        def __init__(self) -> None:
            self._call_started = None

        def bind_call_started(self, callback: object) -> None:
            self._call_started = callback

        def record_calls(self, calls: list[Mapping[str, object]]) -> None:
            assert callable(self._call_started)
            for call in calls:
                self._call_started(
                    {"event": "logical_call_started", "operation": call["operation"]}
                )

    rehearsal_context = _RehearsalContext()
    source_name = "30-23a-3 8117_d.las"
    (tmp_path / source_name).write_text(_D4_REHEARSAL_LAS, encoding="utf-8")
    session_harness = _D4SessionHarness.create(tmp_path)

    def _base_for(case_id: str) -> Path:
        """Create one independent persisted starting artifact per D4 case."""
        if case_id in current_by_case:
            return current_by_case[case_id]
        source = copy.deepcopy(d4.load_gold(REPO_ROOT)["canonical_las_seed"])
        source["sections"][0]["data_source"]["source_path"] = source_name
        if case_id == "D4-L02":
            lower = copy.deepcopy(source["sections"][0])
            source["sections"][0]["id"] = "main-upper"
            source["sections"][0]["title"] = "Main Log – Upper"
            lower["id"] = "main-lower"
            lower["title"] = "Main Log – Lower"
            for track in lower["tracks"]:
                for binding in track.get("bindings", []):
                    binding["binding_id"] = str(binding["binding_id"]).replace(
                        "main.", "main-lower."
                    )
            source["sections"] = [source["sections"][0], lower]
        path = tmp_path / f"{case_id}.log.yaml"
        _write_rehearsal_document(path, source)
        normalized = load_authoring_document(path).model_dump(mode="json")
        _write_rehearsal_document(path, normalized)
        current_by_case[case_id] = path
        return path

    async def execute_turn(
        case: Mapping[str, object],
        expected: Mapping[str, object],
        context: _RehearsalContext,
    ) -> Mapping[str, object]:
        """Apply deterministic fixture mutations while using the actual harness."""

        def finish(actual: dict[str, object]) -> dict[str, object]:
            calls = actual.get("calls", [])
            assert isinstance(calls, list)
            context.record_calls(calls)
            return actual

        turn_id = str(case["turn_id"])
        case_id = str(case["case_id"])
        order.append(turn_id)
        current = _base_for(case_id)
        before = tmp_path / f"{turn_id.replace(':', '-')}.before.yaml"
        after = tmp_path / f"{turn_id.replace(':', '-')}.after.yaml"
        before.write_bytes(current.read_bytes())
        before_payload = load_authoring_document(before).model_dump(mode="json")

        if turn_id == "D4-C01:C01":
            return finish(
                {
                    "outcome": "DIRECT_CORRECT",
                    "canonical_before": {},
                    "canonical_after": {},
                    "persisted": True,
                    "rendered": True,
                    "verifier": {
                        "acceptance_status": "PASS",
                        "requirements": [
                            {"id": item, "status": "PASS"}
                            for item in expected["contract"]["required_verifier_requirements"]
                        ],
                    },
                    "provider": "deterministic",
                    "model": "d4-rehearsal",
                    "calls": [{"operation": "structured"}, {"operation": "program"}],
                    "worker_metrics": {"worker_count": 3, "program_calls": 3},
                }
            )

        result = await session_harness.adapter.revise(
            feedback=str(case["request"]),
            logfile_path=current,
        )
        after.write_bytes(current.read_bytes())
        session_calls = session_harness.take_calls()
        facts = result.report_facts
        after_document = load_authoring_document(after).model_dump(mode="json")
        if facts["success"] is True:
            render_path = tmp_path / f"{turn_id.replace(':', '-')}.pdf"
            rendered = await session_harness.adapter.render_logfile_to_file(
                logfile_path=current,
                output_path=render_path,
                overwrite=True,
            )
            assert rendered and render_path.is_file() and render_path.stat().st_size > 0
            return finish(
                {
                    "outcome": expected["expected_outcome"],
                    "before_path": before,
                    "after_path": after,
                    "render_path": render_path,
                    "canonical_before": before_payload,
                    "canonical_after": after_document,
                    "persisted": True,
                    "rendered": True,
                    "execution_evidence": {
                        "accepted": True,
                        "persisted": True,
                        "rendered": True,
                    },
                    "provider": "deterministic",
                    "model": "d4-rehearsal-model",
                    "calls": session_calls,
                    "worker_metrics": {"worker_count": 1, "program_calls": 1},
                }
            )

        return finish(
            {
                "outcome": expected["expected_outcome"],
                "before_path": before,
                "after_path": after,
                "canonical_before": before_payload,
                "canonical_after": after_document,
                "changed": False,
                "pre_bytes_sha256": d4.sha256_file(before),
                "post_bytes_sha256": d4.sha256_file(after),
                "diagnostic_code": "program.dry_run_error",
                "intent_applied": False,
                "persisted": False,
                "rendered": False,
                "fallback_used": False,
                "substituted_channel": False,
                "prohibited_object_present": False,
                "provider": "deterministic",
                "model": "d4-rehearsal-model",
                "calls": session_calls,
            }
        )

    result = asyncio.run(
        d4.run_campaign(
            repo_root=REPO_ROOT,
            state_path=state_path,
            journal_path=journal_path,
            preflight=lambda: {"current_checkout": "a" * 40},
            credential_factory=lambda: rehearsal_context,
            turn_executor=execute_turn,
        )
    )

    assert order == [case["turn_id"] for case in d4.load_cases(REPO_ROOT)], result
    assert result["decision"] == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED", [
        (row["turn_id"], row["grader_status"], row["diff_status"])
        for row in result["rows"]
        if row["grader_status"] != "PASS"
    ]
    assert result["completed_turns"] == 9
    assert len(result["rows"]) == 9
    assert result["provider_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["model_calls"] == 0
    assert all(row["grader_status"] == "PASS" for row in result["rows"])
    assert all(
        {item["status"] for item in row["verifier_requirements"]} <= {"PASS", "NOT_CHECKABLE"}
        for row in result["rows"]
        if row["turn_id"].startswith("D4-L01") or row["turn_id"] == "D4-L02:T2"
    )
    journal_rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "COMPLETED"
    assert sum(row.get("event") == "logical_call_started" for row in journal_rows) == 17
    assert sum("turn_id" in row for row in journal_rows) == 9
    assert journal_rows[-1]["event"] == "campaign_terminal"
    assert all("raw_generated_program" not in row for row in journal_rows)
