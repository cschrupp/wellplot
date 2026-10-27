"""Canonical typed semantic workers for the shared Code Mode engine."""

from __future__ import annotations

import json
import re
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
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics, SemanticStageEvidence
from .enrichment import ReportContext, ResolvedSectionContext
from .obligations import (
    ObligationState,
    OwnerKind,
    RequestObligation,
    validate_report_obligations,
    verify_worker_correction_scope,
)
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


def _add_report_nonempty_schema_constraint(schema: dict[str, object]) -> None:
    """Encode the sparse-response non-empty invariant for JSON-schema clients."""
    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        return
    alternatives: list[dict[str, object]] = []
    for name in ("title", "subtitle", "page_size", "depth_unit"):
        alternatives.append(
            {"required": [name], "properties": {name: {"type": "string", "minLength": 1}}}
        )
    for name in ("general_fields", "service_titles", "detail_fields", "remarks"):
        alternatives.append(
            {"required": [name], "properties": {name: {"type": "array", "minItems": 1}}}
        )
    alternatives.append(
        {
            "required": ["page_orientation"],
            "properties": {"page_orientation": {"type": "string", "minLength": 1}},
        }
    )
    alternatives.append(
        {"required": ["tail_enabled"], "properties": {"tail_enabled": {"type": "boolean"}}}
    )
    alternatives.append(
        {"required": ["depth_scale"], "properties": {"depth_scale": {"type": ["string", "number"]}}}
    )
    schema.setdefault("allOf", []).append({"anyOf": alternatives})


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

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_extra=_add_report_nonempty_schema_constraint,
    )

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


class _ReportCorrectionRequired(ValueError):
    """Signal one bounded retry for an unknown general-slot alias."""


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
            "report_context": {
                "header_slots": [
                    slot.model_dump(mode="json") for slot in report_context.header_slots
                ],
                "slot_groups": {
                    "general_fields": _report_slots(
                        report_context,
                        report_context.general_slot_ids,
                    ),
                    "service_titles": _report_slots(
                        report_context,
                        report_context.service_title_slot_ids,
                    ),
                    "detail_fields": _report_slots(
                        report_context,
                        report_context.detail_slot_ids,
                    ),
                },
            },
            "authoritative_request": authoritative_request,
            "rules": (
                "Return only explicit report values. Put general values in general_fields, "
                "service-title values in service_titles, and detail-table values in "
                "detail_fields. Use only the slot IDs in the matching slot_groups list. "
                "The report/document title and subtitle belong only to the top-level title "
                "and subtitle fields; general_fields, service_titles, and detail_fields are "
                "header-slot assignments only. An empty header-slot inventory does not "
                "prevent a title or subtitle mutation. Never translate a report title into "
                "a general or other header slot. "
                "When a requested field matches a detail-table key or label, use that "
                "detail_fields slot even if a similar general label exists. "
                "Never place a service-title slot in detail_fields or general_fields. Do not "
                "emit sections, bindings, fills, annotations, paths, programs, or SDK calls."
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
        previous_response: ReportSemanticResponse | None = None
        allowed_fields = frozenset(
            item.field for item in task.obligations if item.state.value == "SET"
        )
        for attempt in range(2):
            try:
                generated = await self.backend.generate_structured(
                    request,
                    response_model=ReportSemanticResponse,
                )
            except ProviderRequestError:
                raise
            except IndexError:
                return _failure(
                    "semantic_context_validation_failure",
                    "Report semantics could not be validated safely.",
                )
            except ValidationError:
                return _failure(
                    "structured_schema_validation_failure",
                    "Report output did not match the canonical semantic schema.",
                )
            try:
                response = _apply_compiled_report_requirements(
                    generated.value,
                    report_context,
                    task.obligations,
                )
                response = _normalize_report_slot_groups(response, report_context)
                if previous_response is not None and allowed_fields:
                    verify_worker_correction_scope(
                        previous_response,
                        response,
                        allowed_fields,
                    )
                validate_report_obligations(response, task.obligations)
                intent = _lower_report(response, report_context)
                return CanonicalWorkerResult(
                    True,
                    intent,
                    (),
                    SemanticMetrics(),
                    SemanticStageEvidence(
                        provider_wire="PASS",
                        python_validation="PASS",
                        worker_obligation="PASS",
                        semantic_lowering="PASS",
                        correction="PASS" if attempt else "NOT_REACHED",
                    ),
                )
            except (_ReportCorrectionRequired, ValidationError, ValueError) as error:
                if attempt:
                    return _failure(
                        "semantic_context_validation_failure",
                        "Report semantics could not be validated against host context.",
                    )
                correction_payload = {
                    **payload,
                    "correction": str(error),
                    "rules": (
                        payload["rules"] + " Do not emit unsupported fields or duplicate aliases."
                    ),
                }
                request = StructuredGenerationRequest(
                    system_prompt=(
                        "You are correcting an incomplete Wellplot report semantic response. "
                        "Preserve the top-level report title and subtitle ownership rule; "
                        "return only explicit report values in the host-approved slot groups."
                    ),
                    user_prompt=_json_payload(correction_payload),
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
                previous_response = response if "response" in locals() else None
            except Exception:
                return _failure(
                    "semantic_lowering_failure",
                    "Report semantics could not be lowered safely.",
                )
        return _failure(
            "semantic_context_validation_failure",
            "Report semantics could not be validated against host context.",
        )


def _lower_report(
    response: ReportSemanticResponse,
    context: ReportContext,
) -> AuthoringDocumentIntent:
    """Lower report values after checking host-approved slot ownership."""
    allowed = {slot.slot_id: slot for slot in context.header_slots}
    general_ids = set(context.general_slot_ids)
    service_title_ids = set(context.service_title_slot_ids)
    detail_ids = set(context.detail_slot_ids)
    if not (general_ids or service_title_ids or detail_ids):
        general_ids = {
            slot.slot_id for slot in context.header_slots if slot.slot_id.startswith("general.")
        }
        service_title_ids = {
            slot.slot_id
            for slot in context.header_slots
            if slot.slot_id.startswith("service_title")
        }
        detail_ids = {
            slot.slot_id for slot in context.header_slots if slot.slot_id.startswith("detail.")
        }
    assignments: set[str] = set()
    fields: list[AuthoringHeaderFieldIntent] = []
    for values, prefix in (
        (response.general_fields, "general."),
        (response.detail_fields, "detail."),
    ):
        for value in values:
            slot_ids = general_ids if prefix == "general." else detail_ids
            if value.slot_id not in slot_ids or value.slot_id not in allowed:
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
        if value.slot_id not in service_title_ids or value.slot_id not in allowed:
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
        header_values: dict[str, object] = {}
        general_fields = [item for item in fields if item.slot_id.startswith("general.")]
        detail_fields = [item for item in fields if item.slot_id.startswith("detail.")]
        if general_fields:
            header_values["general_fields"] = general_fields
        if detail_fields:
            header_values["detail_fields"] = detail_fields
        if service_titles:
            header_values["service_titles"] = service_titles
        header = AuthoringHeaderIntent(**header_values)
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


def _normalize_report_slot_groups(
    response: ReportSemanticResponse,
    context: ReportContext,
    *,
    authoritative_request: str = "",
    task_requirements: tuple[str, ...] = (),
) -> ReportSemanticResponse:
    """Route model aliases and explicit request values to host-owned slots."""
    response = _apply_explicit_report_request(
        response,
        context,
        authoritative_request=authoritative_request,
        task_requirements=task_requirements,
    )
    slots = {slot.slot_id: slot for slot in context.header_slots}
    general_ids = set(context.general_slot_ids)
    service_title_ids = set(context.service_title_slot_ids)
    detail_ids = set(context.detail_slot_ids)
    detail_aliases: dict[str, list[str]] = {}
    for slot_id in context.detail_slot_ids:
        slot = slots.get(slot_id)
        if slot is None:
            continue
        for alias in (slot.key, slot.label):
            if alias:
                normalized = _slot_alias(alias)
                detail_aliases.setdefault(normalized, []).append(slot_id)

    general_fields: list[ReportSlotValue] = []
    detail_fields = list(response.detail_fields)
    explicit_detail_values = {value.slot_id: value for value in detail_fields}
    for value in response.general_fields:
        if value.slot_id in general_ids:
            general_fields.append(value)
            continue
        detail_slot_id = _detail_slot_alias(value.slot_id, detail_aliases, detail_ids)
        if detail_slot_id is None:
            if value.slot_id not in service_title_ids:
                raise _ReportCorrectionRequired(f"Unknown general report slot {value.slot_id!r}.")
            general_fields.append(value)
            continue
        existing_detail = explicit_detail_values.get(detail_slot_id)
        if existing_detail is not None:
            if existing_detail.value != value.value or existing_detail.unit != value.unit:
                raise ValueError("Report assigned conflicting values to one detail slot.")
            continue
        detail_fields.append(value.model_copy(update={"slot_id": detail_slot_id}))
        explicit_detail_values[detail_slot_id] = value
    return response.model_copy(
        update={
            "general_fields": tuple(general_fields),
            "detail_fields": tuple(detail_fields),
        }
    )


def _apply_compiled_report_requirements(
    response: ReportSemanticResponse,
    context: ReportContext,
    obligations: tuple[RequestObligation, ...],
) -> ReportSemanticResponse:
    """Apply host-compiled report values without reparsing request or planner prose."""
    metadata_items = [
        item
        for item in obligations
        if item.owner_kind is OwnerKind.REPORT
        and item.field == "metadata"
        and item.state is ObligationState.SET
    ]
    slots = {slot.slot_id: slot for slot in context.header_slots}
    aliases_by_slot: dict[str, set[str]] = {}
    for slot_id, slot in slots.items():
        aliases = {
            _slot_alias(str(value))
            for value in (getattr(slot, "key", None), getattr(slot, "label", None))
            if value
        }
        key = getattr(slot, "key", None)
        if key:
            aliases.add(_slot_alias(str(key).replace("_", " ")))
        aliases.update(
            {
                "country": {"state"},
                "measured_from": {"drillingandlogdatum"},
                "log_measured_from": {"drillingandlogdatum"},
                "elevation_kb": {"kb"},
                "elevation_gl": {"gl"},
                "elevation_df": {"df"},
                "bottom_temperature": {"maximumtemperature"},
                "fluid_density": {"density"},
                "top_log_interval": {"topinterval"},
                "bottom_log_interval": {"bottominterval"},
                "fluid_type": {"fluid"},
                "run_number": {"run"},
            }.get(str(key), set())
        )
        aliases_by_slot[slot_id] = aliases

    metadata_values: dict[str, str] = {}
    for item in metadata_items:
        matching_slots = [
            slot_id
            for slot_id, aliases in aliases_by_slot.items()
            if _slot_alias(item.owner_ref) in aliases
        ]
        if not matching_slots:
            raise ValueError("Compiled report metadata does not resolve to an inspected slot.")
        for slot_id in matching_slots:
            metadata_values[slot_id] = str(item.value)

    updates: dict[str, object] = {}
    if metadata_values:
        general_ids = set(context.general_slot_ids)
        detail_ids = set(context.detail_slot_ids)
        current_general = {item.slot_id: item for item in response.general_fields}
        current_detail = {item.slot_id: item for item in response.detail_fields}
        for slot_id, value in metadata_values.items():
            target = current_general if slot_id in general_ids else current_detail
            if slot_id in general_ids or slot_id in detail_ids:
                target[slot_id] = ReportSlotValue(slot_id=slot_id, value=value)
            else:
                raise ValueError(
                    "Compiled report metadata resolved outside an authorized slot group."
                )
        updates["general_fields"] = tuple(current_general.values())
        updates["detail_fields"] = tuple(current_detail.values())

    service_items = sorted(
        (
            item
            for item in obligations
            if item.owner_kind is OwnerKind.REPORT
            and item.field == "service_title"
            and item.state is ObligationState.SET
        ),
        key=lambda item: int((item.slot_key or "").rsplit(".", maxsplit=1)[-1]),
    )
    if service_items:
        if len(service_items) != len(context.service_title_slot_ids):
            raise ValueError("Compiled service-title count does not match inspected slots.")
        updates["service_titles"] = tuple(
            ReportSlotValue(slot_id=slot_id, value=str(item.value))
            for slot_id, item in zip(context.service_title_slot_ids, service_items, strict=True)
        )

    remark_items = sorted(
        (
            item
            for item in obligations
            if item.owner_kind is OwnerKind.REPORT
            and item.field == "remark"
            and item.state is ObligationState.SET
        ),
        key=lambda item: item.slot_key or "",
    )
    if remark_items:
        remarks: list[ReportRemark] = []
        for index, item in enumerate(remark_items, start=1):
            value = json.loads(str(item.value))
            remarks.append(
                ReportRemark(
                    semantic_id=f"request-remark-{index}",
                    title=value["title"],
                    text=value["text"],
                )
            )
        updates["remarks"] = tuple(remarks)

    tail_items = [
        item
        for item in obligations
        if item.owner_kind is OwnerKind.REPORT and item.field == "tail_enabled"
    ]
    if tail_items:
        updates["tail_enabled"] = tail_items[-1].value is True

    page_allowed = any(
        item.field == "page_presentation_allowed" and item.value is True for item in obligations
    )
    depth_allowed = any(
        item.field == "depth_presentation_allowed" and item.value is True for item in obligations
    )
    if not page_allowed:
        updates["page_size"] = None
        updates["page_orientation"] = None
    if not depth_allowed:
        updates["depth_unit"] = None
        updates["depth_scale"] = None
    return response.model_copy(update=updates) if updates else response


def _apply_explicit_report_request(
    response: ReportSemanticResponse,
    context: ReportContext,
    *,
    authoritative_request: str,
    task_requirements: tuple[str, ...],
) -> ReportSemanticResponse:
    """Prefer explicit report clauses over ambiguous model slot synonyms."""
    response = _preserve_unrequested_report_depth(response, authoritative_request)
    response = _preserve_unrequested_report_presentation(response, authoritative_request)
    metadata_parts: list[str] = []
    services: str | None = None
    remark_parts: list[str] = []
    if task_requirements:
        requirement_metadata, services, requirement_remarks = _report_requirement_fragments(
            task_requirements
        )
        metadata_parts.extend(requirement_metadata)
        remark_parts.extend(requirement_remarks)
    request_metadata, request_services, request_remarks = _generic_report_request_fragments(
        authoritative_request
    )
    metadata_parts.extend(request_metadata)
    if services is None:
        services = request_services
    if request_remarks:
        remark_parts = list(request_remarks)
    metadata = "; ".join(metadata_parts) or None
    remarks = "\n".join(f"{index}. {value}" for index, value in enumerate(remark_parts, 1)) or None
    tail_requested = _explicit_tail_requested(authoritative_request)
    if metadata is None and services is None and remarks is None and not tail_requested:
        return response

    slots = {slot.slot_id: slot for slot in context.header_slots}
    general_ids = set(context.general_slot_ids)
    detail_ids = set(context.detail_slot_ids)
    assignments = _explicit_report_slot_values(metadata, slots)
    general_fields = tuple(
        ReportSlotValue(slot_id=slot_id, value=value)
        for slot_id, value in assignments.items()
        if slot_id in general_ids
    )
    detail_fields = tuple(
        ReportSlotValue(slot_id=slot_id, value=value)
        for slot_id, value in assignments.items()
        if slot_id in detail_ids
    )
    service_titles = _explicit_service_titles(services, context.service_title_slot_ids)
    parsed_remarks = _explicit_remarks(remarks)
    updates: dict[str, object] = {}
    if assignments:
        updates["general_fields"] = general_fields
        updates["detail_fields"] = detail_fields
    if service_titles:
        updates["service_titles"] = service_titles
    if parsed_remarks:
        updates["remarks"] = parsed_remarks
    if tail_requested:
        updates["tail_enabled"] = True
    return response.model_copy(update=updates) if updates else response


def _preserve_unrequested_report_depth(
    response: ReportSemanticResponse,
    authoritative_request: str,
) -> ReportSemanticResponse:
    """Ignore model depth mutations unless the request names report depth settings."""
    if re.search(
        r"\bdepth\s+(?:axis|scale|unit)\b|\bscale\s+ratio\b",
        authoritative_request,
        flags=re.IGNORECASE,
    ):
        return response
    if response.depth_unit is None and response.depth_scale is None:
        return response
    return response.model_copy(update={"depth_unit": None, "depth_scale": None})


def _preserve_unrequested_report_presentation(
    response: ReportSemanticResponse,
    authoritative_request: str,
) -> ReportSemanticResponse:
    """Ignore model page mutations unless page presentation is explicitly requested."""
    if re.search(
        r"\b(?:page|paper)\s+(?:size|orientation)\b|\b(?:a4|portrait|landscape)\b",
        authoritative_request,
        flags=re.IGNORECASE,
    ):
        return response
    if response.page_size is None and response.page_orientation is None:
        return response
    return response.model_copy(update={"page_size": None, "page_orientation": None})


def _report_requirement_fragments(
    requirements: tuple[str, ...],
) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    """Extract normalized report labels from planner-owned requirements."""
    metadata: list[str] = []
    services: str | None = None
    remarks: list[str] = []
    for requirement in requirements:
        if "\n" in requirement:
            continue
        label, separator, value = requirement.partition(":")
        normalized_label = _slot_alias(label)
        if separator and normalized_label in {"servicetitles", "servicetitle"}:
            services = value.strip()
        elif separator and re.fullmatch(r"remark\d+", normalized_label):
            remarks.append(value.strip())
        else:
            metadata.append(requirement.strip())
    return (
        tuple(item for item in metadata if item),
        services,
        tuple(item for item in remarks if item),
    )


def _generic_report_request_fragments(
    request: str,
) -> tuple[tuple[str, ...], str | None, tuple[str, ...]]:
    """Read generic labeled fragments and bounded report prose blocks."""
    if not request:
        return (), None, ()
    metadata: list[str] = []
    services: str | None = None
    remarks: list[str] = []
    structured_spans: list[tuple[int, int]] = []

    def capture(pattern: str) -> list[str]:
        matches = list(re.finditer(pattern, request, flags=re.IGNORECASE | re.DOTALL))
        for match in matches:
            structured_spans.append(match.span())
        return [re.sub(r"\s+", " ", match.group("body")).strip() for match in matches]

    metadata.extend(
        capture(
            r"\bSet\s+the\s+report\s+metadata\s+to\s*:\s*"
            r"(?P<body>.*?)(?=\n\s*\n|\n\s*(?:Include|For each|On)\b|\Z)"
        )
    )
    service_values = capture(
        r"\bUse\s+these\s+service\s+titles\s*,?\s*in\s+order\s*:\s*"
        r"(?P<body>.*?)(?=\n\s*\n|\n\s*(?:Set|Include|For each|On)\b|\Z)"
    )
    if service_values:
        services = service_values[-1]
    for remark_block in capture(
        r"\bInclude\s+(?:three|the)\s+remarks?\s*:\s*"
        r"(?P<body>.*?)(?=\n\s*\n|\n\s*(?:For each|On)\b|\Z)"
    ):
        numbered = re.findall(
            r"(?:^|\s)\d+\.\s*(.*?)(?=\s+\d+\.\s|\Z)",
            remark_block,
            flags=re.DOTALL,
        )
        remarks.extend(numbered or (remark_block,))

    residual = request
    for start, end in sorted(structured_spans, reverse=True):
        residual = residual[:start] + "\n" + residual[end:]
    for fragment in re.split(r"[;\n]", residual):
        fragment = fragment.strip()
        if not fragment:
            continue
        label, separator, value = fragment.partition(":")
        if not separator:
            continue
        normalized_label = _slot_alias(label)
        value = value.strip()
        if normalized_label in {"servicetitles", "servicetitle"}:
            services = value
        elif re.fullmatch(r"remark\d+", normalized_label):
            remarks.append(value)
        elif re.fullmatch(r"[a-z][a-z _-]*", normalized_label):
            metadata.append(f"{label.strip()}: {value}")
    return tuple(metadata), services, tuple(remarks)


def _explicit_report_slot_values(
    metadata: str | None,
    slots: dict[str, object],
) -> dict[str, str]:
    """Parse explicit metadata clauses and map them to inspected slot IDs."""
    if metadata is None:
        return {}
    values: dict[str, str] = {}
    aliases_by_slot: dict[str, tuple[str, ...]] = {}
    for slot_id, slot in slots.items():
        key = getattr(slot, "key", None)
        label = getattr(slot, "label", None)
        aliases = [item for item in (key, label) if item]
        if key:
            aliases.append(key.replace("_", " "))
        if key == "country":
            aliases.append("state")
        if key == "bottom_temperature":
            aliases.append("maximum temperature")
        if key == "fluid_density":
            aliases.append("density")
        if key == "top_log_interval":
            aliases.append("top interval")
        if key == "bottom_log_interval":
            aliases.append("bottom interval")
        if key == "fluid_type":
            aliases.append("fluid")
        aliases_by_slot[slot_id] = tuple(
            sorted({item for item in aliases if item}, key=len, reverse=True)
        )

    datum_match = re.search(
        r"drilling\s+and\s+log\s+datum\s*:?\s+(?P<value>[^;]+)",
        metadata,
        flags=re.IGNORECASE,
    )
    if datum_match:
        datum = datum_match.group("value").strip().rstrip(".")
        for slot_id, slot in slots.items():
            if getattr(slot, "key", None) in {"measured_from", "log_measured_from"}:
                values[slot_id] = datum

    for clause in (item.strip() for item in metadata.split(";") if item.strip()):
        colon_match = re.match(r"^(?P<label>[^:]+):\s*(?P<value>.+)$", clause)
        clause_label = clause if colon_match is None else colon_match.group("label")
        clause_value = None if colon_match is None else colon_match.group("value")
        for slot_id, aliases in aliases_by_slot.items():
            if slot_id in values:
                continue
            for alias in aliases:
                if colon_match:
                    if _slot_alias(clause_label) != _slot_alias(alias):
                        continue
                    value = str(clause_value).strip()
                else:
                    match = re.match(
                        rf"^\s*{re.escape(alias)}\s+(?P<value>.+)$",
                        clause_label,
                        flags=re.IGNORECASE,
                    )
                    if match is None:
                        continue
                    value = match.group("value").strip()
                if value:
                    values[slot_id] = value.rstrip(".")
                break
    return values


def _explicit_service_titles(
    services: str | None,
    slot_ids: tuple[str, ...],
) -> tuple[ReportSlotValue, ...]:
    """Map quoted service titles to the stable host-owned title slots."""
    if services is None:
        return ()
    titles = tuple(re.findall(r'"([^"]+)"', services))
    if not titles:
        titles = tuple(item.strip() for item in services.split(",") if item.strip())
    return tuple(
        ReportSlotValue(slot_id=slot_id, value=value)
        for slot_id, value in zip(slot_ids, titles, strict=False)
    )


def _explicit_remarks(remarks: str | None) -> tuple[ReportRemark, ...]:
    """Preserve numbered request remarks as bounded canonical remark values."""
    if remarks is None:
        return ()
    pattern = re.compile(
        r"(?:^|\s)\d+\.\s*(?P<title>[^—\n]+?)\s+—\s*"
        r"(?P<text>.*?)(?=\s+\d+\.\s|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    matches = list(pattern.finditer(remarks))
    if not matches:
        matches = list(
            re.finditer(
                r"^\s*Remark\s+\d+\s*:\s*(?P<title>[^—\n]+?)\s+—\s*(?P<text>.*)$",
                remarks,
                flags=re.IGNORECASE | re.MULTILINE,
            )
        )
    parsed: list[ReportRemark] = []
    for index, match in enumerate(matches, start=1):
        title = " ".join(match.group("title").split())
        text = match.group("text").strip()
        if text:
            parsed.append(
                ReportRemark(
                    semantic_id=f"request-remark-{index}",
                    title=title,
                    text=text,
                )
            )
    return tuple(parsed)


def _explicit_tail_requested(request: str) -> bool:
    """Recognize an affirmative request to preserve the existing report tail."""
    flat = " ".join(request.split())
    if re.search(r"\b(?:without|exclude|omit|disable)\b[^.]*\btail\b", flat, re.I):
        return False
    return bool(
        re.search(
            r"\b(?:limit\s+the\s+report\s+to|include|retain|keep|preserve)\b"
            r"[^.]*\btail\b",
            flat,
            re.I,
        )
    )


def _detail_slot_alias(
    slot_id: str,
    aliases: dict[str, list[str]],
    detail_ids: set[str],
) -> str | None:
    """Resolve one unambiguous model alias to a host-owned detail slot."""
    if slot_id in detail_ids:
        return slot_id
    if not slot_id.startswith("general."):
        return None
    requested = _slot_alias(slot_id.removeprefix("general."))
    exact = aliases.get(requested, [])
    if len(exact) == 1:
        return exact[0]
    candidates = {
        detail_id
        for alias, detail_ids_for_alias in aliases.items()
        if requested in alias or alias in requested
        for detail_id in detail_ids_for_alias
    }
    if not candidates:
        requested_tokens = set(re.findall(r"[a-z0-9]+", requested))
        candidates = {
            detail_id
            for alias, detail_ids_for_alias in aliases.items()
            if requested_tokens.intersection(re.findall(r"[a-z0-9]+", alias))
            for detail_id in detail_ids_for_alias
        }
    return next(iter(candidates)) if len(candidates) == 1 else None


def _slot_alias(value: str) -> str:
    """Normalize a bounded slot key or label for deterministic alias matching."""
    return "".join(character for character in value.casefold() if character.isalnum())


def _report_slots(
    context: ReportContext,
    slot_ids: tuple[str, ...],
) -> list[dict[str, str]]:
    """Project grouped slot identities with labels but no current values."""
    slots = {slot.slot_id: slot for slot in context.header_slots}
    return [
        {
            "slot_id": slot_id,
            "key": slots[slot_id].key or "",
            "label": slots[slot_id].label or "",
        }
        for slot_id in slot_ids
        if slot_id in slots
    ]


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
