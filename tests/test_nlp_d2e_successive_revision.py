"""D2E acceptance test for successive revisions on one persisted logfile."""

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

from wellplot.agent.code_mode.enrichment import SemanticEnricher
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler
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
from wellplot.authoring import authoring_document_to_logfile_mapping
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.logfile import load_logfile

TITLE_REQUEST = 'Change the report title to "Gamma Ray Quality Control Review".'
SCALE_REQUEST = "Change the Gamma Ray curve scale to a linear scale from 10 to 100."
TRACK_REQUEST = (
    'In the Main Log section, add a new normal track titled "Caliper QC" at the end, '
    "28 mm wide, and plot the CALI curve on it labeled "
    '"Caliper QC" with a linear scale from 6 to 12.'
)
FILL_REQUEST = (
    "In the Main Log section, on the GR track, fill from the Gamma Ray curve to its "
    "lower scale limit using light gray (#d9d9d9) at 25% opacity."
)
MISSING_SOURCE_REQUEST = (
    'In the Main Log section, add a normal track titled "Neutron" and plot NPHI '
    "from missing.las on it."
)

INITIAL_TITLE = "Original Well Log Report"
TARGET_TITLE = "Gamma Ray Quality Control Review"
ORIGINAL_TRACK_IDS = ("depth", "cbl", "vdl", "gr", "cali", "rt")
GR_TRACK_ID = "gr"
GR_BINDING_ID = "main.gr.GR.3"
CALI_BINDING_ID = "main.cali.CALI.4"
FILL_KIND = "to_lower_limit"
FILL_COLOR = "#d9d9d9"
FILL_ALPHA = 0.25


@dataclass
class _SequencePlanner:
    """Return the accepted deterministic task for each exact revision request."""

    calls: list[dict[str, object]]

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Record planner context and dispatch only the frozen task vocabulary."""
        self.calls.append(kwargs)
        request = kwargs["request"]
        if request == TITLE_REQUEST:
            return SemanticPlan(
                summary="D2E report title revision",
                report_task=ReportTask(
                    goal="Change the report title.",
                    capability_ids=("report.standard",),
                    requirements=(TITLE_REQUEST,),
                ),
            )
        if request == SCALE_REQUEST:
            return SemanticPlan(
                summary="D2E GR scale revision",
                section_tasks=(
                    SectionTask(
                        goal="Change the existing Gamma Ray curve scale.",
                        capability_ids=(
                            "section.log_plot",
                            "track.normal",
                            "binding.curve",
                        ),
                        existing_section_hint="Main Log",
                        requirements=(SCALE_REQUEST,),
                    ),
                ),
            )
        if request == TRACK_REQUEST:
            return SemanticPlan(
                summary="D2E Caliper QC track revision",
                section_tasks=(
                    SectionTask(
                        goal="Add a grounded Caliper QC track.",
                        capability_ids=(
                            "section.log_plot",
                            "track.normal",
                            "binding.curve",
                        ),
                        existing_section_hint="Main Log",
                        requirements=(TRACK_REQUEST,),
                    ),
                ),
            )
        if request == FILL_REQUEST:
            return SemanticPlan(
                summary="D2E GR fill revision",
                section_tasks=(
                    SectionTask(
                        goal="Add a grounded GR lower-limit fill.",
                        capability_ids=(
                            "section.log_plot",
                            "track.normal",
                            "binding.curve",
                            "fill.curve",
                        ),
                        existing_section_hint="Main Log",
                        requirements=(FILL_REQUEST,),
                    ),
                ),
            )
        if request == MISSING_SOURCE_REQUEST:
            return SemanticPlan(
                summary="D2E missing-source rejection",
                section_tasks=(
                    SectionTask(
                        goal="Reject the missing-source request before worker dispatch.",
                        capability_ids=(
                            "section.log_plot",
                            "track.normal",
                            "binding.curve",
                        ),
                        existing_section_hint="Main Log",
                        source_hints=("missing.las",),
                        requirements=(MISSING_SOURCE_REQUEST,),
                    ),
                ),
            )
        raise AssertionError(f"unexpected D2E planner request: {request!r}")


@dataclass
class _ReportBackend:
    """Emit the already accepted sparse D2A report program once."""

    requests: list[ProgramGenerationRequest]

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Record the report worker request and return only the title operation."""
        self.requests.append(request)
        return ProgramGenerationResult(
            text=f'report = wp.report(title="{TARGET_TITLE}")\n',
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _SectionBackend:
    """Assert current grounded state before emitting one accepted section program."""

    requests: list[ProgramGenerationRequest]
    steps: list[str]
    caliper_track_id: str | None = None
    caliper_binding_id: str | None = None

    @staticmethod
    def _payload(request: ProgramGenerationRequest) -> dict[str, object]:
        """Parse the actual structured worker payload from the request."""
        payload_start = request.user_prompt.index('{"capabilities":')
        payload = json.loads(request.user_prompt[payload_start:])
        assert isinstance(payload, dict)
        return payload

    @staticmethod
    def _inventory(request: ProgramGenerationRequest) -> list[dict[str, object]]:
        """Extract the worker's grounded existing-curve inventory."""
        marker = "Grounded existing curve inventory; use exact identities only:"
        sdk_reference = _SectionBackend._payload(request)["sdk_reference"]
        assert isinstance(sdk_reference, str)
        assert marker in sdk_reference
        inventory: list[dict[str, object]] = []
        in_inventory = False
        for line in sdk_reference.splitlines():
            if line == marker:
                in_inventory = True
                continue
            if in_inventory and line.startswith("- "):
                item = json.loads(line[2:])
                assert isinstance(item, dict)
                inventory.append(item)
                continue
            if in_inventory and line and not line.startswith("- "):
                break
        return inventory

    @staticmethod
    def _assert_source_context(request: ProgramGenerationRequest) -> None:
        """Require the real inspected fixture source and its scalar CALI channel."""
        payload = _SectionBackend._payload(request)
        section_context = payload["section_context"]
        assert isinstance(section_context, dict)
        assert section_context["target"]["kind"] == "existing"
        sources = section_context["sources"]
        assert isinstance(sources, list) and sources
        assert any(source["candidate_id"] == "source-1" for source in sources)
        channels = [channel for source in sources for channel in source["channels"]]
        assert any(
            channel["mnemonic"] == "CALI" and channel["kind"] == "scalar" for channel in channels
        )

    def _program_for(self, request: ProgramGenerationRequest, step: str) -> str:
        """Assert the step-specific state and return its accepted SDK program."""
        self._assert_source_context(request)
        inventory = self._inventory(request)
        gr = next(
            item
            for item in inventory
            if item["track_id"] == GR_TRACK_ID and item["binding_id"] == GR_BINDING_ID
        )
        assert gr["channel"] == "GR"
        self.steps.append(step)
        if step == "scale":
            assert gr["scale_kind"] == "linear"
            assert gr["scale_minimum"] == 0.0
            assert gr["scale_maximum"] == 100.0
            return (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.target_track(section, track_id='gr')\n"
                "curve = wp.target_curve(track, binding_id='main.gr.GR.3')\n"
                "wp.update_curve(track, curve, scale_minimum=10, scale_maximum=100, "
                "scale_kind='linear', reverse=False)\n"
            )
        if step == "track":
            assert gr["scale_kind"] == "linear"
            assert gr["scale_minimum"] == 10.0
            assert gr["scale_maximum"] == 100.0
            return (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.track(section, id_hint='caliper_qc', kind='normal', "
                "title='Caliper QC', width_mm=28)\n"
                "wp.curve(track, channel='CALI', id_hint='caliper_qc', "
                "label='Caliper QC', scale_minimum=6, scale_maximum=12, "
                "scale_kind='linear', reverse=False)\n"
            )
        if step == "fill":
            assert gr["scale_kind"] == "linear"
            assert gr["scale_minimum"] == 10.0
            assert gr["scale_maximum"] == 100.0
            assert self.caliper_track_id
            assert self.caliper_binding_id
            caliper = next(
                item
                for item in inventory
                if item["track_id"] == self.caliper_track_id
                and item["binding_id"] == self.caliper_binding_id
            )
            assert caliper["channel"] == "CALI"
            assert caliper["label"] == "Caliper QC"
            assert caliper["scale_kind"] == "linear"
            assert caliper["scale_minimum"] == 6.0
            assert caliper["scale_maximum"] == 12.0
            return (
                "report = wp.report()\n"
                "section = wp.target_section(report)\n"
                "track = wp.target_track(section, track_id='gr')\n"
                "curve = wp.target_curve(track, binding_id='main.gr.GR.3')\n"
                "wp.fill(track, curve, kind='to_lower_limit', id_hint='gr_lower_fill', "
                "color='#d9d9d9', alpha=0.25)\n"
            )
        raise AssertionError(f"unexpected section backend step: {step}")

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Route by the exact request embedded in the real worker material."""
        self.requests.append(request)
        payload = self._payload(request)
        section_task = payload["section_task"]
        assert isinstance(section_task, dict)
        requirements = tuple(section_task["requirements"])
        if requirements == (SCALE_REQUEST,):
            step = "scale"
        elif requirements == (TRACK_REQUEST,):
            step = "track"
        elif requirements == (FILL_REQUEST,):
            step = "fill"
        else:
            raise AssertionError("section worker received an unexpected D2E request")
        return ProgramGenerationResult(
            text=self._program_for(request, step),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


def _sequence_fixture(directory: Path) -> Path:
    """Create S0 with the accepted title, GR scale, and declared LAS source."""
    fixture = create_mcp_fixture_paths(directory)
    mapping = copy.deepcopy(yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8")))
    mapping["document"]["header"] = {
        "title": INITIAL_TITLE,
        "subtitle": "D2E successive revision fixture",
    }
    for binding in mapping["document"]["bindings"]["channels"]:
        if binding["channel"] == "GR":
            binding["scale"] = {"kind": "linear", "min": 0.0, "max": 100.0}
    logfile = directory / "d2e-successive-revision.log.yaml"
    logfile.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return logfile


def _document(logfile: Path) -> object:
    """Load the current canonical document from the persisted logfile."""
    spec = load_logfile(logfile, allowed_root=REPO_ROOT)
    return AuthoringService.from_mapping(report_to_dict(spec)).document


def _snapshot(directory: Path, name: str, document: object) -> Path:
    """Persist a canonical evidence snapshot without replacing the live logfile."""
    path = directory / name
    path.write_text(
        yaml.safe_dump(authoring_document_to_logfile_mapping(document), sort_keys=False),
        encoding="utf-8",
    )
    return path


def _adapter(
    planner: _SequencePlanner,
    report_backend: _ReportBackend,
    section_backend: _SectionBackend,
) -> DirectNotebookSession:
    """Build one public notebook session with deterministic worker backends."""
    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=planner,  # type: ignore[arg-type]
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": REPO_ROOT},
        ),
        report_compiler=ReportProgramCompiler(backend=report_backend, registry=registry),
        section_compiler=ProgramSectionCompiler(backend=section_backend, registry=registry),
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=10.0),
        ),
        provider="deterministic",
        model="d2e-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )


def _render(adapter: DirectNotebookSession, logfile: Path, output: Path) -> None:
    """Render one persisted state through the real deterministic renderer."""
    result = asyncio.run(
        adapter.render_logfile_to_file(logfile_path=logfile, output_path=output, overwrite=True)
    )
    assert result
    assert output.is_file()
    assert output.stat().st_size > 0


def _compilation(result: object) -> dict[str, object]:
    """Return JSON-shaped compilation evidence from a notebook result."""
    compilation = result.report_facts["compilation"]
    assert isinstance(compilation, dict)
    return compilation


def _assert_success_result(result: object, *, worker_kind: str) -> dict[str, object]:
    """Assert one successful persisted revision and return its compilation facts."""
    assert result.request_kind == "revise"
    assert result.report_facts["success"] is True, result.user_report_text
    assert result.report_facts["changed"] is True
    assert result.report_facts["apply_status"] == "persisted"
    assert result.submitted_intent is not None
    compilation = _compilation(result)
    assert compilation["metrics"]["worker_count"] == 1
    assert compilation["metrics"]["successful_workers"] == 1
    assert compilation["metrics"]["failed_workers"] == 0
    assert compilation["metrics"]["total_repairs"] == 0
    assert len(compilation["workers"]) == 1
    assert compilation["workers"][0]["kind"] == worker_kind
    assert compilation["workers"][0]["success"] is True
    return compilation


def _assert_statuses(verdict: dict[str, object], *passed: str) -> None:
    """Require the requested D0 dimensions and workflow to pass."""
    statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
    for requirement_id in passed:
        assert statuses[requirement_id] == "PASS", verdict
    assert verdict["workflow_status"] == "PASS", verdict


def _acceptance_title() -> dict[str, object]:
    """Return D2A's frozen transition contract."""
    return {
        "before_assertions": [{"path": "/title", "operator": "equals", "value": INITIAL_TITLE}],
        "required_changes": {
            "LAS-02": {
                "before": [{"path": "/title", "operator": "equals", "value": INITIAL_TITLE}],
                "after": [{"path": "/title", "operator": "equals", "value": TARGET_TITLE}],
            }
        },
        "allowed_change_paths": [
            "/title",
            "/extensions/compatibility/legacy_document/header/title",
        ],
        "prohibited_change_paths": ["/subtitle", "/sections", "/remarks", "/header"],
        "expected_outcome": "accepted",
    }


def _acceptance_scale() -> dict[str, object]:
    """Return D1's frozen GR-scale transition contract."""
    path = "/sections/0/tracks/3/bindings/0/scale"
    return {
        "before_assertions": [{"path": "/sections/0/id", "operator": "equals", "value": "main"}],
        "required_changes": {
            "LAS-05": {
                "before": [
                    {"path": f"{path}/minimum", "operator": "equals", "value": 0.0},
                    {"path": f"{path}/maximum", "operator": "equals", "value": 100.0},
                ],
                "after": [
                    {"path": f"{path}/minimum", "operator": "equals", "value": 10.0},
                    {"path": f"{path}/maximum", "operator": "equals", "value": 100.0},
                ],
            }
        },
        "allowed_change_paths": [
            path,
            "/extensions/compatibility/legacy_document/bindings/channels/2/scale",
            "/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/scale",
        ],
        "prohibited_change_paths": ["/title", "/subtitle", "/header", "/remarks"],
        "expected_outcome": "accepted",
    }


def _acceptance_track() -> dict[str, object]:
    """Return D2B's frozen new-track and CALI-binding contract."""
    track_path = "/sections/0/tracks/6"
    binding_path = f"{track_path}/bindings/0"
    return {
        "before_assertions": [
            {"path": "/sections/0/id", "operator": "equals", "value": "main"},
            {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"},
        ],
        "required_changes": {
            "LAS-03": {
                "before": [
                    {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"}
                ],
                "after": [
                    {"path": f"{track_path}/title", "operator": "equals", "value": "Caliper QC"},
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
                    {"path": f"{binding_path}/channel", "operator": "equals", "value": "CALI"},
                    {"path": f"{binding_path}/label", "operator": "equals", "value": "Caliper QC"},
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


def _acceptance_fill() -> dict[str, object]:
    """Return D2C's frozen GR-fill transition contract."""
    path = "/sections/0/tracks/3/fills/0"
    return {
        "before_assertions": [
            {"path": "/sections/0/id", "operator": "equals", "value": "main"},
            {"path": "/sections/0/tracks/3/fills", "operator": "equals", "value": []},
        ],
        "required_changes": {
            "LAS-06": {
                "before": [
                    {"path": "/sections/0/tracks/3/fills", "operator": "equals", "value": []}
                ],
                "after": [
                    {"path": f"{path}/kind", "operator": "equals", "value": FILL_KIND},
                    {"path": f"{path}/binding_id", "operator": "equals", "value": GR_BINDING_ID},
                    {"path": f"{path}/color", "operator": "equals", "value": FILL_COLOR},
                    {"path": f"{path}/alpha", "operator": "equals", "value": FILL_ALPHA},
                ],
            }
        },
        "allowed_change_paths": [
            path,
            "/extensions/compatibility/legacy_document/bindings/channels/2/fill",
            "/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/fill",
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


def _acceptance_cumulative() -> dict[str, object]:
    """Return the union contract for S0 through S4."""
    track_path = "/sections/0/tracks/6"
    track_binding = f"{track_path}/bindings/0"
    scale_path = "/sections/0/tracks/3/bindings/0/scale"
    fill_path = "/sections/0/tracks/3/fills/0"
    return {
        "before_assertions": [
            {"path": "/title", "operator": "equals", "value": INITIAL_TITLE},
            {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"},
        ],
        "required_changes": {
            "LAS-02": {
                "before": [{"path": "/title", "operator": "equals", "value": INITIAL_TITLE}],
                "after": [{"path": "/title", "operator": "equals", "value": TARGET_TITLE}],
            },
            "LAS-03": {
                "before": [
                    {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"}
                ],
                "after": [
                    {"path": f"{track_path}/title", "operator": "equals", "value": "Caliper QC"},
                    {"path": f"{track_path}/kind", "operator": "equals", "value": "normal"},
                    {"path": f"{track_path}/width_mm", "operator": "equals", "value": 28.0},
                ],
            },
            "LAS-04": {
                "before": [
                    {"path": "/sections/0/tracks/5/id", "operator": "equals", "value": "rt"}
                ],
                "after": [
                    {"path": f"{track_binding}/kind", "operator": "equals", "value": "curve"},
                    {"path": f"{track_binding}/channel", "operator": "equals", "value": "CALI"},
                    {"path": f"{track_binding}/label", "operator": "equals", "value": "Caliper QC"},
                    {
                        "path": f"{track_binding}/scale/kind",
                        "operator": "equals",
                        "value": "linear",
                    },
                    {"path": f"{track_binding}/scale/minimum", "operator": "equals", "value": 6.0},
                    {"path": f"{track_binding}/scale/maximum", "operator": "equals", "value": 12.0},
                ],
            },
            "LAS-05": {
                "before": [
                    {"path": f"{scale_path}/minimum", "operator": "equals", "value": 0.0},
                    {"path": f"{scale_path}/maximum", "operator": "equals", "value": 100.0},
                ],
                "after": [
                    {"path": f"{scale_path}/minimum", "operator": "equals", "value": 10.0},
                    {"path": f"{scale_path}/maximum", "operator": "equals", "value": 100.0},
                ],
            },
            "LAS-06": {
                "before": [
                    {"path": "/sections/0/tracks/3/fills", "operator": "equals", "value": []}
                ],
                "after": [
                    {"path": f"{fill_path}/kind", "operator": "equals", "value": FILL_KIND},
                    {
                        "path": f"{fill_path}/binding_id",
                        "operator": "equals",
                        "value": GR_BINDING_ID,
                    },
                    {"path": f"{fill_path}/color", "operator": "equals", "value": FILL_COLOR},
                    {"path": f"{fill_path}/alpha", "operator": "equals", "value": FILL_ALPHA},
                ],
            },
        },
        "allowed_change_paths": [
            "/title",
            "/extensions/compatibility/legacy_document/header/title",
            scale_path,
            "/extensions/compatibility/legacy_document/bindings/channels/2/scale",
            "/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/scale",
            track_path,
            "/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/6",
            "/extensions/compatibility/legacy_document/bindings/channels/5",
            fill_path,
            "/extensions/compatibility/legacy_document/bindings/channels/2/fill",
            "/sections/0/tracks/3/bindings/0/extensions/compatibility/legacy_binding/fill",
        ],
        "prohibited_change_paths": [
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
            "/sections/0/tracks/4",
            "/sections/0/tracks/5",
        ],
        "expected_outcome": "accepted",
    }


def _acceptance_rejected() -> dict[str, object]:
    """Return D2D's frozen no-change rejection contract."""
    return {
        "before_assertions": [
            {"path": "/sections/0/id", "operator": "equals", "value": "main"},
            {"path": "/title", "operator": "equals", "value": TARGET_TITLE},
        ],
        "required_changes": {},
        "allowed_change_paths": [],
        "prohibited_change_paths": ["/sections", "/remarks", "/header"],
        "expected_outcome": "rejected",
    }


def _state(document: object) -> tuple[object, object, object, object]:
    """Return the main section, GR track/binding, and optional Caliper track."""
    assert document.title == TARGET_TITLE or document.title == INITIAL_TITLE
    assert len(document.sections) == 1
    section = document.sections[0]
    assert section.id == "main"
    assert section.title == "Main Log"
    gr_track = next(track for track in section.tracks if track.id == GR_TRACK_ID)
    gr_binding = next(binding for binding in gr_track.bindings if binding.channel == "GR")
    caliper_tracks = [track for track in section.tracks if track.title == "Caliper QC"]
    assert len(caliper_tracks) <= 1
    return section, gr_track, gr_binding, caliper_tracks[0] if caliper_tracks else None


def _assert_s0(document: object) -> None:
    """Assert the complete frozen starting state."""
    section, gr_track, gr_binding, caliper = _state(document)
    assert document.title == INITIAL_TITLE
    assert [track.id for track in section.tracks] == list(ORIGINAL_TRACK_IDS)
    assert gr_binding.binding_id == GR_BINDING_ID
    assert gr_binding.channel == "GR"
    assert gr_binding.scale.kind == "linear"
    assert gr_binding.scale.minimum == 0.0
    assert gr_binding.scale.maximum == 100.0
    assert gr_binding.scale.reverse is False
    assert gr_track.fills == []
    assert caliper is None


def _assert_s1(document: object) -> None:
    """Assert the persisted title state after Step 1."""
    section, gr_track, gr_binding, caliper = _state(document)
    assert document.title == TARGET_TITLE
    assert [track.id for track in section.tracks] == list(ORIGINAL_TRACK_IDS)
    assert gr_binding.scale.minimum == 0.0
    assert gr_binding.scale.maximum == 100.0
    assert gr_track.fills == []
    assert caliper is None


def _assert_s2(document: object) -> None:
    """Assert the persisted scale state after Step 2."""
    section, gr_track, gr_binding, caliper = _state(document)
    assert document.title == TARGET_TITLE
    assert [track.id for track in section.tracks] == list(ORIGINAL_TRACK_IDS)
    assert gr_binding.scale.minimum == 10.0
    assert gr_binding.scale.maximum == 100.0
    assert gr_binding.scale.reverse is False
    assert gr_track.fills == []
    assert caliper is None


def _assert_s3(document: object) -> tuple[str, str]:
    """Assert the persisted track/curve state and return allocator-owned IDs."""
    section, gr_track, gr_binding, caliper = _state(document)
    assert document.title == TARGET_TITLE
    assert [track.id for track in section.tracks[:6]] == list(ORIGINAL_TRACK_IDS)
    assert len(section.tracks) == 7
    assert gr_binding.scale.minimum == 10.0
    assert gr_binding.scale.maximum == 100.0
    assert gr_track.fills == []
    assert caliper is not None
    assert caliper.kind == "normal"
    assert caliper.title == "Caliper QC"
    assert caliper.width_mm == 28.0
    assert len(caliper.bindings) == 1
    binding = caliper.bindings[0]
    assert binding.binding_id != CALI_BINDING_ID
    assert binding.channel == "CALI"
    assert binding.label == "Caliper QC"
    assert binding.scale.kind == "linear"
    assert binding.scale.minimum == 6.0
    assert binding.scale.maximum == 12.0
    assert binding.scale.reverse is False
    return caliper.id, binding.binding_id


def _assert_s4(document: object, *, caliper_track_id: str, caliper_binding_id: str) -> str:
    """Assert the accumulated state and return the persisted fill identity."""
    section, gr_track, gr_binding, caliper = _state(document)
    assert document.title == TARGET_TITLE
    assert [track.id for track in section.tracks[:6]] == list(ORIGINAL_TRACK_IDS)
    assert len(section.tracks) == 7
    assert caliper is not None and caliper.id == caliper_track_id
    assert len([track for track in section.tracks if track.title == "Caliper QC"]) == 1
    assert len(caliper.bindings) == 1
    binding = caliper.bindings[0]
    assert binding.binding_id == caliper_binding_id
    assert binding.channel == "CALI"
    assert binding.label == "Caliper QC"
    assert binding.scale.minimum == 6.0
    assert binding.scale.maximum == 12.0
    assert gr_binding.scale.minimum == 10.0
    assert gr_binding.scale.maximum == 100.0
    assert len(gr_track.fills) == 1
    fill = gr_track.fills[0]
    assert fill.kind == FILL_KIND
    assert fill.binding_id == GR_BINDING_ID
    assert fill.color == FILL_COLOR
    assert fill.alpha == FILL_ALPHA
    assert fill.fill_id
    assert (
        sum(item.kind == FILL_KIND and item.binding_id == GR_BINDING_ID for item in gr_track.fills)
        == 1
    )
    return fill.fill_id


def test_d2e_successive_revisions_accumulate_and_reject_without_mutation() -> None:
    """Exercise five revisions on one persisted logfile through the public path."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        directory = Path(temporary_directory)
        logfile = _sequence_fixture(directory)
        planner = _SequencePlanner(calls=[])
        report_backend = _ReportBackend(requests=[])
        section_backend = _SectionBackend(requests=[], steps=[])
        adapter = _adapter(planner, report_backend, section_backend)

        s0 = _document(logfile)
        _assert_s0(s0)
        s0_path = _snapshot(directory, "s0.log.yaml", s0)
        _render(adapter, logfile, directory / "s0.pdf")

        result1 = asyncio.run(adapter.revise(feedback=TITLE_REQUEST, logfile_path=logfile))
        compilation1 = _assert_success_result(result1, worker_kind="report")
        s1 = _document(logfile)
        _assert_s1(s1)
        s1_path = _snapshot(directory, "s1.log.yaml", s1)
        _render(adapter, logfile, directory / "s1.pdf")
        verdict1 = verify_las_revision(
            s0_path,
            logfile,
            _acceptance_title(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        _assert_statuses(verdict1, "LAS-01", "LAS-02", "LAS-07", "LAS-09")

        result2 = asyncio.run(adapter.revise(feedback=SCALE_REQUEST, logfile_path=logfile))
        compilation2 = _assert_success_result(result2, worker_kind="section")
        s2 = _document(logfile)
        _assert_s2(s2)
        s2_path = _snapshot(directory, "s2.log.yaml", s2)
        _render(adapter, logfile, directory / "s2.pdf")
        verdict2 = verify_las_revision(
            s1_path,
            logfile,
            _acceptance_scale(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        _assert_statuses(verdict2, "LAS-01", "LAS-05", "LAS-07", "LAS-09")

        result3 = asyncio.run(adapter.revise(feedback=TRACK_REQUEST, logfile_path=logfile))
        compilation3 = _assert_success_result(result3, worker_kind="section")
        s3 = _document(logfile)
        caliper_track_id, caliper_binding_id = _assert_s3(s3)
        section_backend.caliper_track_id = caliper_track_id
        section_backend.caliper_binding_id = caliper_binding_id
        s3_path = _snapshot(directory, "s3.log.yaml", s3)
        _render(adapter, logfile, directory / "s3.pdf")
        verdict3 = verify_las_revision(
            s2_path,
            logfile,
            _acceptance_track(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        _assert_statuses(verdict3, "LAS-01", "LAS-03", "LAS-04", "LAS-07", "LAS-09")

        result4 = asyncio.run(adapter.revise(feedback=FILL_REQUEST, logfile_path=logfile))
        compilation4 = _assert_success_result(result4, worker_kind="section")
        s4 = _document(logfile)
        fill_id = _assert_s4(
            s4,
            caliper_track_id=caliper_track_id,
            caliper_binding_id=caliper_binding_id,
        )
        s4_path = _snapshot(directory, "s4.log.yaml", s4)
        _render(adapter, logfile, directory / "s4.pdf")
        verdict4 = verify_las_revision(
            s3_path,
            logfile,
            _acceptance_fill(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        _assert_statuses(verdict4, "LAS-01", "LAS-06", "LAS-07", "LAS-09")

        cumulative = verify_las_revision(
            s0_path,
            logfile,
            _acceptance_cumulative(),
            execution_evidence={"accepted": True, "persisted": True, "rendered": True},
        )
        _assert_statuses(
            cumulative,
            "LAS-01",
            "LAS-02",
            "LAS-03",
            "LAS-04",
            "LAS-05",
            "LAS-06",
            "LAS-07",
            "LAS-09",
        )
        cumulative_statuses = {item["id"]: item["status"] for item in cumulative["requirements"]}
        assert cumulative_statuses["LAS-08"] == "NOT_CHECKABLE"

        s4_bytes = logfile.read_bytes()
        s4_payload = _document(logfile).model_dump(mode="json")
        result5 = asyncio.run(adapter.revise(feedback=MISSING_SOURCE_REQUEST, logfile_path=logfile))
        compilation5 = _compilation(result5)
        assert result5.report_facts["success"] is False
        assert result5.report_facts["changed"] is False
        assert result5.report_facts["apply_status"] == "compile_failed"
        assert result5.submitted_intent is None
        assert compilation5["metrics"]["worker_count"] == 0
        assert compilation5["metrics"]["successful_workers"] == 0
        assert compilation5["metrics"]["failed_workers"] == 0
        assert compilation5["workers"] == []
        assert compilation5["diagnostics"][0]["stage"] == "enrichment"
        assert compilation5["diagnostics"][0]["code"] == "enrichment.source_missing"
        assert logfile.read_bytes() == s4_bytes
        assert _document(logfile).model_dump(mode="json") == s4_payload
        s4_after_rejection = _document(logfile)
        assert (
            _assert_s4(
                s4_after_rejection,
                caliper_track_id=caliper_track_id,
                caliper_binding_id=caliper_binding_id,
            )
            == fill_id
        )
        assert all(
            binding.channel != "NPHI"
            for track in s4_after_rejection.sections[0].tracks
            for binding in track.bindings
        )
        _render(adapter, logfile, directory / "s4-after-rejection.pdf")
        verdict5 = verify_las_revision(
            s4_path,
            logfile,
            _acceptance_rejected(),
            execution_evidence={"accepted": False, "persisted": True, "rendered": True},
        )
        _assert_statuses(verdict5, "LAS-01", "LAS-07", "LAS-08", "LAS-09")

        assert len(planner.calls) == 5
        assert [call["mode"] for call in planner.calls] == ["revise"] * 5
        assert [call["request"] for call in planner.calls] == [
            TITLE_REQUEST,
            SCALE_REQUEST,
            TRACK_REQUEST,
            FILL_REQUEST,
            MISSING_SOURCE_REQUEST,
        ]
        assert planner.calls[0]["current_document_summary"]["title"] == INITIAL_TITLE
        assert all(
            call["current_document_summary"]["title"] == TARGET_TITLE for call in planner.calls[1:]
        )
        assert len(report_backend.requests) == 1
        assert len(section_backend.requests) == 3
        assert section_backend.steps == ["scale", "track", "fill"]
        assert compilation1["workers"][0]["kind"] == "report"
        assert compilation2["workers"][0]["kind"] == "section"
        assert compilation3["workers"][0]["kind"] == "section"
        assert compilation4["workers"][0]["kind"] == "section"
        assert not compilation5["workers"]
