"""Shared prompt / context assembly for SLM-01 runners."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from well_ir.schema import well_ir_json_schema
from well_ir.version import WELL_IR_VERSION

SYSTEM_PROMPT = f"""You are the WellPlot semantic compiler.
Translate the user utterance plus workspace context into WELL-IR {WELL_IR_VERSION}.
Emit ONLY one JSON object. No markdown. No commentary.

Exact ok shape example:
{{
  "status": "ok",
  "well_ir_version": "{WELL_IR_VERSION}",
  "ops": [
    {{
      "op": "place_curve",
      "curve": {{"kind": "curve", "ref": "RHOB"}},
      "target": {{
        "mode": "track",
        "reference": {{"kind": "track", "ref": 4}}
      }}
    }}
  ]
}}

Allowed ops only: place_curve, move_curve, remove_curve, configure_curve_display, set_interval, define_fill, remove_fill, create_track.
Allowed statuses: ok, ambiguous, unsupported, invalid.
Executable status "ok" programs MUST contain uniquely resolved refs only (kind+ref, or kind+local_ref for tracks created earlier with bind like "$track1").
When the workspace exposes request-local instance handles (curve-1, curve-2, …) or fill handles, prefer those refs for duplicate channels on the same track.
define_fill may use between_instances when filling between two curve instance handles on the same track with matching effective scales.
create_track may include width_mm and placement relation append|before|after relative to a track reference.
If ambiguous, return {{"status":"ambiguous","well_ir_version":"{WELL_IR_VERSION}","ambiguities":[{{"field":"curve","candidates":["RHOB","RHOZ"],"query":"density"}}]}}.
If a referenced object is absent: {{"status":"unsupported","well_ir_version":"{WELL_IR_VERSION}","reason":"reference_not_found","reference":{{"kind":"curve","query":"..."}}}}.
If outside WELL-IR {WELL_IR_VERSION} (annotations, VDL/array constructs, report/page authoring, unsupported units): reason operation_not_supported.
Never invent LogDocument internal IDs. Never wrap the envelope in "executable" or "program".
"""


def assemble_user_payload(utterance: str, workspace: dict[str, Any], d0: dict[str, Any]) -> str:
    return json.dumps(
        {
            "utterance": utterance,
            "workspace": workspace,
            "document_state_summary": {
                "tracks": d0.get("tracks"),
                "curves": [c.get("ref") for c in d0.get("curves", [])],
                "fills": [f.get("ref") for f in d0.get("fills", [])],
                "interval": d0.get("interval"),
            },
            "well_ir_version": WELL_IR_VERSION,
        },
        indent=2,
    )


def few_shot_messages(exemplars: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex in exemplars:
        messages.append(
            {
                "role": "user",
                "content": assemble_user_payload(ex["utterance"], ex["workspace"], ex["d0"]),
            }
        )
        messages.append({"role": "assistant", "content": json.dumps(ex["gold"])})
    return messages


def schema_hash() -> str:
    import hashlib

    raw = json.dumps(well_ir_json_schema(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
