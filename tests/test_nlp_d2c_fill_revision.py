"""D2C public-path acceptance tests for a grounded existing-curve fill."""

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
from wellplot.authoring import (
    authoring_document_from_mapping,
    authoring_document_to_logfile_mapping,
    load_authoring_document,
)
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.logfile import load_logfile

FROZEN_D2C_REQUEST = (
    "In the Main Log section, on the GR track, fill from the Gamma Ray curve to its "
    "lower scale limit using light gray (#d9d9d9) at 25% opacity."
)
GR_TRACK_ID = "gr"
GR_BINDING_ID = "main.gr.GR.3"
FILL_KIND = "to_lower_limit"
FILL_COLOR = "#d9d9d9"
FILL_ALPHA = 0.25


@dataclass
class _RevisionPlanner:
    """Return one deterministic existing-section fill task."""

    calls: list[dict[str, object]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record the public planner context and return the D2C task."""
        self.calls.append(kwargs)
        return SemanticPlan(
            summary="D2C add grounded GR lower-limit fill",
            section_tasks=(
                SectionTask(
                    goal="Add a grounded lower-limit fill to the GR curve.",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "binding.curve",
                        "fill.curve",
                    ),
                    existing_section_hint="Main Log",
                    requirements=(FROZEN_D2C_REQUEST,),
                ),
            ),
        )


@dataclass
class _RevisionBackend:
    """Verify grounded worker context and return a deterministic fill program."""

    binding_id: str
    requests: list[ProgramGenerationRequest]

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Inspect the actual SDK inventory before emitting the controlled program."""
        self.requests.append(request)
        payload_start = request.user_prompt.index('{"capabilities":')
        payload = json.loads(request.user_prompt[payload_start:])
        assert payload["section_context"]["target"]["kind"] == "existing"
        sdk_reference = payload["sdk_reference"]
        assert "Grounded existing curve inventory; use exact identities only:" in sdk_reference
        inventory = []
        in_inventory = False
        for line in sdk_reference.splitlines():
            if line == "Grounded existing curve inventory; use exact identities only:":
                in_inventory = True
                continue
            if in_inventory and line.startswith("- "):
                inventory.append(json.loads(line[2:]))
                continue
            if in_inventory and line and not line.startswith("- "):
                break
        assert any(
            item["track_id"] == GR_TRACK_ID
            and item["binding_id"] == GR_BINDING_ID
            and item["channel"] == "GR"
            for item in inventory
        )
        source = (
            "report = wp.report()\n"
            "section = wp.target_section(report)\n"
            "track = wp.target_track(section, track_id='gr')\n"
            f"curve = wp.target_curve(track, binding_id={self.binding_id!r})\n"
            "wp.fill(track, curve, kind='to_lower_limit', id_hint='gr_lower_fill', "
            "color='#d9d9d9', alpha=0.25)\n"
        )
        return ProgramGenerationResult(
            text=source,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


class _UnusedReportCompiler:
    """Fail if the fill revision dispatches report work."""

    calls = 0

    async def compile(self, **_kwargs: object) -> object:
        """Reject unexpected report work and count the attempted dispatch."""
        self.calls += 1
        raise AssertionError("D2C fill revision must not dispatch report work")


def _revision_fixture(directory: Path) -> Path:
    """Create the repository LAS-backed fixture used by D2C."""
    fixture = create_mcp_fixture_paths(directory)
    logfile = directory / "d2c-fill-revision.log.yaml"
    logfile.write_text(fixture.single_logfile.read_text(encoding="utf-8"), encoding="utf-8")
    return logfile


def _document_and_inventory(logfile: Path) -> tuple[object, dict[str, object]]:
    """Load and verify the exact starting section, tracks, and bindings."""
    spec = load_logfile(logfile, allowed_root=REPO_ROOT)
    document = AuthoringService.from_mapping(report_to_dict(spec)).document
    assert len(document.sections) == 1
    section = document.sections[0]
    assert section.id == "main"
    assert section.title == "Main Log"
    assert [track.id for track in section.tracks] == ["depth", "cbl", "vdl", "gr", "cali", "rt"]
    gr_track = section.tracks[3]
    assert gr_track.id == GR_TRACK_ID
    assert gr_track.kind == "normal"
    assert gr_track.title == "GR"
    assert len(gr_track.fills) == 0
    gr_bindings = [binding for binding in gr_track.bindings if binding.channel == "GR"]
    assert len(gr_bindings) == 1
    assert gr_bindings[0].binding_id == GR_BINDING_ID
    cali_track = section.tracks[4]
    cali_bindings = [binding for binding in cali_track.bindings if binding.channel == "CALI"]
    assert len(cali_bindings) == 1
    assert cali_bindings[0].binding_id == "main.cali.CALI.4"
    return document, {
        "section": section,
        "gr_track": gr_track,
        "gr_binding": gr_bindings[0],
        "cali_binding": cali_bindings[0],
    }


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
        model="d2c-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )


def _before_path(directory: Path, document: object) -> Path:
    """Persist the canonical before-state used by the frozen verifier."""
    path = directory / "before.log.yaml"
    path.write_text(
        yaml.safe_dump(authoring_document_to_logfile_mapping(document), sort_keys=False),
        encoding="utf-8",
    )
    return path


def _acceptance() -> dict[str, object]:
    """Build D2C's bounded LAS acceptance specification."""
    fill_path = "/sections/0/tracks/3/fills/0"
    return {
        "before_assertions": [
            {"path": "/sections/0/id", "operator": "equals", "value": "main"},
            {"path": "/sections/0/title", "operator": "equals", "value": "Main Log"},
            {"path": "/sections/0/tracks/3/id", "operator": "equals", "value": "gr"},
        ],
        "required_changes": {
            "LAS-06": {
                "before": [
                    {
                        "path": "/sections/0/tracks/3/fills",
                        "operator": "equals",
                        "value": [],
                    }
                ],
                "after": [
                    {"path": f"{fill_path}/kind", "operator": "equals", "value": FILL_KIND},
                    {
                        "path": f"{fill_path}/binding_id",
                        "operator": "equals",
                        "value": GR_BINDING_ID,
                    },
                    {
                        "path": f"{fill_path}/color",
                        "operator": "equals",
                        "value": FILL_COLOR,
                    },
                    {
                        "path": f"{fill_path}/alpha",
                        "operator": "equals",
                        "value": FILL_ALPHA,
                    },
                ],
            }
        },
        "allowed_change_paths": [
            fill_path,
            "/extensions/compatibility/legacy_document/bindings/channels/2/fill",
            ("/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/fill"),
        ],
        "prohibited_change_paths": [
            "/title",
            "/subtitle",
            "/header",
            "/remarks",
            "/page",
            "/depth",
            "/output",
            "/sections/0/tracks/0",
            "/sections/0/tracks/1",
            "/sections/0/tracks/2",
            "/sections/0/tracks/4",
            "/sections/0/tracks/5",
        ],
        "expected_outcome": "accepted",
    }


def test_d2c_public_revision_persists_renders_and_passes_frozen_las_verifier() -> None:
    """Exercise the grounded fill revision through persistence and rendering."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_document, _inventory = _document_and_inventory(logfile)
        normalized_before = authoring_document_from_mapping(
            authoring_document_to_logfile_mapping(before_document)
        )
        before_path = _before_path(directory, before_document)
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(binding_id=GR_BINDING_ID, requests=[])
        report_compiler = _UnusedReportCompiler()
        adapter = _adapter(planner, backend, report_compiler)

        result = asyncio.run(adapter.revise(feedback=FROZEN_D2C_REQUEST, logfile_path=logfile))
        render_path = directory / "d2c-render.pdf"
        render_result = asyncio.run(
            adapter.render_logfile_to_file(
                logfile_path=logfile,
                output_path=render_path,
                overwrite=True,
            )
        )
        after_document = load_authoring_document(logfile)
        after_section = after_document.sections[0]
        after_gr = after_section.tracks[3]
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
    assert planner.calls[0]["request"] == FROZEN_D2C_REQUEST
    assert planner.calls[0]["current_document_summary"]
    assert len(backend.requests) == 1
    assert report_compiler.calls == 0
    assert len(after_section.tracks) == 6
    assert len(after_gr.fills) == 1
    fill = after_gr.fills[0]
    assert fill.fill_id == "main.gr.fill.gr-lower-fill"
    assert fill.kind == FILL_KIND
    assert fill.binding_id == GR_BINDING_ID
    assert fill.color == FILL_COLOR
    assert fill.alpha == FILL_ALPHA
    normalized_gr = normalized_before.sections[0].tracks[3]
    after_binding = after_gr.bindings[0].model_dump(mode="json")
    after_binding["extensions"]["compatibility"]["legacy_binding"].pop("fill")
    assert after_binding == normalized_gr.bindings[0].model_dump(mode="json")
    assert render_result
    assert render_written
    assert statuses["LAS-01"] == "PASS"
    assert statuses["LAS-06"] == "PASS"
    assert statuses["LAS-07"] == "PASS"
    assert statuses["LAS-09"] == "PASS"


def test_d2c_invented_binding_fails_without_persistence() -> None:
    """An invented binding identity cannot be substituted or persisted."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_text = logfile.read_text(encoding="utf-8")
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(binding_id="main.gr.GR.404", requests=[])
        result = asyncio.run(
            _adapter(planner, backend, _UnusedReportCompiler()).revise(
                feedback=FROZEN_D2C_REQUEST,
                logfile_path=logfile,
            )
        )
        after_text = logfile.read_text(encoding="utf-8")

    assert result.report_facts["success"] is False
    assert result.report_facts["apply_status"] != "persisted"
    assert after_text == before_text


def test_d2c_cross_track_binding_fails_without_persistence() -> None:
    """A real binding from another track cannot become a GR fill operand."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _revision_fixture(directory)
        before_document, inventory = _document_and_inventory(logfile)
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(binding_id="main.cali.CALI.4", requests=[])
        result = asyncio.run(
            _adapter(planner, backend, _UnusedReportCompiler()).revise(
                feedback=FROZEN_D2C_REQUEST,
                logfile_path=logfile,
            )
        )
        after_document, after_inventory = _document_and_inventory(logfile)

    assert inventory["cali_binding"].binding_id == "main.cali.CALI.4"
    assert result.report_facts["success"] is False
    assert after_document.model_dump(mode="json") == before_document.model_dump(mode="json")
    assert after_inventory["gr_track"].fills == inventory["gr_track"].fills


def test_d2c_worker_ownership_isolated_to_one_section_worker() -> None:
    """The successful intent contains one existing section and one new fill only."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        logfile = _revision_fixture(Path(temporary_directory))
        planner = _RevisionPlanner(calls=[])
        backend = _RevisionBackend(binding_id=GR_BINDING_ID, requests=[])
        report_compiler = _UnusedReportCompiler()
        result = asyncio.run(
            _adapter(planner, backend, report_compiler).revise(
                feedback=FROZEN_D2C_REQUEST,
                logfile_path=logfile,
            )
        )

    submitted = result.submitted_intent or {}
    sections = submitted.get("sections") or []
    assert len(sections) == 1
    assert sections[0]["section_id"] == "main"
    assert report_compiler.calls == 0
    assert len(backend.requests) == 1
    assert len(sections[0].get("tracks") or []) == 1
    track = sections[0]["tracks"][0]
    assert track["track_id"] == GR_TRACK_ID
    assert len(track.get("fills") or []) == 1
    assert track["fills"][0]["binding_id"] == GR_BINDING_ID
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
            "curve_bindings",
            "raster_bindings",
            "annotations",
            "removals",
        )
    )


def test_d2c_collateral_binding_mutation_fails_las_07() -> None:
    """A valid fill plus unrelated binding mutation fails preservation."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        before = _revision_fixture(directory)
        before_document, _inventory = _document_and_inventory(before)
        before_path = _before_path(directory, before_document)
        after = directory / "collateral-after.log.yaml"
        mapping = yaml.safe_load(before.read_text(encoding="utf-8"))
        gr_binding = next(
            binding
            for binding in mapping["document"]["bindings"]["channels"]
            if binding["track_id"] == GR_TRACK_ID
        )
        gr_binding["style"]["color"] = "#000000"
        after.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
        after_mapping = yaml.safe_load(after.read_text(encoding="utf-8"))
        gr_binding_after = next(
            binding
            for binding in after_mapping["document"]["bindings"]["channels"]
            if binding["track_id"] == GR_TRACK_ID
        )
        gr_binding_after["fill"] = {
            "kind": FILL_KIND,
            "color": FILL_COLOR,
            "alpha": FILL_ALPHA,
        }
        after.write_text(yaml.safe_dump(after_mapping, sort_keys=False), encoding="utf-8")
        verdict = verify_las_revision(
            before_path,
            after,
            _acceptance(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )

    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    assert statuses["LAS-06"] == "PASS"
    assert statuses["LAS-07"] == "FAIL"
    assert verdict["workflow_status"] == "FAIL"
