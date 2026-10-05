"""D1 public-path acceptance tests for an existing-curve scale revision."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml
from scripts.verify_las_revision import verify_las_revision
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent.code_mode.enrichment import SemanticEnricher
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.direct_notebook import DirectNotebookSession
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderMetrics,
)
from wellplot.agent.session import AgentSession, AgentSessionConfig
from wellplot.api.serialize import report_to_dict
from wellplot.authoring import authoring_document_to_logfile_mapping, load_authoring_document
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.logfile import load_logfile

REQUEST = "Change the Gamma Ray curve scale to a linear scale from 10 to 100."


@dataclass
class _RevisionPlanner:
    """Return one deterministic existing-section task without provider calls."""

    calls: list[dict[str, object]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record revision context and return one existing-section task."""
        self.calls.append(kwargs)
        return SemanticPlan(
            summary="D1 existing curve scale revision",
            section_tasks=(
                SectionTask(
                    goal="Change the existing Gamma Ray curve scale.",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "binding.curve",
                    ),
                    existing_section_hint="Main Log",
                    requirements=(
                        "Update the existing Gamma Ray curve to a linear scale from 10 to 100.",
                    ),
                ),
            ),
        )


@dataclass
class _RevisionBackend:
    """Return one fixed grounded program for the section worker."""

    track_id: str
    binding_id: str
    requests: list[ProgramGenerationRequest]

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Record the worker prompt and return the deterministic revision program."""
        self.requests.append(request)
        assert "Grounded existing curve inventory" in request.user_prompt
        source = (
            "report = wp.report()\n"
            "section = wp.target_section(report)\n"
            f"track = wp.target_track(section, track_id={self.track_id!r})\n"
            f"curve = wp.target_curve(track, binding_id={self.binding_id!r})\n"
            "wp.update_curve(track, curve, scale_minimum=10, scale_maximum=100, "
            "scale_kind='linear', reverse=False)\n"
        )
        return ProgramGenerationResult(
            text=source,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _UnusedReportCompiler:
    """Fail if the scale-only revision dispatches a report worker."""

    async def compile(self, **_kwargs: object) -> object:
        """Reject unexpected report work."""
        raise AssertionError("D1 scale revision must not dispatch report work")


def _revision_fixture(directory: Path, *, minimum: float = 0.0) -> Path:
    """Create one LAS-backed canonical request fixture with a known initial scale."""
    fixture = create_mcp_fixture_paths(directory)
    mapping = copy.deepcopy(yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8")))
    for binding in mapping["document"]["bindings"]["channels"]:
        if binding["channel"] == "GR":
            binding["scale"] = {"kind": "linear", "min": minimum, "max": 100.0}
    logfile = directory / "d1-scale-revision.log.yaml"
    logfile.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return logfile


def _document_and_target(logfile: Path) -> tuple[object, str, str, int, int]:
    """Resolve the fixture and return its exact GR identity and indexes."""
    spec = load_logfile(logfile, allowed_root=REPO_ROOT)
    document = AuthoringService.from_mapping(report_to_dict(spec)).document
    section = document.sections[0]
    for track_index, track in enumerate(section.tracks):
        for binding_index, binding in enumerate(getattr(track, "bindings", ())):
            if binding.channel == "GR" and binding.kind == "curve":
                return document, track.id, binding.binding_id, track_index, binding_index
    raise AssertionError("D1 fixture did not contain a grounded GR curve")


def _acceptance(
    track_index: int,
    binding_index: int,
    section_id: str,
    *,
    before_minimum: float = 0.0,
    after_minimum: float = 10.0,
) -> dict[str, object]:
    """Build D1's harness-owned LAS acceptance specification."""
    scale_path = f"/sections/0/tracks/{track_index}/bindings/{binding_index}/scale"
    return {
        "before_assertions": [
            {"path": "/sections/0/id", "operator": "equals", "value": section_id}
        ],
        "required_changes": {
            "LAS-05": {
                "before": [
                    {
                        "path": f"{scale_path}/minimum",
                        "operator": "equals",
                        "value": before_minimum,
                    },
                    {"path": f"{scale_path}/maximum", "operator": "equals", "value": 100.0},
                ],
                "after": [
                    {
                        "path": f"{scale_path}/minimum",
                        "operator": "equals",
                        "value": after_minimum,
                    },
                    {"path": f"{scale_path}/maximum", "operator": "equals", "value": 100.0},
                ],
            }
        },
        "allowed_change_paths": [
            scale_path,
            "/extensions/compatibility/legacy_document/bindings/channels/2/scale",
            "/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/scale",
        ],
        "prohibited_change_paths": ["/remarks", "/header"],
        "expected_outcome": "accepted",
    }


def _adapter(planner: _RevisionPlanner, backend: _RevisionBackend) -> DirectNotebookSession:
    """Build the real public notebook session with deterministic backends."""
    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=planner,  # type: ignore[arg-type]
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": REPO_ROOT},
        ),
        report_compiler=_UnusedReportCompiler(),  # type: ignore[arg-type]
        section_compiler=ProgramSectionCompiler(backend=backend, registry=registry),
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=10.0),
        ),
        provider="deterministic",
        model="d1-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )


def test_d1_public_revision_persists_renders_and_passes_frozen_las_verifier() -> None:
    """Exercise the public revise path through persistence and a real render."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_path = directory / "before.log.yaml"
        document, track_id, binding_id, track_index, binding_index = _document_and_target(logfile)
        before_path.write_text(
            yaml.safe_dump(authoring_document_to_logfile_mapping(document), sort_keys=False),
            encoding="utf-8",
        )
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(track_id=track_id, binding_id=binding_id, requests=[])
        adapter = _adapter(planner, backend)

        result = asyncio.run(adapter.revise(feedback=REQUEST, logfile_path=logfile))
        render_path = directory / "d1-render.pdf"
        render_result = asyncio.run(
            adapter.render_logfile_to_file(
                logfile_path=logfile,
                output_path=render_path,
                overwrite=True,
            )
        )
        after_document = load_authoring_document(logfile)
        target = after_document.model_dump(mode="json")["sections"][0]["tracks"][track_index][
            "bindings"
        ][binding_index]
        verdict = verify_las_revision(
            before_path,
            logfile,
            _acceptance(track_index, binding_index, document.sections[0].id),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        render_written = render_path.is_file() and render_path.stat().st_size > 0

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert result.report_facts["success"] is True, result.user_report_text
    assert result.request_kind == "revise"
    assert planner.calls[0]["mode"] == "revise"
    assert planner.calls[0]["request"] == REQUEST
    assert planner.calls[0]["current_document_summary"]
    assert len(backend.requests) == 1
    assert target["scale"]["minimum"] == 10.0
    assert target["scale"]["maximum"] == 100.0
    assert render_result
    assert render_written
    assert statuses["LAS-01"] == "PASS"
    assert statuses["LAS-05"] == "PASS"
    assert statuses["LAS-07"] == "PASS"
    assert statuses["LAS-09"] == "PASS"


def test_d1_public_revision_cannot_credit_an_already_satisfied_scale_change() -> None:
    """The integrated route leaves a no-op unchanged and LAS-05 fails closed."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory, minimum=10.0)
        before_path = directory / "before.log.yaml"
        before_text = logfile.read_text(encoding="utf-8")
        before_path.write_text(before_text, encoding="utf-8")
        document, track_id, binding_id, track_index, binding_index = _document_and_target(logfile)
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(track_id=track_id, binding_id=binding_id, requests=[])
        result = asyncio.run(
            _adapter(planner, backend).revise(feedback=REQUEST, logfile_path=logfile)
        )
        verdict = verify_las_revision(
            before_path,
            logfile,
            _acceptance(
                track_index,
                binding_index,
                document.sections[0].id,
                before_minimum=10.0,
                after_minimum=10.0,
            ),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        after_text = logfile.read_text(encoding="utf-8")

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert result.report_facts["success"] is True
    assert result.report_facts["apply_status"] == "no_op"
    assert after_text == before_text
    assert statuses["LAS-05"] == "FAIL"


def test_d1_nonexistent_grounded_curve_fails_without_mutation() -> None:
    """An invented binding identity is rejected before canonical application."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_text = logfile.read_text(encoding="utf-8")
        _document, track_id, _binding_id, _track_index, _binding_index = _document_and_target(
            logfile
        )
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(track_id=track_id, binding_id="invented.binding", requests=[])
        result = asyncio.run(
            _adapter(planner, backend).revise(feedback=REQUEST, logfile_path=logfile)
        )
        after_text = logfile.read_text(encoding="utf-8")

    assert result.report_facts["success"] is False
    assert after_text == before_text


def test_d1_worker_prompt_contains_only_grounded_curve_inventory() -> None:
    """The revision worker sees exact current identities, not arbitrary document state."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        _document, track_id, binding_id, _track_index, _binding_index = _document_and_target(
            logfile
        )
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(track_id=track_id, binding_id=binding_id, requests=[])
        result = asyncio.run(
            _adapter(planner, backend).revise(feedback=REQUEST, logfile_path=logfile)
        )

    assert result.report_facts["success"] is True
    prompt = backend.requests[0].user_prompt
    assert track_id in prompt
    assert binding_id in prompt
    assert "target_section(report, section_id" not in prompt
    assert "source_path" not in prompt


@pytest.mark.parametrize(
    "bad_track,bad_binding", [("missing-track", "missing-binding"), ("gr", "missing-binding")]
)
def test_d1_invalid_identity_fails_without_backend_network(
    bad_track: str,
    bad_binding: str,
) -> None:
    """Invalid exact handles cannot reach persistence or a network backend."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_text = logfile.read_text(encoding="utf-8")
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(track_id=bad_track, binding_id=bad_binding, requests=[])
        result = asyncio.run(
            _adapter(planner, backend).revise(feedback=REQUEST, logfile_path=logfile)
        )
        assert logfile.read_text(encoding="utf-8") == before_text
        assert result.report_facts["success"] is False
