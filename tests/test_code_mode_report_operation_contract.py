"""Provider-free tests for host-compiled report operation ownership."""

from __future__ import annotations

import pytest

from wellplot.agent.code_mode.canonical_workers import (
    ReportSemanticResponse,
    ReportSlotValue,
    _validate_report_operation_contract,
)
from wellplot.agent.code_mode.enrichment import HeaderSlotInspectionSummary, ReportContext
from wellplot.agent.code_mode.obligations import compile_request_contract
from wellplot.agent.code_mode.planner import ReportTask, SemanticFieldValue, SemanticOperation
from wellplot.agent.code_mode.worker_contracts import (
    ReportOperationContract,
    ReportOperationContractEntry,
    SectionWorkContractError,
    build_report_operation_contract,
    resolve_report_metadata,
)


@pytest.mark.parametrize(
    ("request_text", "keys", "expected"),
    [
        ("Country: USA", ("country",), {"country": ("resolved", "slot.0")}),
        (
            "State: Utah\nCountry: USA",
            ("state", "country"),
            {"state": ("resolved", "slot.0"), "country": ("resolved", "slot.1")},
        ),
        (
            "Country: USA\nState: Utah",
            ("state", "country"),
            {"state": ("resolved", "slot.0"), "country": ("resolved", "slot.1")},
        ),
        (
            "State: Utah\nCountry: USA",
            ("country",),
            {"state": ("absent", None), "country": ("resolved", "slot.0")},
        ),
        ("State: Utah", ("country",), {"state": ("absent", None)}),
        ("State: Utah", (), {"state": ("uninspected", None)}),
        ("State: Utah", ("state", "state"), {"state": ("ambiguous", None)}),
        (
            "Drilling and Log Datum: Kelly Bushing",
            ("log_measured_from",),
            {"measuredfrom": ("resolved", "slot.0")},
        ),
        ("KB: 1000", ("elevation_kb",), {"elevationkb": ("resolved", "slot.0")}),
    ],
)
def test_report_metadata_binding_retains_request_and_inspection_identity(
    request_text: str,
    keys: tuple[str, ...],
    expected: dict[str, tuple[str, str | None]],
) -> None:
    """Keep original facts while resolving only inspected canonical destinations."""
    facts = compile_request_contract(request_text).requirements.requirements
    slots = tuple(
        HeaderSlotInspectionSummary(
            slot_id=f"slot.{index}", key=key, label="State" if key == "country" else key
        )
        for index, key in enumerate(keys)
    )
    context = ReportContext(
        snapshot_id="snapshot",
        header_slots=slots,
        general_slot_ids=tuple(slot.slot_id for slot in slots),
    )

    bindings = resolve_report_metadata(facts, context)

    assert {item.semantic_field: (item.status, item.slot_id) for item in bindings} == expected
    assert tuple(item.fact for item in bindings) == facts
    assert all(item.fact.requirement_id and item.snapshot_id == "snapshot" for item in bindings)
    assert all(item.group == "general" for item in bindings if item.status == "resolved")


def test_report_metadata_rejects_unknown_fields_and_alias_collisions() -> None:
    """Reject incompatible alias claims and an unsupported metadata identity."""
    facts = compile_request_contract(
        "Drilling and Log Datum: Kelly Bushing\nMeasured From: Ground Level"
    ).requirements.requirements
    context = ReportContext(
        snapshot_id="snapshot",
        header_slots=(HeaderSlotInspectionSummary(slot_id="datum", key="measured_from"),),
        general_slot_ids=("datum",),
    )
    assert [item.status for item in resolve_report_metadata(facts, context)] == [
        "conflict",
        "conflict",
    ]
    unknown = facts[0].model_copy(update={"owner_ref": "unknown"})
    assert resolve_report_metadata((unknown,), context)[0].status == "unsupported"


def _report_contract_fixture() -> tuple[ReportTask, ReportContext]:
    """Build one request-backed metadata operation and inspected report slot."""
    request = "Set the report metadata to:\nCompany: University of Utah\n"
    requirements = compile_request_contract(request).requirements.requirements
    task = ReportTask(
        goal="Set report metadata.",
        capability_ids=("report.standard",),
        operations=(
            SemanticOperation(
                local_ref="set_company",
                scope_ref="report",
                verb="SET",
                object_kind="report_field",
                target_clue="company",
                field_values=(
                    SemanticFieldValue(
                        field="metadata",
                        state="SET",
                        value="University of Utah",
                    ),
                ),
            ),
        ),
        obligations=requirements,
    )
    context = ReportContext(
        snapshot_id="snapshot-report-test",
        header_slots=(
            HeaderSlotInspectionSummary(
                slot_id="general.company",
                key="company",
                label="Company",
            ),
        ),
        general_slot_ids=("general.company",),
    )
    return task, context


def test_report_operation_contract_binds_request_ref_to_existing_slot() -> None:
    """Bind a planner ref to its exact request-authoritative report slot."""
    task, context = _report_contract_fixture()

    contract = build_report_operation_contract(task, context)

    assert contract.scope_ref == "report"
    assert contract.snapshot_id == context.snapshot_id
    assert len(contract.entries) == 1
    entry = contract.entries[0]
    assert entry.operation_ref == "set_company"
    assert entry.field == "metadata"
    assert entry.target == "general.general.company"
    assert entry.value == "University of Utah"
    (binding,) = contract.metadata_bindings
    assert binding.fact.requirement_id == entry.requirement_id
    assert binding.slot_id == "general.company"
    assert ReportOperationContract.model_validate(contract.model_dump(mode="json")) == contract

    response = ReportSemanticResponse(
        general_fields=(ReportSlotValue(slot_id="general.company", value="University of Utah"),)
    )
    _validate_report_operation_contract(response, contract)


def test_report_operation_contract_rejects_missing_or_ambiguous_slot() -> None:
    """Fail closed when two inspected slots could own one metadata fact."""
    task, context = _report_contract_fixture()

    with pytest.raises(SectionWorkContractError, match="Multiple inspected slots") as error:
        build_report_operation_contract(
            task,
            context.model_copy(
                update={
                    "header_slots": (
                        *context.header_slots,
                        HeaderSlotInspectionSummary(
                            slot_id="general.company_alias",
                            key="company",
                            label="Company Name",
                        ),
                    ),
                    "general_slot_ids": (
                        "general.company",
                        "general.company_alias",
                    ),
                }
            ),
        )
    assert error.value.code == "report_metadata_ambiguous"


def test_report_operation_contract_rejects_output_value_drift() -> None:
    """Reject sparse report output that disagrees with a mapped request value."""
    task, context = _report_contract_fixture()
    contract = build_report_operation_contract(task, context)

    response = ReportSemanticResponse(
        general_fields=(ReportSlotValue(slot_id="general.company", value="Other company"),)
    )

    with pytest.raises(ValueError, match="differs from its contract"):
        _validate_report_operation_contract(response, contract)


@pytest.mark.parametrize(
    "response",
    (
        ReportSemanticResponse(
            title="Unrequested title",
            general_fields=(
                ReportSlotValue(slot_id="general.company", value="University of Utah"),
            ),
        ),
        ReportSemanticResponse(
            page_size="A4",
            general_fields=(
                ReportSlotValue(slot_id="general.company", value="University of Utah"),
            ),
        ),
        ReportSemanticResponse(
            general_fields=(
                ReportSlotValue(slot_id="general.company", value="University of Utah"),
                ReportSlotValue(slot_id="general.well", value="Test Well"),
            ),
        ),
    ),
)
def test_report_operation_contract_rejects_unrequested_effects(
    response: ReportSemanticResponse,
) -> None:
    """A valid requested value cannot authorize unrelated report mutations."""
    task, context = _report_contract_fixture()
    contract = build_report_operation_contract(task, context)

    with pytest.raises(ValueError, match="unauthorized effect"):
        _validate_report_operation_contract(response, contract)


def test_report_operation_contract_rejects_order_constraint_on_reversed_slots() -> None:
    """Reject request order constraints contradicted by resolved report positions."""
    contract = ReportOperationContract(
        request_sha256="0" * 64,
        snapshot_id="snapshot-report-test",
        entries=(
            ReportOperationContractEntry(
                operation_ref="first_title",
                field="service_title",
                target="service_title.service_title.2",
                value="First",
                order_index=2,
            ),
            ReportOperationContractEntry(
                operation_ref="second_title",
                field="service_title",
                target="service_title.service_title.1",
                value="Second",
                order_index=1,
            ),
        ),
        ordering_constraints=(("first_title", "before", "second_title"),),
    )
    response = ReportSemanticResponse(
        service_titles=(
            ReportSlotValue(slot_id="service_title.2", value="First"),
            ReportSlotValue(slot_id="service_title.1", value="Second"),
        )
    )

    with pytest.raises(ValueError, match="order differs"):
        _validate_report_operation_contract(response, contract)


def test_fieldless_ensure_is_not_accepted_as_an_unverified_noop() -> None:
    """ENSURE requires an inspectable postcondition instead of a fabricated no-op."""
    task, context = _report_contract_fixture()
    ensure = SemanticOperation(
        local_ref="ensure_company",
        scope_ref="report",
        verb="ENSURE",
        object_kind="report_field",
        semantic_ref="company",
    )

    with pytest.raises(SectionWorkContractError) as error:
        build_report_operation_contract(task.model_copy(update={"operations": (ensure,)}), context)
    assert error.value.code == "report_operation_fields_missing"


def test_report_operation_contract_requires_full_report_obligation_coverage() -> None:
    """A correct prefix cannot conceal an unrepresented report requirement."""
    task, context = _report_contract_fixture()
    existing = task.obligations[0]
    unrepresented = existing.model_copy(
        update={
            "owner_ref": "Field",
            "value": "Uinta Basin",
            "requirement_id": "unrepresented-report-field",
        }
    )
    task = task.model_copy(update={"obligations": (*task.obligations, unrepresented)})
    context = context.model_copy(
        update={
            "header_slots": (
                *context.header_slots,
                HeaderSlotInspectionSummary(slot_id="general.field", key="field", label="Field"),
            ),
            "general_slot_ids": (*context.general_slot_ids, "general.field"),
        }
    )

    with pytest.raises(SectionWorkContractError) as error:
        build_report_operation_contract(task, context)
    assert error.value.code == "report_operation_coverage_incomplete"
