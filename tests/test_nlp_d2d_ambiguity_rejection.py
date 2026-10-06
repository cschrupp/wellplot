"""D2D public-path acceptance tests for bounded rejection behavior."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from scripts.verify_las_revision import verify_las_revision
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent import direct_notebook
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
from wellplot.authoring import load_authoring_document
from wellplot.capabilities import create_builtin_registry

AMBIGUOUS_REQUEST = "In the Main Log section, change the Gamma Ray curve scale to 10–100."
MISSING_SOURCE_REQUEST = (
    'In the Main Log section, add a normal track titled "Neutron" and plot NPHI '
    "from absent-source on it."
)
MISSING_CHANNEL_REQUEST = (
    'In the Main Log section, add a normal track titled "Neutron", 28 mm wide, '
    'and plot NPHI from fixture.las on it labeled "Neutron" with a linear scale '
    "from 0 to 45."
)


@dataclass
class _RevisionPlanner:
    """Return one deterministic section task without provider calls."""

    task: SectionTask
    calls: list[dict[str, object]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record the public planner context and return the frozen task."""
        self.calls.append(kwargs)
        return SemanticPlan(
            summary="D2D deterministic rejection task",
            section_tasks=(self.task,),
        )


@dataclass
class _FailingWorker:
    """Fail loudly if an enrichment-rejected request reaches a worker."""

    calls: int = 0

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Make unexpected worker dispatch an explicit test failure."""
        self.calls += 1
        raise AssertionError(f"worker must not run for this case: {request.user_prompt}")


@dataclass
class _UnavailableChannelWorker:
    """Inspect the real worker context, then preserve the unavailable request."""

    expected_candidate_id: str
    requests: list[ProgramGenerationRequest]
    selected_candidate_id: str | None = None
    inspected_channels: tuple[str, ...] = ()
    attempted_programs: list[str] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable evidence collections."""
        if self.attempted_programs is None:
            self.attempted_programs = []

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Assert exact source grounding and return a faithful NPHI program."""
        self.requests.append(request)
        if len(self.requests) == 1:
            payload_start = request.user_prompt.index('{"capabilities":')
            payload = json.loads(request.user_prompt[payload_start:])
            section_context = payload["section_context"]
            assert section_context["target"]["kind"] == "existing"
            sources = section_context["sources"]
            assert len(sources) == 1
            selected = sources[0]
            self.selected_candidate_id = selected["candidate_id"]
            self.inspected_channels = tuple(channel["mnemonic"] for channel in selected["channels"])
            assert self.selected_candidate_id == self.expected_candidate_id
            assert "NPHI" not in self.inspected_channels
            assert all("NPHI" not in channel.get("aliases", []) for channel in selected["channels"])
        else:
            assert "NPHI" in request.user_prompt

        source = (
            "report = wp.report()\n"
            "section = wp.target_section(report)\n"
            "track = wp.track(section, kind='normal', title='Neutron', width_mm=28)\n"
            "wp.curve(track, channel='NPHI', label='Neutron', scale_minimum=0, "
            "scale_maximum=45, scale_kind='linear', reverse=False)\n"
        )
        self.attempted_programs.append(source)
        return ProgramGenerationResult(
            text=source,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _UnusedReportCompiler:
    """Fail if any D2D case dispatches report work."""

    calls: int = 0

    async def compile(self, **_kwargs: object) -> object:
        """Reject unexpected report worker dispatch."""
        self.calls += 1
        raise AssertionError("D2D must not dispatch report work")


def _task(
    request: str,
    *,
    source_hints: tuple[str, ...] = (),
) -> SectionTask:
    """Build one bounded existing-section task for a frozen request."""
    return SectionTask(
        goal="Execute the requested D2D section revision.",
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        existing_section_hint="Main Log",
        source_hints=source_hints,
        requirements=(request,),
    )


def _revision_fixture(directory: Path) -> Path:
    """Create the repository-contained single-source LAS fixture."""
    fixture = create_mcp_fixture_paths(directory)
    logfile = directory / "d2d-revision.log.yaml"
    logfile.write_text(fixture.single_logfile.read_text(encoding="utf-8"), encoding="utf-8")
    return logfile


def _ambiguous_fixture(directory: Path) -> Path:
    """Create two valid sections with the same title and distinct IDs."""
    fixture = create_mcp_fixture_paths(directory)
    mapping = yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8"))
    first = mapping["document"]["layout"]["log_sections"][0]
    second = {
        "id": "repeat",
        "title": "Main Log",
        "subtitle": "Repeated Main",
        "data": copy.deepcopy(first["data"]),
        "tracks": [copy.deepcopy(first["tracks"][0]) | {"id": "repeat-depth"}],
    }
    mapping["document"]["layout"]["log_sections"].append(second)
    logfile = directory / "d2d-ambiguous.log.yaml"
    logfile.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return logfile


def _adapter(
    planner: _RevisionPlanner,
    worker: object,
) -> tuple[DirectNotebookSession, _UnusedReportCompiler]:
    """Build the real direct notebook adapter with deterministic workers."""
    registry = create_builtin_registry()
    report_compiler = _UnusedReportCompiler()
    dependencies = CodeModeGraphDependencies(
        planner=planner,  # type: ignore[arg-type]
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": REPO_ROOT},
        ),
        report_compiler=report_compiler,  # type: ignore[arg-type]
        section_compiler=ProgramSectionCompiler(backend=worker, registry=registry),  # type: ignore[arg-type]
    )
    adapter = DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=10.0),
        ),
        provider="deterministic",
        model="d2d-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )
    return adapter, report_compiler


def _before_artifact(directory: Path, logfile: Path) -> tuple[Path, object, bytes]:
    """Capture canonical and byte-level before-state evidence."""
    document = load_authoring_document(logfile)
    before_path = directory / "before.log.yaml"
    before_path.write_bytes(logfile.read_bytes())
    return before_path, document, logfile.read_bytes()


def _rejection_acceptance(*, section_ids: tuple[str, ...]) -> dict[str, object]:
    """Build the frozen no-change D0 rejection specification."""
    return {
        "before_assertions": [
            *[
                {
                    "path": f"/sections/{index}/id",
                    "operator": "equals",
                    "value": section_id,
                }
                for index, section_id in enumerate(section_ids)
            ],
        ],
        "required_changes": {},
        "allowed_change_paths": [],
        "prohibited_change_paths": [],
        "expected_outcome": "rejected",
    }


def _assert_rejection(
    *,
    result: object,
    adapter: DirectNotebookSession,
    logfile: Path,
    before_path: Path,
    before_document: object,
    before_bytes: bytes,
    directory: Path,
    section_ids: tuple[str, ...],
) -> dict[str, object]:
    """Assert public rejection, zero mutation, reload, render, and D0 evidence."""
    report_facts = result.report_facts
    assert report_facts["success"] is False
    assert report_facts["changed"] is False
    assert report_facts["apply_status"] == "compile_failed"
    assert result.submitted_intent is None
    assert logfile.read_bytes() == before_bytes
    after_document = load_authoring_document(logfile)
    assert after_document.model_dump(mode="json") == before_document.model_dump(mode="json")

    render_path = directory / "rejected-render.pdf"
    render_result = asyncio.run(
        adapter.render_logfile_to_file(
            logfile_path=logfile,
            output_path=render_path,
            overwrite=True,
        )
    )
    assert render_result
    assert render_path.is_file()
    assert render_path.stat().st_size > 0

    verdict = verify_las_revision(
        before_path,
        logfile,
        _rejection_acceptance(section_ids=section_ids),
        execution_evidence={
            "accepted": False,
            "persisted": True,
            "rendered": True,
        },
    )
    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert statuses["LAS-01"] == "PASS"
    assert statuses["LAS-07"] == "PASS"
    assert statuses["LAS-08"] == "PASS"
    assert statuses["LAS-09"] == "PASS"
    assert verdict["workflow_status"] == "PASS"
    return verdict


def _compilation(result: object) -> dict[str, object]:
    """Return the JSON-shaped compilation evidence from a notebook result."""
    compilation = result.report_facts["compilation"]
    assert isinstance(compilation, dict)
    return compilation


def test_d2d_ambiguous_existing_section_fails_closed() -> None:
    """Ambiguous section identity rejects before any worker dispatch."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _ambiguous_fixture(directory)
        before_path, before_document, before_bytes = _before_artifact(directory, logfile)
        loaded = load_authoring_document(logfile)
        assert [(section.id, section.title) for section in loaded.sections] == [
            ("main", "Main Log"),
            ("repeat", "Main Log"),
        ]
        planner = _RevisionPlanner(_task(AMBIGUOUS_REQUEST), [])
        worker = _FailingWorker()
        adapter, report_compiler = _adapter(planner, worker)
        result = asyncio.run(adapter.revise(feedback=AMBIGUOUS_REQUEST, logfile_path=logfile))
        verdict = _assert_rejection(
            result=result,
            adapter=adapter,
            logfile=logfile,
            before_path=before_path,
            before_document=before_document,
            before_bytes=before_bytes,
            directory=directory,
            section_ids=("main", "repeat"),
        )

    compilation = _compilation(result)
    assert compilation["diagnostics"][0]["stage"] == "enrichment"
    assert compilation["diagnostics"][0]["code"] == "enrichment.section_hint_ambiguous"
    assert "multiple inspected sections" in compilation["diagnostics"][0]["message"]
    assert compilation["metrics"]["worker_count"] == 0
    assert compilation["metrics"]["successful_workers"] == 0
    assert compilation["metrics"]["failed_workers"] == 0
    assert worker.calls == 0
    assert report_compiler.calls == 0
    assert verdict["workflow_status"] == "PASS"


def test_d2d_missing_explicit_source_fails_closed() -> None:
    """An unavailable explicit source rejects before worker dispatch."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_path, before_document, before_bytes = _before_artifact(directory, logfile)
        context = direct_notebook._load_document_context(logfile, root=REPO_ROOT)
        assert len(context.source_candidates) == 1
        assert all("absent-source" not in str(candidate) for candidate in context.source_candidates)
        assert not any(path.name == "absent-source" for path in directory.rglob("*"))
        planner = _RevisionPlanner(
            _task(MISSING_SOURCE_REQUEST, source_hints=("absent-source",)), []
        )
        worker = _FailingWorker()
        adapter, report_compiler = _adapter(planner, worker)
        result = asyncio.run(adapter.revise(feedback=MISSING_SOURCE_REQUEST, logfile_path=logfile))
        verdict = _assert_rejection(
            result=result,
            adapter=adapter,
            logfile=logfile,
            before_path=before_path,
            before_document=before_document,
            before_bytes=before_bytes,
            directory=directory,
            section_ids=("main",),
        )

    compilation = _compilation(result)
    assert compilation["diagnostics"][0]["stage"] == "enrichment"
    assert compilation["diagnostics"][0]["code"] == "enrichment.source_missing"
    assert "did not match an explicit host candidate" in compilation["diagnostics"][0]["message"]
    assert compilation["metrics"]["worker_count"] == 0
    assert worker.calls == 0
    assert report_compiler.calls == 0
    assert verdict["workflow_status"] == "PASS"


def test_d2d_unavailable_channel_fails_in_private_dry_run() -> None:
    """A valid source with no NPHI rejects once the faithful worker program is dry-run."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_path, before_document, before_bytes = _before_artifact(directory, logfile)
        context = direct_notebook._load_document_context(logfile, root=REPO_ROOT)
        assert len(context.source_candidates) == 1
        candidate = context.source_candidates[0]
        assert candidate.candidate_id == "source-1"
        assert "fixture.las" in candidate.labels
        assert Path(candidate.path).name == "fixture.las"
        planner = _RevisionPlanner(
            _task(MISSING_CHANNEL_REQUEST, source_hints=("fixture.las",)), []
        )
        worker = _UnavailableChannelWorker(candidate.candidate_id, [])
        adapter, report_compiler = _adapter(planner, worker)
        result = asyncio.run(adapter.revise(feedback=MISSING_CHANNEL_REQUEST, logfile_path=logfile))
        verdict = _assert_rejection(
            result=result,
            adapter=adapter,
            logfile=logfile,
            before_path=before_path,
            before_document=before_document,
            before_bytes=before_bytes,
            directory=directory,
            section_ids=("main",),
        )

    compilation = _compilation(result)
    assert compilation["metrics"]["worker_count"] == 1
    assert compilation["metrics"]["successful_workers"] == 0
    assert compilation["metrics"]["failed_workers"] == 1
    assert compilation["metrics"]["total_repairs"] == 1
    assert len(worker.requests) == 2
    assert worker.selected_candidate_id == candidate.candidate_id
    assert "NPHI" not in worker.inspected_channels
    assert worker.attempted_programs
    assert all("channel='NPHI'" in source for source in worker.attempted_programs)
    assert all("channel='GR'" not in source for source in worker.attempted_programs)
    diagnostics = compilation["workers"][0]["diagnostics"]
    assert any(
        item["stage"] == "dry_run"
        and item["code"] == "program.dry_run_error"
        and "channel_missing: No source channel matches 'NPHI'." in item["message"]
        for item in diagnostics
    )
    assert report_compiler.calls == 0
    assert verdict["workflow_status"] == "PASS"


def test_d2d_rejected_workflow_mutation_sentinel_fails_d0() -> None:
    """The frozen verifier rejects a rejected workflow with unrelated mutation."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_path, _before_document, _before_bytes = _before_artifact(directory, logfile)
        mutated = yaml.safe_load(logfile.read_text(encoding="utf-8"))
        mutated["document"]["layout"]["log_sections"][0]["title"] = "Unauthorized"
        after = directory / "mutated.log.yaml"
        after.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
        verdict = verify_las_revision(
            before_path,
            after,
            _rejection_acceptance(section_ids=("main",)),
            execution_evidence={
                "accepted": False,
                "persisted": True,
                "rendered": True,
            },
        )

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert statuses["LAS-07"] == "FAIL"
    assert statuses["LAS-08"] == "FAIL"
    assert verdict["workflow_status"] == "FAIL"


def test_d2d_fixture_grounding_sanity_is_host_identity_separated() -> None:
    """The valid fixture exposes candidate identity separately from filename labels."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        logfile = _revision_fixture(Path(temporary_directory))
        context = direct_notebook._load_document_context(logfile, root=REPO_ROOT)

    assert len(context.source_candidates) == 1
    candidate = context.source_candidates[0]
    assert candidate.candidate_id == "source-1"
    assert "fixture.las" in candidate.labels
    assert Path(candidate.path).name == "fixture.las"
    assert all("NPHI" not in label for label in candidate.labels)
