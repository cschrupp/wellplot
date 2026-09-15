"""Deterministic tests for the CM-43 CBL section A/B harness."""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.cbl_section_ab import (
    CBLExperimentCase,
    LegacyBackendRecorder,
    _section_task,
    evaluate_gate,
    evaluate_section_intent,
    run_ab,
)
from scripts.run_cbl_section_ab import (
    _factory_pair,
    _GenerationSettings,
)

from wellplot.agent.code_mode.program_worker import _SDK_REFERENCE
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderMetrics,
)
from wellplot.capabilities.builtins import LogPlotSectionArtifact
from wellplot.model.intent import AuthoringDocumentIntent


@dataclass
class _V1FixtureModel:
    payload: dict[str, object]
    calls: int = 0

    async def generate(self, **kwargs: object) -> LogPlotSectionArtifact:
        self.calls += 1
        response_model = kwargs["response_model"]
        return response_model.model_validate(self.payload)


@dataclass
class _V2FixtureBackend:
    source: str
    requests: list[ProgramGenerationRequest] = field(default_factory=list)

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        self.requests.append(request)
        return ProgramGenerationResult(
            text=self.source,
            metrics=ProviderMetrics(input_tokens=11, output_tokens=13, total_tokens=24),
        )

    async def generate_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("CM-43 section A/B must not invoke the semantic planner.")


def _case(*, run_count: int = 3) -> CBLExperimentCase:
    return CBLExperimentCase.load(
        provider="fake",
        model="fake-model",
        top_p=0.95,
        run_count=run_count,
    )


def _frozen_contract() -> dict[str, object]:
    return json.loads(
        (Path(__file__).parent / "fixtures/agentic_cbl/compile_contract.json").read_text(
            encoding="utf-8"
        )
    )


def _v2_scalar_program() -> str:
    return (
        "report = wp.report()\n"
        "section = wp.section(report, id_hint='main_pass', title='Main Pass')\n"
        "track = wp.track(section, id_hint='combo', kind='normal', "
        "title='Combo', width_mm=30)\n"
        "wp.curve(track, channel='ECGR_STGC', label='GR')\n"
    )


def test_case_freezes_prompt_starter_contract_and_derives_both_inputs() -> None:
    """The case pins corpus hashes and creates planner-free engine inputs."""
    case = _case()

    assert case.section_plan.section_id == "main_pass"
    assert case.top_p == 0.95
    assert case.section_task.capability_ids == (
        "binding.curve",
        "binding.raster",
        "section.log_plot",
        "track.array",
        "track.normal",
        "track.reference",
    )
    assert case.section_context.sections[0].section_id is None
    assert "wp.section" in _SDK_REFERENCE


def test_section_task_preserves_exact_channel_facts_without_legacy_ids() -> None:
    """The A/B adapter retains semantic channels without copying component identity."""
    task = _section_task(_case().section_plan)

    assert any("exact scalar source channel 'CBL'" in item for item in task.requirements)
    assert any("exact array source channel 'VDL'" in item for item in task.requirements)
    assert all("binding_id" not in item for item in task.requirements)
    assert all("main_pass.cbl" not in item for item in task.requirements)


def test_common_acceptance_requires_all_cbl_track_roles() -> None:
    """The shared evaluator accepts the frozen shape and rejects missing VDL."""
    case = _case()
    contract = _frozen_contract()
    artifact = LogPlotSectionArtifact.model_validate(contract["artifacts"]["sections"]["main_pass"])
    intent = AuthoringDocumentIntent.model_validate(
        {"sections": [artifact.section.model_dump(mode="python", exclude_unset=True)]}
    )

    accepted = evaluate_section_intent(intent, case)
    assert accepted.canonical_intent_valid is True
    assert accepted.private_application_valid is True
    assert accepted.success is True
    assert accepted.legacy_target_id_match is True

    combo_index = next(
        index for index, track in enumerate(intent.sections[0].tracks) if track.track_id == "combo"
    )
    combo = intent.sections[0].tracks[combo_index]
    extra_binding = combo.bindings[0].model_copy(
        update={"binding_id": "extra-binding", "channel": "ECGR_STGC"}
    )
    extra_combo = combo.model_copy(update={"bindings": [*combo.bindings, extra_binding]})
    with_extra_binding = intent.model_copy(
        update={
            "sections": [
                intent.sections[0].model_copy(
                    update={
                        "tracks": [
                            extra_combo if index == combo_index else track
                            for index, track in enumerate(intent.sections[0].tracks)
                        ]
                    }
                )
            ]
        }
    )
    rejected_extra = evaluate_section_intent(with_extra_binding, case)
    assert rejected_extra.success is False
    assert "combo track contains unrequested or incomplete bindings" in (
        rejected_extra.unrequested_mutations
    )

    without_vdl = intent.model_copy(
        update={
            "sections": [
                intent.sections[0].model_copy(update={"tracks": intent.sections[0].tracks[:-1]})
            ]
        }
    )
    rejected = evaluate_section_intent(without_vdl, case)
    assert rejected.success is False
    assert "missing array VDL track" in rejected.semantic_omissions


def test_three_fake_pairs_do_not_satisfy_live_gate() -> None:
    """Fake evidence remains ineligible for the live CM-43 decision gate."""
    case = _case()
    contract = _frozen_contract()
    v1_payload = contract["artifacts"]["sections"]["main_pass"]
    rows = asyncio.run(
        run_ab(
            case,
            v1_model_factory=lambda _case: _V1FixtureModel(payload=v1_payload),
            v2_backend_factory=lambda _case: _V2FixtureBackend(source=_v2_scalar_program()),
            live=False,
        )
    )

    assert len(rows) == 6
    assert {row["engine"] for row in rows} == {"v1", "v2"}
    assert all(row["live"] is False for row in rows)
    assert all(row["provider"] == "fake" for row in rows)
    assert all(row["model"] == "fake-model" for row in rows)
    assert len({row["experiment_fingerprint"] for row in rows}) == 1
    assert all(row["legacy_core_reached"] is False for row in rows)
    assert all(row["schema_chars"] == 0 for row in rows if row["engine"] == "v2")
    assert all(row["dynamic_schema_chars"] != 0 for row in rows if row["engine"] == "v1")
    assert all(
        row["representability_status"] != "sdk_prompt_contract_insufficient"
        for row in rows
        if row["engine"] == "v2"
    )
    gate = evaluate_gate(rows)
    assert gate == {
        "ready": False,
        "decision": None,
        "reason": "CM-43 requires at least three live runs for each engine.",
    }


def test_v2_program_source_is_hashed_and_not_stored_in_evidence() -> None:
    """Evidence stores program provenance without storing generated source text."""
    case = _case()
    rows = asyncio.run(
        run_ab(
            case,
            v1_model_factory=lambda _case: _V1FixtureModel(payload={}),
            v2_backend_factory=lambda _case: _V2FixtureBackend(source=_v2_scalar_program()),
            live=False,
        )
    )
    v2_rows = [row for row in rows if row["engine"] == "v2"]
    assert v2_rows
    assert all(isinstance(row["program_hash"], str) for row in v2_rows)
    assert all(_v2_scalar_program() not in json.dumps(row) for row in v2_rows)


def _live_gate_rows(
    case: CBLExperimentCase,
    *,
    v1_acceptance: tuple[bool, bool, bool],
    v2_acceptance: tuple[bool, bool, bool],
    fingerprint: str | None = None,
    v2_gap: bool = False,
) -> list[dict[str, object]]:
    """Build minimal live evidence rows for deterministic gate tests."""
    rows: list[dict[str, object]] = []
    for engine, outcomes in (("v1", v1_acceptance), ("v2", v2_acceptance)):
        for index, accepted in enumerate(outcomes, start=1):
            rows.append(
                {
                    "engine": engine,
                    "run_index": index,
                    "live": True,
                    "experiment_fingerprint": fingerprint or case.experiment_fingerprint,
                    "acceptance_success": accepted,
                    "representability_status": (
                        "sdk_prompt_contract_insufficient"
                        if engine == "v2" and v2_gap
                        else "complete"
                    ),
                    "dynamic_schema_chars": 100 if engine == "v1" else 0,
                    "provider_generation_calls": 2 if engine == "v1" else 1,
                }
            )
    return rows


def test_gate_proceeds_only_when_v2_is_competitive_and_simpler() -> None:
    """The positive gate requires both acceptance parity and material simplicity."""
    case = _case()
    gate = evaluate_gate(
        _live_gate_rows(
            case,
            v1_acceptance=(True, True, False),
            v2_acceptance=(True, True, False),
        )
    )
    assert gate["ready"] is True
    assert gate["decision"] == "PROCEED"


def test_gate_stops_when_v2_acceptance_is_lower_even_if_simpler() -> None:
    """A complexity advantage must not excuse a v2 reliability regression."""
    case = _case()
    gate = evaluate_gate(
        _live_gate_rows(
            case,
            v1_acceptance=(True, True, True),
            v2_acceptance=(True, True, False),
        )
    )
    assert gate["ready"] is True
    assert gate["decision"] == "STOP_V2_REGRESSION"


def test_gate_stops_when_v2_is_not_materially_simpler() -> None:
    """Competitive acceptance without a measured complexity advantage is inconclusive."""
    case = _case()
    rows = _live_gate_rows(
        case,
        v1_acceptance=(True, True, True),
        v2_acceptance=(True, True, True),
    )
    for row in rows:
        row["dynamic_schema_chars"] = 100
        row["provider_generation_calls"] = 2
    gate = evaluate_gate(rows)
    assert gate["ready"] is True
    assert gate["decision"] == "STOP_V2_REGRESSION"


def test_gate_stops_for_published_sdk_context_gap() -> None:
    """A missing published capability blocks the A/B decision before scoring."""
    case = _case()
    gate = evaluate_gate(
        _live_gate_rows(
            case,
            v1_acceptance=(True, True, True),
            v2_acceptance=(True, True, True),
            v2_gap=True,
        )
    )
    assert gate["ready"] is True
    assert gate["decision"] == "STOP_SDK_CONTEXT_GAP"


def test_gate_rejects_an_engine_with_only_provider_configuration_failures() -> None:
    """Configuration failures cannot be counted as live architecture evidence."""
    case = _case()
    rows = _live_gate_rows(
        case,
        v1_acceptance=(True, True, True),
        v2_acceptance=(True, True, True),
        v2_gap=True,
    )
    for row in rows:
        if row["engine"] == "v2":
            row["failure_stage"] = "provider"
            row["failure_code"] = "configuration"

    gate = evaluate_gate(rows)

    assert gate == {
        "ready": False,
        "decision": None,
        "reason": "CM-43 v2 runs never reached a valid provider transaction.",
    }


def test_v2_factory_exposes_awaitable_chat_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The live v2 factory must supply an async Chat Completions client."""

    class AsyncCompletions:
        async def create(self, **arguments: object) -> dict[str, object]:
            return arguments

    class AsyncChat:
        completions = AsyncCompletions()

    class AsyncClient:
        chat = AsyncChat()

    raw_client = AsyncClient()
    monkeypatch.setattr(
        "scripts.run_cbl_section_ab._load_async_openai_client",
        lambda _settings: raw_client,
    )
    settings = _GenerationSettings(
        base_url="https://provider.example/v1",
        api_key="redacted",
        temperature=1.0,
        top_p=0.95,
        max_output_tokens=16384,
        max_tokens_parameter="max_tokens",
        timeout_seconds=300.0,
    )
    _v1_factory, v2_factory = _factory_pair(
        root=Path.cwd(),
        settings=settings,
        model="fake-model",
    )

    backend = v2_factory(_case())
    configured = backend.client
    request = configured.chat.completions.create(model="fake-model")

    assert inspect.isawaitable(request)
    arguments = asyncio.run(request)
    assert arguments["temperature"] == 1.0
    assert arguments["top_p"] == 0.95
    assert arguments["max_tokens"] == 16384


def test_gate_rejects_mixed_experiment_fingerprints() -> None:
    """Rows from different provider/settings/corpus configurations cannot mix."""
    case = _case()
    rows = _live_gate_rows(
        case,
        v1_acceptance=(True, True, True),
        v2_acceptance=(True, True, True),
        fingerprint="different-experiment",
    )
    rows[-1]["experiment_fingerprint"] = case.experiment_fingerprint
    gate = evaluate_gate(rows)
    assert gate == {
        "ready": False,
        "decision": None,
        "reason": "CM-43 evidence rows must share one experiment fingerprint.",
    }


def test_legacy_backend_recorder_keeps_only_aggregate_metrics() -> None:
    """The v1 measurement wrapper records counts without retaining provider text."""

    class Backend:
        async def run_authoring(self, **_kwargs: object) -> object:
            return SimpleNamespace(
                report_facts={
                    "input_tokens": 7,
                    "output_tokens": 5,
                    "total_tokens": 12,
                    "correction_count": 1,
                    "provider_response": "must not be copied",
                }
            )

    recorder = LegacyBackendRecorder(Backend())
    asyncio.run(recorder.run_authoring())
    assert recorder.provider_generation_calls == 1
    assert recorder.input_tokens == 7
    assert recorder.output_tokens == 5
    assert recorder.total_tokens == 12
    assert recorder.repair_count == 1
    assert recorder.provider_latency_ms != "not_available"
    assert not hasattr(recorder, "provider_response")
