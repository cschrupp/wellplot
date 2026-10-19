"""DECOMPOSER-PILOT-01 runner — exactly six constrained greedy generations."""

from __future__ import annotations

import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import xgrammar as xgr
from transformers import AutoModelForCausalLM, AutoTokenizer

from nlp_gate_modernbert.decomposer_pilot import inference_pins
from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.decomposer_pilot import workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import (
    AUTH,
    AUTHORITY_REMOTE_HEAD,
    EXPECTED_INFERENCE_CONFIG_SHA256,
    HIGH_LEVEL_CALLS_AUTHORIZED,
    INVOCATION_ORDER,
    SLICE,
    STARTING_TIP,
)
from nlp_gate_modernbert.decomposer_pilot.pilot_01.layer2 import (
    compute_layer2,
    mechanical_decision,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.adapter import (
    compile_accepted_constraint_path,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.case_hashes import (
    freeze_six_case_hashes,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.constants import (
    REQUIRED_XGRAMMAR,
    WELL_EBNF1_SHA256,
    XGRAMMAR_NATIVE_GRAMMAR_SHA256,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.identity import (
    verify_identities,
)
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_frozen
from nlp_gate_modernbert.nl_program_eval.freeze import FreezeFailure, freeze_candidate
from nlp_gate_modernbert.nl_program_eval.input import build_decomposer_input
from nlp_gate_modernbert.paths import EVIDENCE_DIR

HIGH_LEVEL_MODEL_CALLS = 0


class PreRunStop(RuntimeError):
    """Frozen pre-run gate failed — zero model inference."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _seed_all() -> None:
    seed = inference_pins.SEED
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def pre_run_gates() -> dict[str, Any]:
    """Mechanically reverify all frozen identities before any weight load."""
    errors: list[str] = []

    # Inference runtime must match accepted preflight hash exactly.
    inf_sha = inference_pins.inference_config_sha256()
    if inf_sha != EXPECTED_INFERENCE_CONFIG_SHA256:
        raise PreRunStop(
            f"inference_config_sha256 mismatch: got {inf_sha} "
            f"expected {EXPECTED_INFERENCE_CONFIG_SHA256}"
        )
    runtime = inference_pins.inference_config_dict()["runtime"]
    if runtime.get("device") != "cpu" or runtime.get("dtype") != "float32":
        raise PreRunStop(f"runtime_device_dtype_mismatch:{runtime}")
    if runtime.get("torch_version") != "2.14.1+cpu":
        raise PreRunStop(f"torch_version_mismatch:{runtime.get('torch_version')}")
    if runtime.get("cuda_available") is not False:
        raise PreRunStop("cuda_must_be_unavailable_for_this_frozen_run")

    identity = verify_identities()
    grammar_bytes = identity.pop("grammar_bytes")
    well_text = grammar_bytes.decode("utf-8")
    snapshot = identity["model_provenance"]["snapshot_path"]

    import importlib.metadata as md

    if md.version("xgrammar") != REQUIRED_XGRAMMAR:
        errors.append("xgrammar_version")

    # Six-case hashes must match frozen preflight evidence.
    tok = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    recomputed = freeze_six_case_hashes(tok)
    if not recomputed["pass"]:
        raise PreRunStop(f"case_hash_recompute_failed:{recomputed}")

    frozen_path = (
        EVIDENCE_DIR
        / "decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json"
    )
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    for a, b in zip(recomputed["cases"], frozen["cases"], strict=True):
        for key in (
            "case_id",
            "decomposer_input_sha256",
            "utterance_sha256",
            "workspace_sha256",
            "rendered_model_input_sha256",
            "constraint_sha256",
            "inference_config_sha256",
        ):
            if a[key] != b[key]:
                errors.append(f"case_hash_mismatch:{a['case_id']}:{key}")

    if [c["case_id"] for c in recomputed["cases"]] != list(INVOCATION_ORDER):
        errors.append("invocation_order")

    if errors:
        raise PreRunStop(";".join(errors))

    path = compile_accepted_constraint_path(well_text, snapshot)
    if path.lowered_sha256 != XGRAMMAR_NATIVE_GRAMMAR_SHA256:
        raise PreRunStop("native_grammar_sha")

    return {
        "identity": {
            k: v
            for k, v in identity.items()
            if k not in ("grammar_bytes", "full_model_provenance")
        },
        "snapshot": snapshot,
        "well_text": well_text,
        "constraint_path": path,
        "tokenizer": tok,
        "case_hashes": recomputed,
        "inference_config_sha256": inf_sha,
        "inference_config": inference_pins.inference_config_dict(),
    }


def _authorized_stop_ids(compiled: Any) -> set[int]:
    matcher = xgr.GrammarMatcher(compiled)
    return {int(s) for s in matcher.stop_token_ids}


def _strip_trailing_stops(token_ids: list[int], stop_ids: set[int]) -> list[int]:
    out = list(token_ids)
    while out and out[-1] in stop_ids:
        out.pop()
    return out


def _decode_payload(tokenizer: Any, token_ids: list[int]) -> bytes:
    text = tokenizer.decode(
        token_ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )
    return text.encode("utf-8")


def run_one_case(
    *,
    case_id: str,
    call_index: int,
    model: Any,
    tokenizer: Any,
    compiled: Any,
    stop_ids: set[int],
    expected_case_row: dict[str, Any],
    device: torch.device,
) -> dict[str, Any]:
    global HIGH_LEVEL_MODEL_CALLS

    di = build_decomposer_input(case_id)
    ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
    utterance = di.utterance
    rendered = prompt_contract.render_chat_template_text(
        tokenizer, utterance=utterance, workspace_json=ws_json
    )

    # Recompute and match frozen hashes before the call.
    row_check = {
        "decomposer_input_sha256": _sha256_text(
            json.dumps(
                {
                    "utterance": utterance,
                    "projected_workspace_json": ws_json,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        ),
        "utterance_sha256": _sha256_text(utterance),
        "workspace_sha256": _sha256_text(ws_json),
        "rendered_model_input_sha256": _sha256_text(rendered),
        "constraint_sha256": XGRAMMAR_NATIVE_GRAMMAR_SHA256,
        "inference_config_sha256": EXPECTED_INFERENCE_CONFIG_SHA256,
    }
    for k, v in row_check.items():
        if v != expected_case_row[k]:
            return {
                "case_id": case_id,
                "call_index": call_index,
                "status": "PRE_CALL_HASH_MISMATCH",
                "detail": f"{k}:got={v}:expected={expected_case_row[k]}",
                "high_level_model_call_consumed": False,
            }

    if case_id in rendered or "fixture_id" in rendered:
        return {
            "case_id": case_id,
            "call_index": call_index,
            "status": "CONTAMINATION",
            "high_level_model_call_consumed": False,
        }

    enc = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"].to(device)
    attention_mask = enc.get("attention_mask")
    if attention_mask is not None:
        attention_mask = attention_mask.to(device)

    logits_processor = xgr.contrib.hf.LogitsProcessor(compiled)

    t0 = time.perf_counter()
    HIGH_LEVEL_MODEL_CALLS += 1
    try:
        with torch.inference_mode():
            gen_kwargs: dict[str, Any] = {
                "input_ids": input_ids,
                "max_new_tokens": inference_pins.MAX_NEW_TOKENS,
                "do_sample": False,
                "logits_processor": [logits_processor],
            }
            if attention_mask is not None:
                gen_kwargs["attention_mask"] = attention_mask
            if tokenizer.pad_token_id is not None:
                gen_kwargs["pad_token_id"] = tokenizer.pad_token_id
            elif tokenizer.eos_token_id is not None:
                gen_kwargs["pad_token_id"] = tokenizer.eos_token_id
            outputs = model.generate(**gen_kwargs)
    except Exception as exc:  # noqa: BLE001
        latency = time.perf_counter() - t0
        return {
            "case_id": case_id,
            "call_index": call_index,
            "status": "DECOMPOSITION_DECODE_FAILURE",
            "failure_labels": ["DECOMPOSITION_DECODE_FAILURE"],
            "error": f"{type(exc).__name__}:{exc}",
            "latency_seconds": latency,
            "high_level_model_calls": HIGH_LEVEL_MODEL_CALLS,
            "input_hashes": row_check,
            "semantically_equivalent": False,
            "freeze_status": "NOT_FROZEN",
            "reached_freeze": False,
        }

    latency = time.perf_counter() - t0
    full_ids = outputs[0].tolist()
    prompt_len = int(input_ids.shape[-1])
    generated_ids = full_ids[prompt_len:]
    payload_ids = _strip_trailing_stops(generated_ids, stop_ids)
    payload_bytes = _decode_payload(tokenizer, payload_ids)
    payload_sha = _sha256_bytes(payload_bytes)

    # Freeze before oracle.
    frozen = freeze_candidate(payload_bytes)
    if isinstance(frozen, FreezeFailure):
        return {
            "case_id": case_id,
            "call_index": call_index,
            "status": frozen.failure,
            "failure_labels": [frozen.failure],
            "freeze_status": frozen.failure,
            "freeze_detail": frozen.detail,
            "reached_freeze": False,
            "semantically_equivalent": False,
            "latency_seconds": latency,
            "high_level_model_calls": HIGH_LEVEL_MODEL_CALLS,
            "input_hashes": row_check,
            "generated_token_ids": generated_ids,
            "payload_token_ids": payload_ids,
            "raw_output_utf8": payload_bytes.decode("utf-8", errors="replace"),
            "raw_output_sha256": payload_sha,
            "n_generated_tokens": len(generated_ids),
            "n_payload_tokens": len(payload_ids),
        }

    # Evaluate only after freeze (oracle unlocked by FrozenCandidate).
    ev = evaluate_frozen(
        frozen,
        case_id=case_id,
        decomposer_input_keys=["utterance", "projected_workspace"],
    )
    return {
        "case_id": case_id,
        "call_index": call_index,
        "status": "EVALUATED",
        "reached_freeze": True,
        "freeze_status": ev.freeze_status,
        "candidate_digest": ev.candidate_digest,
        "canonicalization_version": ev.canonicalization_version,
        "semantically_equivalent": ev.semantically_equivalent,
        "failure_labels": list(ev.failure_labels),
        "schema_valid": ev.schema_valid,
        "runtime_gate": ev.runtime_gate,
        "q3_comparison": ev.q3_comparison,
        "diagnostics": list(ev.diagnostics),
        "oracle_access_before_freeze": ev.oracle_access_before_freeze,
        "latency_seconds": latency,
        "high_level_model_calls": HIGH_LEVEL_MODEL_CALLS,
        "input_hashes": row_check,
        "generated_token_ids": generated_ids,
        "payload_token_ids": payload_ids,
        "raw_output_utf8": payload_bytes.decode("utf-8"),
        "raw_output_sha256": payload_sha,
        "n_generated_tokens": len(generated_ids),
        "n_payload_tokens": len(payload_ids),
        "termination": {
            "ended_with_stop_stripped": len(generated_ids) != len(payload_ids),
            "stop_ids": sorted(stop_ids),
        },
    }


def run_pilot_01(*, evidence_dir: Path | None = None) -> dict[str, Any]:
    global HIGH_LEVEL_MODEL_CALLS
    HIGH_LEVEL_MODEL_CALLS = 0
    evidence = evidence_dir or EVIDENCE_DIR
    evidence.mkdir(parents=True, exist_ok=True)

    # --- Pre-run (zero inference) ---
    try:
        prep = pre_run_gates()
    except PreRunStop as exc:
        report = {
            "authority": AUTH,
            "slice": SLICE,
            "result": "PRE_RUN_STOP",
            "decision": "INCONCLUSIVE",
            "error": str(exc),
            "high_level_model_calls": 0,
            "model_weights_loaded": False,
            "starting_tip": STARTING_TIP,
            "authority_remote_head": AUTHORITY_REMOTE_HEAD,
            "candidate_sha": "(pending commit)",
            "tip_sha": "(pending SHA-record commit)",
        }
        _write_json(evidence / "decomposer_pilot_01_summary.json", report)
        (evidence / "decomposer_pilot_01.md").write_text(
            f"# DECOMPOSER-PILOT-01 — PRE-RUN STOP\n\n{exc}\n",
            encoding="utf-8",
        )
        return report

    snapshot = prep["snapshot"]
    path = prep["constraint_path"]
    tokenizer = prep["tokenizer"]
    case_by_id = {c["case_id"]: c for c in prep["case_hashes"]["cases"]}
    stop_ids = _authorized_stop_ids(path.compiled)

    # --- Load model once ---
    _seed_all()
    device = torch.device("cpu")
    t_load0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        torch_dtype=torch.float32,
    )
    model.to(device)
    model.eval()
    load_seconds = time.perf_counter() - t_load0
    model_weights_loaded = True

    results: list[dict[str, Any]] = []
    for i, case_id in enumerate(INVOCATION_ORDER, start=1):
        if HIGH_LEVEL_MODEL_CALLS >= HIGH_LEVEL_CALLS_AUTHORIZED and i <= 6:
            # Should not happen mid-loop before call; safety stop.
            break
        row = run_one_case(
            case_id=case_id,
            call_index=i,
            model=model,
            tokenizer=tokenizer,
            compiled=path.compiled,
            stop_ids=stop_ids,
            expected_case_row=case_by_id[case_id],
            device=device,
        )
        results.append(row)
        if HIGH_LEVEL_MODEL_CALLS > HIGH_LEVEL_CALLS_AUTHORIZED:
            break

    # --- Summary ---
    reached_freeze = sum(1 for r in results if r.get("reached_freeze"))
    decode_failures = sum(
        1
        for r in results
        if "DECOMPOSITION_DECODE_FAILURE" in (r.get("failure_labels") or [])
        or r.get("status") == "DECOMPOSITION_DECODE_FAILURE"
    )
    schema_invalid = sum(
        1
        for r in results
        if "DECOMPOSITION_SCHEMA_INVALID" in (r.get("failure_labels") or [])
    )
    equivalent = sum(1 for r in results if r.get("semantically_equivalent") is True)

    layer2 = compute_layer2(results)
    decision = mechanical_decision(
        layer0_reached_freeze=reached_freeze,
        layer1_equivalent=equivalent,
        layer2=layer2,
    )

    run_manifest = {
        "authority": AUTH,
        "slice": SLICE,
        "starting_tip": STARTING_TIP,
        "authority_remote_head": AUTHORITY_REMOTE_HEAD,
        "MODEL": prep["identity"]["model_provenance"],
        "CONSTRAINT": {
            "backend": "xgrammar",
            "backend_version": REQUIRED_XGRAMMAR,
            "well_ebnf1_sha256": WELL_EBNF1_SHA256,
            "xgrammar_native_grammar_sha256": XGRAMMAR_NATIVE_GRAMMAR_SHA256,
            "adapter_id": "pilot_xgrammar_transformers_hard_mask.v1",
        },
        "PROMPT": {
            "system_prompt_sha256": prompt_contract.system_prompt_sha256(),
            "user_template_sha256": prompt_contract.user_template_sha256(),
            "regime": "zero-shot",
        },
        "WORKSPACE_SERIALIZATION": workspace_serialize.serializer_spec(),
        "INFERENCE": {
            **prep["inference_config"],
            "inference_config_sha256": prep["inference_config_sha256"],
        },
        "invocation_order": list(INVOCATION_ORDER),
        "high_level_model_calls": HIGH_LEVEL_MODEL_CALLS,
        "model_loads": 1,
        "model_weights_loaded": model_weights_loaded,
        "model_load_seconds": load_seconds,
        "case_hashes": prep["case_hashes"]["cases"],
    }

    summary = {
        "authority": AUTH,
        "slice": SLICE,
        "starting_tip": STARTING_TIP,
        "authority_remote_head": AUTHORITY_REMOTE_HEAD,
        "candidate_sha": "(pending commit)",
        "tip_sha": "(pending SHA-record commit)",
        "high_level_model_calls": HIGH_LEVEL_MODEL_CALLS,
        "high_level_model_calls_authorized": HIGH_LEVEL_CALLS_AUTHORIZED,
        "model_weights_loaded": model_weights_loaded,
        "model_loads": 1,
        "model_load_seconds": load_seconds,
        "layer0": {
            "reached_freeze": reached_freeze,
            "n": 6,
            "decode_failures": decode_failures,
            "schema_invalid_failures": schema_invalid,
        },
        "layer1": {
            "semantically_equivalent": equivalent,
            "n": 6,
        },
        "layer2": layer2,
        "decision": decision,
        "case_order": list(INVOCATION_ORDER),
        "per_case_status": [
            {
                "case_id": r["case_id"],
                "reached_freeze": bool(r.get("reached_freeze")),
                "semantically_equivalent": r.get("semantically_equivalent"),
                "failure_labels": r.get("failure_labels") or [],
                "latency_seconds": r.get("latency_seconds"),
            }
            for r in results
        ],
        "terminal_state": "RUN_COMPLETE_AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW",
    }

    # Persist artifacts
    _write_json(evidence / "decomposer_pilot_01_run_manifest.json", run_manifest)
    with (evidence / "decomposer_pilot_01_results.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    _write_json(evidence / "decomposer_pilot_01_summary.json", summary)

    md = f"""# DECOMPOSER-PILOT-01 — Run closeout

```
SLICE:
{SLICE}

AUTHORITY:
{AUTH}

STARTING TIP:
{STARTING_TIP}

AUTHORITY REMOTE HEAD:
{AUTHORITY_REMOTE_HEAD}

CANDIDATE SHA:
(pending commit)

TIP:
(pending SHA-record commit)

HIGH-LEVEL MODEL CALLS:
{HIGH_LEVEL_MODEL_CALLS} / {HIGH_LEVEL_CALLS_AUTHORIZED}

MODEL LOADS:
1

DECISION:
{decision}
```

## Layer 0 / 1 / 2

| Layer | Result |
|-------|--------|
| 0 reached_freeze | {reached_freeze}/6 |
| 0 decode failures | {decode_failures} |
| 0 schema-invalid | {schema_invalid} |
| 1 semantically_equivalent | {equivalent}/6 |
| 2 veto A | {layer2['veto_a']} {layer2['veto_a_mechanisms']} |
| 2 veto B | {layer2['veto_b']} {layer2['veto_b_mechanisms']} |

## Per-case

| Case | Freeze | Equivalent | Labels | Latency s |
|------|--------|------------|--------|-----------|
"""
    for r in results:
        md += (
            f"| {r['case_id']} | {r.get('freeze_status')} | "
            f"{r.get('semantically_equivalent')} | "
            f"{','.join(r.get('failure_labels') or []) or '-'} | "
            f"{r.get('latency_seconds')} |\n"
        )
    md += """
## Terminal state

```
RUN_COMPLETE_AWAITING_INDEPENDENT_SCIENTIFIC_REVIEW
```

STATUS:
STOP FOR INDEPENDENT SCIENTIFIC DECOMPOSER-PILOT-01 REVIEW
"""
    (evidence / "decomposer_pilot_01.md").write_text(md, encoding="utf-8")

    # Free model memory hint
    del model
    return summary


def main() -> None:
    summary = run_pilot_01()
    print(
        json.dumps(
            {
                "decision": summary.get("decision"),
                "high_level_model_calls": summary.get("high_level_model_calls"),
                "layer0": summary.get("layer0"),
                "layer1": summary.get("layer1"),
                "result": summary.get("result") or summary.get("decision"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
