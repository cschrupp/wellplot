"""Compliance tests for the stable model-facing MCP projection."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
import yaml

try:
    from tests._mcp_fixtures import create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - exercised by unittest discovery mode
    from _mcp_fixtures import create_mcp_fixture_paths

from wellplot.agent.tool_contract import stable_tool_profile
from wellplot.authoring_service import (
    AuthoringService,
    SectionPatch,
    UpdateSectionRequest,
)
from wellplot.errors import TemplateValidationError
from wellplot.mcp import service
from wellplot.mcp.stable import dispatch_stable_tool, register_stable_tools
from wellplot.mcp.telemetry import TELEMETRY_PATH_ENV

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOGFILE = "examples/production/cbl_log_example/full_reconstruction.log.yaml"


class _ToolCollector:
    def __init__(self) -> None:
        self.tools: list[dict[str, object]] = []

    def add_tool(self, function: object, **metadata: object) -> None:
        self.tools.append({"function": function, **metadata})


def _seed_draft(path: Path) -> None:
    service.create_logfile_draft(
        str(path),
        source_logfile_path=SOURCE_LOGFILE,
        root=REPO_ROOT,
    )


def _canonical_document(path: Path) -> dict[str, object]:
    spec = service.load_logfile(path, allowed_root=REPO_ROOT)
    return AuthoringService.from_mapping(service.report_to_dict(spec)).document.model_dump(
        mode="json"
    )


def test_stable_projection_registers_only_contract_responsibilities() -> None:
    """The MCP projection exposes the reviewed profile and no legacy wrappers."""
    collector = _ToolCollector()
    names = register_stable_tools(
        collector,
        root=REPO_ROOT,
        image_factory=lambda data: data,
        annotation_factory=lambda values: dict(values),
    )
    expected = tuple(tool.name for tool in stable_tool_profile())

    assert names == expected
    assert [item["name"] for item in collector.tools] == list(expected)
    assert len(collector.tools) == 17
    assert all("description" in item for item in collector.tools)


def test_stable_dispatch_telemetry_is_opt_in_and_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Record metadata-only telemetry without changing a stable tool result."""
    collector = _ToolCollector()
    telemetry_path = tmp_path / "telemetry" / "dispatch.jsonl"
    monkeypatch.setenv(TELEMETRY_PATH_ENV, str(telemetry_path))
    register_stable_tools(
        collector,
        root=tmp_path,
        image_factory=lambda data: data,
        annotation_factory=lambda values: dict(values),
    )
    inspect_tool = next(
        item["function"] for item in collector.tools if item["name"] == "inspect_vocab"
    )

    expected = dispatch_stable_tool("inspect_vocab", {}, root=tmp_path)
    actual = inspect_tool()
    events = [
        json.loads(line)
        for line in telemetry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert actual == expected
    assert len(events) == 1
    event = events[0]
    assert event["tool_name"] == "inspect_vocab"
    assert event["outcome"] == "success"
    assert event["argument_bytes"] == 2
    assert event["result_bytes"] is not None
    assert event["changed"] is None
    assert event["exception_type"] is None
    assert "arguments" not in event
    assert "result" not in event


def test_stable_telemetry_classifies_scope_and_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record inspect scope and a shared draft revision without payload contents."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        telemetry_path = Path(temp_dir) / "telemetry" / "dispatch.jsonl"
        monkeypatch.setenv(TELEMETRY_PATH_ENV, str(telemetry_path))
        collector = _ToolCollector()
        register_stable_tools(
            collector,
            root=REPO_ROOT,
            image_factory=lambda data: data,
            annotation_factory=lambda values: dict(values),
        )
        tools = {str(item["name"]): item["function"] for item in collector.tools}

        mutation = tools["edit_section"](
            logfile_path=str(fixture.single_logfile),
            operation="update",
            section_id="main",
            subtitle="Telemetry revision",
        )
        inspection = tools["inspect_authoring"](
            logfile_path=str(fixture.single_logfile),
            object_kind="track",
            section_id="main",
            detail="summary",
        )
        events = [
            json.loads(line)
            for line in telemetry_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        assert mutation["revision"]
        assert inspection["revision"] == mutation["revision"]
        assert events[0]["operation"] == "update"
        assert events[0]["section_id"] == "main"
        assert events[0]["draft_revision"] == mutation["revision"]
        assert events[1]["object_kind"] == "track"
        assert events[1]["detail"] == "summary"
        assert events[1]["draft_revision"] == mutation["revision"]
        assert len(events[1]["argument_sha256"]) == 64
        assert "arguments" not in events[1]
        assert "result" not in events[1]


def test_stable_mutation_matches_direct_authoring_service() -> None:
    """A projected section edit produces the same canonical document as the API."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        temp_root = Path(temp_dir)
        projected = temp_root / "projected.log.yaml"
        direct = temp_root / "direct.log.yaml"
        _seed_draft(projected)
        _seed_draft(direct)

        result = dispatch_stable_tool(
            "edit_section",
            {
                "logfile_path": str(projected),
                "operation": "update",
                "section_id": "main_pass",
                "subtitle": "Projection parity",
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        direct_spec = service.load_logfile(direct, allowed_root=REPO_ROOT)
        direct_authoring = AuthoringService.from_mapping(service.report_to_dict(direct_spec))
        direct_authoring.update(
            UpdateSectionRequest(
                section_id="main_pass",
                patch=SectionPatch(subtitle="Projection parity"),
            )
        )
        service._persist_validated_logfile_mapping(
            service.authoring_document_to_logfile_mapping(direct_authoring.document),
            logfile_path=direct,
            root=REPO_ROOT,
        )

        assert result["ok"] is True
        assert result["changed"] is True
        assert result["target"] == {
            "object_kind": "section",
            "object_id": "main_pass",
            "section_id": "main_pass",
        }
        assert result["changed_fields"] == ["subtitle"]
        assert result["before"]["subtitle"] != result["after"]["subtitle"]
        assert _canonical_document(projected) == _canonical_document(direct)


def test_stable_section_depth_range_adapts_public_object_to_domain_tuple() -> None:
    """Convert one MCP depth-range object before constructing the domain patch."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "depth-range.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "edit_section",
            {
                "logfile_path": str(draft),
                "operation": "update",
                "section_id": "main_pass",
                "depth_range": {"minimum": 25.0, "maximum": 4845.0, "unit": "ft"},
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        section = saved["document"]["layout"]["log_sections"][0]
        assert result["ok"] is True
        assert result["changed"] is True
        assert result["changed_fields"] == ["depth_range"]
        assert section["depth_range"] == [25.0, 4845.0]


def test_stable_section_view_reuses_depth_range_adapter() -> None:
    """Keep the composite section-view mutation on the same public contract."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "section-view-depth-range.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "edit_report_settings",
            {
                "logfile_path": str(draft),
                "operation": "set_section_view",
                "section_id": "main_pass",
                "depth_range": {"minimum": 25.0, "maximum": 4845.0, "unit": "ft"},
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert result["ok"] is True
        assert result["changed"] is True


@pytest.mark.parametrize(
    ("depth_range", "message"),
    [
        ([25.0, 4845.0], "object"),
        ({"minimum": 4845.0, "maximum": 25.0}, "maximum greater"),
        ({"minimum": 25.0, "maximum": 4845.0, "extra": 1}, "no extra"),
    ],
)
def test_stable_section_depth_range_rejects_ambiguous_public_shapes(
    depth_range: object,
    message: str,
) -> None:
    """Reject list, reversed, and extra-field depth ranges at the stable boundary."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "depth-range-invalid.log.yaml"
        _seed_draft(draft)

        with pytest.raises(TemplateValidationError, match=message):
            dispatch_stable_tool(
                "edit_section",
                {
                    "logfile_path": str(draft),
                    "operation": "update",
                    "section_id": "main_pass",
                    "depth_range": depth_range,
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )


def test_stable_section_depth_range_rejects_unsupported_unit() -> None:
    """Keep unsupported depth units explicit instead of silently persisting them."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "depth-range-unit.log.yaml"
        _seed_draft(draft)

        with pytest.raises(TemplateValidationError, match="Unsupported conversion"):
            dispatch_stable_tool(
                "edit_section",
                {
                    "logfile_path": str(draft),
                    "operation": "update",
                    "section_id": "main_pass",
                    "depth_range": {
                        "minimum": 25.0,
                        "maximum": 4845.0,
                        "unit": "furlong",
                    },
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )


def test_stable_create_draft_returns_only_creation_evidence() -> None:
    """Draft creation reports the new artifact identity instead of document snapshots."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "created.log.yaml"

        result = dispatch_stable_tool(
            "create_draft",
            {
                "operation": "clone",
                "logfile_path": str(draft),
                "source_logfile_path": SOURCE_LOGFILE,
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert result["ok"] is True
        assert result["changed"] is True
        assert result["logfile_path"] == str(draft)
        assert result["section_ids"] == ["main_pass", "repeat_pass"]
        assert result["section_count"] == 2
        assert "before" not in result
        assert "after" not in result


def test_stable_inspections_honor_summary_full_and_family_scope() -> None:
    """Summary inspections are compact while full and family scopes stay deliberate."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "inspection.log.yaml"
        _seed_draft(draft)

        summary = dispatch_stable_tool(
            "inspect_authoring",
            {
                "logfile_path": str(draft),
                "object_kind": "track",
                "section_id": "main_pass",
                "detail": "summary",
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )
        full = dispatch_stable_tool(
            "inspect_authoring",
            {
                "logfile_path": str(draft),
                "object_kind": "track",
                "section_id": "main_pass",
                "detail": "full",
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )
        track_vocabulary = dispatch_stable_tool(
            "inspect_vocab",
            {"family": "track", "detail": "summary"},
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )
        vocabulary_index = dispatch_stable_tool(
            "inspect_vocab",
            {"detail": "summary"},
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert summary["items"]
        assert set(summary["items"][0]) == {"ref", "summary"}
        assert "object" in full["items"][0]
        assert len(json.dumps(summary)) < len(json.dumps(full))

        vocabulary = track_vocabulary["items"][0]
        assert vocabulary["family"] == "track"
        assert set(vocabulary["values"]) == {
            "track_kinds",
            "track_patch_keys",
            "track_archetypes",
            "move_track_selectors",
        }
        assert "scale_kinds" not in vocabulary["values"]
        assert vocabulary_index["items"][0]["values"] == {}
        assert "track" in vocabulary_index["items"][0]["available_families"]


def test_stable_section_replication_copies_a_validated_scaffold() -> None:
    """Expose the existing deterministic section replication primitive to the agent."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)

        result = dispatch_stable_tool(
            "replicate_section_structure",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "replicate",
                "source_section_id": "main",
                "target_section_id": "repeat",
                "source_path": str(fixture.las_path),
                "source_format": "las",
                "title": "Repeat",
                "subtitle": "Fixture Repeat",
                "include_bindings": False,
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8"))
        sections = saved["document"]["layout"]["log_sections"]
        main = next(section for section in sections if section["id"] == "main")
        repeat = next(section for section in sections if section["id"] == "repeat")

        assert result["ok"] is True
        assert result["changed"] is True
        assert [track["id"] for track in repeat["tracks"]] == [
            track["id"] for track in main["tracks"]
        ]
        assert repeat["data"]["source_format"] == "las"


def test_stable_section_replication_is_retry_safe_and_returns_id_map() -> None:
    """Equivalent section replication is a stable no-op on retry."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        arguments = {
            "logfile_path": str(fixture.single_logfile),
            "operation": "replicate",
            "source_section_id": "main",
            "target_section_id": "repeat",
            "title": "Repeat",
            "subtitle": "Retry-safe Repeat",
            "include_bindings": True,
        }

        first = dispatch_stable_tool(
            "replicate_section_structure",
            arguments,
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )
        first_bytes = fixture.single_logfile.read_bytes()
        second = dispatch_stable_tool(
            "replicate_section_structure",
            arguments,
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert first["ok"] is True
        assert first["changed"] is True
        assert first["already_exists"] is False
        assert first["id_map"]
        assert second["ok"] is True
        assert second["changed"] is False
        assert second["already_exists"] is True
        assert second["id_map"] == first["id_map"]
        assert fixture.single_logfile.read_bytes() == first_bytes


def test_stable_section_replication_rejects_conflicting_existing_target() -> None:
    """A conflicting target remains an explicit error instead of being overwritten."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        dispatch_stable_tool(
            "replicate_section_structure",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "replicate",
                "source_section_id": "main",
                "target_section_id": "repeat",
                "title": "Repeat",
                "include_bindings": False,
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        with pytest.raises(
            TemplateValidationError,
            match="different properties.*overwrite=True",
        ):
            dispatch_stable_tool(
                "replicate_section_structure",
                {
                    "logfile_path": str(fixture.single_logfile),
                    "operation": "replicate",
                    "source_section_id": "main",
                    "target_section_id": "repeat",
                    "title": "Conflicting Repeat",
                    "include_bindings": False,
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )


def test_stable_track_set_scales_updates_track_and_curve_scale() -> None:
    """Expose one deterministic operation for synchronized track-scale edits."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "scales.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "edit_track",
            {
                "logfile_path": str(draft),
                "operation": "set_scales",
                "section_id": "main_pass",
                "track_id": "combo",
                "x_scale": {
                    "kind": "log",
                    "min": 0.2,
                    "max": 2000,
                    "unit": "ohm.m",
                },
                "channel_scales": {
                    "ECGR_STGC": {
                        "kind": "log",
                        "min": 0.2,
                        "max": 2000,
                        "unit": "ohm.m",
                    }
                },
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        track = next(
            item
            for item in saved["document"]["layout"]["log_sections"][0]["tracks"]
            if item["id"] == "combo"
        )
        binding = next(
            item
            for item in saved["document"]["bindings"]["channels"]
            if item.get("section") == "main_pass" and item.get("channel") == "ECGR_STGC"
        )

        assert result["changed"] is True
        assert track["x_scale"] == {
            "kind": "log",
            "min": 0.2,
            "max": 2000,
            "reverse": False,
        }
        assert binding["scale"] == {
            "kind": "log",
            "min": 0.2,
            "max": 2000,
            "reverse": False,
        }


def test_stable_track_add_validates_all_creation_fields_at_once() -> None:
    """A malformed add reports every missing creation field in one response."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "track-add.log.yaml"
        _seed_draft(draft)

        with pytest.raises(
            TemplateValidationError,
            match="Missing: title, kind, width_mm",
        ):
            dispatch_stable_tool(
                "edit_track",
                {
                    "logfile_path": str(draft),
                    "operation": "add",
                    "section_id": "main_pass",
                    "track_id": "resistivity",
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )


def test_stable_track_add_is_idempotent_for_equivalent_definition() -> None:
    """A retry of an equivalent track add is a successful, non-mutating no-op."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "track-add.log.yaml"
        _seed_draft(draft)
        original = draft.read_bytes()

        result = dispatch_stable_tool(
            "edit_track",
            {
                "logfile_path": str(draft),
                "operation": "add",
                "section_id": "main_pass",
                "track_id": "depth",
                "title": "depth",
                "kind": "reference",
                "width_mm": 36,
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert result["ok"] is True
        assert result["changed"] is False
        assert result["already_exists"] is True
        assert draft.read_bytes() == original


def test_stable_track_add_rejects_conflicting_existing_definition() -> None:
    """A conflicting add tells the provider to use update instead."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "track-add.log.yaml"
        _seed_draft(draft)

        with pytest.raises(
            TemplateValidationError,
            match="different properties .*operation='update'",
        ):
            dispatch_stable_tool(
                "edit_track",
                {
                    "logfile_path": str(draft),
                    "operation": "add",
                    "section_id": "main_pass",
                    "track_id": "depth",
                    "title": "Different Depth",
                    "kind": "reference",
                    "width_mm": 36,
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )


def test_stable_track_update_syncs_grid_to_log_scale() -> None:
    """Keep logarithmic grid metadata synchronized for ordinary track updates."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "track-update.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "edit_track",
            {
                "logfile_path": str(draft),
                "operation": "update",
                "section_id": "main_pass",
                "track_id": "combo",
                "x_scale": {"kind": "log", "min": 0.2, "max": 20},
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        track = next(
            item
            for item in saved["document"]["layout"]["log_sections"][0]["tracks"]
            if item["id"] == "combo"
        )
        vertical = track["grid"]["vertical"]

        assert result["changed"] is True
        assert vertical["main"]["scale"] == "logarithmic"
        assert vertical["main"]["spacing_mode"] == "scale"
        assert vertical["secondary"]["scale"] == "logarithmic"
        assert vertical["secondary"]["spacing_mode"] == "scale"


def test_stable_array_track_update_accepts_x_scale() -> None:
    """Array tracks support the shared sample-axis scale used by raster plots."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "array-scale.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "edit_track",
            {
                "logfile_path": str(draft),
                "operation": "update",
                "section_id": "main_pass",
                "track_id": "vdl",
                "x_scale": {"kind": "linear", "min": 250, "max": 1100},
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        tracks = saved["document"]["layout"]["log_sections"][0]["tracks"]
        vdl = next(track for track in tracks if track["id"] == "vdl")

        assert result["changed"] is True
        assert vdl["x_scale"] == {
            "kind": "linear",
            "min": 250,
            "max": 1100,
            "reverse": False,
        }


def test_stable_report_settings_updates_matplotlib_style() -> None:
    """Keep report-wide style edits inside the stable report-settings tool."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "style.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "edit_report_settings",
            {
                "logfile_path": str(draft),
                "operation": "set_matplotlib_style",
                "style_patch": {
                    "grid": {
                        "depth_minor_linewidth": 0.45,
                        "x_minor_linewidth": 0.45,
                    }
                },
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        style = saved["render"]["matplotlib"]["style"]
        assert result["ok"] is True
        assert result["changed"] is True
        assert result["target"] == {
            "object_kind": "document",
            "object_id": "document",
        }
        assert result["after"]["style"]["grid"]["depth_minor_linewidth"] == 0.45
        assert style["grid"]["x_minor_linewidth"] == 0.45


def test_stable_header_values_use_qualified_rm_target() -> None:
    """Route a qualified RM phrase to the bottom-temperature slot."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        draft = fixture.single_logfile
        service.apply_header_archetype(
            str(draft),
            archetype_id="open_hole",
            root=REPO_ROOT,
        )

        result = dispatch_stable_tool(
            "edit_header",
            {
                "logfile_path": str(draft),
                "operation": "apply_values",
                "values": {"RM at bottom temperature": "0.010 @ 100"},
                "overwrite_policy": "replace",
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        rows = saved["document"]["layout"]["heading"]["detail"]["rows"]
        bottom = next(row for row in rows if row.get("key") == "rm_bottom_temp")
        measured = next(row for row in rows if row.get("key") == "rm_measured_temp")
        assert result["changed"] is True
        assert [entry["target_key"] for entry in result["applied_assignments"]] == [
            "rm_bottom_temp"
        ]
        assert bottom["columns"][0]["cells"][0] == "0.010"
        assert bottom["columns"][0]["cells"][2] == "100"
        assert measured["columns"][0]["cells"][0] == ""


def test_stable_remarks_accept_line_based_content() -> None:
    """Persist the canonical line-based representation accepted by the schema."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        draft = fixture.single_logfile

        result = dispatch_stable_tool(
            "edit_remarks",
            {
                "logfile_path": str(draft),
                "operation": "add",
                "remark": {
                    "title": "Notes",
                    "lines": [
                        "Open-hole quicklook from a user-supplied LAS file.",
                        "Only source-confirmed channels should be plotted.",
                    ],
                    "alignment": "left",
                },
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(draft.read_text(encoding="utf-8"))
        remarks = saved["document"]["layout"]["remarks"]
        assert result["ok"] is True
        assert result["changed"] is True
        assert remarks[-1]["lines"] == [
            "Open-hole quicklook from a user-supplied LAS file.",
            "Only source-confirmed channels should be plotted.",
        ]


def test_stable_remarks_reject_missing_content_with_actionable_error() -> None:
    """Reject title-only remarks without exposing a Pydantic traceback."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)

        with pytest.raises(
            TemplateValidationError,
            match=r"edit_remarks\(operation='add'\) requires actual remark content\.",
        ) as error:
            dispatch_stable_tool(
                "edit_remarks",
                {
                    "logfile_path": str(fixture.single_logfile),
                    "operation": "add",
                    "remark": {
                        "title": "Notes",
                        "alignment": "left",
                    },
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )

        message = str(error.value)
        assert "Provide either non-empty remark.text" in message
        assert "validation error for AuthoringRemarkSpec" not in message


def test_registered_remarks_tool_translates_schema_validation_error() -> None:
    """The registered MCP callback does not leak Pydantic validation text."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        collector = _ToolCollector()
        register_stable_tools(
            collector,
            root=REPO_ROOT,
            image_factory=lambda data: data,
            annotation_factory=lambda values: dict(values),
        )
        remarks_tool = next(
            item["function"] for item in collector.tools if item["name"] == "edit_remarks"
        )

        with pytest.raises(
            TemplateValidationError,
            match=r"edit_remarks\(operation='add'\) requires actual remark content\.",
        ):
            remarks_tool(
                logfile_path=str(fixture.single_logfile),
                operation="add",
                remark={"title": "Notes", "lines": []},
            )


def test_stable_fill_persists_between_instance_crossover_metadata() -> None:
    """The stable fill operation preserves catalog-driven crossover styling."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        dispatch_stable_tool(
            "edit_track",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "add",
                "section_id": "main",
                "track_id": "overlay",
                "title": "Overlay",
                "kind": "normal",
                "width_mm": 28,
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )
        for channel, binding_id in (("GR", "overlay.gr"), ("CALI", "overlay.cali")):
            dispatch_stable_tool(
                "edit_curve_binding",
                {
                    "logfile_path": str(fixture.single_logfile),
                    "operation": "add",
                    "section_id": "main",
                    "track_id": "overlay",
                    "channel": channel,
                    "binding_id": binding_id,
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )

        result = dispatch_stable_tool(
            "edit_fill",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "add",
                "section_id": "main",
                "track_id": "overlay",
                "channel": "CALI",
                "binding_id": "overlay.cali",
                "other_binding_id": "overlay.gr",
                "kind": "between_instances",
                "label": "Crossover",
                "color": "#d1d5db",
                "alpha": 0.18,
                "crossover": {
                    "enabled": True,
                    "left_color": "#bfdbfe",
                    "right_color": "#fed7aa",
                    "alpha": 0.28,
                },
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8"))
        fill = next(
            item
            for item in saved["document"]["bindings"]["channels"]
            if item.get("id") == "overlay.cali"
        )["fill"]
        assert result["changed"] is True
        assert fill["kind"] == "between_instances"
        assert fill["other_element_id"] == "overlay.gr"
        assert fill["crossover"]["enabled"] is True


def test_stable_source_inspection_is_json_serializable() -> None:
    """Normalize NumPy-backed LAS metadata and gate full metadata explicitly."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)

        result = dispatch_stable_tool(
            "inspect_source",
            {
                "source_path": str(fixture.las_path),
                "source_format": "auto",
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )
        with_metadata = dispatch_stable_tool(
            "inspect_source",
            {
                "source_path": str(fixture.las_path),
                "source_format": "auto",
                "include_metadata": True,
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        json.dumps(result)
        assert result["available_channels"]
        assert "GR" in result["available_channels"]
        assert "well_metadata" not in result["items"][0]
        assert "well_metadata" in with_metadata["items"][0]


def test_stable_binding_update_infers_channel_from_binding_id() -> None:
    """Existing binding updates need not repeat the channel identity."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        result = dispatch_stable_tool(
            "edit_curve_binding",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "update",
                "section_id": "main",
                "track_id": "cbl",
                "binding_id": "main.cbl.CBL.1",
                "patch": {"label": "CBL amplitude"},
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert result["ok"] is True
        assert result["changed"] is True


def test_stable_curve_add_projects_canonical_scale_to_legacy_yaml() -> None:
    """Stable curve additions persist typed bounds as legacy min/max keys."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        result = dispatch_stable_tool(
            "edit_curve_binding",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "add",
                "section_id": "main",
                "track_id": "cbl",
                "channel": "GR",
                "binding_id": "main.cbl.GR.typed",
                "label": "Gamma Ray",
                "scale": {
                    "kind": "linear",
                    "minimum": -80,
                    "maximum": 20,
                    "unit": "mV",
                },
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8"))
        binding = next(
            item
            for item in saved["document"]["bindings"]["channels"]
            if item.get("id") == "main.cbl.GR.typed"
        )
        assert result["ok"] is True
        assert binding["scale"] == {
            "kind": "linear",
            "min": -80,
            "max": 20,
            "reverse": False,
        }


def test_stable_curve_add_projects_canonical_style_to_legacy_yaml() -> None:
    """Stable curve additions persist alpha as the legacy opacity key."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        dispatch_stable_tool(
            "edit_curve_binding",
            {
                "logfile_path": str(fixture.single_logfile),
                "operation": "add",
                "section_id": "main",
                "track_id": "cbl",
                "channel": "GR",
                "binding_id": "main.cbl.GR.styled",
                "style": {"color": "#2e7d32", "alpha": 0.6},
            },
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        saved = yaml.safe_load(fixture.single_logfile.read_text(encoding="utf-8"))
        binding = next(
            item
            for item in saved["document"]["bindings"]["channels"]
            if item.get("id") == "main.cbl.GR.styled"
        )
        assert binding["style"]["color"] == "#2e7d32"
        assert binding["style"]["opacity"] == 0.6


def test_stable_scoped_preview_uses_section_renderer() -> None:
    """A section-scoped preview must render the log section, not report page zero."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir), repo_root=REPO_ROOT)
        with (
            patch(
                "wellplot.mcp.stable.service.preview_section_png",
                return_value=b"section-preview",
            ) as section_preview,
            patch("wellplot.mcp.stable.service.preview_logfile_png") as report_preview,
        ):
            result = dispatch_stable_tool(
                "preview_logfile",
                {
                    "logfile_path": str(fixture.single_logfile),
                    "section_id": "main",
                    "page": 0,
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )

        assert result == b"section-preview"
        section_preview.assert_called_once()
        report_preview.assert_not_called()


def test_invalid_projected_mutation_does_not_persist() -> None:
    """Typed service validation rejects an invalid projection before persistence."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "draft.log.yaml"
        _seed_draft(draft)
        original = draft.read_bytes()

        with pytest.raises(TemplateValidationError, match="Unsupported track patch keys"):
            dispatch_stable_tool(
                "edit_track",
                {
                    "logfile_path": str(draft),
                    "operation": "update",
                    "section_id": "main_pass",
                    "track_id": "combo",
                    "patch": {"not_a_track_field": True},
                },
                root=REPO_ROOT,
                image_factory=lambda data: data,
            )

        assert draft.read_bytes() == original


def test_stable_validation_reports_invalid_documents() -> None:
    """The validation responsibility returns a structured failure without mutation."""
    with TemporaryDirectory(dir=REPO_ROOT) as temp_dir:
        draft = Path(temp_dir) / "draft.log.yaml"
        _seed_draft(draft)

        result = dispatch_stable_tool(
            "validate_logfile",
            {"logfile_path": str(draft), "operation": "validate"},
            root=REPO_ROOT,
            image_factory=lambda data: data,
        )

        assert result["ok"] is True
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["validation_level"] == "render"
