"""P2: field-level Q6 MODEL/CONSTRAINT/PROMPT/WORKSPACE/INFERENCE completeness."""

from __future__ import annotations

from typing import Any

from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.constants import (
    AGGREGATE_WEIGHT_MANIFEST_SHA256,
    CONFIG_SHA256,
    EXPECTED_WEIGHT_MANIFEST,
    REQUIRED_XGRAMMAR,
    TOKENIZER_ARTIFACT_SHA256,
    WELL_EBNF1_SHA256,
    XGRAMMAR_NATIVE_GRAMMAR_SHA256,
)

# Frozen Q6 MODEL fields required before any future inference.
REQUIRED_MODEL_FIELDS = (
    "model_id",
    "variant",
    "source",
    "snapshot_path",
    "snapshot_revision",
    "config_sha256",
    "tokenizer_artifact_sha256",
    "weight_file_manifest",
    "aggregate_weight_manifest_sha256",
    "adapters",
    "auto_download",
    "fallback_model",
)


def build_q6_model_section(full_provenance: dict[str, Any]) -> dict[str, Any]:
    """Preserve full collect_model_provenance fields plus preflight attestations."""
    tok = full_provenance.get("tokenizer_artifact_sha256") or {}
    return {
        "model_id": full_provenance.get("model_id"),
        "variant": full_provenance.get("variant"),
        "source": full_provenance.get("source"),
        "snapshot_path": full_provenance.get("snapshot_path"),
        "snapshot_revision": full_provenance.get("snapshot_revision"),
        "config_sha256": full_provenance.get("config_sha256"),
        "tokenizer_artifact_sha256": {
            "tokenizer.json": tok.get("tokenizer.json"),
            "tokenizer_config.json": tok.get("tokenizer_config.json"),
            "merges.txt": tok.get("merges.txt"),
            "vocab.json": tok.get("vocab.json"),
        },
        "weight_file_manifest": full_provenance.get("weight_file_manifest"),
        "aggregate_weight_manifest_sha256": full_provenance.get(
            "aggregate_weight_manifest_sha256"
        ),
        "adapters": full_provenance.get("adapters", "NONE"),
        "auto_download": bool(full_provenance.get("auto_download", False)),
        "fallback_model": full_provenance.get("fallback_model", "NONE"),
        "weights_deserialized_as_tensors": False,
        "auto_model_invoked": False,
    }


def validate_q6_run_manifest(run_manifest: dict[str, Any]) -> dict[str, Any]:
    """Mechanically validate required Q6 sections and frozen MODEL field values."""
    errors: list[str] = []
    for section in (
        "MODEL",
        "CONSTRAINT",
        "PROMPT",
        "WORKSPACE_SERIALIZATION",
        "INFERENCE",
    ):
        if section not in run_manifest:
            errors.append(f"missing_section:{section}")

    model = run_manifest.get("MODEL") or {}
    for field in REQUIRED_MODEL_FIELDS:
        if field not in model or model[field] is None:
            errors.append(f"model_missing:{field}")

    if model.get("model_id") != "Qwen/Qwen3-1.7B":
        errors.append(f"model_id:{model.get('model_id')}")
    if model.get("adapters") != "NONE":
        errors.append(f"adapters:{model.get('adapters')}")
    if model.get("auto_download") is not False:
        errors.append(f"auto_download:{model.get('auto_download')}")
    if model.get("fallback_model") != "NONE":
        errors.append(f"fallback_model:{model.get('fallback_model')}")
    if model.get("snapshot_revision") != "master":
        errors.append(f"snapshot_revision:{model.get('snapshot_revision')}")
    if model.get("config_sha256") != CONFIG_SHA256:
        errors.append("config_sha256_mismatch")
    if model.get("aggregate_weight_manifest_sha256") != AGGREGATE_WEIGHT_MANIFEST_SHA256:
        errors.append("aggregate_weight_manifest_mismatch")

    tok = model.get("tokenizer_artifact_sha256") or {}
    for name, expected in TOKENIZER_ARTIFACT_SHA256.items():
        if tok.get(name) != expected:
            errors.append(f"tokenizer_artifact:{name}")

    by_path = {w["path"]: w for w in (model.get("weight_file_manifest") or [])}
    for expected in EXPECTED_WEIGHT_MANIFEST:
        got = by_path.get(expected["path"])
        if got is None:
            errors.append(f"weight_missing:{expected['path']}")
        else:
            if got.get("sha256") != expected["sha256"]:
                errors.append(f"weight_sha:{expected['path']}")
            if int(got.get("size_bytes", -1)) != int(expected["size_bytes"]):
                errors.append(f"weight_size:{expected['path']}")

    constraint = run_manifest.get("CONSTRAINT") or {}
    if constraint.get("backend") != "xgrammar":
        errors.append("constraint_backend")
    if constraint.get("backend_version") != REQUIRED_XGRAMMAR:
        errors.append("constraint_backend_version")
    if constraint.get("well_ebnf1_sha256") != WELL_EBNF1_SHA256:
        errors.append("constraint_grammar_sha")
    if constraint.get("xgrammar_native_grammar_sha256") != XGRAMMAR_NATIVE_GRAMMAR_SHA256:
        errors.append("constraint_native_sha")

    prompt = run_manifest.get("PROMPT") or {}
    for key in ("system_prompt_sha256", "user_template_sha256", "regime"):
        if key not in prompt:
            errors.append(f"prompt_missing:{key}")
    if prompt.get("regime") != "zero-shot":
        errors.append("prompt_regime")

    ser = run_manifest.get("WORKSPACE_SERIALIZATION") or {}
    if "implementation_sha256" not in ser:
        errors.append("serializer_missing_implementation_sha256")

    inf = run_manifest.get("INFERENCE") or {}
    for key in (
        "temperature",
        "do_sample",
        "thinking_enabled",
        "max_new_tokens",
        "seed",
        "inference_config_sha256",
    ):
        if key not in inf:
            errors.append(f"inference_missing:{key}")
    if inf.get("temperature") != 0 and inf.get("temperature") != 0.0:
        errors.append("inference_temperature")
    if inf.get("do_sample") is not False:
        errors.append("inference_do_sample")
    if inf.get("thinking_enabled") is not False:
        errors.append("inference_thinking")
    if inf.get("max_new_tokens") != 1024:
        errors.append("inference_max_new_tokens")
    if inf.get("seed") != 20261016:
        errors.append("inference_seed")

    return {
        "pass": not errors,
        "errors": errors,
        "required_model_fields": list(REQUIRED_MODEL_FIELDS),
        "checked_sections": [
            "MODEL",
            "CONSTRAINT",
            "PROMPT",
            "WORKSPACE_SERIALIZATION",
            "INFERENCE",
        ],
    }
