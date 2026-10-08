"""Provider-free tests for the D4 live-acceptance harness."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import BaseModel
from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


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
        if assertion.get("operator") == "length":
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
        "canonical_after": {"title": "Gamma Ray Quality Control Review"},
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
