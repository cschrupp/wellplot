"""D2B public-path acceptance tests for a grounded track and curve revision."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

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

FROZEN_D2B_REQUEST = (
    'In the Main Log section, add a new normal track titled "Caliper QC" at the end, '
    '28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear scale '
    "from 6 to 12."
)
NEW_TRACK_TITLE = "Caliper QC"
NEW_CHANNEL = "CALI"


@dataclass
class _RevisionPlanner:
    """Return one deterministic existing-section task without provider calls."""

    calls: list[dict[str, object]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record public planner context and return the D2B section task."""
        self.calls.append(kwargs)
        return SemanticPlan(
            summary="D2B add grounded Caliper QC track",
            section_tasks=(
                SectionTask(
                    goal="Add a Caliper QC track using the inspected CALI channel.",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "binding.curve",
                    ),
                    existing_section_hint="Main Log",
                    requirements=(FROZEN_D2B_REQUEST,),
                ),
            ),
        )


@dataclass
class _RevisionBackend:
    """Return a controlled section program after inspecting grounded worker context."""

    channel: str
    requests: list[ProgramGenerationRequest]

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Verify source grounding and return one restricted track/curve program."""
        self.requests.append(request)
        payload_start = request.user_prompt.index('{"capabilities":')
        payload = json.loads(request.user_prompt[payload_start:])
        section_context = payload["section_context"]
        assert section_context["target"]["kind"] == "existing"
        sources = section_context["sources"]
        assert sources
        assert any(source["candidate_id"] == "source-1" for source in sources)
        source_channels = [channel for source in sources for channel in source["channels"]]
        assert any(
            channel["mnemonic"] == NEW_CHANNEL and channel["kind"] == "scalar"
            for channel in source_channels
        )
        assert "Grounded existing curve inventory" in request.user_prompt
        assert "wp.track(section)" in request.user_prompt
        assert "wp.curve(track)" in request.user_prompt
        source = (
            "report = wp.report()\n"
            "section = wp.target_section(report)\n"
            "track = wp.track(section, id_hint='caliper_qc', kind='normal', "
            "title='Caliper QC', width_mm=28)\n"
            f"wp.curve(track, channel={self.channel!r}, id_hint='caliper_qc', "
            "label='Caliper QC', scale_minimum=6, scale_maximum=12, "
            "scale_kind='linear', reverse=False)\n"
        )
        return ProgramGenerationResult(
            text=source,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _UnusedReportCompiler:
    """Fail if the structural revision dispatches report work."""

    calls = 0

    async def compile(self, **_kwargs: object) -> object:
        """Reject unexpected report work and retain an invocation count."""
        self.calls += 1
        raise AssertionError("D2B structural revision must not dispatch report work")


def _revision_fixture(directory: Path) -> Path:
    """Create the repository LAS-backed fixture used by D2B."""
    fixture = create_mcp_fixture_paths(directory)
    logfile = directory / "d2b-track-curve-revision.log.yaml"
    logfile.write_text(fixture.single_logfile.read_text(encoding="utf-8"), encoding="utf-8")
    return logfile


def _document_and_inventory(logfile: Path) -> tuple[object, list[str], str, str]:
    """Load the canonical fixture and return ordered tracks plus CALI identities."""
    spec = load_logfile(logfile, allowed_root=REPO_ROOT)
    document = AuthoringService.from_mapping(report_to_dict(spec)).document
    assert len(document.sections) == 1
    section = document.sections[0]
    assert section.id == "main"
    assert section.title == "Main Log"
    track_ids = [track.id for track in section.tracks]
    assert track_ids == ["depth", "cbl", "vdl", "gr", "cali", "rt"]
    cali_bindings = [
        binding
        for track in section.tracks
        for binding in getattr(track, "bindings", ())
        if binding.channel == NEW_CHANNEL
    ]
    assert len(cali_bindings) == 1
    return document, track_ids, cali_bindings[0].binding_id, section.id


def _adapter(
    planner: _RevisionPlanner,
    backend: _RevisionBackend,
    report_compiler: _UnusedReportCompiler,
) -> DirectNotebookSession:
    """Build the real public notebook session with deterministic backends."""
    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=planner,  # type: ignore[arg-type]
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": REPO_ROOT},
        ),
        report_compiler=report_compiler,  # type: ignore[arg-type]
        section_compiler=ProgramSectionCompiler(backend=backend, registry=registry),
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=10.0),
        ),
        provider="deterministic",
        model="d2b-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )


def _acceptance() -> dict[str, object]:
    """Build D2B's harness-owned LAS acceptance specification."""
    track_path = "/sections/0/tracks/6"
    binding_path = f"{track_path}/bindings/0"
    return {
        "before_assertions": [
            {"path": "/sections/0/id", "operator": "equals", "value": "main"},
            {"path": "/sections/0/title", "operator": "equals", "value": "Main Log"},
        ],
        "required_changes": {
            "LAS-03": {
                "before": [
                    {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"}
                ],
                "after": [
                    {"path": f"{track_path}/title", "operator": "equals", "value": NEW_TRACK_TITLE},
                    {"path": f"{track_path}/kind", "operator": "equals", "value": "normal"},
                    {"path": f"{track_path}/width_mm", "operator": "equals", "value": 28.0},
                ],
            },
            "LAS-04": {
                "before": [
                    {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"}
                ],
                "after": [
                    {"path": f"{binding_path}/kind", "operator": "equals", "value": "curve"},
                    {
                        "path": f"{binding_path}/channel",
                        "operator": "equals",
                        "value": NEW_CHANNEL,
                    },
                    {
                        "path": f"{binding_path}/label",
                        "operator": "equals",
                        "value": NEW_TRACK_TITLE,
                    },
                    {"path": f"{binding_path}/scale/kind", "operator": "equals", "value": "linear"},
                    {"path": f"{binding_path}/scale/minimum", "operator": "equals", "value": 6.0},
                    {"path": f"{binding_path}/scale/maximum", "operator": "equals", "value": 12.0},
                ],
            },
        },
        "allowed_change_paths": [
            track_path,
            "/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/6",
            "/extensions/compatibility/legacy_document/bindings/channels/5",
        ],
        "prohibited_change_paths": [
            "/title",
            "/subtitle",
            "/header",
            "/remarks",
            "/page",
            "/depth",
            "/output",
            "/sections/0/data_source",
            "/sections/0/tracks/0",
            "/sections/0/tracks/1",
            "/sections/0/tracks/2",
            "/sections/0/tracks/3",
            "/sections/0/tracks/4",
            "/sections/0/tracks/5",
        ],
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


def test_d2b_public_revision_persists_renders_and_passes_frozen_las_verifier() -> None:
    """Exercise source grounding, structural revision, persistence, and rendering."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_document, before_track_ids, old_cali_binding_id, _section_id = (
            _document_and_inventory(logfile)
        )
        before_path = _before_path(directory, before_document)
        normalized_before = load_authoring_document(before_path)
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(channel=NEW_CHANNEL, requests=[])
        report_compiler = _UnusedReportCompiler()
        adapter = _adapter(planner, backend, report_compiler)

        result = asyncio.run(adapter.revise(feedback=FROZEN_D2B_REQUEST, logfile_path=logfile))
        render_path = directory / "d2b-render.pdf"
        render_result = asyncio.run(
            adapter.render_logfile_to_file(
                logfile_path=logfile,
                output_path=render_path,
                overwrite=True,
            )
        )
        after_document = load_authoring_document(logfile)
        after_section = after_document.sections[0]
        after_track_ids = [track.id for track in after_section.tracks]
        new_track = after_section.tracks[6]
        new_binding = new_track.bindings[0]
        before_payload = normalized_before.model_dump(mode="json")
        after_payload = after_document.model_dump(mode="json")
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
    assert planner.calls[0]["request"] == FROZEN_D2B_REQUEST
    assert planner.calls[0]["current_document_summary"]
    assert len(backend.requests) == 1
    assert report_compiler.calls == 0
    assert len(before_track_ids) == 6
    assert after_track_ids[:6] == before_track_ids
    assert len(after_track_ids) == 7
    assert after_payload["sections"][0]["tracks"][:6] == before_payload["sections"][0]["tracks"]
    assert after_payload["sections"][0]["id"] == before_payload["sections"][0]["id"]
    assert after_payload["sections"][0]["title"] == before_payload["sections"][0]["title"]
    assert after_payload["sections"][0]["subtitle"] == before_payload["sections"][0]["subtitle"]
    for field in ("title", "subtitle", "header", "remarks", "page", "depth", "output", "tail"):
        assert after_payload[field] == before_payload[field]
    assert new_track.id
    assert new_track.kind == "normal"
    assert new_track.title == NEW_TRACK_TITLE
    assert new_track.width_mm == 28
    assert len(new_track.bindings) == 1
    assert new_binding.binding_id
    assert new_binding.binding_id != old_cali_binding_id
    assert new_binding.kind == "curve"
    assert new_binding.channel == NEW_CHANNEL
    assert new_binding.label == NEW_TRACK_TITLE
    assert new_binding.scale.kind == "linear"
    assert new_binding.scale.minimum == 6
    assert new_binding.scale.maximum == 12
    assert new_binding.scale.reverse is False
    assert render_result
    assert render_written
    assert statuses["LAS-01"] == "PASS"
    assert statuses["LAS-03"] == "PASS"
    assert statuses["LAS-04"] == "PASS"
    assert statuses["LAS-07"] == "PASS"
    assert statuses["LAS-09"] == "PASS"


def test_d2b_ungrounded_channel_fails_without_persistence() -> None:
    """A channel absent from inspected source metadata fails closed before persistence."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_text = logfile.read_text(encoding="utf-8")
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(channel="NOT_A_CHANNEL", requests=[])
        result = asyncio.run(
            _adapter(planner, backend, _UnusedReportCompiler()).revise(
                feedback=FROZEN_D2B_REQUEST,
                logfile_path=logfile,
            )
        )
        after_text = logfile.read_text(encoding="utf-8")

    assert result.report_facts["success"] is False
    assert result.report_facts["apply_status"] != "persisted"
    assert after_text == before_text


def test_d2b_worker_ownership_isolated_to_one_section_worker() -> None:
    """The submitted intent contains only one existing-section structural fragment."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(channel=NEW_CHANNEL, requests=[])
        report_compiler = _UnusedReportCompiler()
        result = asyncio.run(
            _adapter(planner, backend, report_compiler).revise(
                feedback=FROZEN_D2B_REQUEST,
                logfile_path=logfile,
            )
        )

    submitted = result.submitted_intent or {}
    sections = submitted.get("sections") or []
    assert len(sections) == 1
    assert report_compiler.calls == 0
    assert len(backend.requests) == 1
    assert sections[0]["section_id"] == "main"
    assert len(sections[0]["tracks"]) == 1
    assert sections[0]["tracks"][0]["title"] == NEW_TRACK_TITLE
    assert len(sections[0]["tracks"][0]["bindings"]) == 1
    assert sections[0]["tracks"][0]["bindings"][0]["channel"] == NEW_CHANNEL
    assert all(
        field not in submitted
        for field in (
            "title",
            "subtitle",
            "header",
            "remarks",
            "page",
            "depth",
            "output",
            "tail",
            "fills",
            "annotations",
            "removals",
        )
    )


def test_d2b_collateral_existing_track_mutation_fails_las_07() -> None:
    """A valid new track plus an existing-track mutation fails preservation."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        before = _revision_fixture(directory)
        document, _track_ids, _old_binding_id, _section_id = _document_and_inventory(before)
        before_path = _before_path(directory, document)
        after = directory / "collateral-after.log.yaml"
        mapping = yaml.safe_load(before.read_text(encoding="utf-8"))
        section = mapping["document"]["layout"]["log_sections"][0]
        section["tracks"].append(
            {
                "id": "caliper_qc",
                "title": NEW_TRACK_TITLE,
                "kind": "normal",
                "width_mm": 28.0,
            }
        )
        mapping["document"]["bindings"]["channels"].append(
            {
                "channel": NEW_CHANNEL,
                "track_id": "caliper_qc",
                "kind": "curve",
                "label": NEW_TRACK_TITLE,
                "scale": {"kind": "linear", "min": 6.0, "max": 12.0, "reverse": False},
                "section": "main",
            }
        )
        section["tracks"][0]["title"] = "Collateral mutation"
        after.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
        verdict = verify_las_revision(
            before_path,
            after,
            _acceptance(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert statuses["LAS-03"] == "PASS"
    assert statuses["LAS-04"] == "PASS"
    assert statuses["LAS-07"] == "FAIL"
    assert verdict["workflow_status"] == "FAIL"


def test_d2b_fixture_preserves_repeated_cali_binding_identity() -> None:
    """The starting fixture contains one legitimate CALI binding to preserve."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        logfile = _revision_fixture(Path(temporary_directory))
        document, _track_ids, old_binding_id, _section_id = _document_and_inventory(logfile)

    assert document.sections[0].tracks[4].bindings[0].channel == NEW_CHANNEL
    assert old_binding_id
