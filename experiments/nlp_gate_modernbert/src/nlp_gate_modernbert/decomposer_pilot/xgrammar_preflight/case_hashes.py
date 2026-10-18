"""P6: mechanical six-case pre-inference hash freeze (no model; hashes only)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from nlp_gate_modernbert.decomposer_pilot import inference_pins
from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.decomposer_pilot import workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.constants import (
    INVOCATION_ORDER,
    XGRAMMAR_NATIVE_GRAMMAR_SHA256,
)
from nlp_gate_modernbert.nl_program_eval.input import (
    FORBIDDEN_DECOMPOSER_KEYS,
    assert_decomposer_payload_clean,
    build_decomposer_input,
)

# Field/token leaks that must not appear in rendered model input.
# Do not ban the word "oracle" — the frozen system prompt mentions it negatively.
_FORBIDDEN_FIELD_LEAKS = (
    "fixture_id",
    "expected_terminal",
    "oracle_witness_id",
    "coverage_atom",
    "gold_operation",
    "normalized_program",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _decomposer_input_sha256(utterance: str, workspace_json: str) -> str:
    payload = {
        "utterance": utterance,
        "projected_workspace_json": workspace_json,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_text(blob)


def _contamination_hits(rendered: str, *, case_id: str) -> list[str]:
    hits: list[str] = []
    # No sealed-six case id may appear in model input (including other cases).
    for other in INVOCATION_ORDER:
        if other in rendered:
            hits.append(other)
    for field in _FORBIDDEN_FIELD_LEAKS:
        if field in rendered:
            hits.append(field)
    # Explicit current case_id check (also covered above).
    if case_id in rendered and case_id not in hits:
        hits.append(case_id)
    return hits


def freeze_six_case_hashes(tokenizer: Any) -> dict[str, Any]:
    """Build per-case pre-inference hashes in frozen invocation order."""
    inf_sha = inference_pins.inference_config_sha256()
    constraint_sha = XGRAMMAR_NATIVE_GRAMMAR_SHA256
    prompt_sys = prompt_contract.system_prompt_sha256()
    prompt_usr = prompt_contract.user_template_sha256()
    ser_sha = workspace_serialize.serializer_source_sha256()

    cases: list[dict[str, Any]] = []
    contamination_failures: list[dict[str, Any]] = []
    shared_prompt_ok = True
    shared_constraint_ok = True
    shared_serializer_ok = True
    shared_inference_ok = True

    for case_id in INVOCATION_ORDER:
        di = build_decomposer_input(case_id)
        payload = di.to_payload()
        # Model-facing top-level keys only; fixture_id may exist on the harness
        # ProjectedWorkspace object but must be stripped by the serializer.
        assert_decomposer_payload_clean(payload)
        assert set(payload.keys()) <= {"utterance", "projected_workspace"}

        ws_json = workspace_serialize.serialize_projected_workspace(
            di.projected_workspace
        )
        if "fixture_id" in ws_json:
            raise RuntimeError(f"fixture_id_leaked_into_workspace_json:{case_id}")
        leaked = FORBIDDEN_DECOMPOSER_KEYS.intersection(
            set(json.loads(ws_json).keys()) if ws_json.startswith("{") else set()
        )
        if leaked:
            raise RuntimeError(f"workspace_json_forbidden_keys:{case_id}:{sorted(leaked)}")

        utterance = di.utterance
        rendered = prompt_contract.render_chat_template_text(
            tokenizer, utterance=utterance, workspace_json=ws_json
        )
        hits = _contamination_hits(rendered, case_id=case_id)
        if hits:
            contamination_failures.append({"case_id": case_id, "hits": hits})

        row = {
            "case_id": case_id,  # harness-side only in this evidence record
            "decomposer_input_sha256": _decomposer_input_sha256(utterance, ws_json),
            "utterance_sha256": _sha256_text(utterance),
            "workspace_sha256": _sha256_text(ws_json),
            "rendered_model_input_sha256": _sha256_text(rendered),
            "constraint_sha256": constraint_sha,
            "inference_config_sha256": inf_sha,
            "prompt_system_sha256": prompt_sys,
            "prompt_user_template_sha256": prompt_usr,
            "serializer_implementation_sha256": ser_sha,
            "model_input_keys": ["utterance", "projected_workspace"],
            "case_id_in_model_input": False,
        }
        cases.append(row)

        if row["prompt_system_sha256"] != prompt_sys or row["prompt_user_template_sha256"] != prompt_usr:
            shared_prompt_ok = False
        if row["constraint_sha256"] != constraint_sha:
            shared_constraint_ok = False
        if row["serializer_implementation_sha256"] != ser_sha:
            shared_serializer_ok = False
        if row["inference_config_sha256"] != inf_sha:
            shared_inference_ok = False

    order_ok = [c["case_id"] for c in cases] == list(INVOCATION_ORDER)
    # Cross-case: all share identical prompt/constraint/serializer/inference hashes
    shared = (
        shared_prompt_ok
        and shared_constraint_ok
        and shared_serializer_ok
        and shared_inference_ok
        and len({c["constraint_sha256"] for c in cases}) == 1
        and len({c["inference_config_sha256"] for c in cases}) == 1
        and len({c["prompt_system_sha256"] for c in cases}) == 1
        and len({c["serializer_implementation_sha256"] for c in cases}) == 1
    )

    passed = order_ok and shared and not contamination_failures and len(cases) == 6
    return {
        "pass": passed,
        "invocation_order": list(INVOCATION_ORDER),
        "order_match": order_ok,
        "identical_prompt_constraint_serializer_inference": shared,
        "contamination_failures": contamination_failures,
        "persist_raw_utterance_or_workspace": False,
        "cases": cases,
    }
