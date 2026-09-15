"""Deterministic tests for the CM-43 CBL section A/B harness."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.cbl_section_ab import (
    CBLExperimentCase,
    evaluate_gate,
    evaluate_section_intent,
    run_ab,
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


def _case() -> CBLExperimentCase:
    return CBLExperimentCase.load(
        provider="fake",
        model="fake-model",
        run_count=3,
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
            v1_model_factory=lambda: _V1FixtureModel(payload=v1_payload),
            v2_backend_factory=lambda: _V2FixtureBackend(source=_v2_scalar_program()),
            live=False,
        )
    )

    assert len(rows) == 6
    assert {row["engine"] for row in rows} == {"v1", "v2"}
    assert all(row["live"] is False for row in rows)
    assert all(row["provider"] == "fake" for row in rows)
    assert all(row["model"] == "fake-model" for row in rows)
    assert all(row["schema_chars"] == 0 for row in rows if row["engine"] == "v2")
    assert all(row["dynamic_schema_chars"] != 0 for row in rows if row["engine"] == "v1")
    assert any(
        row["representability_status"] == "sdk_prompt_contract_insufficient"
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
            v1_model_factory=lambda: _V1FixtureModel(payload={}),
            v2_backend_factory=lambda: _V2FixtureBackend(source=_v2_scalar_program()),
            live=False,
        )
    )
    v2_rows = [row for row in rows if row["engine"] == "v2"]
    assert v2_rows
    assert all(isinstance(row["program_hash"], str) for row in v2_rows)
    assert all(_v2_scalar_program() not in json.dumps(row) for row in v2_rows)
