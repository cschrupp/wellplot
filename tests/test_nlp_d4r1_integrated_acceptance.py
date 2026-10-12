"""Provider-free integrated acceptance for the typed D4R1 delivery route."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT

from wellplot.agent import direct_notebook
from wellplot.agent.code_mode.canonical_workers import ReportSemanticResponse
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.typed_delivery import (
    DeliveryCurve,
    DeliveryFill,
    DeliveryRaster,
    DeliveryReportResponse,
    DeliverySampleAxis,
    DeliveryScale,
    DeliverySection,
    DeliverySectionResponse,
    DeliverySlotValue,
    DeliveryStyle,
    DeliveryTarget,
    DeliveryTrack,
)
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

_CBL_GENERAL_VALUES = {
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

_CBL_DETAIL_VALUES = {
    "detail.row_2.column_1.cell_1": "ONE",
    "detail.row_4.column_1.cell_1": "4980.00 ft",
    "detail.row_5.column_1.cell_1": "TD Not Tag",
    "detail.row_12.value_1": "8.4 lbm/gal",
    "detail.row_19.column_1.cell_1": "177.2 degF",
    "detail.row_23.value_1": "D. May / D. Jones",
    "detail.row_24.value_1": "Leroy Swearingen",
}


def _scale(
    minimum: float,
    maximum: float,
    *,
    kind: str = "linear",
    reverse: bool = False,
) -> DeliveryScale:
    """Build one deterministic worker-owned scale."""
    return DeliveryScale(kind=kind, minimum=minimum, maximum=maximum, reverse=reverse)


def _curve(
    semantic_id: str,
    channel: str,
    label: str,
    scale: DeliveryScale,
    *,
    color: str,
    line_style: str,
    alpha: float,
) -> DeliveryCurve:
    """Build one deterministic typed scalar binding."""
    return DeliveryCurve(
        semantic_id=semantic_id,
        channel=channel,
        label=label,
        scale=scale,
        style=DeliveryStyle(
            color=color,
            line_style=line_style,
            line_width=alpha,
            alpha=alpha,
        ),
    )


def _cbl_section_response(*, source_candidate: str, title: str) -> DeliverySectionResponse:
    """Build one exact CBL section response from the frozen verifier contract."""
    combo = DeliveryTrack(
        semantic_id="combo",
        kind="normal",
        title="Combo",
        width_mm=50,
        curves=(
            _curve(
                "ecgr",
                "ECGR_STGC",
                "Gamma Ray (ECGR_STGC) QTGC-B",
                _scale(0, 150),
                color="#16a34a",
                line_style="solid",
                alpha=0.8,
            ),
            _curve(
                "tt",
                "TT",
                "Transit Time for CBL (TT) QSLT-B",
                _scale(200, 400, reverse=True),
                color="#2142ff",
                line_style="solid",
                alpha=0.75,
            ),
            _curve(
                "tens",
                "TENS",
                "Cable Tension (TENS)",
                _scale(5000, 0),
                color="#111111",
                line_style="dashed",
                alpha=0.65,
            ),
            _curve(
                "mtem",
                "MTEM",
                "Mud Temperature (MTEM) LEH-MT",
                _scale(100, 500),
                color="#111111",
                line_style="solid",
                alpha=0.9,
            ),
        ),
    )
    depth = DeliveryTrack(
        semantic_id="depth",
        kind="reference",
        title="Depth",
        width_mm=10,
        curves=(
            _curve(
                "stit",
                "STIT",
                "Stuck Tool Indicator, Total (STIT)",
                _scale(0, 50),
                color="#111111",
                line_style="solid",
                alpha=0.65,
            ),
            _curve(
                "tdsp",
                "TDSP",
                "Cable Drag",
                _scale(0, 50),
                color="#92400e",
                line_style="dotted",
                alpha=0.65,
            ),
            _curve(
                "vsec",
                "VSEC",
                "Tool_Tot. Drag",
                _scale(0, 50),
                color="#1d4ed8",
                line_style="dashed",
                alpha=0.65,
            ),
        ),
    )
    cbl = DeliveryTrack(
        semantic_id="cbl",
        kind="normal",
        title="CBL",
        width_mm=44,
        curves=(
            _curve(
                "cbl-wide",
                "CBL",
                "CBL Amplitude (CBL) QSLT-B",
                _scale(0, 100),
                color="#111111",
                line_style="solid",
                alpha=0.75,
            ),
            _curve(
                "cbl-narrow",
                "CBL",
                "CBL Amplitude (CBL) QSLT-B",
                _scale(0, 10),
                color="#2563eb",
                line_style="dashed",
                alpha=0.65,
            ),
        ),
    )
    vdl = DeliveryTrack(
        semantic_id="vdl",
        kind="array",
        title="VDL",
        width_mm=48,
        scale=_scale(200, 1200),
        grid_vertical_main_visible=False,
        grid_vertical_secondary_visible=False,
        rasters=(
            DeliveryRaster(
                semantic_id="vdl",
                channel="VDL",
                label="VDL VariableDensity (VDL) QSLT-B",
                profile="vdl",
                colormap="gray_r",
                colorbar_enabled=True,
                colorbar_label="Amplitude",
                colorbar_position="header",
                sample_axis=DeliverySampleAxis(
                    unit="us",
                    minimum=200,
                    maximum=1200,
                    tick_count=7,
                    source_origin=40,
                    source_step=10,
                ),
            ),
        ),
    )
    return DeliverySectionResponse(
        mode="reconstruct",
        section=DeliverySection(
            title=title,
            source_candidate=source_candidate,
            tracks=(combo, depth, cbl, vdl),
        ),
    )


def _cbl_report_response(payload: dict[str, Any]) -> DeliveryReportResponse:
    """Build the report fragment using only host-advertised slots."""
    slots = payload["report_context"]["header_slots"]
    general_fields = []
    detail_fields = []
    service_titles = []
    for slot in slots:
        slot_id = str(slot["slot_id"])
        key = slot.get("key")
        if slot_id.startswith("general.") and key in _CBL_GENERAL_VALUES:
            general_fields.append(
                DeliverySlotValue(slot_id=slot_id, value=_CBL_GENERAL_VALUES[key])
            )
        elif slot_id.startswith("detail.") and slot_id in _CBL_DETAIL_VALUES:
            detail_fields.append(
                DeliverySlotValue(slot_id=slot_id, value=_CBL_DETAIL_VALUES[slot_id])
            )
        elif slot_id.startswith("service_title."):
            service_titles.append(
                DeliverySlotValue(
                    slot_id=slot_id,
                    value=(
                        "Cement Bond Log",
                        "Variable Density Log",
                        "Gamma Ray - CCL",
                    )[len(service_titles)],
                )
            )
    return DeliveryReportResponse(
        general_fields=tuple(general_fields),
        service_titles=tuple(service_titles),
        detail_fields=tuple(detail_fields),
        remarks=(
            {
                "semantic_id": "scope",
                "title": "Supported Reconstruction Scope",
                "lines": ("Reconstruct only the supported subset of this packet.",),
            },
            {
                "semantic_id": "sources",
                "title": "Data Sources",
                "lines": ("This packet uses staged DLIS files.",),
            },
            {
                "semantic_id": "notice",
                "title": "Public Data and IP Notice",
                "lines": ("Rendered by wellplot for educational use.",),
            },
        ),
    )


def _plan_for(request: str) -> SemanticPlan:
    """Return the deterministic planner output for one frozen D4 request."""
    if request.startswith("Using CBL_Main.dlis"):
        section_capabilities = (
            "section.log_plot",
            "track.normal",
            "track.reference",
            "track.array",
            "binding.curve",
            "binding.raster",
        )
        return SemanticPlan(
            summary="Reconstruct the bounded CBL packet.",
            report_task=ReportTask(
                goal="Populate the supported CBL report metadata.",
                capability_ids=("report.standard",),
                requirements=(request,),
            ),
            section_tasks=(
                SectionTask(
                    goal="Reconstruct the main CBL pass.",
                    capability_ids=section_capabilities,
                    existing_section_hint="Main Pass",
                    source_hints=("CBL_Main.dlis",),
                    requirements=(request,),
                ),
                SectionTask(
                    goal="Reconstruct the repeat CBL pass.",
                    capability_ids=section_capabilities,
                    existing_section_hint="Repeat Pass",
                    source_hints=("CBL_Repeat.dlis",),
                    requirements=(request,),
                ),
            ),
        )
    if request.startswith("Rename this report"):
        return SemanticPlan(
            summary="Rename the report.",
            report_task=ReportTask(
                goal="Rename the report.",
                capability_ids=("report.standard",),
                requirements=(request,),
            ),
        )
    section_hint = "Main Log"
    if "Main Log – Upper" in request:
        section_hint = "Main Log – Upper"
    source_hints = ("missing_neutron.las",) if "missing_neutron.las" in request else ()
    capability_ids = ["section.log_plot", "track.normal", "binding.curve"]
    if "fill from" in request:
        capability_ids.append("fill.curve")
    return SemanticPlan(
        summary="Apply the requested LAS change.",
        section_tasks=(
            SectionTask(
                goal="Apply the requested LAS change.",
                capability_ids=tuple(capability_ids),
                existing_section_hint=section_hint,
                source_hints=source_hints,
                requirements=(request,),
            ),
        ),
    )


def _section_response(request: str, payload: dict[str, Any]) -> DeliverySectionResponse:
    """Return one typed worker response for the frozen request."""
    if request.startswith("Using CBL_Main.dlis"):
        source = payload["section_context"]["sources"][0]["candidate_id"]
        section_task = payload["section_task"]
        title = (
            "Main Pass" if section_task["existing_section_hint"] == "Main Pass" else "Repeat Pass"
        )
        return _cbl_section_response(source_candidate=source, title=title)
    if (
        "set the Gamma Ray curve" in request
        or "change the Gamma Ray curve" in request
        or "20–110" in request
    ):
        minimum, maximum = (20, 110) if "20–110" in request else (5, 125)
        return DeliverySectionResponse(
            mode="update_curve_scale",
            target=DeliveryTarget(channel="GR"),
            scale=_scale(minimum, maximum),
        )
    if "Append a 30 mm normal track" in request:
        return DeliverySectionResponse(
            mode="add_track_curve",
            track=DeliveryTrack(
                semantic_id="resistivity-qc",
                kind="normal",
                title="Resistivity QC",
                width_mm=30,
                curves=(
                    DeliveryCurve(
                        semantic_id="ild",
                        channel="ILD",
                        label="Resistivity QC",
                        scale=_scale(0.2, 2000, kind="log"),
                    ),
                ),
            ),
        )
    if "fill from the Gamma Ray curve" in request:
        return DeliverySectionResponse(
            mode="add_fill",
            target=DeliveryTarget(channel="GR"),
            fill=DeliveryFill(
                semantic_id="gr-fill",
                target_binding="GR",
                kind="to_lower_limit",
                color="#f2e8a0",
                alpha=0.2,
            ),
        )
    return DeliverySectionResponse(
        mode="add_track_curve",
        track=DeliveryTrack(
            semantic_id="resistivity-alias-qc",
            kind="normal",
            title="Resistivity Alias QC",
            width_mm=24,
            curves=(
                DeliveryCurve(
                    semantic_id="rt",
                    channel="RT",
                    label="Resistivity Alias QC",
                    scale=_scale(0.2, 2000, kind="log"),
                ),
            ),
        ),
    )


def _canonical_section_action(
    response: DeliverySectionResponse,
    payload: dict[str, Any],
) -> dict[str, object]:
    """Translate the frozen fixture response into the canonical action contract."""
    if response.mode == "update_curve_scale":
        target_channel = response.target.channel if response.target is not None else None
        handles = payload["section_context"]["existing_curves"]
        handle = next(
            item["handle"]
            for item in handles
            if target_channel is None or item["channel"] == target_channel
        )
        return {
            "action": "update_curve_scale",
            "target": {"handle": handle},
            "scale": response.scale.model_dump(mode="json"),
        }
    if response.mode in {"add_track", "add_track_curve"}:
        track = response.track
        assert track is not None
        bindings: list[dict[str, object]] = []
        for curve in track.curves:
            item = {
                "kind": "curve",
                "semantic_id": curve.semantic_id,
                "channel": curve.channel,
            }
            if curve.label is not None:
                item["label"] = curve.label
            if curve.scale is not None:
                item["scale"] = curve.scale.model_dump(mode="json")
            if curve.style is not None:
                item["style"] = curve.style.model_dump(mode="json")
            bindings.append(item)
        track_payload: dict[str, object] = {
            "semantic_id": track.semantic_id,
            "kind": track.kind,
            "title": track.title,
            "bindings": bindings,
        }
        if track.width_mm is not None:
            track_payload["width_mm"] = track.width_mm
        if track.scale is not None:
            track_payload["x_scale"] = track.scale.model_dump(mode="json")
        return {"action": "add_track", "track": track_payload}
    if response.mode == "add_fill":
        target_channel = response.target.channel if response.target is not None else None
        handles = payload["section_context"]["existing_curves"]
        handle = next(
            item["handle"]
            for item in handles
            if target_channel is None or item["channel"] == target_channel
        )
        assert response.fill is not None
        fill_payload = {
            key: value
            for key, value in response.fill.model_dump(mode="json").items()
            if value is not None
        }
        return {
            "action": "add_fill",
            "target": {"handle": handle},
            "fill": fill_payload,
        }
    assert response.section is not None
    tracks: list[dict[str, object]] = []
    for track in response.section.tracks:
        bindings: list[dict[str, object]] = []
        for curve in track.curves:
            item = {
                "kind": "curve",
                "semantic_id": curve.semantic_id,
                "channel": curve.channel,
                "label": curve.label,
                "scale": curve.scale.model_dump(mode="json") if curve.scale else None,
                "style": (
                    {
                        key: value
                        for key, value in curve.style.model_dump(mode="json").items()
                        if value is not None
                    }
                    if curve.style
                    else None
                ),
            }
            bindings.append({key: value for key, value in item.items() if value is not None})
        for raster in track.rasters:
            item = {
                "kind": "raster",
                "semantic_id": raster.semantic_id,
                "channel": raster.channel,
                "label": raster.label,
                "profile": raster.profile,
                "colormap": raster.colormap,
                "alpha": raster.alpha,
                "colorbar_enabled": raster.colorbar_enabled,
                "colorbar_label": raster.colorbar_label,
                "colorbar_position": raster.colorbar_position,
                "sample_axis": (
                    raster.sample_axis.model_dump(mode="json") if raster.sample_axis else None
                ),
            }
            bindings.append({key: value for key, value in item.items() if value is not None})
        track_payload = {
            "semantic_id": track.semantic_id,
            "kind": track.kind,
            "title": track.title,
            "bindings": bindings,
        }
        if (
            track.grid_vertical_main_visible is not None
            or track.grid_vertical_secondary_visible is not None
        ):
            track_payload["grid"] = {
                key: value
                for key, value in {
                    "vertical_main_visible": track.grid_vertical_main_visible,
                    "vertical_secondary_visible": track.grid_vertical_secondary_visible,
                }.items()
                if value is not None
            }
        if track.width_mm is not None:
            track_payload["width_mm"] = track.width_mm
        if track.scale is not None:
            track_payload["x_scale"] = track.scale.model_dump(mode="json")
        tracks.append(track_payload)
    return {
        "action": "reconstruct",
        "section": {
            "title": response.section.title,
            "source_candidate": response.section.source_candidate,
            "tracks": tracks,
        },
    }


@dataclass
class _D4R1Backend:
    """Deterministic provider boundary for the integrated typed rehearsal."""

    current_request: str = ""
    planner_requests: list[str] = field(default_factory=list)
    structured_requests: list[StructuredGenerationRequest] = field(default_factory=list)
    worker_kinds: list[str] = field(default_factory=list)
    program_calls: int = 0

    def prepare(self, request: str) -> None:
        """Select the exact typed worker responses for one frozen turn."""
        self.current_request = request

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> StructuredGenerationResult[object]:
        """Return deterministic planner or typed-worker data without a provider."""
        self.structured_requests.append(request)
        if response_model is SemanticPlan:
            self.worker_kinds.append("planner")
            context = json.loads(request.user_prompt.split("Context:\n", 1)[1])
            self.planner_requests.append(str(context["request"]))
            assert context["request"] == self.current_request
            value: object = _plan_for(self.current_request)
        else:
            payload = json.loads(request.user_prompt)
            if response_model is ReportSemanticResponse:
                self.worker_kinds.append("report")
                if self.current_request.startswith("Rename this report"):
                    value = {"title": "Formation Integrity Review"}
                else:
                    value = _cbl_report_response(payload).model_dump(mode="json")
            else:
                self.worker_kinds.append("section")
                value = _canonical_section_action(
                    _section_response(self.current_request, payload), payload
                )
        return StructuredGenerationResult(
            value=response_model.model_validate(value),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )

    async def generate_program(self, request: ProgramGenerationRequest) -> object:
        """Fail if any typed route attempts to fall back to generated code."""
        del request
        self.program_calls += 1
        raise AssertionError("D4R1 typed acceptance must not call generate_program")


class _D4R1CountingBackend(d4.CountingBackend):
    """Count planner and typed-worker calls without legacy control assumptions."""

    def _before(
        self,
        operation: str,
        request: object,
        *,
        generation_role: str,
    ) -> int:
        """Reserve and attest every typed boundary call uniformly."""
        self._validate_controls(request, generation_role)
        if operation not in {"structured", "program"}:
            raise ValueError(f"unsupported operation: {operation}")
        if self.prompt_guard is not None:
            prompt = getattr(request, "user_prompt", None)
            if not isinstance(prompt, str):
                raise d4.PreflightError("generation request has no user prompt")
            self.prompt_guard(prompt)
        assert self.ledger is not None
        index = self.ledger.reserve()
        if self.call_started is not None:
            self.call_started(
                {
                    "event": "logical_call_started",
                    "index": index,
                    "operation": operation,
                    "generation_role": generation_role,
                    "provider": self.provider,
                    "model": self.model,
                    "temperature": getattr(request, "temperature", None),
                    "max_output_tokens": getattr(request, "max_output_tokens", None),
                }
            )
        return index


def test_typed_route_replays_all_frozen_d4_turns_provider_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run every frozen D4 turn through typed workers and the unchanged D4 grader."""
    cases = d4.load_cases(REPO_ROOT)
    gold = d4.load_gold(REPO_ROOT)
    expected_by_turn = {item["turn_id"]: item for item in gold["cases"]}
    backend = _D4R1Backend()
    calls: list[d4.LogicalCall] = []
    ledger = d4.LogicalCallLedger()
    counted = _D4R1CountingBackend(
        delegate=backend,
        provider="deterministic",
        model="d4r1-fixture-model",
        calls=calls,
        ledger=ledger,
    )

    def fake_provider_backend(**_kwargs: object) -> tuple[d4.CountingBackend, str]:
        return counted, "deterministic"

    monkeypatch.setattr(direct_notebook, "_provider_backend", fake_provider_backend)
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        artifact_root = Path(temporary)
        session, credential_source = direct_notebook._build_agent_session(
            provider="deterministic",
            model="d4r1-fixture-model",
            root=REPO_ROOT,
            api_key=None,
            base_url=None,
            timeout=120,
        )
        notebook = direct_notebook.DirectNotebookSession(
            session=session,
            provider="deterministic",
            model="d4r1-fixture-model",
            credential_source=credential_source,
            server_root=REPO_ROOT,
        )
        campaign = d4.D4CampaignAdapter(
            repo_root=REPO_ROOT,
            artifact_root=artifact_root,
            session=notebook,
            call_source=d4.CampaignCallSource(backends=(counted,), calls=calls, ledger=ledger),
            provider_backed=False,
        )

        grades: list[dict[str, Any]] = []
        actual_rows: list[dict[str, Any]] = []
        for case in cases:
            backend.prepare(str(case["request"]))
            actual = dict(
                asyncio.run(campaign.execute_turn(case, expected_by_turn[case["turn_id"]]))
            )
            expected = expected_by_turn[case["turn_id"]]
            grade = d4.grade_turn(actual, expected)
            assert grade["status"] == "PASS", (case["turn_id"], grade, actual)
            grades.append(grade)
            actual_rows.append(actual)

    assert [case["turn_id"] for case in cases] == [
        "D4-C01:C01",
        "D4-L01:T1",
        "D4-L01:T2",
        "D4-L01:T3",
        "D4-L01:T4",
        "D4-L02:T1",
        "D4-L02:T2",
        "D4-L03:C01",
        "D4-L04:C01",
    ]
    assert backend.planner_requests == [str(case["request"]) for case in cases]
    assert len(actual_rows) == 9
    assert all(row["persisted"] is True for row in actual_rows[:5])
    assert actual_rows[5]["persisted"] is False
    assert actual_rows[7]["persisted"] is False
    assert actual_rows[8]["persisted"] is False
    assert len(backend.structured_requests) == 18
    assert backend.worker_kinds.count("planner") == 9
    assert backend.worker_kinds.count("report") == 2
    assert backend.worker_kinds.count("section") == 7
    assert backend.program_calls == 0
    assert all(grade["status"] == "PASS" for grade in grades)
