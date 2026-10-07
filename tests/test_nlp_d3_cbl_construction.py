"""D3 one-shot CBL/VDL construction acceptance tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml
from scripts.verify_cbl_packet import verify_cbl_packet
from tests._mcp_fixtures import REPO_ROOT

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
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.io.dlis import load_dlis
from wellplot.logfile import load_logfile
from wellplot.model.channels import ArrayChannel

_FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "agentic_cbl"
_EXTERNAL_ROOT = Path(
    "/home/user/projects/well_log_os/workspace/tutorials/agent_cbl_log_example_from_prompt"
)
_EXTERNAL_FILES = {
    "CBL_Main.dlis": (
        111573216,
        "3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7",
    ),
    "CBL_Repeat.dlis": (
        3294924,
        "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640",
    ),
}
_REQUIRED_CHANNELS = {
    "ECGR_STGC": "scalar",
    "TT": "scalar",
    "TENS": "scalar",
    "MTEM": "scalar",
    "STIT": "scalar",
    "TDSP": "scalar",
    "VSEC": "scalar",
    "CBL": "scalar",
    "VDL": "array",
}


def _normalized_request() -> str:
    """Return the frozen request with only its two staging paths normalized."""
    request = (_FIXTURE_ROOT / "frozen_prompt.txt").read_text(encoding="utf-8")
    replacements = {
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis": "CBL_Main.dlis",
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis": "CBL_Repeat.dlis",
    }
    for source, target in replacements.items():
        assert request.count(source) == 1
        request = request.replace(source, target)
    return request


D3_REQUEST = _normalized_request()
D3_REQUEST_SHA256 = hashlib.sha256(D3_REQUEST.encode("utf-8")).hexdigest()

_REPORT_REQUIREMENTS = (
    "Set service titles to Cement Bond Log, Variable Density Log, and Gamma Ray - CCL.",
    "Set the requested University of Utah / FORGE 16B (78)-32 well header values.",
    "Set the requested location, elevation, datum, interval, fluid, and logging values.",
    (
        "Set run number ONE, driller depth 4980.00 ft, logged depth TD Not Tag, "
        "density 8.4 lbm/gal, temperature 177.2 degF, logged by D. May / D. Jones, "
        "and witnessed by Leroy Swearingen."
    ),
    "Add the three requested titled remarks with their requested text.",
    "Preserve the cased-hole packet boundary and do not invent unsupported vendor-only content.",
)
_SECTION_REQUIREMENTS = (
    "Preserve the existing combo anchor as the first normal 50 mm track.",
    (
        "Create depth as a 10 mm reference track, cbl as a 44 mm normal track, "
        "and vdl as a 48 mm array track."
    ),
    (
        "Bind ECGR_STGC, TT, TENS, and MTEM on combo with the exact requested labels, "
        "scales, colors, and line styles."
    ),
    (
        "Bind STIT, TDSP, and VSEC on depth with the exact requested labels, scales, "
        "colors, and line styles."
    ),
    (
        "Bind CBL twice on cbl with the exact requested labels, scales, styles, "
        "and distinct identities."
    ),
    (
        "Bind VDL on vdl as a vdl raster with the requested x scale, colormap, "
        "colorbar, sample axis, and hidden vertical grids."
    ),
)


@dataclass
class _D3Planner:
    """Return the one frozen semantic plan and retain the public call evidence."""

    calls: list[dict[str, object]] = field(default_factory=list)

    async def plan(self, **kwargs: object) -> SemanticPlan:
        """Assert public reconstruction context before returning local work units."""
        self.calls.append(kwargs)
        assert kwargs["request"] == D3_REQUEST.rstrip("\n")
        assert str(kwargs["mode"]) == "reconstruct"
        current = str(kwargs["current_document_summary"])
        assert "main_pass" in current and "repeat_pass" in current
        sources = str(kwargs["source_summary"])
        assert "CBL_Main.dlis" in sources and "CBL_Repeat.dlis" in sources
        return SemanticPlan(
            summary="D3 one-shot cased-hole CBL/VDL construction",
            report_task=ReportTask(
                goal="Construct the supported report-wide CBL/VDL packet presentation.",
                capability_ids=("report.standard",),
                requirements=_REPORT_REQUIREMENTS,
            ),
            section_tasks=(
                _section_task("Main Pass", "CBL_Main.dlis"),
                _section_task("Repeat Pass", "CBL_Repeat.dlis"),
            ),
        )


def _section_task(section_hint: str, source_name: str) -> SectionTask:
    """Build one complete task-local section contract."""
    return SectionTask(
        goal=f"Construct the complete grounded {section_hint} CBL/VDL section.",
        capability_ids=(
            "section.log_plot",
            "track.normal",
            "track.reference",
            "track.array",
            "binding.curve",
            "binding.raster",
        ),
        existing_section_hint=section_hint,
        source_hints=(source_name,),
        requirements=_SECTION_REQUIREMENTS,
    )


def _assert_requirements(actual: object, expected: tuple[str, ...]) -> None:
    """Require the worker payload to carry every frozen semantic obligation."""
    assert isinstance(actual, list)
    assert set(expected).issubset(actual)


@dataclass
class _D3ReportBackend:
    """Validate report-task custody, then emit one deterministic report program."""

    requests: list[ProgramGenerationRequest] = field(default_factory=list)

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Reject missing task semantics before returning controlled SDK source."""
        self.requests.append(request)
        payload = _payload(request)
        task = payload["report_task"]
        assert isinstance(task, dict)
        _assert_requirements(task["requirements"], _REPORT_REQUIREMENTS)
        assert task["capability_ids"] == ["report.standard"]
        assert "track" not in " ".join(task["requirements"]).lower()
        return ProgramGenerationResult(
            text=_report_program(),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


@dataclass
class _D3SectionBackend:
    """Validate isolated task and host-grounded source facts before emitting code."""

    requests: list[ProgramGenerationRequest] = field(default_factory=list)

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Require exact source/channel and local semantic evidence for each section."""
        self.requests.append(request)
        payload = _payload(request)
        task = payload["section_task"]
        assert isinstance(task, dict)
        _assert_requirements(task["requirements"], _SECTION_REQUIREMENTS)
        assert task["capability_ids"] == [
            "section.log_plot",
            "track.normal",
            "track.reference",
            "track.array",
            "binding.curve",
            "binding.raster",
        ]
        source_name = "CBL_Main.dlis" if "Main Pass" in str(task["goal"]) else "CBL_Repeat.dlis"
        context = payload["section_context"]
        assert isinstance(context, dict)
        assert context["target"] == {"kind": "existing"}
        sources = context["sources"]
        assert isinstance(sources, list) and len(sources) == 1
        source = sources[0]
        expected_candidate = "source-1" if source_name == "CBL_Main.dlis" else "source-2"
        assert source["candidate_id"] == expected_candidate
        channels = source["channels"]
        assert isinstance(channels, list)
        available = {item["mnemonic"]: item["kind"] for item in channels}
        assert {name: available[name] for name in _REQUIRED_CHANNELS} == _REQUIRED_CHANNELS
        existing_tracks = context["existing_tracks"]
        assert existing_tracks == [
            {
                "track_id": "combo",
                "title": "Combo",
                "kind": "normal",
                "width_mm": 50.0,
                "binding_ids": [],
            }
        ]
        return ProgramGenerationResult(
            text=_section_program(),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )


def _payload(request: ProgramGenerationRequest) -> dict[str, object]:
    """Parse the actual bounded JSON payload from a worker request."""
    payload_start = request.user_prompt.index('{"capabilities":')
    payload = json.loads(request.user_prompt[payload_start:])
    assert isinstance(payload, dict)
    return payload


def _report_program() -> str:
    """Return the deterministic report program for the frozen request."""
    lines = [
        "report = wp.report()",
        "wp.service_title(report, slot_id='service_title.1', value='Cement Bond Log', alignment='center', bold=True)",  # noqa: E501
        "wp.service_title(report, slot_id='service_title.2', value='Variable Density Log', alignment='center', bold=True)",  # noqa: E501
        "wp.service_title(report, slot_id='service_title.3', value='Gamma Ray - CCL', alignment='center', bold=True)",  # noqa: E501
    ]
    header_values = {
        "company": "University of Utah",
        "well": "FORGE 16B (78)-32",
        "field": "Utah Forge",
        "county": "Beaver",
        "country": "Utah",
        "section": "NWSW 32",
        "township": "26",
        "range": "9",
        "footage": "972' FSL & 523' FWL",
        "latitude": "38.501242",
        "longitude": "-112.882661",
        "logging_date": "08-May-2023",
        "measured_from": "Kelly Bushing",
        "log_measured_from": "Kelly Bushing",
        "elevation_kb": "5445.50 ft",
        "elevation_gl": "5415.00 ft",
        "elevation_df": "5445.00 ft",
        "top_log_interval": "25.00 ft",
        "bottom_log_interval": "4845.00 ft",
        "fluid_type": "Fresh Water",
    }
    lines.extend(
        f"wp.header_field(report, key='{key}', value={value!r})"
        for key, value in header_values.items()
    )
    detail_values = {
        "detail.row_2.column_1.cell_1": "ONE",
        "detail.row_4.column_1.cell_1": "4980.00 ft",
        "detail.row_5.column_1.cell_1": "TD Not Tag",
        "detail.row_12.value_1": "8.4 lbm/gal",
        "detail.row_19.column_1.cell_1": "177.2 degF",
        "detail.row_23.value_1": "D. May / D. Jones",
        "detail.row_24.value_1": "Leroy Swearingen",
    }
    lines.extend(
        f"wp.detail_field(report, key='{key}', value={value!r})"
        for key, value in detail_values.items()
    )
    lines.extend(
        [
            "wp.remark(report, remark_id='scope', title='Supported Reconstruction Scope', text='Reconstruct only the supported subset: heading page, remarks, main pass, repeat pass, and tail.', alignment='left')",  # noqa: E501
            "wp.remark(report, remark_id='sources', title='Data Sources', text='Use the staged DLIS files under the project directory as the main and repeat packet sources.', alignment='left')",  # noqa: E501
            "wp.remark(report, remark_id='notice', title='Public Data and IP Notice', text='Keep the wellplot reproduction boundary explicit and avoid vendor-specific disclaimer artwork.', alignment='left')",  # noqa: E501
            "wp.page(report, size='A4', orientation='portrait', continuous=False)",
            "wp.depth(report, unit='ft', scale=240)",
            "wp.output(report, backend='matplotlib', output_path='d3.pdf', dpi=144)",
            "wp.tail(report, enabled=True)",
        ]
    )
    return "\n".join(lines) + "\n"


def _section_program() -> str:
    """Return one complete section program, applied once per selected section."""
    return (
        "\n".join(
            [
                "report = wp.report()",
                "section = wp.target_section(report)",
                "combo = wp.target_track(section, track_id='combo')",
                "wp.curve(combo, channel='ECGR_STGC', label='Gamma Ray (ECGR_STGC) QTGC-B', scale_minimum=0, scale_maximum=150, scale_kind='linear', reverse=False, color='#16a34a', line_width=0.8)",  # noqa: E501
                "wp.curve(combo, channel='TT', label='Transit Time for CBL (TT) QSLT-B', scale_minimum=200, scale_maximum=400, scale_kind='linear', reverse=True, color='#2142ff', line_width=0.75)",  # noqa: E501
                "wp.curve(combo, channel='TENS', label='Cable Tension (TENS)', scale_minimum=5000, scale_maximum=0, scale_kind='linear', reverse=False, color='#111111', line_style='dashed', line_width=0.65)",  # noqa: E501
                "wp.curve(combo, channel='MTEM', label='Mud Temperature (MTEM) LEH-MT', scale_minimum=100, scale_maximum=500, scale_kind='linear', reverse=False, color='#111111', line_width=0.9)",  # noqa: E501
                "depth = wp.track(section, id_hint='depth', kind='reference', title='Depth', width_mm=10)",  # noqa: E501
                "wp.curve(depth, channel='STIT', label='Stuck Tool Indicator, Total (STIT)', scale_minimum=0, scale_maximum=50, scale_kind='linear', reverse=False, color='#111111', line_width=0.65)",  # noqa: E501
                "wp.curve(depth, channel='TDSP', label='Cable Drag', scale_minimum=0, scale_maximum=50, scale_kind='linear', reverse=False, color='#92400e', line_style='dotted', line_width=0.65)",  # noqa: E501
                "wp.curve(depth, channel='VSEC', label='Tool_Tot. Drag', scale_minimum=0, scale_maximum=50, scale_kind='linear', reverse=False, color='#1d4ed8', line_style='dashed', line_width=0.65)",  # noqa: E501
                "cbl = wp.track(section, id_hint='cbl', kind='normal', title='CBL', width_mm=44)",
                "wp.curve(cbl, channel='CBL', id_hint='cbl_first', label='CBL Amplitude (CBL) QSLT-B', scale_minimum=0, scale_maximum=100, scale_kind='linear', reverse=False, color='#111111', line_width=0.75)",  # noqa: E501
                "wp.curve(cbl, channel='CBL', id_hint='cbl_second', label='CBL Amplitude (CBL) QSLT-B', scale_minimum=0, scale_maximum=10, scale_kind='linear', reverse=False, color='#2563eb', line_style='dashed', line_width=0.65)",  # noqa: E501
                "vdl = wp.track(section, id_hint='vdl', kind='array', title='VDL', width_mm=48, scale_minimum=200, scale_maximum=1200, scale_kind='linear', reverse=False, grid_vertical_main_visible=False, grid_vertical_secondary_visible=False)",  # noqa: E501
                "wp.raster(vdl, channel='VDL', label='VDL VariableDensity (VDL) QSLT-B', profile='vdl', colormap='gray_r', colorbar_enabled=True, colorbar_label='Amplitude', colorbar_position='header', sample_axis_enabled=True, sample_axis_unit='us', sample_axis_minimum=200, sample_axis_maximum=1200, sample_axis_tick_count=7, sample_axis_source_origin=40, sample_axis_source_step=10)",  # noqa: E501
            ]
        )
        + "\n"
    )


def _external_data() -> tuple[Path, Path]:
    """Authenticate and parse the two authorized local external DLIS files."""
    paths = tuple(_EXTERNAL_ROOT / name for name in _EXTERNAL_FILES)
    present = tuple(path.is_file() for path in paths)
    if not any(present):
        pytest.skip(
            "D3 external-data integration skipped: local CBL DLIS fixtures are not present."
        )
    if not all(present):
        pytest.fail("D3 external-data integration requires both authorized DLIS files.")
    for path, (expected_size, expected_sha) in zip(paths, _EXTERNAL_FILES.values(), strict=True):
        assert path.stat().st_size == expected_size
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha
        dataset = load_dlis(path)
        observed = {
            str(name): "array" if isinstance(channel, ArrayChannel) else "scalar"
            for name, channel in dataset.channels.items()
        }
        assert {name: observed[name] for name in _REQUIRED_CHANNELS} == _REQUIRED_CHANNELS
    return paths  # type: ignore[return-value]


def _scaffold(path: Path) -> None:
    """Create the minimal two-section scaffold without requested science."""
    mapping = yaml.safe_load((_FIXTURE_ROOT / "base.template.yaml").read_text(encoding="utf-8"))
    mapping["version"] = 1
    mapping["name"] = "D3 CBL scaffold"
    mapping["render"]["output_path"] = "d3.pdf"
    mapping["document"]["layout"]["remarks"] = []
    mapping["document"]["layout"]["log_sections"] = [
        {
            "id": "main_pass",
            "title": "Main Pass",
            "subtitle": "CBL/VDL packet main pass",
            "data": {"source_path": "CBL_Main.dlis", "source_format": "dlis"},
            "tracks": [{"id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50}],
        },
        {
            "id": "repeat_pass",
            "title": "Repeat Pass",
            "subtitle": "CBL/VDL packet repeat pass",
            "data": {"source_path": "CBL_Repeat.dlis", "source_format": "dlis"},
            "tracks": [{"id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50}],
        },
    ]
    mapping["document"]["bindings"]["channels"] = []
    path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")


def _adapter(
    planner: _D3Planner,
    report: _D3ReportBackend,
    section: _D3SectionBackend,
) -> DirectNotebookSession:
    """Build the public notebook session with deterministic worker doubles."""
    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=planner,  # type: ignore[arg-type]
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": REPO_ROOT},
        ),
        report_compiler=ReportProgramCompiler(backend=report, registry=registry),
        section_compiler=ProgramSectionCompiler(backend=section, registry=registry),
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=30.0),
        ),
        provider="deterministic",
        model="d3-fixture-model",
        credential_source="none",
        server_root=REPO_ROOT,
    )


def test_d3_request_normalization_is_exact() -> None:
    """Only the two source path lines differ from the frozen request fixture."""
    original = (_FIXTURE_ROOT / "frozen_prompt.txt").read_text(encoding="utf-8")
    assert original != D3_REQUEST
    assert D3_REQUEST.count("CBL_Main.dlis") == 1
    assert D3_REQUEST.count("CBL_Repeat.dlis") == 1
    assert hashlib.sha256(D3_REQUEST.encode("utf-8")).hexdigest() == D3_REQUEST_SHA256


def test_d3_scaffold_is_incomplete() -> None:
    """The structural seed cannot already satisfy the scientific packet contract."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        scaffold = Path(temporary) / "d3-scaffold.log.yaml"
        _scaffold(scaffold)
        mapping = yaml.safe_load(scaffold.read_text(encoding="utf-8"))
        sections = mapping["document"]["layout"]["log_sections"]
        assert [section["id"] for section in sections] == ["main_pass", "repeat_pass"]
        assert all(
            [track["id"] for track in section["tracks"]] == ["combo"] for section in sections
        )
        assert mapping["document"]["bindings"]["channels"] == []
        verdict = verify_cbl_packet(scaffold)
        assert verdict["acceptance_status"] != "PASS"
        statuses = {item["id"]: item["status"] for item in verdict["requirements"]}
        assert any(
            statuses[item] == "FAIL" for item in ("CBL-02", "CBL-04", "CBL-05", "CBL-07", "CBL-08")
        )


def test_d3_one_shot_real_dlis_construction() -> None:
    """Construct, persist, reload, render, and verify the complete CBL packet once."""
    external_paths = _external_data()
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        directory = Path(temporary)
        for path in external_paths:
            shutil.copyfile(path, directory / path.name)
        scaffold = directory / "d3-scaffold.log.yaml"
        output = directory / "d3-output.log.yaml"
        render = directory / "d3-render.pdf"
        _scaffold(scaffold)

        planner = _D3Planner()
        report = _D3ReportBackend()
        section = _D3SectionBackend()
        adapter = _adapter(planner, report, section)
        result = asyncio.run(
            adapter.run(
                goal=D3_REQUEST,
                output_logfile=output,
                source_logfile_path=scaffold,
            )
        )

        assert result.request_kind == "author"
        assert result.report_facts["success"] is True, result.user_report_text
        assert result.report_facts["changed"] is True
        assert result.report_facts["apply_status"] == "persisted"
        assert len(planner.calls) == 1
        assert len(report.requests) == 1
        assert len(section.requests) == 2
        compilation = result.report_facts["compilation"]
        assert compilation["metrics"]["worker_count"] == 3
        assert compilation["metrics"]["successful_workers"] == 3
        assert compilation["metrics"]["failed_workers"] == 0
        assert compilation["metrics"]["total_repairs"] == 0
        assert output.is_file()

        reloaded = AuthoringService.from_mapping(
            report_to_dict(load_logfile(output, allowed_root=REPO_ROOT))
        ).document
        assert [section.id for section in reloaded.sections] == ["main_pass", "repeat_pass"]
        assert all(
            [track.id for track in section.tracks] == ["combo", "depth", "cbl", "vdl"]
            for section in reloaded.sections
        )
        assert all(
            len(next(track for track in section.tracks if track.id == "combo").bindings) == 4
            for section in reloaded.sections
        )

        rendered = asyncio.run(
            adapter.render_logfile_to_file(
                logfile_path=output,
                output_path=render,
                overwrite=True,
            )
        )
        assert rendered
        assert render.is_file() and render.stat().st_size > 0

        verdict = verify_cbl_packet(
            output,
            execution_evidence={"persisted": True, "rendered": True},
        )
        assert verdict["acceptance_status"] == "PASS", verdict
        assert verdict["errors"] == []
        assert {item["id"] for item in verdict["requirements"]} == {
            "CBL-01",
            "CBL-02",
            "CBL-03",
            "CBL-04",
            "CBL-05",
            "CBL-06",
            "CBL-07",
            "CBL-08",
            "CBL-09",
        }
        assert all(item["status"] == "PASS" for item in verdict["requirements"])
