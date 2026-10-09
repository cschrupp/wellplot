"""Provider-free tests for the D4 live-acceptance harness."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
import yaml
from pydantic import BaseModel
from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent.code_mode.enrichment import SemanticEnricher
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan, SemanticPlanner
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
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.agent.providers.response_diagnostics import StructuredResponseProviderError
from wellplot.agent.session import AgentSession, AgentSessionConfig
from wellplot.authoring import (
    _fill_element,
    authoring_document_to_logfile_mapping,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


class _Value(BaseModel):
    value: str = "ok"


class _RequiredValue(BaseModel):
    value: str


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.kwargs: dict[str, object] | None = None

    async def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        role="assistant",
                        content=self.content,
                        refusal=None,
                        tool_calls=None,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


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
        endpoint_identity={
            "model_catalog": [d4.EXPECTED_MODEL],
            "model_path_basename": "qwen3.6-35b-a3b.gguf",
            "model_path_fingerprint_sha256": "a" * 64,
            "context_size": 32768,
            "build_info": "llama.cpp test build",
            "total_slots": 1,
            "gguf_byte_identity": "NOT_AVAILABLE",
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


def test_endpoint_identity_projects_only_bounded_props_and_exact_catalog() -> None:
    """Fake authenticated GETs prove the Qwen-only catalog and sanitized props."""
    requests: list[tuple[str, str]] = []
    responses = {
        d4.MODEL_CATALOG_URL: {"data": [{"id": d4.EXPECTED_MODEL, "object": "model"}]},
        d4.PROPS_URL: {
            "model_path": "/srv/models/qwen3.6-35b-a3b.gguf",
            "default_generation_settings": {"n_ctx": 32768},
            "build_info": "llama.cpp build abc",
            "total_slots": 1,
            "chat_template": "must not persist",
        },
    }

    def fake_get(url: str, token: str) -> object:
        requests.append((url, token))
        return responses[url]

    identity = d4.observe_endpoint_identity("secret-token", http_get_json=fake_get)
    assert [url for url, _ in requests] == [d4.MODEL_CATALOG_URL, d4.PROPS_URL]
    assert all(token == "secret-token" for _, token in requests)
    assert "secret-token" not in json.dumps(identity)
    assert identity["model_catalog"] == [d4.EXPECTED_MODEL]
    assert identity["model_path_basename"] == "qwen3.6-35b-a3b.gguf"
    assert identity["model_path_fingerprint_sha256"] == d4.sha256_text(
        "/srv/models/qwen3.6-35b-a3b.gguf"
    )
    assert "model_path" not in identity
    assert "chat_template" not in identity
    assert identity["gguf_byte_identity"] == "NOT_AVAILABLE"


@pytest.mark.parametrize(
    "catalog",
    [
        {"data": []},
        {"data": [{"id": "wrong-model"}]},
        {"data": [{"id": d4.EXPECTED_MODEL}, {"id": "fallback"}]},
        {"data": [{"object": "model"}]},
    ],
)
def test_endpoint_identity_rejects_catalog_drift(catalog: dict[str, object]) -> None:
    """Missing, aliased, extra, and malformed catalog entries fail closed."""
    with pytest.raises(d4.PostStartedFailure, match="endpoint_identity_mismatch"):
        d4.observe_endpoint_identity(
            "token",
            http_get_json=lambda url, token: (
                catalog
                if url == d4.MODEL_CATALOG_URL
                else {
                    "model_path": "/models/qwen.gguf",
                    "default_generation_settings": {"n_ctx": 1},
                    "build_info": "build",
                    "total_slots": 1,
                }
            ),
        )


@pytest.mark.parametrize(
    "props",
    [
        {"default_generation_settings": {"n_ctx": 32768}, "build_info": "build", "total_slots": 1},
        {
            "model_path": "/models/qwen.gguf",
            "default_generation_settings": {},
            "build_info": "build",
            "total_slots": 1,
        },
        {
            "model_path": "/models/qwen.gguf",
            "default_generation_settings": {"n_ctx": 32768},
            "total_slots": 1,
        },
        {
            "model_path": "/models/qwen.gguf",
            "default_generation_settings": {"n_ctx": 32768},
            "build_info": "build",
            "total_slots": 0,
        },
    ],
)
def test_endpoint_identity_rejects_invalid_props(props: dict[str, object]) -> None:
    """The bounded /props projection requires all four identity facts."""
    with pytest.raises(d4.PostStartedFailure, match="endpoint_identity_mismatch"):
        d4.observe_endpoint_identity(
            "token",
            http_get_json=lambda url, token: (
                {"data": [{"id": d4.EXPECTED_MODEL}]} if url == d4.MODEL_CATALOG_URL else props
            ),
        )


def test_endpoint_identity_must_match_external_authorization() -> None:
    """Observed identity cannot silently select a different deployment."""
    authorization = _authorization()
    observed = dict(authorization.endpoint_identity)
    observed["build_info"] = "different build"
    with pytest.raises(d4.PostStartedFailure, match="endpoint_identity_mismatch"):
        d4.validate_endpoint_identity(observed, authorization)


@pytest.mark.parametrize(
    "field",
    ["server_origin", "openai_compat_base_url", "model_catalog_url", "props_url"],
)
def test_endpoint_identity_rejects_authorized_url_drift(field: str) -> None:
    """The configured origin and every frozen endpoint URL are immutable."""
    authorization = _authorization()
    observed = dict(authorization.endpoint_identity)
    with pytest.raises(d4.PostStartedFailure, match="endpoint_identity_mismatch"):
        d4.validate_endpoint_identity(observed, replace(authorization, **{field: "http://wrong"}))


def test_credential_loader_does_not_fall_back_to_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The amended harness accepts only the OpenAI-compatible credential names."""
    monkeypatch.delenv("OPENAI_COMPAT_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    with (
        TemporaryDirectory() as temporary,
        pytest.raises(
            d4.PostStartedFailure,
            match="credential_unavailable",
        ),
    ):
        d4.load_d4_api_key(Path(temporary))


def test_runtime_passes_loaded_token_only_to_explicit_provider_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime composition keeps the credential ephemeral and provider-bound."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(d4, "load_d4_api_key", lambda repo_root: "ephemeral-token")

    def fake_adapter(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(d4, "create_live_campaign_adapter", fake_adapter)
    recorded: list[dict[str, object]] = []

    def fake_get(url: str, token: str) -> object:
        if url == d4.MODEL_CATALOG_URL:
            return {"data": [{"id": d4.EXPECTED_MODEL}]}
        return {
            "model_path": "/models/qwen.gguf",
            "default_generation_settings": {"n_ctx": 32768},
            "build_info": "build",
            "total_slots": 1,
        }

    authorization = replace(
        _authorization(),
        endpoint_identity={
            "model_catalog": [d4.EXPECTED_MODEL],
            "model_path_basename": "qwen.gguf",
            "model_path_fingerprint_sha256": d4.sha256_text("/models/qwen.gguf"),
            "context_size": 32768,
            "build_info": "build",
            "total_slots": 1,
            "gguf_byte_identity": "NOT_AVAILABLE",
        },
    )
    result = d4.create_live_campaign_runtime(
        repo_root=REPO_ROOT,
        artifact_root=REPO_ROOT / "tmp",
        authorization=authorization,
        record_identity=lambda identity: recorded.append(dict(identity)),
        http_get_json=fake_get,
    )
    assert result is not None
    assert captured["api_key"] == "ephemeral-token"
    assert captured["base_url"] == d4.OPENAI_COMPAT_BASE_URL
    assert "ephemeral-token" not in json.dumps(recorded)


def test_real_compat_backend_uses_frozen_sparse_token_contract() -> None:
    """Production backend kwargs omit both legacy token parameter names."""
    structured_client = _FakeClient('{"value":"ok"}')
    structured = OpenAICompatibleBackendV2(
        model=d4.EXPECTED_MODEL,
        client=structured_client,
        structured_output="json_schema",
    )
    asyncio.run(structured.generate_structured(_structured_request(), response_model=_Value))
    structured_kwargs = structured_client.chat.completions.kwargs
    assert structured_kwargs is not None
    assert structured_kwargs["model"] == d4.EXPECTED_MODEL
    assert structured_kwargs["temperature"] == 0.0
    assert structured_kwargs["response_format"]["type"] == "json_schema"
    assert structured_kwargs["response_format"]["json_schema"]["strict"] is True
    assert "max_tokens" not in structured_kwargs
    assert "max_completion_tokens" not in structured_kwargs

    program_client = _FakeClient("report = wp.report()")
    program = OpenAICompatibleBackendV2(model=d4.EXPECTED_MODEL, client=program_client)
    asyncio.run(program.generate_program(_program_request()))
    program_kwargs = program_client.chat.completions.kwargs
    assert program_kwargs is not None
    assert program_kwargs["model"] == d4.EXPECTED_MODEL
    assert "temperature" not in program_kwargs
    assert "max_tokens" not in program_kwargs
    assert "max_completion_tokens" not in program_kwargs


@pytest.mark.parametrize("content", ["not-json", "{}"])
def test_real_compat_backend_rejects_invalid_local_structured_content(content: str) -> None:
    """Local JSON/Pydantic validation remains authoritative over provider success."""
    backend = OpenAICompatibleBackendV2(
        model=d4.EXPECTED_MODEL,
        client=_FakeClient(content),
        structured_output="json_schema",
    )
    with pytest.raises(StructuredResponseProviderError):
        asyncio.run(
            backend.generate_structured(_structured_request(), response_model=_RequiredValue)
        )


def _run_post_started_failure(
    root: Path,
    failure: Callable[[d4.CampaignCustody], object],
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    """Run one fake post-STARTED failure and return state plus terminal event."""
    state_path = root / "state.json"
    journal_path = root / "journal.jsonl"
    result = asyncio.run(
        d4.run_campaign(
            repo_root=REPO_ROOT,
            state_path=state_path,
            journal_path=journal_path,
            preflight=lambda: {"current_checkout": "a" * 40},
            execution_factory=failure,
        )
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in journal_path.read_text().splitlines()]
    return result, state, events


def test_missing_credential_after_started_is_durable_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential failure occurs after STARTED and leaves a terminal journal event."""
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(
            d4,
            "load_d4_api_key",
            lambda repo_root: (_ for _ in ()).throw(
                d4.PostStartedFailure("credential_unavailable")
            ),
        )
        result, state, events = _run_post_started_failure(
            root,
            lambda custody: d4.create_live_campaign_runtime(
                repo_root=REPO_ROOT,
                artifact_root=root,
                authorization=_authorization(),
                record_identity=custody.record_endpoint_identity,
            ),
        )
    assert result["terminal_reason_code"] == "credential_unavailable"
    assert state["status"] == "TERMINAL"
    assert state["terminal_decision"] == d4.INCONCLUSIVE_DECISION
    assert state["terminal_reason_code"] == "credential_unavailable"
    assert state["completed_turns"] == 0
    assert state["logical_generation_calls"] == 0
    assert events[-1]["event"] == "campaign_terminal"
    assert events[-1]["terminal_reason_code"] == "credential_unavailable"


def test_endpoint_unavailable_after_started_has_no_provider_or_logical_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint failure is terminal before provider construction or generation."""
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(d4, "load_d4_api_key", lambda repo_root: "ephemeral")
        result, state, events = _run_post_started_failure(
            root,
            lambda custody: d4.create_live_campaign_runtime(
                repo_root=REPO_ROOT,
                artifact_root=root,
                authorization=_authorization(),
                record_identity=custody.record_endpoint_identity,
                http_get_json=lambda url, token: (_ for _ in ()).throw(
                    d4.PostStartedFailure("endpoint_unreachable")
                ),
            ),
        )
    assert result["terminal_reason_code"] == "endpoint_unreachable"
    assert state["logical_generation_calls"] == 0
    assert events[-1]["terminal_reason_code"] == "endpoint_unreachable"


def test_identity_mismatch_after_started_has_no_provider_or_logical_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrong model catalog cannot fall through to provider construction."""
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(d4, "load_d4_api_key", lambda repo_root: "ephemeral")
        result, state, events = _run_post_started_failure(
            root,
            lambda custody: d4.create_live_campaign_runtime(
                repo_root=REPO_ROOT,
                artifact_root=root,
                authorization=_authorization(),
                record_identity=custody.record_endpoint_identity,
                http_get_json=lambda url, token: (
                    {"data": [{"id": "wrong-model"}]} if url == d4.MODEL_CATALOG_URL else {}
                ),
            ),
        )
    assert result["terminal_reason_code"] == "endpoint_identity_mismatch"
    assert state["logical_generation_calls"] == 0
    assert events[-1]["terminal_reason_code"] == "endpoint_identity_mismatch"


def test_provider_construction_failure_is_durable_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful identity observation followed by construction failure is terminal."""
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        monkeypatch.setattr(d4, "load_d4_api_key", lambda repo_root: "ephemeral")
        monkeypatch.setattr(
            d4,
            "create_live_campaign_adapter",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        )

        def fake_get(url: str, token: str) -> object:
            if url == d4.MODEL_CATALOG_URL:
                return {"data": [{"id": d4.EXPECTED_MODEL}]}
            return {
                "model_path": "/models/qwen.gguf",
                "default_generation_settings": {"n_ctx": 32768},
                "build_info": "build",
                "total_slots": 1,
            }

        result, state, events = _run_post_started_failure(
            root,
            lambda custody: d4.create_live_campaign_runtime(
                repo_root=REPO_ROOT,
                artifact_root=root,
                authorization=replace(
                    _authorization(),
                    endpoint_identity={
                        "model_catalog": [d4.EXPECTED_MODEL],
                        "model_path_basename": "qwen.gguf",
                        "model_path_fingerprint_sha256": d4.sha256_text("/models/qwen.gguf"),
                        "context_size": 32768,
                        "build_info": "build",
                        "total_slots": 1,
                        "gguf_byte_identity": "NOT_AVAILABLE",
                    },
                ),
                record_identity=custody.record_endpoint_identity,
                http_get_json=fake_get,
            ),
        )
    assert result["terminal_reason_code"] == "provider_construction_failed"
    assert state["logical_generation_calls"] == 0
    assert events[-1]["terminal_reason_code"] == "provider_construction_failed"


def test_journal_failure_leaves_state_terminal_evidence_integrity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If terminal journaling fails, state remains the bounded evidence source."""

    def fail_append(self: d4.CampaignJournal, event: Mapping[str, object]) -> None:
        raise OSError("journal unavailable")

    monkeypatch.setattr(d4.CampaignJournal, "append", fail_append)
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        state_path = root / "state.json"
        journal_path = root / "journal.jsonl"
        result = asyncio.run(
            d4.run_campaign(
                repo_root=REPO_ROOT,
                state_path=state_path,
                journal_path=journal_path,
                preflight=lambda: {"current_checkout": "a" * 40},
                execution_factory=lambda custody: (_ for _ in ()).throw(
                    d4.PostStartedFailure("credential_unavailable")
                ),
            )
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["terminal_reason_code"] == "evidence_integrity_failure"
    assert state["status"] == "TERMINAL"
    assert state["terminal_decision"] == d4.INCONCLUSIVE_DECISION
    assert state["terminal_reason_code"] == "evidence_integrity_failure"


def test_live_cli_requires_explicit_d4b_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the live adapter unreachable from an ordinary preflight invocation."""
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nlp_d4_live_acceptance.py",
            "--execute-live",
            "--authorization-json",
            str(authorization_path),
        ],
    )
    assert d4._main() == 2


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


def test_counting_backend_reserves_unique_indexes_under_concurrent_calls() -> None:
    """Reserve start identities before overlapping delegates and enforce the cap."""

    class _BlockingBackend(_Backend):
        def __init__(self) -> None:
            super().__init__()
            self.release = asyncio.Event()

        async def generate_structured(
            self,
            request: StructuredGenerationRequest,
            *,
            response_model: type[_Value],
        ) -> StructuredGenerationResult[_Value]:
            result = await super().generate_structured(request, response_model=response_model)
            await self.release.wait()
            return result

    async def run() -> tuple[list[dict[str, object]], list[dict[str, object]], list[object], int]:
        delegate = _BlockingBackend()
        ledger = d4.LogicalCallLedger(max_calls=2)
        events: list[dict[str, object]] = []
        calls: list[d4.LogicalCall] = []
        backends = tuple(
            d4.CountingBackend(
                delegate=delegate,
                max_calls=2,
                ledger=ledger,
                calls=calls,
                call_started=events.append,
                call_completed=events.append,
            )
            for _ in range(2)
        )
        tasks = [
            asyncio.create_task(
                backend.generate_structured(_structured_request(), response_model=_Value)
            )
            for backend in (*backends, backends[0])
        ]
        while delegate.calls < 2:
            await asyncio.sleep(0)
        backends[0].delegate.release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        started = [event for event in events if event["event"] == "logical_call_started"]
        completed = [event for event in events if event["event"] == "logical_call_completed"]
        return started, completed, results, delegate.calls

    started, completed, results, delegated = asyncio.run(run())
    assert [event["index"] for event in started] == [1, 2]
    assert sorted(event["index"] for event in completed) == [1, 2]
    assert len({event["index"] for event in started}) == 2
    assert len({event["index"] for event in completed}) == 2
    assert delegated == 2
    assert sum(isinstance(result, d4.CallCapExceeded) for result in results) == 1


def test_campaign_state_is_durable_before_post_started_runtime() -> None:
    """Write STARTED state before invoking any post-STARTED runtime code."""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        state_path = directory / "state.json"
        journal_path = directory / "journal.jsonl"
        events: list[str] = []

        def preflight() -> dict[str, str]:
            events.append("preflight")
            return {"current_checkout": "a" * 40}

        state, _ = d4.start_campaign(
            state_path=state_path,
            journal_path=journal_path,
            preflight=preflight,
        )
        assert events == ["preflight"]
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
        )
        custody = d4.CampaignCustody(
            state_path=state_path,
            journal=d4.CampaignJournal(journal_path),
            state=state,
        )
        backend = d4.CountingBackend(
            delegate=_Backend(),
            call_started=custody.record_call_started,
            call_completed=custody.record_call_completed,
        )

        async def run() -> None:
            await backend.generate_structured(_structured_request(), response_model=_Value)

        asyncio.run(run())
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert persisted["logical_generation_calls"] == 1
        events = [json.loads(line) for line in journal_path.read_text().splitlines()]
        assert events[0]["event"] == "logical_call_started"
        assert events[0]["logical_generation_calls"] == 1
        assert "raw_structured_payload" not in events[0]
        assert events[1]["event"] == "logical_call_completed"
        assert events[1]["index"] == 1
        assert events[1]["outcome"] == "success"
        assert events[1]["total_tokens"] == 5
        assert "raw_structured_payload" not in events[1]
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
    detected = [*passed[:-1], {"grader_status": "PASS", "outcome": "DETECTED_INCORRECT_OUTPUT"}]
    assert d4.derive_terminal_decision(detected) == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_FAILED"
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

    def plan(self, **kwargs: object) -> SemanticPlan:
        """Map each frozen LAS request to its bounded production work unit."""
        self.calls.append(kwargs)
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
class _D4PlannerBackend:
    """Adapt the deterministic plan fixture to the structured backend boundary."""

    planner: _D4SessionPlanner

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[SemanticPlan],
    ) -> StructuredGenerationResult[SemanticPlan]:
        del response_model
        context = json.loads(request.user_prompt.split("Context:\n", 1)[1])
        value = self.planner.plan(
            request=context["request"],
            mode=context["mode"],
            current_document_summary=context["current_document_summary"],
            source_summary=context["source_summary"],
            timeout_seconds=request.timeout_seconds,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )
        return StructuredGenerationResult(
            value=value,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _D4SessionReportBackend:
    """Emit the deterministic D4 title operation through ReportProgramCompiler."""

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Return only the report title operation required by D4-L01:T1."""
        del request
        return ProgramGenerationResult(
            text='report = wp.report(title="Formation Integrity Review")\n',
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _D4SessionSectionBackend:
    """Emit deterministic section programs after inspecting real worker context."""

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
    adapter: d4.D4CampaignAdapter

    @classmethod
    def create(cls, root: Path) -> _D4SessionHarness:
        """Build the unchanged production graph around deterministic backends."""
        calls: list[d4.LogicalCall] = []
        ledger = d4.LogicalCallLedger()
        planner = _D4SessionPlanner(calls=[])
        planner_backend = d4.CountingBackend(
            delegate=_D4PlannerBackend(planner),
            provider="deterministic",
            model="d4-rehearsal-model",
            calls=calls,
            ledger=ledger,
        )
        report_backend = d4.CountingBackend(
            delegate=_D4SessionReportBackend(),
            provider="deterministic",
            model="d4-rehearsal-model",
            calls=calls,
            ledger=ledger,
        )
        section_backend = d4.CountingBackend(
            delegate=_D4SessionSectionBackend(),
            provider="deterministic",
            model="d4-rehearsal-model",
            calls=calls,
            ledger=ledger,
        )
        registry = create_builtin_registry()
        dependencies = CodeModeGraphDependencies(
            planner=SemanticPlanner(backend=planner_backend, registry=registry),
            enricher=SemanticEnricher(
                loader=LogfileSourceLoader(),
                allowed_roots={"server": root},
            ),
            report_compiler=ReportProgramCompiler(backend=report_backend, registry=registry),
            section_compiler=ProgramSectionCompiler(backend=section_backend, registry=registry),
        )
        session = DirectNotebookSession(
            session=AgentSession(
                compiler=CodeModeCompileFacade(dependencies),
                config=AgentSessionConfig(timeout_seconds=10.0),
            ),
            provider="deterministic",
            model="d4-rehearsal-model",
            credential_source="none",
            server_root=root,
        )
        call_source = d4.CampaignCallSource(
            backends=(planner_backend, report_backend, section_backend),
            calls=calls,
            ledger=ledger,
        )
        adapter = d4.D4CampaignAdapter(
            repo_root=REPO_ROOT,
            artifact_root=root,
            session=session,
            call_source=call_source,
        )
        return cls(root, planner, adapter)


@dataclass
class _GeneratedCblSession:
    """Provider-free session double that records the exact CBL render input."""

    template: Path
    provider: str = "deterministic"
    model: str = "d4-rehearsal-model"
    render_source: Path | None = None

    async def run(self, *, output_logfile: Path, source_logfile_path: Path, goal: str) -> object:
        del source_logfile_path, goal
        output_logfile.write_bytes(self.template.read_bytes())
        return SimpleNamespace(
            submitted_intent=None,
            report_facts={
                "success": True,
                "compilation": {
                    "diagnostics": [],
                    "workers": [],
                    "metrics": {
                        "worker_count": 0,
                        "successful_workers": 0,
                        "failed_workers": 0,
                        "total_calls": 0,
                        "total_repairs": 0,
                    },
                },
                "apply_status": "persisted",
                "changed": True,
            },
        )

    async def render_logfile_to_file(
        self,
        *,
        logfile_path: Path,
        output_path: Path,
        overwrite: bool,
    ) -> dict[str, object]:
        del overwrite
        self.render_source = Path(logfile_path)
        output_path.write_bytes(b"rendered generated CBL")
        return {"output_path": str(output_path)}


def test_live_cbl_branch_verifies_and_renders_generated_artifact() -> None:
    """The live CBL path grades and renders the generated artifact, not LAS seed state."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        template = _build_rehearsal_cbl_artifact(root)
        session = _GeneratedCblSession(template=template)
        adapter = d4.D4CampaignAdapter(
            repo_root=REPO_ROOT,
            artifact_root=root,
            session=session,
            call_source=d4.CampaignCallSource(backends=(), calls=[]),
        )
        case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-C01:C01")
        expected = next(
            item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == case["turn_id"]
        )
        actual = asyncio.run(adapter.execute_turn(case, expected))
        grade = d4.grade_turn(actual, expected)

        assert grade["status"] == "PASS", grade
        assert actual["artifact_path"] == actual["after_path"]
        assert actual["rendered_artifact_path"] == actual["artifact_path"]
        assert actual["starting_artifact_path"].name == "cbl-scaffold.log.yaml"
        assert d4.sha256_file(actual["starting_artifact_path"])
        assert actual["ending_artifact_path"] == actual["artifact_path"]
        assert session.render_source == actual["artifact_path"]
        assert actual["rendered"] is True
        wrong_artifact = dict(actual, rendered_artifact_path=root / "wrong-cbl.log.yaml")
        assert d4.grade_turn(wrong_artifact, expected)["status"] == "FAIL"


def test_d4_l02_seed_instantiates_the_frozen_depth_windows() -> None:
    """Both L02 sections use the accepted source and exact shared-boundary ranges."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        harness = _D4SessionHarness.create(root)
        document = d4.load_logfile_document(harness.adapter._base_for("D4-L02"))
        sections = document["sections"]
        assert sections[0]["data_source"] == sections[1]["data_source"]
        assert [section["depth_range"] for section in sections] == [
            [8400.0, 9300.0],
            [9300.0, 10200.0],
        ]


def test_observed_negative_outcomes_distinguish_safe_rejection_from_bad_output() -> None:
    """A persisted illegal proposal is not equivalent to an untouched rejection."""
    safe = {
        "persisted": False,
        "rendered": False,
        "observed_safe_rejection": True,
    }
    bad = {
        "persisted": False,
        "rendered": False,
        "observed_safe_rejection": False,
    }
    case = {"workflow": "LAS-REVISE", "request": "missing channel"}
    assert d4._observed_outcome(safe, case, {"sections": []}) == "SAFE_ACTIONABLE_FAILURE"
    assert d4._observed_outcome(bad, case, {"sections": []}) == "DETECTED_INCORRECT_OUTPUT"


def test_safe_actionable_failure_uses_observed_diagnostics_not_request_text() -> None:
    """Request wording cannot turn an unrelated failure into a safe rejection."""
    before = {"sections": []}
    common = {
        "persisted": False,
        "rendered": False,
        "intent_applied": False,
        "canonical_before": before,
        "canonical_after": before,
        "pre_bytes_sha256": "same",
        "post_bytes_sha256": "same",
        "created_channels": [],
    }

    parse_failure = {
        **common,
        "diagnostic_code": "program.parse_error",
        "diagnostics": [
            {
                "code": "program.parse_error",
                "message": "could not parse missing_neutron.las",
            }
        ],
    }
    assert d4._observed_failure_facts(parse_failure, before)["observed_safe_rejection"] is False

    source_missing = {
        **common,
        "diagnostic_code": "enrichment.source_missing",
        "diagnostics": [{"code": "enrichment.source_missing"}],
    }
    assert d4._observed_failure_facts(source_missing, before)["observed_safe_rejection"] is True

    ambiguous = {
        **common,
        "diagnostic_code": "enrichment.section_hint_ambiguous",
        "diagnostics": [{"code": "enrichment.section_hint_ambiguous"}],
    }
    assert d4._observed_failure_facts(ambiguous, before)["observed_safe_rejection"] is True

    missing_rt = {
        **common,
        "diagnostic_code": "program.dry_run_error",
        "diagnostics": [
            {
                "code": "program.dry_run_error",
                "message": "channel_missing: No source channel matches 'RT'.",
            }
        ],
    }
    assert d4._observed_failure_facts(missing_rt, before)["observed_safe_rejection"] is True


def test_outcome_taxonomy_is_derived_after_deterministic_grade() -> None:
    """A persisted scientific mismatch is undetected, not direct correctness."""
    expected = next(
        item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == "D4-L01:T1"
    )
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-L01:T1")
    actual = {
        "canonical_before": {"title": "Original Well Log Report"},
        "canonical_after": {"title": "Wrong title"},
        "persisted": True,
        "rendered": True,
        "verifier": _verifier(expected["contract"]["required_verifier_requirements"]),
    }
    grade = d4.grade_turn(actual, expected)
    assert grade["status"] == "FAIL"
    assert d4._observed_outcome(actual, case, actual["canonical_before"], grade) == (
        "UNDETECTED_INCORRECT_OUTPUT"
    )


def test_failed_request_with_mutation_is_unintended_mutation() -> None:
    """A failed safety path that mutates the document is not safely rejected."""
    expected = next(
        item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == "D4-L03:C01"
    )
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-L03:C01")
    before = {"sections": []}
    actual = {
        "changed": True,
        "persisted": False,
        "rendered": False,
        "intent_applied": False,
        "canonical_before": before,
        "canonical_after": {"sections": [{"id": "unexpected"}]},
        "pre_bytes_sha256": "before",
        "post_bytes_sha256": "after",
        "diagnostic_code": "enrichment.source_missing",
        "diagnostics": [{"code": "enrichment.source_missing"}],
        "created_channels": [],
    }
    grade = d4.grade_turn(actual, expected)
    assert grade["status"] == "FAIL"
    assert d4._observed_outcome(actual, case, before, grade) == "UNINTENDED_MUTATION"


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


def _build_rehearsal_cbl_artifact(root: Path) -> Path:
    """Write the accepted D0/D3 canonical CBL artifact as a fixture input."""
    from tests.test_nlp_d0_acceptance import _cbl_payload

    output = root / "d4-cbl-output.log.yaml"
    output.write_text(yaml.safe_dump(_cbl_payload(), sort_keys=False), encoding="utf-8")
    return output


def test_campaign_runner_rehearses_all_nine_turns_and_real_graders() -> None:
    """Run all turns through the frozen adapter and both unchanged graders."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        root = Path(temporary)
        state_path = root / "state.json"
        journal_path = root / "journal.jsonl"
        source_name = "30-23a-3 8117_d.las"
        source_path = root / source_name
        source_path.write_text(_D4_REHEARSAL_LAS, encoding="utf-8")
        session_harness = _D4SessionHarness.create(root)
        adapter = session_harness.adapter
        adapter.source_path = source_path
        adapter.cbl_artifact_path = _build_rehearsal_cbl_artifact(root)

        result = asyncio.run(
            d4.run_campaign(
                repo_root=REPO_ROOT,
                state_path=state_path,
                journal_path=journal_path,
                preflight=lambda: {"current_checkout": "a" * 40},
                execution_factory=lambda custody: adapter,
            )
        )
        journal_rows = [json.loads(line) for line in journal_path.read_text().splitlines()]
        state_status = json.loads(state_path.read_text(encoding="utf-8"))["status"]

    assert [row["turn_id"] for row in result["rows"]] == [
        case["turn_id"] for case in d4.load_cases(REPO_ROOT)
    ], result
    assert result["decision"] == "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED", [
        (row["turn_id"], row["grader_status"], row["grader_errors"])
        for row in result["rows"]
        if row["grader_status"] != "PASS"
    ]
    assert result["completed_turns"] == 9
    assert len(result["rows"]) == 9
    assert result["provider_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["model_calls"] == 0
    assert all(row["grader_status"] == "PASS" for row in result["rows"])
    gold_by_turn = {item["turn_id"]: item for item in d4.load_gold(REPO_ROOT)["cases"]}
    assert [row["outcome"] for row in result["rows"]] == [
        gold_by_turn[row["turn_id"]]["expected_outcome"] for row in result["rows"]
    ]
    assert all(
        set(row["token_usage"])
        == {
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "latency_ms",
        }
        for row in result["rows"]
    )
    assert all(
        {item["status"] for item in row["verifier_requirements"]} <= {"PASS", "NOT_CHECKABLE"}
        for row in result["rows"]
        if row["turn_id"].startswith("D4-L01") or row["turn_id"] == "D4-L02:T2"
    )
    cbl_row = next(row for row in result["rows"] if row["turn_id"] == "D4-C01:C01")
    assert {item["status"] for item in cbl_row["verifier_requirements"]} == {"PASS"}
    assert cbl_row["starting_artifact_sha256"] == cbl_row["ending_artifact_sha256"]
    assert cbl_row["starting_artifact_sha256"] is not None
    assert cbl_row["ending_artifact_sha256"] is not None
    assert state_status == "COMPLETED"
    assert result["logical_generation_calls"] == 16
    assert sum(row.get("event") == "logical_call_started" for row in journal_rows) == 16
    assert sum(row.get("event") == "logical_call_completed" for row in journal_rows) == 16
    started_indexes = [
        row["index"] for row in journal_rows if row.get("event") == "logical_call_started"
    ]
    completed_indexes = [
        row["index"] for row in journal_rows if row.get("event") == "logical_call_completed"
    ]
    assert started_indexes == list(range(1, 17))
    assert sorted(completed_indexes) == list(range(1, 17))
    assert len(set(completed_indexes)) == 16
    assert sum("turn_id" in row for row in journal_rows) == 9
    assert journal_rows[-1]["event"] == "campaign_terminal"
    assert all("raw_generated_program" not in row for row in journal_rows)
    assert all(
        "message" not in diagnostic
        for row in journal_rows
        for diagnostic in row.get("diagnostics", [])
    )
