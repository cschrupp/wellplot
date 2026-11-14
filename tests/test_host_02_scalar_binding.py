"""Provider-free HOST-02 scalar binding contract tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    ExistingCurveContext,
    ExistingTrackContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.obligations import compile_request_contract
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.semantic_actions import AddBindingAction, lower_section_action
from wellplot.agent.code_mode.typed_section_worker import (
    _provider_operation_contract,
    _provider_work_contract,
)
from wellplot.agent.code_mode.worker_contracts import (
    SectionWorkContractError,
    build_preworker_semantic_publication_contract,
    build_section_operation_contract,
    build_section_work_contract,
    validate_section_action_contract,
)
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.semantic_catalog import SemanticCatalogTrustError


def _context() -> ResolvedSectionContext:
    return ResolvedSectionContext(
        task_index=0,
        section_id="section-main",
        snapshot_id="snapshot-1",
        sources=(
            SourceContext(
                candidate_id="candidate-1",
                handle="source-1",
                labels=("approved.las",),
                canonical_path=(
                    "/home/user/projects/well_log_os/workspace/data/30-23a-3 8117_d.las"
                ),
                source_format="las",
                revision_token="revision-1",
                channels=(
                    ChannelContext(
                        mnemonic="GR",
                        kind="scalar",
                        unit="gAPI",
                        physical_identity={"format": "LAS", "curve_index": 7},
                    ),
                    ChannelContext(
                        mnemonic="CGR",
                        kind="scalar",
                        unit="gAPI",
                        physical_identity={"format": "LAS", "curve_index": 8},
                    ),
                    ChannelContext(
                        mnemonic="GRD",
                        kind="scalar",
                        unit="gAPI",
                        physical_identity={"format": "LAS", "curve_index": 9},
                    ),
                ),
            ),
        ),
        existing_tracks=(
            ExistingTrackContext(
                handle="track-1",
                track_id="track-main",
                title="Main Log",
                kind="normal",
            ),
        ),
    )


def _task() -> SectionTask:
    compilation = compile_request_contract("Plot Gamma Ray.")
    return SectionTask(
        goal="Add the requested scalar binding.",
        capability_ids=("section.log_plot", "binding.curve"),
        existing_section_hint=None,
        scope_ref="scope.existing.request.1",
        scope_id="scope.existing.request.1",
        operations=(
            {
                "local_ref": "create_gamma_ray_binding",
                "scope_ref": "scope.existing.request.1",
                "verb": "CREATE",
                "object_kind": "binding",
                "semantic_ref": "request.binding.1",
                "field_values": ({"field": "channel", "state": "SET", "value": "Gamma Ray"},),
            },
        ),
        obligations=compilation.requirements.requirements,
    )


def test_plot_gamma_ray_compiles_one_semantic_binding_obligation() -> None:
    """Compile the reviewed term without replacing it with the physical mnemonic."""
    task = _task()

    channel_facts = [
        item
        for item in task.obligations
        if item.owner_kind.value == "binding" and item.field == "channel"
    ]

    assert len(channel_facts) == 1
    assert channel_facts[0].value == "Gamma Ray"
    assert channel_facts[0].slot_key == "request.binding.1"


def test_scalar_binding_contract_is_host_selected_and_provider_ids_stay_private() -> None:
    """Keep target and binding identity host-owned while exposing opaque handles."""
    task = _task()
    context = _context()
    work_contract = build_section_work_contract(task, context)
    operation_contract = build_section_operation_contract(task, context)

    assert work_contract.required_action == "add_binding"
    assert len(work_contract.required_bindings) == 1
    expected = work_contract.required_bindings[0]
    assert expected.track_handle == "track-1"
    assert expected.host_binding_id is not None
    assert operation_contract.operations[0].binding_id == expected.host_binding_id

    provider_work = _provider_work_contract(work_contract)
    provider_operations = _provider_operation_contract(operation_contract)
    assert "host_binding_id" not in provider_work["required_bindings"][0]
    assert "binding_id" not in provider_operations["operations"][0]
    assert provider_work["required_bindings"][0]["track_handle"] == "track-1"


def test_preworker_ledger_binds_semantic_expectation_before_worker_output() -> None:
    """Construct the expected semantic slot from host facts before realization."""
    task = _task()
    plan = SemanticPlan(
        summary="HOST-02 test plan",
        section_tasks=(task,),
        obligations=task.obligations,
    )

    contract = build_preworker_semantic_publication_contract(
        plan,
        SimpleNamespace(sections=(_context(),)),
    )

    assert contract is not None
    assert len(contract.expected_bindings) == 1
    expected = contract.expected_bindings[0]
    assert expected.requested_term == "Gamma Ray"
    assert expected.track_id == "track-main"
    assert expected.binding_id.startswith("binding-host-")
    assert expected.source_handle == "source-1"


def test_preworker_semantic_binding_rejects_untrusted_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not downgrade semantic publication when catalog trust fails."""
    task = _task()
    plan = SemanticPlan(
        summary="HOST-02 trust test",
        section_tasks=(task,),
        obligations=task.obligations,
    )

    def reject_catalog() -> object:
        raise SemanticCatalogTrustError("deployment_pin_missing")

    monkeypatch.setattr(
        "wellplot.agent.code_mode.worker_contracts.load_deployed_catalog_release",
        reject_catalog,
    )

    with pytest.raises(SectionWorkContractError) as caught:
        build_preworker_semantic_publication_contract(
            plan,
            SimpleNamespace(sections=(_context(),)),
        )

    assert caught.value.code == "semantic_catalog_unavailable"
    assert caught.value.details == {"catalog_error": "deployment_pin_missing"}


def test_scalar_binding_action_lowers_through_existing_intent_boundary() -> None:
    """Lower one validated sparse action through the existing intent boundary."""
    task = _task()
    context = _context()
    work_contract = build_section_work_contract(task, context)
    operation_contract = build_section_operation_contract(task, context)
    expected = work_contract.required_bindings[0]
    action = AddBindingAction(
        action="add_binding",
        target={"handle": "track-1"},
        binding={"semantic_id": "request.binding.1", "channel": "Gamma Ray"},
    )

    validate_section_action_contract(action, work_contract, operation_contract)
    intent = lower_section_action(
        action,
        context=context,
        document=AuthoringDocumentSpec(
            name="host-02-test",
            sections=[
                {
                    "id": "section-main",
                    "title": "Main Log",
                    "tracks": [
                        {
                            "id": "track-main",
                            "title": "Main Log",
                            "kind": "normal",
                            "width_mm": 25,
                            "bindings": [],
                        }
                    ],
                }
            ],
        ),
        host_binding_id=expected.host_binding_id,
        expected_snapshot_id=context.snapshot_id,
    )

    assert len(intent.curve_bindings) == 1
    binding = intent.curve_bindings[0]
    assert binding.binding_id == expected.host_binding_id
    assert binding.section_id == "section-main"
    assert binding.track_id == "track-main"
    assert binding.channel == "Gamma Ray"


def test_exact_binding_replay_is_accepted_without_reallocating_identity() -> None:
    """Accept an exact existing binding as an idempotent host-owned replay."""
    task = _task()
    context = _context()
    initial = build_section_work_contract(task, context)
    binding_id = initial.required_bindings[0].host_binding_id
    replay_context = context.model_copy(
        update={
            "existing_curves": (
                ExistingCurveContext(
                    track_id="track-main",
                    track_title="Main Log",
                    track_kind="normal",
                    binding_id=binding_id,
                    channel="GR",
                    label="Gamma Ray",
                ),
            )
        }
    )

    replay = build_section_work_contract(task, replay_context)

    assert replay.required_bindings[0].host_binding_id == binding_id


def test_unrelated_binding_identity_collision_fails_closed() -> None:
    """Reject a derived binding ID that belongs to an unrelated existing binding."""
    task = _task()
    context = _context()
    initial = build_section_work_contract(task, context)
    binding_id = initial.required_bindings[0].host_binding_id
    collision_context = context.model_copy(
        update={
            "existing_curves": (
                ExistingCurveContext(
                    track_id="other-track",
                    track_title="Other",
                    track_kind="normal",
                    binding_id=binding_id,
                    channel="RHOB",
                ),
            )
        }
    )

    try:
        build_section_work_contract(task, collision_context)
    except Exception as error:
        assert getattr(error, "code", None) == "binding_identity_collision"
    else:
        raise AssertionError("An unrelated binding identity collision was accepted.")


def test_sparse_binding_rejects_new_parent_operation() -> None:
    """HOST-02 does not introduce a parent track through a sparse binding."""
    task = _task().model_copy(
        update={
            "operations": (_task().operations[0].model_copy(update={"parent_ref": "new-track"}),)
        }
    )

    with pytest.raises(SectionWorkContractError, match="parent"):
        build_section_operation_contract(task, _context())


def test_sparse_binding_rejects_array_channel_kind() -> None:
    """HOST-02 admits only scalar channels and leaves raster paths unchanged."""
    context = _context()
    source = context.sources[0].model_copy(
        update={
            "channels": tuple(
                channel.model_copy(update={"kind": "array"})
                if channel.mnemonic == "GR"
                else channel
                for channel in context.sources[0].channels
            )
        }
    )

    with pytest.raises(SectionWorkContractError, match="scalar"):
        build_section_work_contract(_task(), context.model_copy(update={"sources": (source,)}))
