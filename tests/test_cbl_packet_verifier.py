"""Acceptance tests for the deterministic CBL packet verifier."""

# The repository-root bootstrap must run before importing script modules.
# isort: off
from __future__ import annotations

import copy
from importlib import import_module
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
# isort: on

yaml = import_module("yaml")
cbl_packet_verifier = import_module("scripts.verify_cbl_packet")
verify_cbl_packet = cbl_packet_verifier.verify_cbl_packet
load_authoring_document = import_module("wellplot.authoring").load_authoring_document


_DRAFT = Path(
    "workspace/tutorials/agent_cbl_log_example_from_prompt/agent_cbl_log_example_draft.log.yaml"
)


def test_cbl_packet_verifier_accepts_descriptive_line_style_aliases() -> None:
    """Provider-facing style names remain equivalent to Matplotlib shorthand."""
    assert cbl_packet_verifier._line_style_matches("dashed", "--")
    assert cbl_packet_verifier._line_style_matches("dotted", ":")


def _repaired_payload() -> dict[str, object]:
    """Build a valid acceptance fixture from the current packet draft."""
    payload = load_authoring_document(_DRAFT).model_dump(mode="json")
    main_section, repeat_section = payload["sections"]
    main_tracks = {track["id"]: track for track in main_section["tracks"]}
    repeat_tracks = {track["id"]: track for track in repeat_section["tracks"]}

    for track_id in ("combo", "cbl", "vdl"):
        repeat_track = repeat_tracks[track_id]
        main_track = main_tracks[track_id]
        repeat_track["bindings"] = copy.deepcopy(main_track["bindings"])
        for index, binding in enumerate(repeat_track["bindings"], start=1):
            binding["binding_id"] = f"repeat_pass.{track_id}.{binding['channel']}.{index}"
    repeat_tracks["vdl"]["x_scale"] = copy.deepcopy(main_tracks["vdl"]["x_scale"])
    repeat_tracks["vdl"]["grid"] = copy.deepcopy(main_tracks["vdl"]["grid"])

    for section in payload["sections"]:
        raster = next(track for track in section["tracks"] if track["id"] == "vdl")["bindings"][0]
        raster["colorbar"] = {
            "enabled": True,
            "label": "Amplitude",
            "position": "header",
        }
        raster["sample_axis"] = {
            "enabled": True,
            "label": None,
            "maximum": 1200.0,
            "minimum": 200.0,
            "source_origin": 40.0,
            "source_step": 10.0,
            "tick_count": 7,
            "unit": "us",
        }
    return payload


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
