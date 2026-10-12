"""Canonical typed semantic workers for the shared Code Mode engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, model_validator

from ...model.intent import (
    AuthoringDepthIntent,
    AuthoringDocumentIntent,
    AuthoringHeaderFieldIntent,
    AuthoringHeaderIntent,
    AuthoringPageIntent,
    AuthoringRemarkIntent,
    AuthoringReportValueIntent,
    AuthoringServiceTitleIntent,
    AuthoringTailIntent,
)
from ..providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics
from .enrichment import ReportContext, ResolvedSectionContext
from .planner import ReportTask
from .semantic_actions import SectionSemanticAction
from .worker_contracts import CanonicalWorkerResult


class _SemanticModel(BaseModel):
    """Strict immutable base for canonical provider-facing semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SectionSemanticActionResponse(RootModel[SectionSemanticAction]):
    """Root response whose JSON Schema is the discriminated action union."""


class ReportSlotValue(_SemanticModel):
    """One host-approved report slot mutation."""

    slot_id: str = Field(min_length=1)
    value: str | float | int
    unit: str | None = Field(default=None, min_length=1)


class ReportRemark(_SemanticModel):
    """One report remark with request-local identity."""

    semantic_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    text: str | None = None
    lines: tuple[str, ...] = ()
    alignment: Literal["left", "center", "right"] = "left"

    @model_validator(mode="after")
    def validate_content(self) -> ReportRemark:
        """Require non-empty remark content."""
        if self.text is None and not self.lines:
            raise ValueError("A report remark requires text or lines.")
        return self


class ReportSemanticResponse(_SemanticModel):
    """Sparse report semantics; omitted fields preserve the document."""

    title: str | None = Field(default=None, min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    general_fields: tuple[ReportSlotValue, ...] = ()
    service_titles: tuple[ReportSlotValue, ...] = ()
    detail_fields: tuple[ReportSlotValue, ...] = ()
    remarks: tuple[ReportRemark, ...] = ()
    page_size: str | None = Field(default=None, min_length=1)
    page_orientation: Literal["portrait", "landscape"] | None = None
    depth_unit: str | None = Field(default=None, min_length=1)
    depth_scale: str | float | None = None
    tail_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_nonempty(self) -> ReportSemanticResponse:
        """Reject an empty report mutation."""
        if not any(
            (
                self.title,
                self.subtitle,
                self.general_fields,
                self.service_titles,
                self.detail_fields,
                self.remarks,
                self.page_size,
                self.page_orientation,
                self.depth_unit,
                self.depth_scale is not None,
                self.tail_enabled is not None,
            )
        ):
            raise ValueError("Report semantic response contains no report mutation.")
        return self


@dataclass(frozen=True, slots=True)
class CanonicalReportWorker:
    """Generate one sparse report semantic response and lower it deterministically."""

    backend: ModelBackendProtocol

    async def compile(
        self,
        *,
        task: ReportTask,
        report_context: ReportContext,
        document: object,
        authoritative_request: str,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> CanonicalWorkerResult:
        """Generate exactly one report semantic response."""
        payload = {
            "report_task": task.model_dump(mode="json"),
            "report_context": report_context.model_dump(mode="json"),
            "authoritative_request": authoritative_request,
            "rules": (
                "Return only explicit report values. Do not emit sections, bindings, fills, "
                "annotations, paths, programs, or SDK calls."
            ),
        }
        request = StructuredGenerationRequest(
            system_prompt=(
                "You are the Wellplot report semantic worker. Return one sparse JSON object "
                "containing only explicit report semantics requested by the user."
            ),
            user_prompt=_json_payload(payload),
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            generated = await self.backend.generate_structured(
                request,
                response_model=ReportSemanticResponse,
            )
        except ProviderRequestError:
            raise
        except ValidationError:
            return _failure(
                "structured_schema_validation_failure",
                "Report output did not match the canonical semantic schema.",
            )
        try:
            intent = _lower_report(generated.value, report_context)
            return CanonicalWorkerResult(True, intent, (), SemanticMetrics())
        except ValidationError:
            return _failure(
                "semantic_context_validation_failure",
                "Report semantics failed canonical validation.",
            )
        except ValueError:
            return _failure(
                "semantic_context_validation_failure",
                "Report semantics could not be validated against host context.",
            )
        except Exception:
            return _failure(
                "semantic_lowering_failure",
                "Report semantics could not be lowered safely.",
            )


def _lower_report(
    response: ReportSemanticResponse,
    context: ReportContext,
) -> AuthoringDocumentIntent:
    """Lower report values after checking host-approved slot ownership."""
    allowed = {slot.slot_id: slot for slot in context.header_slots}
    assignments: set[str] = set()
    fields: list[AuthoringHeaderFieldIntent] = []
    for values, prefix in (
        (response.general_fields, "general."),
        (response.detail_fields, "detail."),
    ):
        for value in values:
            if not value.slot_id.startswith(prefix) or value.slot_id not in allowed:
                raise ValueError("Report selected an invalid host-approved slot.")
            if value.slot_id in assignments:
                raise ValueError("Report assigned one slot more than once.")
            assignments.add(value.slot_id)
            slot = allowed[value.slot_id]
            report_value = {
                "value": str(value.value),
                "provenance": "user",
                "availability": "available",
            }
            if value.unit is not None:
                report_value["unit"] = value.unit
            field_values: dict[str, object] = {
                "slot_id": value.slot_id,
                "value": AuthoringReportValueIntent(**report_value),
            }
            if slot.key is not None:
                field_values["key"] = slot.key
            if slot.label is not None:
                field_values["label"] = slot.label
            fields.append(AuthoringHeaderFieldIntent(**field_values))
    service_titles: list[AuthoringServiceTitleIntent] = []
    for value in response.service_titles:
        if not value.slot_id.startswith("service_title") or value.slot_id not in allowed:
            raise ValueError("Report selected an invalid service-title slot.")
        if value.slot_id in assignments:
            raise ValueError("Report assigned one slot more than once.")
        assignments.add(value.slot_id)
        report_value = {
            "value": str(value.value),
            "provenance": "user",
            "availability": "available",
        }
        if value.unit is not None:
            report_value["unit"] = value.unit
        service_titles.append(
            AuthoringServiceTitleIntent(
                slot_id=value.slot_id,
                value=AuthoringReportValueIntent(**report_value),
            )
        )
    header = None
    if fields or service_titles:
        header = AuthoringHeaderIntent(
            general_fields=[item for item in fields if item.slot_id.startswith("general.")] or None,
            detail_fields=[item for item in fields if item.slot_id.startswith("detail.")] or None,
            service_titles=service_titles or None,
        )
    remarks: list[AuthoringRemarkIntent] = []
    for index, item in enumerate(response.remarks):
        remark_values: dict[str, object] = {
            "remark_id": f"semantic-remark-{index + 1}",
            "alignment": item.alignment,
        }
        if item.title is not None:
            remark_values["title"] = item.title
        if item.text is not None:
            remark_values["text"] = item.text
        else:
            remark_values["lines"] = list(item.lines)
        remarks.append(AuthoringRemarkIntent(**remark_values))
    values: dict[str, object] = {}
    for name, value in (("title", response.title), ("subtitle", response.subtitle)):
        if value is not None:
            values[name] = value
    if header is not None:
        values["header"] = header
    if remarks:
        values["remarks"] = remarks
    page_values: dict[str, object] = {}
    if response.page_size is not None:
        page_values["size"] = response.page_size
    if response.page_orientation is not None:
        page_values["orientation"] = response.page_orientation
    if page_values:
        values["page"] = AuthoringPageIntent(**page_values)
    depth_values: dict[str, object] = {}
    if response.depth_unit is not None:
        depth_values["unit"] = response.depth_unit
    if response.depth_scale is not None:
        depth_values["scale"] = response.depth_scale
    if depth_values:
        values["depth"] = AuthoringDepthIntent(**depth_values)
    if response.tail_enabled is not None:
        values["tail"] = AuthoringTailIntent(enabled=response.tail_enabled)
    return AuthoringDocumentIntent(**values)


def _section_context(context: ResolvedSectionContext) -> dict[str, object]:
    """Expose bounded source facts and request-local existing-curve handles."""
    return {
        "target": {"kind": "existing" if context.section_id else "new"},
        "sources": [
            {
                "candidate_id": source.candidate_id,
                "channels": [
                    {"mnemonic": channel.mnemonic, "kind": channel.kind, "unit": channel.unit}
                    for channel in source.channels
                ],
            }
            for source in context.sources
        ],
        "existing_curves": [
            {
                "handle": f"curve-{index}",
                "track_title": curve.track_title,
                "track_kind": curve.track_kind,
                "channel": curve.channel,
                "label": curve.label,
                "scale_kind": curve.scale_kind,
                "scale_minimum": curve.scale_minimum,
                "scale_maximum": curve.scale_maximum,
                "reverse": curve.reverse,
            }
            for index, curve in enumerate(context.existing_curves, start=1)
        ],
    }


def _failure(code: str, message: str) -> CanonicalWorkerResult:
    """Create bounded sanitized semantic failure evidence."""
    return CanonicalWorkerResult(
        success=False,
        intent_fragment=None,
        diagnostics=(
            SemanticDiagnostic(
                stage="semantic_worker",
                code=code,
                message=message,
                remediation_hint="Return one valid canonical semantic action.",
            ),
        ),
        metrics=SemanticMetrics(),
    )


def _json_payload(value: object) -> str:
    """Serialize provider input without paths or generated payload retention."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "CanonicalReportWorker",
    "CanonicalWorkerResult",
    "ReportRemark",
    "ReportSemanticResponse",
    "ReportSlotValue",
    "SectionSemanticActionResponse",
]
