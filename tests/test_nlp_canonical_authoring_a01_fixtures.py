"""A01 provider-free golden fixture integrity checks."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from wellplot.model.authoring import AuthoringDocumentSpec

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "nlp_canonical_authoring" / "a01_golden_contract.json"
)
EXPECTED_FIXTURE_SHA256 = "6f8486ed825d252ffbc3882dc96220824376405b0780c8b98f8e919258bdfa7a"

REQUIRED_CASES = {
    "existing-two-track-sparse-add",
    "eight-track-full-reemission",
    "duplicate-local-handle",
    "invalid-channel-for-source",
    "existing-track-must-not-be-mutated",
    "mixed-report-and-section-operations",
    "missing-header-slot",
    "optional-sp-omitted-when-absent",
    "source-not-inspected",
    "source-unavailable",
    "ambiguous-resistivity-role",
    "existing-target-resolution",
    "absent-target-resolution",
    "duplicate-targets-fail-closed",
    "reordered-existing-tracks",
    "duplicate-existing-gr-track",
    "same-mnemonic-distinct-sources",
}


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_a01_fixture_identity_is_frozen() -> None:
    """Detect accidental fixture drift after A01 golden review."""
    digest = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED_FIXTURE_SHA256


def test_a01_forge_document_fixtures_are_canonical_and_preserve_context() -> None:
    """Validate the synthetic document fixtures with the existing model."""
    fixture = _load_fixture()
    documents = fixture["canonical_document_fixtures"]

    existing = AuthoringDocumentSpec.model_validate(documents["existing_forge_main"])
    new = AuthoringDocumentSpec.model_validate(documents["new_forge_document"])

    assert existing.sections[0].id == "main_log"
    assert len(existing.sections[0].tracks) == 6
    assert existing.sections[1].id == "mud_log"
    assert existing.header is not None
    assert existing.header.general_fields[0].value.value == "FORGE 16B"
    assert existing.header.service_titles[0].value.value == "Open Hole Evaluation"
    assert existing.remarks[0].text == "Preserve this unrelated note."
    assert new.sections[0].id == "new_main_log"


def test_a01_ambiguity_overlays_are_canonical_documents() -> None:
    """Represent duplicate targets with concrete valid host-document states."""
    fixture = _load_fixture()
    overlays = fixture["document_overlays"]
    base = fixture["canonical_document_fixtures"]["existing_forge_main"]

    duplicate_target = deepcopy(base)
    duplicate_target["sections"].append(overlays["duplicate_main_log_target"]["section"])
    parsed_target = AuthoringDocumentSpec.model_validate(duplicate_target)
    assert sum(section.title == "Main Log" for section in parsed_target.sections) == 2

    duplicate_track = deepcopy(base)
    duplicate_track["sections"][0]["tracks"].append(overlays["duplicate_gr_track"]["track"])
    parsed_track = AuthoringDocumentSpec.model_validate(duplicate_track)
    gamma_tracks = [
        track
        for track in parsed_track.sections[0].tracks
        if any(binding.channel == "GR" for binding in getattr(track, "bindings", []))
    ]
    assert len(gamma_tracks) == 2


def test_a01_source_inventories_keep_inspection_states_and_no_private_assets() -> None:
    """Represent controlled LAS facts without embedding source bytes or paths."""
    fixture = _load_fixture()
    inventories = {item["id"]: item for item in fixture["source_inventories"]}

    assert inventories["forge-full"]["inspection_state"] == "inspected"
    assert {channel["mnemonic"] for channel in inventories["forge-full"]["channels"]} == {
        "DEPT",
        "GR",
        "BI",
        "SP",
        "RDEP",
        "RMED",
        "RSHA",
    }
    assert inventories["forge-no-sp"]["inspection_state"] == "inspected"
    assert {channel["mnemonic"] for channel in inventories["forge-no-sp"]["channels"]} == {
        "DEPT",
        "GR",
    }
    assert inventories["forge-uninspected"]["inspection_state"] == "not_inspected"
    assert inventories["forge-unavailable"]["inspection_state"] == "unavailable"
    assert {
        channel["mnemonic"] for channel in inventories["forge-ambiguous-resistivity"]["channels"]
    } >= {"RDEP", "RMED", "RSHA"}

    serialized = json.dumps(fixture)
    assert '"private_las_bytes_included": false' in serialized
    assert "/home/" not in serialized
    assert "/tmp/" not in serialized


def test_a01_golden_layers_are_separate_and_case_inventory_is_complete() -> None:
    """Keep model, host CRUD, final-state, and visual gold distinct."""
    fixture = _load_fixture()
    cases = {case["id"]: case for case in fixture["case_gold"]}
    assert set(cases) == REQUIRED_CASES

    for case in cases.values():
        assert "model_contract_gold" in case
        assert "host_crud_gold" in case
        assert case["visual_evidence"] == {
            "status": "not_generated",
            "grading_authority": False,
        }
        assert case["source_inventory"]
        assert case["document_fixture"] in fixture["canonical_document_fixtures"]
        overlay = case.get("fixture_overlay")
        if overlay is not None:
            assert overlay in fixture["document_overlays"]

    positive = cases["existing-two-track-sparse-add"]
    operations = positive["model_contract_gold"]["operations"]
    assert [(item["track"]["title"], item["binding"]["channel"]) for item in operations] == [
        ("Bond Index", "BI"),
        ("Gamma Ray (New)", "GR"),
    ]
    assert positive["host_crud_gold"]["outcome"] == "two_create_operations_only"
    assert positive["expected_model_state"]["main_log_track_ids_in_order"][:6] == [
        "depth",
        "gr",
        "sp",
        "rdep",
        "rmed",
        "rsha",
    ]


def test_a01_negative_and_unresolved_gold_fail_without_host_operations() -> None:
    """Require invalid or ungrounded cases to remain non-mutating."""
    fixture = _load_fixture()
    cases = {case["id"]: case for case in fixture["case_gold"]}
    nonmutating_cases = {
        "eight-track-full-reemission",
        "duplicate-local-handle",
        "invalid-channel-for-source",
        "existing-track-must-not-be-mutated",
        "missing-header-slot",
        "source-not-inspected",
        "source-unavailable",
        "ambiguous-resistivity-role",
        "duplicate-targets-fail-closed",
        "duplicate-existing-gr-track",
    }

    for case_id in nonmutating_cases:
        assert cases[case_id]["host_crud_gold"] == {
            "outcome": "no_operations",
            "document_mutation": False,
        }
