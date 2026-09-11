"""Acceptance tests for the deterministic CBL packet verifier."""

# The repository-root bootstrap must run before importing script modules.
# isort: off
from __future__ import annotations

import json
from importlib import import_module
import sys
from pathlib import Path

import pytest

from wellplot.agent.graph.executor import execute_document_intent
from wellplot.authoring_service import AuthoringService
from wellplot.model.intent import AuthoringDocumentIntent

sys.path.insert(0, str(Path(__file__).parents[1]))
# isort: on

yaml = import_module("yaml")
cbl_packet_verifier = import_module("scripts.verify_cbl_packet")
verify_cbl_packet = cbl_packet_verifier.verify_cbl_packet
load_authoring_document = import_module("wellplot.authoring").load_authoring_document


_FIXTURES = Path(__file__).parent / "fixtures" / "agentic_cbl"


def test_cbl_packet_verifier_accepts_descriptive_line_style_aliases() -> None:
    """Provider-facing style names remain equivalent to Matplotlib shorthand."""
    assert cbl_packet_verifier._line_style_matches("solid", "-")
    assert cbl_packet_verifier._line_style_matches("dashed", "--")
    assert cbl_packet_verifier._line_style_matches("dotted", ":")


def _repaired_payload() -> dict[str, object]:
    """Build the accepted two-pass packet independently of notebook state."""
    contract = json.loads((_FIXTURES / "compile_contract.json").read_text())
    service = AuthoringService(load_authoring_document(_FIXTURES / "cased_hole_starter.log.yaml"))
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


def test_cbl_packet_verifier_accepts_repaired_packet(tmp_path: Path) -> None:
    """The verifier accepts the complete final-state contract."""
    path = tmp_path / "cbl.log.yaml"
    path.write_text(yaml.safe_dump(_repaired_payload(), sort_keys=False), encoding="utf-8")

    result = verify_cbl_packet(path)

    assert result["ok"] is True
    assert result["errors"] == []
    assert isinstance(result["document_sha256"], str)
    assert len(result["document_sha256"]) == 64


def test_cbl_packet_verifier_accepts_descriptive_dotted_style(tmp_path: Path) -> None:
    """Accept the descriptive style name emitted by the notebook provider."""
    payload = _repaired_payload()
    for section in payload["sections"]:
        depth = next(track for track in section["tracks"] if track["id"] == "depth")
        tdsp = next(binding for binding in depth["bindings"] if binding["channel"] == "TDSP")
        tdsp["style"]["line_style"] = "dotted"
    path = tmp_path / "cbl-dotted.log.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = verify_cbl_packet(path)

    assert result["ok"] is True
    assert result["errors"] == []


def test_cbl_packet_verifier_accepts_equivalent_reversed_scale_representation(
    tmp_path: Path,
) -> None:
    """A descending scale can use ascending bounds plus the reverse flag."""
    payload = _repaired_payload()
    for section in payload["sections"]:
        combo = next(track for track in section["tracks"] if track["id"] == "combo")
        tension = next(binding for binding in combo["bindings"] if binding["channel"] == "TENS")
        tension["scale"].update(minimum=0.0, maximum=5000.0, reverse=True)
    path = tmp_path / "cbl-reversed-scale.log.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = verify_cbl_packet(path)

    assert result["ok"] is True
    assert result["errors"] == []


def test_cbl_packet_verifier_rejects_double_reversed_scale(tmp_path: Path) -> None:
    """Descending bounds and the reverse flag together invert the requested scale."""
    payload = _repaired_payload()
    for section in payload["sections"]:
        combo = next(track for track in section["tracks"] if track["id"] == "combo")
        tension = next(binding for binding in combo["bindings"] if binding["channel"] == "TENS")
        tension["scale"]["reverse"] = True
    path = tmp_path / "cbl-double-reversed-scale.log.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = verify_cbl_packet(path)

    assert result["ok"] is False
    assert (
        "main_pass/combo[2]: scale endpoints are 0.0 to 5000.0, expected 5000.0 to 0.0"
        in (result["errors"])
    )


def test_cbl_packet_verifier_reports_exact_final_state_defect(tmp_path: Path) -> None:
    """A requested raster setting cannot be hidden by a successful mutation report."""
    payload = _repaired_payload()
    raster = next(track for track in payload["sections"][0]["tracks"] if track["id"] == "vdl")[
        "bindings"
    ][0]
    raster["sample_axis"]["enabled"] = False
    path = tmp_path / "cbl.log.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = verify_cbl_packet(path)

    assert result["ok"] is False
    assert "main_pass/vdl/VDL: sample axis enabled is False" in result["errors"]


def _frozen_report() -> dict[str, object]:
    """Apply the frozen report to a tracked scaffold, not notebook output."""
    contract = json.loads((_FIXTURES / "compile_contract.json").read_text())
    service = AuthoringService(load_authoring_document(_FIXTURES / "cased_hole_starter.log.yaml"))
    result = execute_document_intent(
        service, AuthoringDocumentIntent.model_validate(contract["artifacts"]["report"]["intent"])
    )
    assert result.success, result.errors
    return service.document.model_dump(mode="json")


def test_frozen_report_satisfies_independent_content_and_layout_acceptance() -> None:
    """Canonical success alone is not the oracle for the requested report."""
    payload = _frozen_report()
    errors = []
    cbl_packet_verifier._check_header(payload, errors)
    cbl_packet_verifier._check_remarks(payload, errors)
    cbl_packet_verifier._check_report_settings(payload, errors)
    assert errors == []


@pytest.mark.parametrize("setting", ["dimensions", "service_font", "remark_font", "remark_title"])
def test_report_acceptance_rejects_schema_valid_microscopic_sizes(setting: str) -> None:
    """Positive-but-unreadable placeholders must not pass packet evaluation."""
    payload = _frozen_report()
    if setting == "dimensions":
        payload["page"].update(width_mm=0.0001, height_mm=0.0001)
    elif setting == "service_font":
        payload["header"]["service_titles"][0]["font_size"] = 0.0001
    else:
        field = "font_size" if setting == "remark_font" else "title_font_size"
        payload["remarks"][0][field] = 0.0001
    errors = []
    cbl_packet_verifier._check_report_settings(payload, errors)
    assert errors
    assert all("0.0001" in error for error in errors)


def test_report_acceptance_still_rejects_captured_empty_remark_bodies() -> None:
    """Having the requested titles does not satisfy the requested remark content."""
    fixture = _FIXTURES / "report_placeholders_failure.json"
    payload = _frozen_report()
    payload["remarks"] = json.loads(fixture.read_text())["artifact"]["intent"]["remarks"]
    errors = []
    cbl_packet_verifier._check_remarks(payload, errors)
    assert len(errors) == 3


def test_report_acceptance_allows_equivalent_a4_dimensions_and_readable_fonts() -> None:
    """Accept explicit sizes that preserve the requested packet's visual contract."""
    payload = _frozen_report()
    payload["page"].update(width_mm=210.0, height_mm=297.0)
    payload["header"]["service_titles"][0]["font_size"] = 12.0
    payload["remarks"][0].update(font_size=8.0, title_font_size=10.0)
    errors = []
    cbl_packet_verifier._check_report_settings(payload, errors)
    assert errors == []
