"""XOR + regression parity suite against persisted patched constraint schema."""

from __future__ import annotations

import json
from typing import Any, Literal

Expected = Literal["ACCEPT", "REJECT"]


def _minimal_program(*, query: dict[str, Any] | None = None, **request_extra: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "requested_operation": "PLACE_CURVE",
        "deictic_reference": False,
        "scale_direction_claims": [],
        "target_claims": [],
    }
    if query is not None:
        request["query"] = query
    request.update(request_extra)
    return {
        "tasks": [
            {
                "task_id": "t1",
                "depends_on": [],
                "produces_binds": {},
                "request": request,
            }
        ]
    }


def _create_track_program() -> dict[str, Any]:
    return {
        "tasks": [
            {
                "task_id": "t_create",
                "depends_on": [],
                "produces_binds": {"petrophysics": "track"},
                "request": {
                    "requested_operation": "CREATE_TRACK",
                    "deictic_reference": False,
                    "scale_direction_claims": [],
                    "target_claims": [],
                    "track_title": "Petrophysics",
                },
            }
        ]
    }


def probe_instances() -> list[dict[str, Any]]:
    """Canonical probe payloads (dict form)."""
    return [
        {
            "probe_id": "xor_text_only",
            "expected": "ACCEPT",
            "stage": "xor",
            "instance": _minimal_program(query={"kind": "curve", "text": "GR"}),
        },
        {
            "probe_id": "xor_local_ref_only",
            "expected": "ACCEPT",
            "stage": "xor",
            "instance": _minimal_program(query={"kind": "track", "local_ref": "$petrophysics"}),
        },
        {
            "probe_id": "xor_both",
            "expected": "REJECT",
            "stage": "xor",
            "instance": _minimal_program(
                query={"kind": "curve", "text": "GR", "local_ref": "$t"}
            ),
        },
        {
            "probe_id": "xor_neither",
            "expected": "REJECT",
            "stage": "xor",
            "instance": _minimal_program(query={"kind": "curve"}),
        },
        {
            "probe_id": "regression_unknown_field",
            "expected": "REJECT",
            "stage": "regression",
            "instance": {
                **_minimal_program(query={"kind": "curve", "text": "GR"}),
                "unexpected_top_level": True,
            },
        },
        {
            "probe_id": "regression_illegal_enum",
            "expected": "REJECT",
            "stage": "regression",
            "instance": _minimal_program(
                query={"kind": "curve", "text": "GR"},
                requested_operation="NOT_A_REAL_OP",
            ),
        },
        {
            "probe_id": "regression_wrong_primitive",
            "expected": "REJECT",
            "stage": "regression",
            "instance": _minimal_program(
                query={"kind": "curve", "text": "GR"},
                alpha="not-a-number",
            ),
        },
        {
            "probe_id": "regression_malformed_nesting",
            "expected": "REJECT",
            "stage": "regression",
            "instance": {
                "tasks": [
                    {
                        "task_id": "t1",
                        "depends_on": [],
                        "produces_binds": {},
                        "request": "not-an-object",
                    }
                ]
            },
        },
        {
            "probe_id": "regression_valid_non_query_program",
            "expected": "ACCEPT",
            "stage": "regression",
            "instance": _create_track_program(),
        },
    ]


def _jsonschema_accepts(schema: dict[str, Any], instance: Any) -> tuple[bool, str]:
    import jsonschema

    try:
        jsonschema.validate(instance=instance, schema=schema)
        return True, "jsonschema_accept"
    except jsonschema.ValidationError as exc:
        return False, f"jsonschema_reject:{exc.message}"
    except jsonschema.SchemaError as exc:  # pragma: no cover
        return False, f"jsonschema_schema_error:{exc.message}"


def _outlines_accepts(compiled: Any, instance: Any) -> tuple[bool, str]:
    """Outlines regex acceptance; instances serialized with sort_keys for grammar alignment."""
    text = json.dumps(instance, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    try:
        compiled.validate(text)
        return True, "outlines_accept"
    except Exception as exc:  # noqa: BLE001
        # Outlines dumps the full compiled regex into ValueError; keep evidence compact.
        msg = str(exc)
        if len(msg) > 240:
            msg = msg[:240] + "…[truncated]"
        return False, f"outlines_reject:{type(exc).__name__}:{msg}"


def run_parity_suite(
    *,
    patched_schema: dict[str, Any],
    outlines_compiled: Any | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    all_pass = True

    for probe in probe_instances():
        expected: Expected = probe["expected"]
        instance = probe["instance"]
        js_ok, js_diag = _jsonschema_accepts(patched_schema, instance)
        observed_js: Expected = "ACCEPT" if js_ok else "REJECT"
        js_pass = observed_js == expected

        outlines_diag = None
        outlines_pass = None
        observed_outlines = None
        if outlines_compiled is not None:
            ol_ok, outlines_diag = _outlines_accepts(outlines_compiled, instance)
            observed_outlines = "ACCEPT" if ol_ok else "REJECT"
            outlines_pass = observed_outlines == expected

        # Conjunctive: jsonschema must match expected; Outlines must match when compiled.
        probe_pass = js_pass and (outlines_pass if outlines_pass is not None else True)
        if not probe_pass:
            all_pass = False

        records.append(
            {
                "probe_id": probe["probe_id"],
                "expected": expected,
                "observed": observed_js,
                "observed_outlines": observed_outlines,
                "pass": probe_pass,
                "stage": probe["stage"],
                "diagnostic": {
                    "jsonschema": js_diag,
                    "outlines": outlines_diag,
                    "jsonschema_pass": js_pass,
                    "outlines_pass": outlines_pass,
                },
            }
        )

    return {
        "suite": "decomposer_pilot_preflight_01_parity",
        "pass": all_pass,
        "probe_count": len(records),
        "probes": records,
    }
