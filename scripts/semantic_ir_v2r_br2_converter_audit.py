"""Provider-free SI-V2R converter provenance and compatibility audit.

This audit deliberately separates historical deployment provenance from a
future pinned-source reference converter.  It never contacts a model endpoint
and never treats a current endpoint build label as proof of historical use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_br2"
V2R_GOLD_PATH = REPO_ROOT / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
BASELINE_SHA = "d441b84068a06457ded8651cac67708ee17c2cd0"
HISTORICAL_LQ0_CHECKPOINT = "4f37ef8d6fa441d138f399dd3ac1c45da331fb86"
HISTORICAL_EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
HISTORICAL_ENDPOINT_IDENTITY_SHA256 = (
    "23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980"
)
V2R_SCHEMA_SHA256 = "d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8"
UPSTREAM_REFERENCE_COMMIT = "bed0a856606ee4a24a164066f73d2379447033f5"
UPSTREAM_REFERENCE_ARCHIVE_SHA256 = (
    "0984123c33b7e959f8003f9169e9109897112d9448b681737813911083eca4cc"
)
EXPERIMENT_VERSION = "SI-V2R-BR2"

PINNED_TOOLCHAIN_UNRESOLVED = "SI_V2R_BR2_PINNED_TOOLCHAIN_UNRESOLVED"
PINNED_DIRECT_SCHEMA_SUPPORTED = "SI_V2R_BR2_PINNED_DIRECT_SCHEMA_SUPPORTED"
PINNED_SCHEMA_INCOMPATIBILITY_ESTABLISHED = "SI_V2R_BR2_PINNED_SCHEMA_INCOMPATIBILITY_ESTABLISHED"
REWORK_REQUIRED = "SI_V2R_BR2_REWORK_REQUIRED"

SUPPORTED_SCHEMA_KEYWORDS = {
    "$defs",
    "$ref",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "items",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "oneOf",
    "pattern",
    "prefixItems",
    "properties",
    "required",
    "type",
}
IGNORED_SCHEMA_KEYWORDS = {"default", "description", "discriminator", "title"}
RUNTIME_ONLY_INVARIANTS = {
    "non_blank_string_values",
    "semantic_feature_ids_unique",
    "reference_target_required",
    "companion_target_forbidden",
    "reference_target_membership",
    "fill_target_is_curve",
    "report_or_section_required",
}


def canonical_json(value: object) -> str:
    """Serialize JSON evidence deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """Return a SHA-256 digest for immutable evidence."""
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file without retaining its contents in an evidence artifact."""
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> object:
    """Load one JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_metrics(schema: dict[str, Any]) -> dict[str, int]:
    """Return stable descriptive metrics for a JSON Schema document."""
    encoded = canonical_json(schema).encode("utf-8")
    refs = 0
    one_of = 0
    any_of = 0
    required = 0
    additional_false = 0
    defs = schema.get("$defs", {})
    nodes: list[tuple[object, int]] = [(schema, 1)]
    max_depth = 0
    object_nodes = 0
    array_nodes = 0
    while nodes:
        node, depth = nodes.pop()
        if not isinstance(node, dict):
            continue
        max_depth = max(max_depth, depth)
        if node.get("type") == "object":
            object_nodes += 1
        if node.get("type") == "array":
            array_nodes += 1
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
        "defs": len(defs),
        "refs": refs,
        "one_of": one_of,
        "any_of": any_of,
        "max_depth": max_depth,
        "object_nodes": object_nodes,
        "array_nodes": array_nodes,
        "required_fields": required,
        "additional_properties_false": additional_false,
    }


def _schema_keywords(schema: dict[str, Any]) -> list[str]:
    """Collect JSON Schema keywords without treating definition names as keys."""
    found: set[str] = set()
    stack: list[object] = [schema]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            found.update(value)
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return sorted(found)


def _classify_schema_constructs(schema: dict[str, Any]) -> dict[str, list[str]]:
    """Classify observed keywords without claiming runtime-validator support."""
    keywords = set(_schema_keywords(schema))
    return {
        "converter_supported": sorted(keywords & SUPPORTED_SCHEMA_KEYWORDS),
        "converter_ignored_or_weakened": sorted(keywords & IGNORED_SCHEMA_KEYWORDS),
        "unknown": sorted(keywords - SUPPORTED_SCHEMA_KEYWORDS - IGNORED_SCHEMA_KEYWORDS),
        "canonical_runtime_only": sorted(RUNTIME_ONLY_INVARIANTS),
    }


def historical_provenance() -> dict[str, Any]:
    """Describe retained historical evidence without inferring continuity."""
    return {
        "status": "UNRESOLVED",
        "lq0_checkpoint": HISTORICAL_LQ0_CHECKPOINT,
        "raw_evidence_sha256": HISTORICAL_EVIDENCE_SHA256,
        "endpoint_identity_sha256": HISTORICAL_ENDPOINT_IDENTITY_SHA256,
        "facts": [
            {
                "fact": "llama_cpp_build",
                "value": "b11160-a3c12db9d",
                "classification": "REPORTED_NOT_AUTHENTICATED",
                "evidence": "retained /props build label",
            },
            {
                "fact": "llama_cpp_source_commit",
                "value": "a3c12db9d",
                "classification": "UNAVAILABLE",
                "evidence": "reported suffix does not resolve to authenticated upstream source",
            },
            {
                "fact": "llama_server_binary_sha256",
                "value": None,
                "classification": "UNAVAILABLE",
                "evidence": "remote host binary was not retained",
            },
            {
                "fact": "schema_converter_identity",
                "value": None,
                "classification": "UNAVAILABLE",
                "evidence": "historical warning/converter artifact was not retained",
            },
        ],
        "same_endpoint_is_not_same_converter": True,
    }


def current_endpoint_observation() -> dict[str, Any]:
    """Record bounded current metadata observed through read-only requests."""
    return {
        "metadata_calls": 2,
        "request_classes": ["GET /props", "GET /v1/models"],
        "provider_inference_calls": 0,
        "model_alias": "qwen3.6-35b-a3b",
        "available_model_ids": ["qwen3.6-35b-a3b"],
        "reported_build_info": "b11160-a3c12db9d",
        "model_path_present": True,
        "model_path_persisted": False,
        "binary_sha256": None,
        "converter_source_identity": None,
        "classification": "CURRENT_ONLY",
    }


def _compiler_version() -> dict[str, Any]:
    """Capture the local compiler identity used for a reference build."""
    executable = shutil.which("g++")
    if executable is None:
        return {"executable": None, "version": None, "sha256": None}
    version = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=False
    ).stdout.splitlines()
    return {
        "executable": Path(executable).name,
        "version": version[0] if version else None,
        "sha256": sha256_file(Path(executable)),
    }


def _run_converter(converter: Path, schema: dict[str, Any]) -> dict[str, Any]:
    """Run one exact converter invocation and retain grammar metadata only."""
    with tempfile.TemporaryDirectory(prefix="si-v2r-br2-") as temp_dir:
        schema_path = Path(temp_dir) / "schema.json"
        schema_path.write_text(canonical_json(schema), encoding="utf-8")
        result = subprocess.run(
            [str(converter), str(schema_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    warnings = [line for line in result.stderr.splitlines() if "WARNING" in line]
    grammar = result.stdout
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "return_code": result.returncode,
        "warnings": warnings,
        "warning_count": len(warnings),
        "errors": [] if result.returncode == 0 else [result.stderr.strip()[-1000:]],
        "grammar_sha256": sha256_bytes(grammar.encode("utf-8")) if result.returncode == 0 else None,
        "grammar_bytes": len(grammar.encode("utf-8")) if result.returncode == 0 else None,
        "grammar_rule_count": grammar.count(" ::= ") if result.returncode == 0 else None,
        "grammar_parser": "NOT_AVAILABLE",
        "gold_grammar_representability": "NOT_EVALUABLE",
    }


def converter_audit(
    schemas: dict[str, dict[str, Any]],
    converter: Path | None,
) -> dict[str, Any]:
    """Audit a pinned reference converter, or fail closed when absent."""
    reference: dict[str, Any] = {
        "source_commit": UPSTREAM_REFERENCE_COMMIT,
        "source_archive_sha256": UPSTREAM_REFERENCE_ARCHIVE_SHA256,
        "converter_binary_sha256": sha256_file(converter) if converter else None,
        "compiler": _compiler_version() if converter else None,
        "invocation": ["<converter>", "<schema.json>"],
        "source_matches_historical_server": False,
    }
    conversions: dict[str, Any] = {}
    if converter is None:
        for name in schemas:
            conversions[name] = {
                "status": "NOT_EVALUABLE",
                "reason": "No exact converter executable was supplied.",
            }
    else:
        if not converter.is_file() or not converter.stat().st_mode & 0o111:
            raise ValueError(f"Converter is not an executable file: {converter}")
        for name, schema in schemas.items():
            conversions[name] = _run_converter(converter, schema)
    return {
        "reference_toolchain": reference,
        "conversions": conversions,
        "constructs": {
            name: _classify_schema_constructs(schema) for name, schema in schemas.items()
        },
    }


def _load_malformed_fixtures() -> dict[str, dict[str, Any]]:
    """Reuse the frozen BR1 malformed matrix without modifying it."""
    try:
        from scripts.semantic_ir_v2r_br1_boundary_audit import malformed_fixtures
    except ModuleNotFoundError:
        from semantic_ir_v2r_br1_boundary_audit import malformed_fixtures

    return malformed_fixtures()


def validation_matrix(schema: dict[str, Any]) -> dict[str, Any]:
    """Run the canonical schema/Pydantic malformed matrix.

    The grammar gate is deliberately reported as not evaluable because BR2
    does not have a parser from the same pinned toolchain.
    """
    from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

    validator = Draft202012Validator(schema)
    rows = []
    for fixture, payload in _load_malformed_fixtures().items():
        schema_accepts = not list(validator.iter_errors(payload))
        try:
            SemanticIRV2R.model_validate(payload)
        except ValidationError as error:
            canonical_accepts = False
            error_type = type(error).__name__
        else:
            canonical_accepts = True
            error_type = None
        rows.append(
            {
                "fixture": fixture,
                "json_schema_accepts": schema_accepts,
                "pinned_grammar_gate": "NOT_EVALUABLE",
                "canonical_model_accepts": canonical_accepts,
                "canonical_error_type": error_type,
                "expected_canonical_accepts": False,
            }
        )
    return {"version": "si-v2r-br2.validation-matrix.v1", "rows": rows}


def gold_representability(
    v2r_schema: dict[str, Any],
) -> dict[str, Any]:
    """Account for all gold objects without overstating grammar parsing."""
    from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

    validator = Draft202012Validator(v2r_schema)
    cases = _load_json(V2R_GOLD_PATH)["cases"]
    schema_accepts = 0
    canonical_accepts = 0
    for case in cases:
        payload = {key: value for key, value in case.items() if key != "case_id"}
        if not list(validator.iter_errors(payload)):
            schema_accepts += 1
        try:
            SemanticIRV2R.model_validate(payload)
        except ValidationError:
            continue
        canonical_accepts += 1
    return {
        "case_count": len(cases),
        "json_schema_accepts": f"{schema_accepts}/{len(cases)}",
        "canonical_model_accepts": f"{canonical_accepts}/{len(cases)}",
        "grammar_parser": "NOT_AVAILABLE",
        "grammar_representability": "NOT_EVALUABLE",
    }


def build_audit(converter: Path | None = None) -> dict[str, Any]:
    """Build deterministic BR2 artifacts without selecting an adapter."""
    from wellplot.agent.code_mode.semantic_ir_v2 import SemanticIRV2
    from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

    v2_schema = SemanticIRV2.model_json_schema()
    v2r_schema = SemanticIRV2R.model_json_schema()
    schemas = {"si_v2": v2_schema, "si_v2r": v2r_schema}
    if sha256_bytes(canonical_json(v2r_schema).encode()) != V2R_SCHEMA_SHA256:
        raise ValueError("Frozen V2R schema hash changed.")
    converter_result = converter_audit(schemas, converter)
    conversion_values = converter_result["conversions"].values()
    reference_conversion_pass = bool(converter) and all(
        value.get("status") == "PASS" for value in conversion_values
    )
    if converter and not reference_conversion_pass:
        decision = REWORK_REQUIRED
    else:
        decision = PINNED_TOOLCHAIN_UNRESOLVED
    return {
        "experiment": EXPERIMENT_VERSION,
        "baseline": BASELINE_SHA,
        "provider_inference_calls": 0,
        "endpoint_metadata_calls": 2,
        "worker_program_calls": 0,
        "historical_provenance": historical_provenance(),
        "current_endpoint_observation": current_endpoint_observation(),
        "converter_audit": converter_result,
        "schemas": {
            name: {
                "sha256": sha256_bytes(canonical_json(schema).encode()),
                "metrics": _schema_metrics(schema),
            }
            for name, schema in schemas.items()
        },
        "gold_representability": gold_representability(v2r_schema),
        "validation_matrix": validation_matrix(v2r_schema),
        "canonical_runtime_only_invariants": sorted(RUNTIME_ONLY_INVARIANTS),
        "historical_lq0_converter_provenance": "UNRESOLVED",
        "future_target_converter_pinned": False,
        "reference_converter_conversion": "PASS" if reference_conversion_pass else "NOT_EVALUABLE",
        "adapter_justified": "NONE",
        "decision": decision,
    }


def write_outputs(output_dir: Path, converter: Path | None = None) -> dict[str, Any]:
    """Write deterministic BR2 evidence artifacts."""
    audit = build_audit(converter)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "provenance.json").write_text(
        json.dumps(
            {
                "experiment": EXPERIMENT_VERSION,
                "baseline": BASELINE_SHA,
                "historical": audit["historical_provenance"],
                "current_endpoint": audit["current_endpoint_observation"],
                "provider_inference_calls": 0,
                "endpoint_metadata_calls": 2,
                "worker_program_calls": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "converter_audit.json").write_text(
        json.dumps(audit["converter_audit"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "grammar_metadata.json").write_text(
        json.dumps(
            {
                "schemas": audit["schemas"],
                "gold_representability": audit["gold_representability"],
                "reference_converter_conversion": audit["reference_converter_conversion"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "validation_matrix.json").write_text(
        json.dumps(audit["validation_matrix"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "result.json").write_text(
        json.dumps(
            {
                "experiment": audit["experiment"],
                "baseline": audit["baseline"],
                "decision": audit["decision"],
                "adapter_justified": audit["adapter_justified"],
                "historical_lq0_converter_provenance": audit["historical_lq0_converter_provenance"],
                "future_target_converter_pinned": audit["future_target_converter_pinned"],
                "reference_converter_conversion": audit["reference_converter_conversion"],
                "gold_representability": audit["gold_representability"],
                "provider_inference_calls": audit["provider_inference_calls"],
                "endpoint_metadata_calls": audit["endpoint_metadata_calls"],
                "worker_program_calls": audit["worker_program_calls"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return audit


def main() -> None:
    """Generate BR2 evidence without contacting a provider."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--converter", type=Path)
    args = parser.parse_args()
    audit = write_outputs(args.output_dir, args.converter)
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
