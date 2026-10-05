"""D0 acceptance contracts for CBL construction and LAS revision."""

from __future__ import annotations

import copy
import json
import sys
from importlib import import_module
from pathlib import Path

import pytest

from wellplot.agent.graph.executor import execute_document_intent
from wellplot.authoring import load_authoring_document
from wellplot.authoring_service import AuthoringService
from wellplot.model.intent import AuthoringDocumentIntent

sys.path.insert(0, str(Path(__file__).parents[1]))

yaml = import_module("yaml")
cbl_verifier = import_module("scripts.verify_cbl_packet")
las_verifier = import_module("scripts.verify_las_revision")

FIXTURES = Path(__file__).parent / "fixtures" / "agentic_cbl"
D0_FIXTURES = Path(__file__).parent / "fixtures" / "d0"


def _cbl_payload() -> dict[str, object]:
    contract = json.loads((FIXTURES / "compile_contract.json").read_text())
    service = AuthoringService(load_authoring_document(FIXTURES / "cased_hole_starter.log.yaml"))
    result = execute_document_intent(
        service,
        AuthoringDocumentIntent.model_validate(contract["merged_intent"]),
        available_channels={
            section: source["channels"] for section, source in contract["source_manifest"].items()
        },
        header_aliases=contract["execution_context"]["header_aliases"],
    )
    assert result.success, result.errors
    return service.document.model_dump(mode="json")


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _requirement(result: dict[str, object], requirement_id: str) -> dict[str, object]:
    return next(item for item in result["requirements"] if item["id"] == requirement_id)


def _break_required_remark(payload: dict[str, object]) -> None:
    for remark in payload["remarks"]:
        if remark.get("title") == "Supported Reconstruction Scope":
            remark["lines"] = ["Wrong remarks"]
            return
    raise AssertionError("required remark fixture is missing")


def _break_label(payload: dict[str, object]) -> None:
    payload["sections"][0]["tracks"][0]["bindings"][0]["label"] = "Wrong label"


def _break_style(payload: dict[str, object]) -> None:
    payload["sections"][0]["tracks"][0]["bindings"][0]["style"]["color"] = "#ffffff"


def _break_width(payload: dict[str, object]) -> None:
    payload["sections"][0]["tracks"][0]["width_mm"] = 99.0


def test_cbl_requirement_results_are_explicit_and_positive(tmp_path: Path) -> None:
    """Report every CBL requirement as PASS when the full evidence is present."""
    path = tmp_path / "cbl.yaml"
    _write_payload(path, _cbl_payload())

    result = cbl_verifier.verify_cbl_packet(
        path,
        execution_evidence={"persisted": True, "rendered": True},
    )

    assert result["acceptance_status"] == "PASS"
    assert result["ok"] is True
    assert [item["id"] for item in result["requirements"]] == [
        f"CBL-0{index}" for index in range(1, 10)
    ]
    assert all(item["status"] == "PASS" for item in result["requirements"])


def test_cbl_render_evidence_is_not_promoted_without_observation(tmp_path: Path) -> None:
    """Keep render evidence NOT_CHECKABLE when it was not observed."""
    path = tmp_path / "cbl.yaml"
    _write_payload(path, _cbl_payload())

    result = cbl_verifier.verify_cbl_packet(path)

    assert result["acceptance_status"] == "NOT_CHECKABLE"
    assert _requirement(result, "CBL-09")["status"] == "NOT_CHECKABLE"


@pytest.mark.parametrize(
    ("requirement_id", "mutate"),
    [
        (
            "CBL-01",
            lambda payload: payload["header"]["service_titles"][0]["value"].update(value="Wrong"),
        ),
        ("CBL-02", _break_required_remark),
        ("CBL-03", lambda payload: payload["sections"].reverse()),
        ("CBL-04", lambda payload: payload["sections"][0]["tracks"].reverse()),
        ("CBL-05", lambda payload: payload["sections"][0]["tracks"][2]["bindings"].pop()),
        ("CBL-06", lambda payload: payload["sections"][0]["tracks"][1].update(kind="normal")),
        (
            "CBL-07",
            lambda payload: payload["sections"][0]["tracks"][3]["bindings"][0].update(
                profile="generic"
            ),
        ),
        (
            "CBL-08",
            lambda payload: payload["sections"][0]["tracks"][0]["bindings"][0]["scale"].update(
                minimum=10.0
            ),
        ),
        ("CBL-08", _break_label),
        ("CBL-08", _break_style),
        ("CBL-04", _break_width),
    ],
)
def test_cbl_adversarial_mutations_fail_the_relevant_requirement(
    tmp_path: Path,
    requirement_id: str,
    mutate: object,
) -> None:
    """Attribute each controlled mutation to its scientist-visible requirement."""
    payload = _cbl_payload()
    mutate(payload)
    path = tmp_path / f"{requirement_id}.yaml"
    _write_payload(path, payload)

    result = cbl_verifier.verify_cbl_packet(
        path, execution_evidence={"persisted": True, "rendered": True}
    )

    assert result["acceptance_status"] == "FAIL"
    assert _requirement(result, requirement_id)["status"] == "FAIL"


def test_cbl_invalid_document_is_a_workflow_failure_not_harness_success(tmp_path: Path) -> None:
    """Classify an invalid final document as a workflow failure."""
    payload = _cbl_payload()
    payload["sections"] = []
    path = tmp_path / "invalid.yaml"
    _write_payload(path, payload)

    result = cbl_verifier.verify_cbl_packet(path)

    assert result["acceptance_status"] == "FAIL"
    assert result["harness_error"] is False
    assert _requirement(result, "CBL-03")["status"] == "FAIL"


def test_cbl_unsuccessful_render_evidence_is_a_requirement_failure(tmp_path: Path) -> None:
    """Reject explicit evidence that persistence or rendering did not succeed."""
    path = tmp_path / "cbl.yaml"
    _write_payload(path, _cbl_payload())

    result = cbl_verifier.verify_cbl_packet(
        path,
        execution_evidence={"persisted": True, "rendered": False},
    )

    assert result["acceptance_status"] == "FAIL"
    assert _requirement(result, "CBL-09")["status"] == "FAIL"


def _las_paths(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    before = tmp_path / "before.yaml"
    after = tmp_path / "after.yaml"
    payload = load_authoring_document(FIXTURES / "cased_hole_starter.log.yaml").model_dump(
        mode="json"
    )
    payload["sections"][0]["tracks"][0]["bindings"][0]["scale"] = {
        "kind": "linear",
        "minimum": 0.0,
        "maximum": 100.0,
        "reverse": False,
    }
    _write_payload(before, payload)
    return before, after, payload


def test_las_requested_delta_passes_and_preserves_unrelated_state(tmp_path: Path) -> None:
    """Accept the requested scale change while leaving unrelated state intact."""
    before, after, payload = _las_paths(tmp_path)
    changed = copy.deepcopy(payload)
    changed["sections"][0]["tracks"][0]["bindings"][0]["scale"]["minimum"] = 10.0
    _write_payload(after, changed)
    acceptance = json.loads((D0_FIXTURES / "las_revision_specs.json").read_text())[
        "requested_scale_change"
    ]

    result = las_verifier.verify_las_revision(
        before,
        after,
        acceptance,
        execution_evidence={"accepted": True, "persisted": True, "rendered": True},
    )

    assert result["workflow_status"] == "PASS"
    assert result["status"] == "NOT_CHECKABLE"
    assert {item["id"] for item in result["requirements"] if item["status"] == "PASS"} >= {
        "LAS-01",
        "LAS-05",
        "LAS-07",
        "LAS-09",
    }


def test_las_collateral_mutation_fails_even_when_requested_change_succeeds(tmp_path: Path) -> None:
    """Reject a correct requested change that also mutates an unrelated track."""
    before, after, payload = _las_paths(tmp_path)
    changed = copy.deepcopy(payload)
    changed["sections"][0]["tracks"][0]["bindings"][0]["scale"]["minimum"] = 10.0
    changed["sections"][0]["tracks"][1]["width_mm"] = 99.0
    _write_payload(after, changed)
    acceptance = json.loads((D0_FIXTURES / "las_revision_specs.json").read_text())[
        "requested_scale_change"
    ]

    result = las_verifier.verify_las_revision(
        before,
        after,
        acceptance,
        execution_evidence={"accepted": True, "persisted": True, "rendered": True},
    )

    assert result["status"] == "FAIL"
    assert _requirement(result, "LAS-07")["status"] == "FAIL"


def test_las_acceptance_can_ignore_declared_generated_identity_metadata(tmp_path: Path) -> None:
    """Do not turn an explicitly declared generated-ID change into collateral failure."""
    before, after, payload = _las_paths(tmp_path)
    changed = copy.deepcopy(payload)
    changed["sections"][0]["tracks"][0]["bindings"][0]["scale"]["minimum"] = 10.0
    changed["sections"][0]["tracks"][0]["bindings"][0]["binding_id"] = "new-generated-id"
    _write_payload(after, changed)
    acceptance = json.loads((D0_FIXTURES / "las_revision_specs.json").read_text())[
        "requested_scale_change"
    ]
    acceptance["ignored_change_paths"] = ["/sections/0/tracks/0/bindings/0/binding_id"]

    result = las_verifier.verify_las_revision(
        before,
        after,
        acceptance,
        execution_evidence={"accepted": True, "persisted": True, "rendered": True},
    )

    assert result["workflow_status"] == "PASS"
    assert result["status"] == "NOT_CHECKABLE"


def test_las_rejected_noop_passes_and_any_mutation_fails(tmp_path: Path) -> None:
    """Require rejected ambiguous revisions to leave the document unchanged."""
    before, after, payload = _las_paths(tmp_path)
    acceptance = json.loads((D0_FIXTURES / "las_revision_specs.json").read_text())[
        "rejected_ambiguous_request"
    ]
    _write_payload(after, copy.deepcopy(payload))

    result = las_verifier.verify_las_revision(
        before,
        after,
        acceptance,
        execution_evidence={"accepted": False, "persisted": True, "rendered": True},
    )
    assert result["workflow_status"] == "PASS"
    assert result["status"] == "NOT_CHECKABLE"
    assert _requirement(result, "LAS-08")["status"] == "PASS"

    mutated = copy.deepcopy(payload)
    mutated["remarks"].append({"title": "Unexpected", "text": "Mutation"})
    _write_payload(after, mutated)
    result = las_verifier.verify_las_revision(
        before,
        after,
        acceptance,
        execution_evidence={"accepted": False, "persisted": True, "rendered": True},
    )
    assert result["status"] == "FAIL"
    assert _requirement(result, "LAS-08")["status"] == "FAIL"
    assert _requirement(result, "LAS-07")["status"] == "FAIL"


def test_las_missing_render_evidence_is_not_checkable(tmp_path: Path) -> None:
    """Keep persistence/render claims NOT_CHECKABLE without execution evidence."""
    before, after, payload = _las_paths(tmp_path)
    _write_payload(after, copy.deepcopy(payload))
    acceptance = json.loads((D0_FIXTURES / "las_revision_specs.json").read_text())[
        "rejected_ambiguous_request"
    ]

    result = las_verifier.verify_las_revision(before, after, acceptance)

    assert result["workflow_status"] == "PASS"
    assert result["status"] == "NOT_CHECKABLE"
    assert _requirement(result, "LAS-08")["status"] == "NOT_CHECKABLE"
    assert _requirement(result, "LAS-09")["status"] == "NOT_CHECKABLE"


def test_las_verifier_errors_are_separate_from_workflow_failures(tmp_path: Path) -> None:
    """Expose malformed acceptance specifications as harness errors."""
    before, after, payload = _las_paths(tmp_path)
    _write_payload(after, copy.deepcopy(payload))
    acceptance = {"required_changes": [], "allowed_change_paths": None}

    result = las_verifier.verify_las_revision(before, after, acceptance)

    assert result["status"] == "HARNESS_ERROR"
    assert result["harness_error"] is True
