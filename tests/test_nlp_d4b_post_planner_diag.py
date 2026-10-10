"""Provider-free reproduction of the D4 CBL post-planner path."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.section_leaf_safety import project_section_leaf_request
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class _CblDeterministicBackend:
    """Return one validated CBL plan and bounded worker programs."""

    def __init__(self, request: str) -> None:
        self.request = request
        self.structured_calls = 0
        self.program_calls = 0
        self.last_stage = "constructed"

    def _plan(self) -> SemanticPlan:
        return SemanticPlan(
            summary="Reconstruct the supported cased-hole CBL/VDL packet subset.",
            report_task=ReportTask(
                goal="Compile the requested heading, remarks, and tail.",
                capability_ids=("report.standard",),
                requirements=(self.request,),
            ),
            section_tasks=(
                SectionTask(
                    goal="Compile the main pass CBL/VDL strip section.",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "track.reference",
                        "track.array",
                        "binding.curve",
                        "binding.raster",
                    ),
                    existing_section_hint="Main Pass",
                    source_hints=("CBL_Main.dlis",),
                    requirements=("Preserve the main pass section.",),
                ),
                SectionTask(
                    goal="Compile the repeat pass CBL/VDL strip section.",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "track.reference",
                        "track.array",
                        "binding.curve",
                        "binding.raster",
                    ),
                    existing_section_hint="Repeat Pass",
                    source_hints=("CBL_Repeat.dlis",),
                    requirements=("Preserve the repeat pass section.",),
                ),
            ),
        )

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[SemanticPlan],
    ) -> StructuredGenerationResult[SemanticPlan]:
        del request
        assert response_model is SemanticPlan
        self.last_stage = "planner_complete"
        self.structured_calls += 1
        return StructuredGenerationResult(
            value=self._plan(),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        self.program_calls += 1
        if '"report_task"' in request.user_prompt:
            self.last_stage = "report_worker_started"
            program = 'report = wp.report(title="D4 CBL scaffold")\n'
        else:
            self.last_stage = "section_worker_started"
            title = "Repeat Pass" if "repeat_pass" in request.user_prompt else "Main Pass"
            program = (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                f"wp.update_section(section, title={title!r})\n"
            )
        return ProgramGenerationResult(
            text=program,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _RecordingNotebookSession:
    """Retain only the bounded public result for local stage diagnosis."""

    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.result: object | None = None

    @property
    def provider(self) -> str:
        return self.delegate.provider

    @property
    def model(self) -> str:
        return self.delegate.model

    async def run(self, **kwargs: object) -> object:
        self.result = await self.delegate.run(**kwargs)
        return self.result

    async def render_logfile_to_file(self, **kwargs: object) -> object:
        return await self.delegate.render_logfile_to_file(**kwargs)


def test_d4_cbl_post_planner_path_reproduces_provider_free() -> None:
    """Exercise the exact CBL adapter path without a provider or campaign state."""
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-C01:C01")
    expected = next(
        item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == "D4-C01:C01"
    )
    backend = _CblDeterministicBackend(str(case["request"]))

    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        artifact_root = Path(temporary)
        production_session = d4.build_notebook_session(
            backend=backend,
            provider="deterministic",
            model="d4-post-planner-diagnostic",
            server_root=REPO_ROOT,
            credential_source="diagnostic",
            timeout=10.0,
        )
        session = _RecordingNotebookSession(production_session)
        adapter = d4.D4CampaignAdapter(
            repo_root=REPO_ROOT,
            artifact_root=artifact_root,
            session=session,
            call_source=d4.CampaignCallSource(backends=(), calls=[]),
        )

        try:
            actual = asyncio.run(adapter.execute_turn(case, expected))
        except Exception as error:
            raise AssertionError(
                f"Stage A failed after {backend.last_stage}: {type(error).__name__}"
            ) from error

    assert backend.structured_calls == 1
    report_facts = getattr(session.result, "report_facts", None)
    if backend.program_calls != 3:
        raise AssertionError(f"stage={backend.last_stage}; report_facts={report_facts!r}")
    assert actual["persisted"] is True


def test_frozen_cbl_request_projects_scalar_curve_intent() -> None:
    """The mixed CBL/VDL request must not enter the raster-only ambiguity guard."""
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-C01:C01")
    evidence = project_section_leaf_request(str(case["request"]))
    assert evidence.curve_explicit is True
    assert evidence.raster_explicit is True
