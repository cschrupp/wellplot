"""Provider-free invariants for deterministic section work contracts."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    ExistingCurveContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.obligations import compile_request_contract
from wellplot.agent.code_mode.planner import SectionTask
from wellplot.agent.code_mode.semantic_actions import (
    SectionSemanticAction,
    lower_section_action,
)
from wellplot.agent.code_mode.typed_section_worker import (
    _ACTION_RESPONSE_MODELS,
    _SECTION_ACTION_EXAMPLES,
    _bind_compiled_source,
    _section_action_example,
)
from wellplot.agent.code_mode.worker_contracts import (
    SectionWorkContract,
    SectionWorkContractError,
    build_section_work_contract,
    validate_section_action_contract,
)
from wellplot.agent.providers.base import StructuredGenerationRequest
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.model.authoring import AuthoringDocumentSpec


def _context(*, section_id: str | None = "main") -> ResolvedSectionContext:
    """Construct host context with private IDs/paths for leakage assertions."""
    return ResolvedSectionContext(
        task_index=0,
        section_id=section_id,
        sources=(
            SourceContext(
                candidate_id="host-source-secret-id",
                labels=("fixture.las",),
                canonical_path="/private/source/fixture.las",
                source_format="las",
                channels=(
                    ChannelContext(mnemonic="BI", kind="scalar"),
                    ChannelContext(mnemonic="GR_STGC", kind="scalar"),
                    ChannelContext(mnemonic="GR", kind="scalar"),
                    ChannelContext(mnemonic="DEPT", kind="scalar", unit="ft"),
                ),
            ),
        ),
        existing_curves=(
            ExistingCurveContext(
                track_id="host-track-id",
                track_title="Gamma Ray",
                track_kind="normal",
                binding_id="host-binding-id",
                channel="GR",
                label="Gamma Ray",
            ),
        ),
    )


def _contract(
    request: str,
    *,
    context: ResolvedSectionContext | None = None,
) -> SectionWorkContract:
    """Build the deterministic contract directly from compiled obligations."""
    compilation = compile_request_contract(request)
    task = SectionTask(
        goal="Execute the compiled section-local task.",
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        existing_section_hint="Main Log",
        obligations=compilation.requirements.requirements,
    )
    return build_section_work_contract(task, context or _context())


def _smoke_request() -> str:
    return (
        "In the Main Log section, add two normal tracks while preserving the existing tracks.\n"
        "Track Bond Index: normal, width 34 mm.\n"
        "Track Gamma Ray: normal, width 26 mm.\n"
        "On Bond Index: BI -> Bond Index, linear 0..1, #111111, width 0.8.\n"
        "On Gamma Ray: GR_STGC -> Gamma Ray, linear 0..150, #16a34a, width 0.8."
    )


def _valid_reconstruct_payload() -> dict[str, object]:
    """Return one contract-conforming action for the frozen smoke request."""
    return {
        "action": "reconstruct",
        "section": {
            "title": "Main Log",
            "source_candidate": "source-1",
            "tracks": [
                {
                    "semantic_id": "bond_index",
                    "kind": "normal",
                    "title": "Bond Index",
                    "width_mm": 34,
                    "bindings": [
                        {
                            "semantic_id": "bond_index.binding.1",
                            "channel": "BI",
                            "label": "Bond Index",
                            "scale": {"kind": "linear", "minimum": 0, "maximum": 1},
                            "style": {
                                "color": "#111111",
                                "line_width": 0.8,
                                "line_style": "solid",
                            },
                        }
                    ],
                },
                {
                    "semantic_id": "gamma_ray",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "width_mm": 26,
                    "bindings": [
                        {
                            "semantic_id": "gamma_ray.binding.1",
                            "channel": "GR_STGC",
                            "label": "Gamma Ray",
                            "scale": {"kind": "linear", "minimum": 0, "maximum": 150},
                            "style": {
                                "color": "#16a34a",
                                "line_width": 0.8,
                                "line_style": "solid",
                            },
                        }
                    ],
                },
            ],
        },
    }


def test_two_track_contract_is_reconstruct_and_provider_safe() -> None:
    """Two requested tracks produce stable handles without host provenance."""
    contract = _contract(_smoke_request())
    payload = contract.model_dump(mode="json")

    assert contract.required_action == "reconstruct"
    assert [track.handle for track in contract.required_tracks] == [
        "bond_index",
        "gamma_ray",
    ]
    assert [binding.handle for binding in contract.required_bindings] == [
        "bond_index.binding.1",
        "gamma_ray.binding.1",
    ]
    assert contract.required_bindings[1].scale.minimum == 0
    assert contract.required_bindings[1].scale.maximum == 150
    serialized = json.dumps(payload)
    for forbidden in (
        "request_sha256",
        "span_sha256",
        "start_byte",
        "canonical_path",
        "candidate_id",
        "host-source-secret-id",
        "host-binding-id",
        "/private/source",
    ):
        assert forbidden not in serialized


def test_action_selection_is_deterministic_for_add_scale_and_fill() -> None:
    """A single-track, scale-only, or fill task selects one exact action."""
    add_track = _contract(
        "Track Quality: normal, width 28 mm.\n"
        "On Quality: GR -> Gamma Ray, linear 0..150, #111111, width 1."
    )
    scale = _contract("Change Gamma Ray scale to linear 5..125.")
    fill = _contract("Fill Gamma Ray to lower limit using #f2e8a0 at 20% opacity.")

    assert add_track.required_action == "add_track"
    assert scale.required_action == "update_curve_scale"
    assert scale.target_handle == "curve-1"
    assert scale.required_scale.minimum == 5
    assert scale.required_scale.maximum == 125
    assert fill.required_action == "add_fill"
    assert fill.target_handle == "curve-1"


def test_normalized_track_handle_collision_fails_closed() -> None:
    """Distinct request objects may not collapse to one local handle."""
    compilation = compile_request_contract(_smoke_request())
    obligations = list(compilation.requirements.requirements)
    track_fact = next(item for item in obligations if item.owner_kind.value == "track")
    obligations.append(track_fact.model_copy(update={"owner_ref": "Bond-Index"}))
    task = SectionTask(
        goal="Build requested tracks.",
        capability_ids=("section.log_plot",),
        existing_section_hint="Main Log",
        obligations=tuple(obligations),
    )

    with pytest.raises(SectionWorkContractError) as error:
        build_section_work_contract(task, _context())
    assert error.value.code == "section_work_handle_collision"


def test_action_contract_rejects_missing_extra_wrong_kind_and_wrong_channel() -> None:
    """The same contract validates exact action, object cardinality, and values."""
    contract = _contract(_smoke_request())
    valid = _valid_reconstruct_payload()
    action = TypeAdapter(SectionSemanticAction).validate_python(valid)
    validate_section_action_contract(action, contract)

    missing = _valid_reconstruct_payload()
    missing["section"]["tracks"].pop()
    with pytest.raises(SectionWorkContractError, match="omitted or added required tracks"):
        validate_section_action_contract(
            TypeAdapter(SectionSemanticAction).validate_python(missing), contract
        )

    extra = _valid_reconstruct_payload()
    extra["section"]["tracks"].append(extra["section"]["tracks"][0].copy())
    extra["section"]["tracks"][2]["semantic_id"] = "unrequested"
    with pytest.raises(SectionWorkContractError, match="omitted or added required tracks"):
        validate_section_action_contract(
            TypeAdapter(SectionSemanticAction).validate_python(extra), contract
        )

    wrong_kind = _valid_reconstruct_payload()
    wrong_kind["section"]["tracks"][0]["kind"] = "reference"
    with pytest.raises(SectionWorkContractError, match="Track identity"):
        validate_section_action_contract(
            TypeAdapter(SectionSemanticAction).validate_python(wrong_kind), contract
        )

    wrong_channel = _valid_reconstruct_payload()
    wrong_channel["section"]["tracks"][0]["bindings"][0]["channel"] = "GR"
    with pytest.raises(SectionWorkContractError, match="Binding semantics"):
        validate_section_action_contract(
            TypeAdapter(SectionSemanticAction).validate_python(wrong_channel), contract
        )

    wrong_action = {
        "action": "add_track",
        "track": _valid_reconstruct_payload()["section"]["tracks"][0],
    }
    with pytest.raises(SectionWorkContractError, match="unauthorized action"):
        validate_section_action_contract(
            TypeAdapter(SectionSemanticAction).validate_python(wrong_action), contract
        )


def test_action_schemas_and_static_examples_are_versioned_and_specific() -> None:
    """Each contract action has one strict schema and one hashed static example."""
    expected = {"reconstruct", "add_track", "update_curve_scale", "add_fill"}
    assert set(_ACTION_RESPONSE_MODELS) == expected
    assert set(_SECTION_ACTION_EXAMPLES) == expected
    for action_name in sorted(expected):
        model = _ACTION_RESPONSE_MODELS[action_name]
        schema = model.model_json_schema()
        assert schema["properties"]["action"]["const"] == action_name
        example = _section_action_example(action_name)
        assert example["version"] == "wellplot.section-action-examples.v1"
        assert len(example["sha256"]) == 64
        assert example["payload"]["action"] == action_name


@pytest.mark.parametrize("action_name", sorted(_ACTION_RESPONSE_MODELS))
def test_action_schema_is_the_schema_sent_by_existing_openai_compat_adapter(
    action_name: str,
) -> None:
    """The canonical adapter emits each strict action model's exact JSON Schema."""
    model = _ACTION_RESPONSE_MODELS[action_name]
    payload = _section_action_example(action_name)["payload"]
    captured: dict[str, object] = {}

    class _Create:
        async def __call__(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(role="assistant", content=json.dumps(payload)),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_Create())))
    backend = OpenAICompatibleBackendV2(
        model="provider-free-schema-check",
        client=client,
        structured_output="json_schema",
    )
    request = StructuredGenerationRequest(
        system_prompt="Provider-free schema validation.",
        user_prompt="Validate the static example.",
        timeout_seconds=1.0,
    )

    asyncio.run(backend.generate_structured(request, response_model=model))

    response_format = captured["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == model.model_json_schema()


def test_reconstruct_reconciliation_preserves_unrequested_existing_depth_track() -> None:
    """Sparse reconstruction adds requested tracks without deleting Depth."""
    request = _smoke_request()
    compilation = compile_request_contract(request)
    task = SectionTask(
        goal="Add the requested quality tracks.",
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        existing_section_hint="Main Log",
        obligations=compilation.requirements.requirements,
    )
    context = _context()
    contract = build_section_work_contract(task, context)
    action = TypeAdapter(SectionSemanticAction).validate_python(_valid_reconstruct_payload())
    validate_section_action_contract(action, contract)
    grounded = _bind_compiled_source(
        action,
        context,
        work_contract=contract,
    )
    document = AuthoringDocumentSpec.model_validate(
        {
            "name": "binding-smoke-preservation",
            "sections": [
                {
                    "id": "main",
                    "title": "Main Log",
                    "data_source": {
                        "source_path": "/private/source/fixture.las",
                        "source_format": "las",
                    },
                    "tracks": [
                        {
                            "id": "depth",
                            "kind": "normal",
                            "title": "Depth",
                            "width_mm": 12,
                            "bindings": [
                                {
                                    "kind": "curve",
                                    "binding_id": "depth.dept",
                                    "channel": "DEPT",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    intent = lower_section_action(grounded, context=context, document=document)
    plan = reconcile_authoring(
        intent,
        existing=document,
        available_channels={"main": ["BI", "GR_STGC", "DEPT"]},
    )

    assert plan.ready is True
    assert all(
        not (operation.object_kind == "track" and operation.object_id == "depth")
        for operation in plan.operations
    )
    assert all(operation.action.value != "remove" for operation in plan.operations)
