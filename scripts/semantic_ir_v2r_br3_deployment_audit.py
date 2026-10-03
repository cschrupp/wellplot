"""Provider-free SI-V2R deployment toolchain and grammar audit.

BR3 keeps deployment identity, build provenance, grammar conversion, grammar
acceptance, and canonical semantic validation as separate evidence.  It does
not contact a model endpoint during normal audit construction and never
selects an adapter or changes a production contract.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

try:
    from scripts.semantic_ir_v2r_br2_converter_audit import (
        UPSTREAM_REFERENCE_ARCHIVE_SHA256,
        UPSTREAM_REFERENCE_COMMIT,
        V2R_SCHEMA_SHA256,
        canonical_json,
        sha256_bytes,
        sha256_file,
    )
except ModuleNotFoundError:
    from semantic_ir_v2r_br2_converter_audit import (
        UPSTREAM_REFERENCE_ARCHIVE_SHA256,
        UPSTREAM_REFERENCE_COMMIT,
        V2R_SCHEMA_SHA256,
        canonical_json,
        sha256_bytes,
        sha256_file,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_br3"
V2R_GOLD_PATH = REPO_ROOT / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"

BASELINE_SHA = "95033de99285db85d5c818e733805b102f08b328"
EXPERIMENT_VERSION = "SI-V2R-BR3"
CURRENT_MODEL_ALIAS = "qwen3.6-35b-a3b"
CURRENT_BUILD_INFO = "b11160-a3c12db9d"

DIRECT_SUPPORTED = "SI_V2R_BR3_DIRECT_BOUNDARY_SUPPORTED"
SCHEMA_INCOMPATIBILITY = "SI_V2R_BR3_SCHEMA_INCOMPATIBILITY_ESTABLISHED"
TOOLCHAIN_UNRESOLVED = "SI_V2R_BR3_DEPLOYMENT_TOOLCHAIN_UNRESOLVED"
REWORK_REQUIRED = "SI_V2R_BR3_REWORK_REQUIRED"

RUNTIME_ONLY_INVARIANTS = {
    "reference_target_required",
    "reference_target_membership",
    "semantic_feature_ids_unique",
    "fill_target_is_curve",
    "report_or_section_required",
    "non_blank_collection_items",
}


def _serialized(value: object) -> str:
    """Serialize provider JSON in model field order without retaining it."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load one local JSON input."""
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_metrics(schema: dict[str, Any]) -> dict[str, int]:
    """Return descriptive JSON Schema metrics."""
    encoded = canonical_json(schema).encode("utf-8")
    nodes: list[tuple[object, int]] = [(schema, 1)]
    refs = one_of = any_of = required = additional_false = 0
    max_depth = object_nodes = array_nodes = 0
    while nodes:
        node, depth = nodes.pop()
        if not isinstance(node, dict):
            continue
        max_depth = max(max_depth, depth)
        object_nodes += int(node.get("type") == "object")
        array_nodes += int(node.get("type") == "array")
        refs += int("$ref" in node)
        one_of += int("oneOf" in node)
        any_of += int("anyOf" in node)
        required += len(node.get("required", []))
        additional_false += int(node.get("additionalProperties") is False)
        for value in node.values():
            if isinstance(value, dict):
                nodes.append((value, depth + 1))
            elif isinstance(value, list):
                nodes.extend((item, depth + 1) for item in value if isinstance(item, dict))
    return {
        "bytes": len(encoded),
        "defs": len(schema.get("$defs", {})),
        "refs": refs,
        "one_of": one_of,
        "any_of": any_of,
        "max_depth": max_depth,
        "object_nodes": object_nodes,
        "array_nodes": array_nodes,
        "required_fields": required,
        "additional_properties_false": additional_false,
    }


def endpoint_observation() -> dict[str, Any]:
    """Return the bounded metadata observation made without inference."""
    return {
        "classification": "CURRENT_ONLY",
        "metadata_calls": 2,
        "request_classes": ["GET /props", "GET /v1/models"],
        "provider_inference_calls": 0,
        "model_alias": CURRENT_MODEL_ALIAS,
        "available_model_ids": [CURRENT_MODEL_ALIAS],
        "reported_build_info": CURRENT_BUILD_INFO,
        "model_path_present": True,
        "model_path_persisted": False,
        "deployment_artifact_identity": "UNRESOLVED",
        "structured_output_backend": "UNRESOLVED",
    }


def deployment_provenance() -> dict[str, Any]:
    """Record artifact identity and build provenance as separate facts."""
    return {
        "status": "UNRESOLVED",
        "deployment_artifact": {
            "classification": "UNRESOLVED",
            "kind": "remote_llama_server",
            "sha256": None,
            "immutable_image_digest": None,
        },
        "llama_server_binary": {
            "classification": "UNRESOLVED",
            "sha256": None,
            "path_persisted": False,
        },
        "source_commit": {"classification": "UNRESOLVED", "value": None},
        "build_definition": {"classification": "UNRESOLVED", "digest": None},
        "compiler_toolchain": {"classification": "UNRESOLVED", "digest": None},
        "structured_output_backend": {"classification": "UNRESOLVED", "identity": None},
        "json_schema_converter": {"classification": "UNRESOLVED", "identity": None},
        "grammar_parser_validator": {"classification": "UNRESOLVED", "identity": None},
        "reported_endpoint_build": {
            "classification": "REPORTED_ONLY",
            "value": CURRENT_BUILD_INFO,
        },
        "current_endpoint_observation": endpoint_observation(),
    }


def _compiler_identity() -> dict[str, Any]:
    """Capture the local compiler used to build a reference executable."""
    executable = shutil.which("g++")
    if executable is None:
        return {"executable": None, "version": None, "sha256": None}
    version_lines = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=False
    ).stdout.splitlines()
    return {
        "executable": Path(executable).name,
        "version": version_lines[0] if version_lines else None,
        "sha256": sha256_file(Path(executable)),
    }


def toolchain_identity(
    converter: Path | None,
    validator: Path | None,
) -> dict[str, Any]:
    """Describe optional reference tools without calling them a deployment."""
    converter_record = {
        "classification": "REFERENCE_ONLY" if converter else "UNRESOLVED",
        "source_commit": UPSTREAM_REFERENCE_COMMIT if converter else None,
        "source_archive_sha256": UPSTREAM_REFERENCE_ARCHIVE_SHA256 if converter else None,
        "binary_sha256": sha256_file(converter) if converter else None,
    }
    validator_record = {
        "classification": "REFERENCE_ONLY" if validator else "UNRESOLVED",
        "source_commit": UPSTREAM_REFERENCE_COMMIT if validator else None,
        "source_archive_sha256": UPSTREAM_REFERENCE_ARCHIVE_SHA256 if validator else None,
        "binary_sha256": sha256_file(validator) if validator else None,
    }
    return {
        "deployment_match": False,
        "deployment_toolchain_pinned": False,
        "converter": converter_record,
        "grammar_parser_validator": validator_record,
        "compiler": _compiler_identity() if converter or validator else None,
        "source_build": {
            "source_commit": UPSTREAM_REFERENCE_COMMIT if converter or validator else None,
            "source_archive_sha256": UPSTREAM_REFERENCE_ARCHIVE_SHA256
            if converter or validator
            else None,
            "build_flags": "isolated reference build" if converter or validator else None,
        },
        "pair_status": "REFERENCE_ONLY" if converter and validator else "NOT_PINNED",
    }


def _run_converter(
    converter: Path,
    schema: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Convert a schema and return metadata plus ephemeral grammar text."""
    with tempfile.TemporaryDirectory(prefix="si-v2r-br3-") as temp_dir:
        schema_path = Path(temp_dir) / "schema.json"
        schema_path.write_text(canonical_json(schema), encoding="utf-8")
        result = subprocess.run(
            [str(converter), str(schema_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    grammar = result.stdout if result.returncode == 0 else None
    warnings = [line for line in result.stderr.splitlines() if "WARNING" in line]
    grammar_bytes = grammar.encode("utf-8") if grammar is not None else None
    return (
        {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "return_code": result.returncode,
            "warnings": warnings,
            "warning_count": len(warnings),
            "errors": [] if result.returncode == 0 else [result.stderr.strip()[-1000:]],
            "grammar_sha256": sha256_bytes(grammar_bytes) if grammar_bytes is not None else None,
            "grammar_bytes": len(grammar_bytes) if grammar_bytes is not None else None,
            "grammar_rule_count": grammar.count(" ::= ") if grammar is not None else None,
            "grammar_parser": "NOT_EVALUABLE",
        },
        grammar,
    )


def _run_validator(validator: Path, grammar: str, payload: object) -> bool:
    """Run the bounded BR3 validator interface: validator grammar.json payload.json."""
    with tempfile.TemporaryDirectory(prefix="si-v2r-br3-validator-") as temp_dir:
        root = Path(temp_dir)
        grammar_path = root / "grammar.gbnf"
        payload_path = root / "payload.json"
        grammar_path.write_text(grammar, encoding="utf-8")
        payload_path.write_text(_serialized(payload), encoding="utf-8")
        result = subprocess.run(
            [str(validator), str(grammar_path), str(payload_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    return result.returncode == 0


def _load_malformed_fixtures() -> dict[str, dict[str, Any]]:
    """Reuse the frozen BR1 malformed cases."""
    try:
        from scripts.semantic_ir_v2r_br1_boundary_audit import malformed_fixtures
    except ModuleNotFoundError:
        from semantic_ir_v2r_br1_boundary_audit import malformed_fixtures
    return malformed_fixtures()


def _feature(kind: str, semantic_id: str, **extra: object) -> dict[str, Any]:
    """Build one compact valid feature fixture."""
    return {
        "kind": kind,
        "semantic_id": semantic_id,
        "requirements": [],
        "constraints": [],
        **extra,
    }


def valid_domain_fixtures() -> dict[str, dict[str, Any]]:
    """Return independent valid V2R fixtures for grammar validation."""

    def section(
        goal: str,
        features: list[dict[str, Any]],
        reference: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build one valid section fixture."""
        return {
            "kind": "log_plot",
            "goal": goal,
            "existing_section_hint": None,
            "source_hints": [],
            "features": features,
            "reference_intent": reference,
            "requirements": [],
            "constraints": [],
        }

    return {
        "report_only": {
            "summary": "Prepare a report.",
            "report_work": {
                "goal": "Prepare a report.",
                "requirements": ["Signoff"],
                "constraints": [],
            },
            "sections": [],
            "unresolved_requirements": [],
        },
        "single_scalar": {
            "summary": "Show a scalar.",
            "report_work": None,
            "sections": [section("Show a scalar.", [_feature("curve", "scalar")])],
            "unresolved_requirements": [],
        },
        "single_raster": {
            "summary": "Show a raster.",
            "report_work": None,
            "sections": [section("Show a raster.", [_feature("raster", "raster")])],
            "unresolved_requirements": [],
        },
        "multiple_scalar": {
            "summary": "Compare scalar features.",
            "report_work": None,
            "sections": [
                section(
                    "Compare scalars.",
                    [_feature("curve", "curve_a"), _feature("curve", "curve_b")],
                )
            ],
            "unresolved_requirements": [],
        },
        "scalar_annotation": {
            "summary": "Annotate a scalar.",
            "report_work": None,
            "sections": [
                section(
                    "Annotate a scalar.",
                    [_feature("curve", "curve"), _feature("annotation", "marker")],
                )
            ],
            "unresolved_requirements": [],
        },
        "fill": {
            "summary": "Fill a scalar.",
            "report_work": None,
            "sections": [
                section(
                    "Fill a scalar.",
                    [
                        _feature("curve", "curve"),
                        _feature("fill", "fill", target_semantic_id="curve"),
                    ],
                )
            ],
            "unresolved_requirements": [],
        },
        "companion_depth_lane": {
            "summary": "Show a scalar with depth.",
            "report_work": None,
            "sections": [
                section(
                    "Show a scalar with depth.",
                    [_feature("curve", "curve")],
                    {"kind": "companion_depth_lane", "target_semantic_id": None},
                )
            ],
            "unresolved_requirements": [],
        },
        "reference_track_target": {
            "summary": "Assign a scalar to a reference track.",
            "report_work": None,
            "sections": [
                section(
                    "Assign a scalar to a reference track.",
                    [_feature("curve", "curve")],
                    {"kind": "reference_track", "target_semantic_id": "curve"},
                )
            ],
            "unresolved_requirements": [],
        },
        "multiple_sections": {
            "summary": "Show independent panels.",
            "report_work": None,
            "sections": [
                section("First panel.", [_feature("curve", "first")]),
                section("Second panel.", [_feature("raster", "second")]),
            ],
            "unresolved_requirements": [],
        },
        "mixed_report_section": {
            "summary": "Prepare a report and panel.",
            "report_work": {"goal": "Prepare a report.", "requirements": [], "constraints": []},
            "sections": [section("Show a panel.", [_feature("curve", "panel")])],
            "unresolved_requirements": [],
        },
        "unresolved_requirements": {
            "summary": "Preserve an unresolved request.",
            "report_work": None,
            "sections": [section("Show a panel.", [_feature("curve", "panel")])],
            "unresolved_requirements": ["A future capability is unspecified."],
        },
    }


def _model_accepts(payload: dict[str, Any]) -> bool:
    """Check one payload against canonical V2R validation."""
    from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

    try:
        SemanticIRV2R.model_validate(payload)
    except ValidationError:
        return False
    return True


def _canonical_model_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return canonical field-order JSON data when the model accepts it."""
    from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

    try:
        model = SemanticIRV2R.model_validate(payload)
    except ValidationError:
        return None
    return model.model_dump(mode="json")


def _grammar_check(
    validator: Path | None,
    grammar: str | None,
    payload: dict[str, Any],
) -> bool | str:
    """Return deterministic grammar status or an explicit unavailable marker."""
    if validator is None or grammar is None:
        return "NOT_EVALUABLE"
    return _run_validator(validator, grammar, payload)


def _reverse_object_order(value: object) -> object:
    """Reverse object key order recursively for serialization diagnostics."""
    if isinstance(value, dict):
        return {key: _reverse_object_order(item) for key, item in reversed(list(value.items()))}
    if isinstance(value, list):
        return [_reverse_object_order(item) for item in value]
    return value


def _gold_payloads() -> list[dict[str, Any]]:
    """Load frozen gold objects without their audit-only case IDs."""
    cases = _load_json(V2R_GOLD_PATH)["cases"]
    return [{key: value for key, value in case.items() if key != "case_id"} for case in cases]


def _fixture_accounting(
    schema: dict[str, Any],
    grammar: str | None,
    validator: Path | None,
) -> dict[str, Any]:
    """Account for independent valid fixture coverage."""
    schema_validator = Draft202012Validator(schema)
    rows = []
    for name, payload in valid_domain_fixtures().items():
        canonical_payload = _canonical_model_payload(payload)
        rows.append(
            {
                "fixture": name,
                "json_schema_accepts": not list(schema_validator.iter_errors(payload)),
                "canonical_model_accepts": canonical_payload is not None,
                "grammar_accepts": _grammar_check(validator, grammar, canonical_payload or payload),
            }
        )
    return {
        "fixture_count": len(rows),
        "accepted": sum(
            row["json_schema_accepts"] and row["canonical_model_accepts"] for row in rows
        ),
        "grammar_accepted": (
            sum(row["grammar_accepts"] is True for row in rows)
            if validator and grammar
            else "NOT_EVALUABLE"
        ),
        "rows": rows,
    }


def _gold_accounting(
    schema: dict[str, Any],
    grammar: str | None,
    validator: Path | None,
) -> dict[str, Any]:
    """Account for the 24 frozen gold objects and ordering behavior."""
    schema_validator = Draft202012Validator(schema)
    rows = []
    for index, payload in enumerate(_gold_payloads(), start=1):
        canonical_payload = _canonical_model_payload(payload)
        canonical_json_payload = canonical_payload or payload
        alternate_payload = _reverse_object_order(canonical_json_payload)
        rows.append(
            {
                "ordinal": index,
                "json_schema_accepts": not list(schema_validator.iter_errors(payload)),
                "canonical_model_accepts": canonical_payload is not None,
                "grammar_accepts": _grammar_check(validator, grammar, canonical_json_payload),
                "alternate_order_grammar_accepts": _grammar_check(
                    validator, grammar, alternate_payload
                ),
            }
        )
    grammar_values = [row["grammar_accepts"] for row in rows]
    alternate_values = [row["alternate_order_grammar_accepts"] for row in rows]
    return {
        "case_count": len(rows),
        "json_schema_accepts": sum(row["json_schema_accepts"] for row in rows),
        "canonical_model_accepts": sum(row["canonical_model_accepts"] for row in rows),
        "grammar_accepts": (
            sum(value is True for value in grammar_values)
            if validator and grammar
            else "NOT_EVALUABLE"
        ),
        "alternate_order_grammar_accepts": (
            sum(value is True for value in alternate_values)
            if validator and grammar
            else "NOT_EVALUABLE"
        ),
        "serialization_order_restriction": (
            "PRESENT"
            if validator and grammar and any(value is False for value in alternate_values)
            else "NONE"
            if validator and grammar
            else "NOT_EVALUABLE"
        ),
        "rows": rows,
    }


def _malformed_accounting(
    schema: dict[str, Any],
    grammar: str | None,
    validator: Path | None,
) -> dict[str, Any]:
    """Run the frozen malformed matrix across all validation layers."""
    schema_validator = Draft202012Validator(schema)
    rows = []
    for fixture, payload in _load_malformed_fixtures().items():
        rows.append(
            {
                "fixture": fixture,
                "json_schema_accepts": not list(schema_validator.iter_errors(payload)),
                "grammar_accepts": _grammar_check(validator, grammar, payload),
                "canonical_model_accepts": _model_accepts(payload),
            }
        )
    return {"row_count": len(rows), "rows": rows}


def _constraint_matrix(
    schema: dict[str, Any],
    malformed: dict[str, Any],
    grammar_available: bool,
) -> dict[str, Any]:
    """Classify schema-level and canonical runtime invariants."""
    explicit = {
        "feature_discriminator": "JSON_SCHEMA_ENFORCED",
        "required_fields": "JSON_SCHEMA_ENFORCED",
        "non_empty_string_length": "JSON_SCHEMA_ENFORCED",
        "collection_min_items": "JSON_SCHEMA_ENFORCED",
        "additional_properties_forbidden": "JSON_SCHEMA_ENFORCED",
    }
    rows = []
    for invariant, schema_status in explicit.items():
        rows.append(
            {
                "invariant": invariant,
                "json_schema": schema_status,
                "grammar": "NOT_EVALUABLE" if not grammar_available else "REQUIRES_CASE_AUDIT",
                "canonical_runtime": "ALSO_VALIDATED",
            }
        )
    for invariant in sorted(RUNTIME_ONLY_INVARIANTS):
        rows.append(
            {
                "invariant": invariant,
                "json_schema": "CANONICAL_RUNTIME_ONLY",
                "grammar": "NOT_EVALUABLE" if not grammar_available else "CANONICAL_RUNTIME_ONLY",
                "canonical_runtime": "CANONICAL_RUNTIME_ONLY",
            }
        )
    return {
        "schema_keyword_metrics": _schema_metrics(schema),
        "rows": rows,
        "schema_level_count": len(explicit),
        "grammar_enforced_count": (
            "NOT_EVALUABLE" if not grammar_available else "REQUIRES_CASE_AUDIT"
        ),
        "canonical_runtime_only_count": len(RUNTIME_ONLY_INVARIANTS),
        "relevant_weakened_count": 0,
        "malformed_row_count": malformed["row_count"],
    }


def build_audit(
    converter: Path | None = None,
    validator: Path | None = None,
) -> dict[str, Any]:
    """Build BR3 evidence without inference or production integration."""
    from wellplot.agent.code_mode.semantic_ir_v2 import SemanticIRV2
    from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

    if validator and not converter:
        raise ValueError("A grammar validator requires its converter in BR3.")
    if converter and (not converter.is_file() or not converter.stat().st_mode & 0o111):
        raise ValueError(f"Converter is not executable: {converter}")
    if validator and (not validator.is_file() or not validator.stat().st_mode & 0o111):
        raise ValueError(f"Grammar validator is not executable: {validator}")

    schemas = {
        "si_v2": SemanticIRV2.model_json_schema(),
        "si_v2r": SemanticIRV2R.model_json_schema(),
    }
    v2r_hash = sha256_bytes(canonical_json(schemas["si_v2r"]).encode("utf-8"))
    if v2r_hash != V2R_SCHEMA_SHA256:
        raise ValueError("Frozen V2R schema hash changed.")

    conversions: dict[str, dict[str, Any]] = {}
    grammars: dict[str, str | None] = {}
    for name, schema in schemas.items():
        if converter is None:
            conversions[name] = {
                "status": "NOT_EVALUABLE",
                "reason": "No converter executable was supplied.",
            }
            grammars[name] = None
        else:
            conversions[name], grammars[name] = _run_converter(converter, schema)

    gold = _gold_accounting(schemas["si_v2r"], grammars["si_v2r"], validator)
    valid_fixtures = _fixture_accounting(schemas["si_v2r"], grammars["si_v2r"], validator)
    malformed = _malformed_accounting(schemas["si_v2r"], grammars["si_v2r"], validator)
    constraints = _constraint_matrix(
        schemas["si_v2r"], malformed, validator is not None and grammars["si_v2r"] is not None
    )
    deployment = deployment_provenance()
    toolchain = toolchain_identity(converter, validator)
    conversion_pass = converter is not None and all(
        result.get("status") == "PASS" for result in conversions.values()
    )
    if deployment["status"] != "AUTHENTICATED" or not toolchain["deployment_toolchain_pinned"]:
        decision = TOOLCHAIN_UNRESOLVED
    elif not conversion_pass or validator is None:
        decision = REWORK_REQUIRED
    elif gold["grammar_accepts"] != gold["case_count"]:
        decision = SCHEMA_INCOMPATIBILITY
    else:
        decision = DIRECT_SUPPORTED
    return {
        "experiment": EXPERIMENT_VERSION,
        "baseline": BASELINE_SHA,
        "decision": decision,
        "deployment_provenance": deployment,
        "toolchain_identity": toolchain,
        "conversions": conversions,
        "schemas": {
            name: {
                "sha256": sha256_bytes(canonical_json(schema).encode("utf-8")),
                "metrics": _schema_metrics(schema),
            }
            for name, schema in schemas.items()
        },
        "grammar_validation": {
            "gold": gold,
            "valid_domain_fixtures": valid_fixtures,
            "malformed": malformed,
        },
        "constraint_matrix": constraints,
        "adapter_justified": "NONE",
        "provider_inference_calls": 0,
        "endpoint_metadata_calls": 2,
        "host_inspection_operations": ["GET /props", "GET /v1/models"],
        "worker_program_calls": 0,
        "production_changes": 0,
    }


def write_outputs(
    output_dir: Path,
    converter: Path | None = None,
    validator: Path | None = None,
) -> dict[str, Any]:
    """Write bounded BR3 machine-readable artifacts without grammar bodies."""
    audit = build_audit(converter, validator)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "deployment_provenance.json": audit["deployment_provenance"],
        "toolchain_identity.json": audit["toolchain_identity"],
        "grammar_validation.json": {
            "schemas": audit["schemas"],
            "conversions": audit["conversions"],
            **audit["grammar_validation"],
        },
        "constraint_matrix.json": audit["constraint_matrix"],
        "result.json": {
            key: audit[key]
            for key in (
                "experiment",
                "baseline",
                "decision",
                "adapter_justified",
                "provider_inference_calls",
                "endpoint_metadata_calls",
                "host_inspection_operations",
                "worker_program_calls",
                "production_changes",
            )
        },
    }
    for name, value in outputs.items():
        (output_dir / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return audit


def main() -> None:
    """Generate BR3 provider-free evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--converter", type=Path)
    parser.add_argument("--validator", type=Path)
    args = parser.parse_args()
    audit = write_outputs(args.output_dir, args.converter, args.validator)
    print(
        json.dumps(
            {
                "decision": audit["decision"],
                "provider_inference_calls": audit["provider_inference_calls"],
                "endpoint_metadata_calls": audit["endpoint_metadata_calls"],
                "worker_program_calls": audit["worker_program_calls"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
