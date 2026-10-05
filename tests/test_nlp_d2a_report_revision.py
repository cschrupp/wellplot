"""D2A public-path acceptance tests for a report-title revision."""

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
from wellplot.agent.code_mode.planner import ReportTask, SemanticPlan
from wellplot.agent.code_mode.report_worker import ReportProgramCompiler
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

TITLE_REQUEST = 'Change the report title to "Gamma Ray Quality Control Review".'
INITIAL_TITLE = "Original Well Log Report"
TARGET_TITLE = "Gamma Ray Quality Control Review"


@dataclass
class _ReportPlanner:
    """Return one deterministic report-only task without provider calls."""

    calls: list[dict[str, object]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record the public planner inputs and return the report task."""
        self.calls.append(kwargs)
        return SemanticPlan(
            summary="D2A report title revision",
            report_task=ReportTask(
                goal="Change the report title.",
                capability_ids=("report.standard",),
                requirements=(TITLE_REQUEST,),
            ),
        )


@dataclass
class _ReportBackend:
    """Return one fixed report program and record its worker request."""

    requests: list[ProgramGenerationRequest]

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Record the report-worker request and return the title mutation."""
        self.requests.append(request)
        return ProgramGenerationResult(
            text=f'report = wp.report(title="{TARGET_TITLE}")\n',
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _UnusedSectionCompiler:
    """Fail if the report-only revision dispatches section work."""

    calls = 0

    async def compile(self, **_kwargs: object) -> object:
        """Reject unexpected section work and retain an invocation count."""
        self.calls += 1
        raise AssertionError("D2A title revision must not dispatch section work")


def _title_fixture(directory: Path, *, title: str = INITIAL_TITLE) -> Path:
    """Create one LAS-backed fixture with a controlled canonical report title."""
    fixture = create_mcp_fixture_paths(directory)
    mapping = copy.deepcopy(yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8")))
    mapping["document"]["header"] = {
        "title": title,
        "subtitle": "D2A acceptance fixture",
    }
    logfile = directory / "d2a-report-title.log.yaml"
    logfile.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return logfile


def _document(logfile: Path) -> object:
    """Load the canonical document represented by a fixture logfile."""
    spec = load_logfile(logfile, allowed_root=REPO_ROOT)
    return AuthoringService.from_mapping(report_to_dict(spec)).document


def _adapter(
    planner: _ReportPlanner,
    backend: _ReportBackend,
    section_compiler: _UnusedSectionCompiler,
) -> DirectNotebookSession:
    """Build the real public notebook session with deterministic backends."""
    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=planner,  # type: ignore[arg-type]
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": REPO_ROOT},
        ),
        report_compiler=ReportProgramCompiler(backend=backend, registry=registry),
        section_compiler=section_compiler,  # type: ignore[arg-type]
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=10.0),
        ),
        provider="deterministic",
        model="d2a-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )


def _acceptance(
    *, expected_before: str = INITIAL_TITLE, expected_after: str = TARGET_TITLE
) -> dict[str, object]:
    """Build D2A's harness-owned LAS acceptance specification."""
    return {
        "before_assertions": [{"path": "/title", "operator": "equals", "value": expected_before}],
        "required_changes": {
            "LAS-02": {
                "before": [{"path": "/title", "operator": "equals", "value": expected_before}],
                "after": [{"path": "/title", "operator": "equals", "value": expected_after}],
            }
        },
        "allowed_change_paths": [
            "/title",
            "/extensions/compatibility/legacy_document/header/title",
        ],
        "prohibited_change_paths": ["/subtitle", "/sections", "/remarks", "/header"],
        "expected_outcome": "accepted",
    }


def _before_path(directory: Path, document: object) -> Path:
    """Persist the canonical before-state used by the frozen verifier."""
    path = directory / "before.log.yaml"
    path.write_text(
        yaml.safe_dump(authoring_document_to_logfile_mapping(document), sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_d2a_title_revision_persists_renders_and_passes_frozen_las_verifier() -> None:
    """Exercise the public revise path through persistence and a real render."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _title_fixture(directory)
        before_document = _document(logfile)
        before_path = _before_path(directory, before_document)
        planner = _ReportPlanner(calls=[])
        backend = _ReportBackend(requests=[])
        section_compiler = _UnusedSectionCompiler()
        result = asyncio.run(
            _adapter(planner, backend, section_compiler).revise(
                feedback=TITLE_REQUEST,
                logfile_path=logfile,
            )
        )
        render_path = directory / "d2a-render.pdf"
        render_adapter = _adapter(
            _ReportPlanner(calls=[]), _ReportBackend(requests=[]), _UnusedSectionCompiler()
        )
        render_result = asyncio.run(
            render_adapter.render_logfile_to_file(
                logfile_path=logfile,
                output_path=render_path,
                overwrite=True,
            )
        )
        after_document = load_authoring_document(logfile)
        verdict = verify_las_revision(
            before_path,
            logfile,
            _acceptance(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        render_written = render_path.is_file() and render_path.stat().st_size > 0

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert result.report_facts["success"] is True, result.user_report_text
    assert result.request_kind == "revise"
    assert planner.calls[0]["mode"] == "revise"
    assert planner.calls[0]["request"] == TITLE_REQUEST
    assert len(backend.requests) == 1
    assert after_document.title == TARGET_TITLE
    assert {change["path"] for change in verdict["canonical_diff"]} == {
        "/title",
        "/extensions/compatibility/legacy_document/header/title",
    }
    assert render_result
    assert render_written
    assert statuses["LAS-01"] == "PASS"
    assert statuses["LAS-02"] == "PASS"
    assert statuses["LAS-07"] == "PASS"
    assert statuses["LAS-09"] == "PASS"


def test_d2a_already_satisfied_title_has_no_transition_credit() -> None:
    """An already-satisfied title remains unchanged and LAS-02 fails closed."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _title_fixture(directory, title=TARGET_TITLE)
        before_document = _document(logfile)
        before_path = _before_path(directory, before_document)
        before_text = logfile.read_text(encoding="utf-8")
        adapter = _adapter(
            _ReportPlanner(calls=[]), _ReportBackend(requests=[]), _UnusedSectionCompiler()
        )
        result = asyncio.run(
            adapter.revise(
                feedback=TITLE_REQUEST,
                logfile_path=logfile,
            )
        )
        verdict = verify_las_revision(
            before_path,
            logfile,
            _acceptance(expected_before=TARGET_TITLE),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        after_text = logfile.read_text(encoding="utf-8")

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert result.report_facts["success"] is True
    assert result.report_facts["apply_status"] == "no_op"
    assert after_text == before_text
    assert statuses["LAS-02"] == "FAIL"


def test_d2a_report_revision_uses_report_worker_only() -> None:
    """The report route emits a sparse report intent and never section work."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _title_fixture(directory)
        planner = _ReportPlanner(calls=[])
        backend = _ReportBackend(requests=[])
        section_compiler = _UnusedSectionCompiler()
        result = asyncio.run(
            _adapter(planner, backend, section_compiler).revise(
                feedback=TITLE_REQUEST,
                logfile_path=logfile,
            )
        )

    submitted = result.submitted_intent or {}
    assert len(backend.requests) == 1
    assert section_compiler.calls == 0
    assert submitted.get("title") == TARGET_TITLE
    assert all(
        field not in submitted
        for field in (
            "sections",
            "curve_bindings",
            "raster_bindings",
            "fills",
            "annotations",
            "removals",
        )
    )


def test_d2a_collateral_mutation_fails_las_07() -> None:
    """A title change plus an unrelated semantic mutation fails preservation."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        before = _title_fixture(directory)
        after = directory / "after.log.yaml"
        mapping = yaml.safe_load(before.read_text(encoding="utf-8"))
        mapping["document"]["header"]["title"] = TARGET_TITLE
        mapping["document"]["layout"]["log_sections"][0]["title"] = "Unrelated mutation"
        after.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
        verdict = verify_las_revision(
            before,
            after,
            _acceptance(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert statuses["LAS-02"] == "PASS"
    assert statuses["LAS-07"] == "FAIL"
    assert verdict["workflow_status"] == "FAIL"


@pytest.mark.parametrize("title", [INITIAL_TITLE, TARGET_TITLE])
def test_d2a_fixture_has_expected_canonical_title(title: str) -> None:
    """The D2A fixture helper controls only the report title."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        logfile = _title_fixture(Path(temporary_directory), title=title)
        document = _document(logfile)

    assert document.title == title
