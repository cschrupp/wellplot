"""P1 immutable identity verification (fail closed)."""

from __future__ import annotations

from typing import Any

from nlp_gate_modernbert.decomposer_pilot import model_provenance
from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.decomposer_pilot import workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
    LOWERER_ID,
    lowerer_source_sha256,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import (
    load_accepted_grammar,
    verify_pinned_tokenizer,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.constants import (
    AGGREGATE_WEIGHT_MANIFEST_SHA256,
    CONFIG_SHA256,
    EXPECTED_WEIGHT_MANIFEST,
    LOWERER_ID as EXPECTED_LOWERER_ID,
    LOWERER_SOURCE_SHA256,
    REQUIRED_XGRAMMAR,
    SERIALIZER_IMPLEMENTATION_SHA256,
    SYSTEM_PROMPT_SHA256,
    TOKENIZER_ARTIFACT_SHA256,
    USER_TEMPLATE_SHA256,
    WELL_EBNF1_SHA256,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.manifest_q6 import (
    build_q6_model_section,
)
from nlp_gate_modernbert.paths import REPO_ROOT


class IdentityMismatchError(RuntimeError):
    """Frozen identity mismatch — PREFLIGHT FAIL."""


def verify_identities() -> dict[str, Any]:
    errors: list[str] = []

    grammar_bytes, grammar_sha = load_accepted_grammar(REPO_ROOT)
    if grammar_sha != WELL_EBNF1_SHA256:
        errors.append(f"grammar_sha:{grammar_sha}")

    if LOWERER_ID != EXPECTED_LOWERER_ID:
        errors.append(f"lowerer_id:{LOWERER_ID}")
    low_sha = lowerer_source_sha256()
    if low_sha != LOWERER_SOURCE_SHA256:
        errors.append(f"lowerer_source_sha:{low_sha}")

    import importlib.metadata as md

    xg_ver = md.version("xgrammar")
    if xg_ver != REQUIRED_XGRAMMAR:
        errors.append(f"xgrammar_version:{xg_ver}")

    tok = verify_pinned_tokenizer()
    for name, expected in TOKENIZER_ARTIFACT_SHA256.items():
        got = tok["artifact_sha256"].get(name)
        if got != expected:
            errors.append(f"tokenizer:{name}:{got}")

    if prompt_contract.system_prompt_sha256() != SYSTEM_PROMPT_SHA256:
        errors.append("system_prompt_sha")
    if prompt_contract.user_template_sha256() != USER_TEMPLATE_SHA256:
        errors.append("user_template_sha")
    if workspace_serialize.serializer_source_sha256() != SERIALIZER_IMPLEMENTATION_SHA256:
        errors.append("serializer_sha")

    # Full provenance — do not discard Q6 MODEL fields.
    prov = model_provenance.collect_model_provenance()
    if prov.get("config_sha256") != CONFIG_SHA256:
        errors.append(f"config_sha:{prov.get('config_sha256')}")
    if prov.get("aggregate_weight_manifest_sha256") != AGGREGATE_WEIGHT_MANIFEST_SHA256:
        errors.append(
            f"aggregate_weight_manifest:{prov.get('aggregate_weight_manifest_sha256')}"
        )

    by_path = {w["path"]: w for w in prov.get("weight_file_manifest", [])}
    for expected in EXPECTED_WEIGHT_MANIFEST:
        got = by_path.get(expected["path"])
        if got is None:
            errors.append(f"missing_weight:{expected['path']}")
            continue
        if got["sha256"] != expected["sha256"]:
            errors.append(f"weight_sha:{expected['path']}")
        if int(got["size_bytes"]) != int(expected["size_bytes"]):
            errors.append(f"weight_size:{expected['path']}")

    tok_art = prov.get("tokenizer_artifact_sha256") or {}
    for name, expected in TOKENIZER_ARTIFACT_SHA256.items():
        if tok_art.get(name) != expected:
            errors.append(f"prov_tokenizer:{name}")

    model_section = build_q6_model_section(prov)

    result = {
        "pass": not errors,
        "errors": errors,
        "grammar_sha256": grammar_sha,
        "lowerer_id": LOWERER_ID,
        "lowerer_source_sha256": low_sha,
        "xgrammar_version": xg_ver,
        "tokenizer": tok,
        "model_provenance": model_section,
        "full_model_provenance": prov,
        "prompt": {
            "system_prompt_sha256": prompt_contract.system_prompt_sha256(),
            "user_template_sha256": prompt_contract.user_template_sha256(),
        },
        "serializer_implementation_sha256": workspace_serialize.serializer_source_sha256(),
        "grammar_bytes": grammar_bytes,
    }
    if errors:
        raise IdentityMismatchError(";".join(errors))
    return result
