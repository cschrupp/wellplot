"""Deterministic CM-56R8 semantic-contract tests."""

from __future__ import annotations

import json

from scripts.cm56r6_authoritative_request import build_authoritative_worker_input
from scripts.cm56r7_semantic_failure_decomposition import applicable_checks
from scripts.cm56r8_semantic_contract_diagnostic import (
    AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
    CONTRACT_INSTRUCTION,
    build_contract_system_prompt,
    build_contract_worker_input,
    load_semantic_contracts,
    select_semantic_contracts,
    semantic_contract_only_differs,
)


def _artifact() -> tuple[dict[str, object], str]:
    """Load the frozen R8 contract artifact."""
    return load_semantic_contracts()


def _base_input() -> str:
    """Build a representative path-free authoritative payload."""
    return build_authoritative_worker_input(
        json.dumps(
            {
                "section_task": {
                    "goal": "Create a synthetic section.",
                    "capability_ids": [
                        "section.log_plot",
                        "track.normal",
                        "binding.curve",
                    ],
                    "source_hints": ["source-1"],
                },
                "capabilities": [],
                "sources": [
                    {
                        "candidate_id": "source-1",
                        "channels": [{"mnemonic": "CALX", "kind": "scalar"}],
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "Create CALX with a linear scale from -25 to 75.",
    )


def test_contract_artifact_is_path_free_and_not_benchmark_specific() -> None:
    """Contracts contain semantic vocabulary but no frozen case answers."""
    artifact, digest = _artifact()
    serialized = json.dumps(artifact, sort_keys=True)
    assert digest
    forbidden = (
        "scalar_linear",
        "reverse_scale",
        "generic_raster",
        "vdl_sample_axis",
        "cbl_continuity",
        "main-source",
        "repeat-source",
        "Gamma Ray",
        "Resistivity",
        "CBL Amplitude",
        "200 to 1200",
        "0 to 150",
        "0 to 100",
        "5000",
    )
    assert all(value not in serialized for value in forbidden)
    assert "/home/" not in serialized
    assert "/tmp/" not in serialized
    assert "\\\\" not in serialized
    assert "canonical_path" not in serialized


def test_contracts_cover_required_capabilities_and_field_meanings() -> None:
    """The artifact documents the required domain-to-IR mappings."""
    artifact, _ = _artifact()
    ids = {contract["capability_id"] for contract in artifact["contracts"]}
    assert ids == {"track.normal", "track.array", "binding.curve", "binding.raster"}
    serialized = json.dumps(artifact, sort_keys=True)
    for field in (
        "scale.kind",
        "scale.minimum",
        "scale.maximum",
        "scale.reverse",
        "track.x_scale",
        "profile",
        "sample_axis",
        "source_origin",
        "source_step",
        "tick_count",
    ):
        assert field.split(".")[-1] in serialized
    assert "binding.scale" in serialized
    assert "track.x_scale is not binding.scale" in serialized


def test_contract_selection_is_capability_local() -> None:
    """Scalar and raster tasks receive only relevant contract documents."""
    artifact, _ = _artifact()
    scalar = select_semantic_contracts(
        ("section.log_plot", "track.normal", "binding.curve"), artifact
    )
    raster = select_semantic_contracts(
        ("section.log_plot", "track.array", "binding.raster"), artifact
    )
    assert [contract["capability_id"] for contract in scalar] == [
        "track.normal",
        "binding.curve",
    ]
    assert [contract["capability_id"] for contract in raster] == [
        "track.array",
        "binding.raster",
    ]


def test_b_is_exactly_a_plus_selected_contracts() -> None:
    """Pair construction changes no authoritative/task/context data."""
    artifact, _ = _artifact()
    base = _base_input()
    contracts = select_semantic_contracts(
        ("section.log_plot", "track.normal", "binding.curve"), artifact
    )
    variant_b = build_contract_worker_input(base, contracts=contracts)
    assert semantic_contract_only_differs(base, variant_b)
    left = json.loads(base)
    right = json.loads(variant_b)
    right.pop("semantic_contracts")
    assert left == right


def test_b_contract_payload_is_deterministic() -> None:
    """Identical A input and contracts serialize identically."""
    artifact, _ = _artifact()
    contracts = select_semantic_contracts(("track.array", "binding.raster"), artifact)
    first = build_contract_worker_input(_base_input(), contracts=contracts)
    second = build_contract_worker_input(_base_input(), contracts=contracts)
    assert first == second


def test_b_prompt_is_bounded_and_examples_are_not_defaults() -> None:
    """B adds only contract-use instructions to the R6 authoritative prompt."""
    prompt = build_contract_system_prompt()
    assert prompt.startswith(AUTHORITATIVE_REQUEST_SYSTEM_PROMPT)
    assert prompt.endswith(CONTRACT_INSTRUCTION)
    assert "examples illustrate mappings only" in prompt
    assert "never copy example values" in prompt
    assert "expected_sections" not in prompt


def test_schema_and_evaluator_contracts_are_unchanged() -> None:
    """R8 documents existing semantics rather than changing their checks."""
    assert "tracks[0].bindings[0].scale" in applicable_checks(
        {
            "tracks": [
                {
                    "kind": "normal",
                    "title": "Synthetic",
                    "bindings": [{"channel": "CALX", "scale": {"minimum": -25, "maximum": 75}}],
                }
            ]
        }
    )
