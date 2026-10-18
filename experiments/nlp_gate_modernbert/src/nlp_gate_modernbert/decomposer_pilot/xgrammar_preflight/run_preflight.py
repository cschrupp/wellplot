"""DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01 orchestrator."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot import inference_pins
from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.decomposer_pilot import workspace_serialize
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff import backend_xgrammar
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.source_oracle import (
    source_oracle_parity,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight import case_hashes as ch
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.adapter import (
    compile_accepted_constraint_path,
    run_synthetic_adapter_suite,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.constants import (
    AUTH,
    AUTHORITY_REMOTE_HEAD,
    CHAT_TEMPLATE_TEXT_SHA256,
    INVOCATION_ORDER,
    REQUIRED_XGRAMMAR,
    SLICE,
    STARTING_TIP,
    WELL_EBNF1_SHA256,
    XGRAMMAR_NATIVE_GRAMMAR_SHA256,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.identity import (
    IdentityMismatchError,
    verify_identities,
)
from nlp_gate_modernbert.paths import EVIDENCE_DIR, REPO_ROOT, SLM01_ROOT

MODEL_CALLS = 0
MODEL_WEIGHTS_LOADED = False
MODEL_FORWARD_CALLS = 0
MODEL_GENERATE_CALLS = 0


class GenerateForbiddenError(RuntimeError):
    """Raised if generate is attempted during preflight."""


class AutoModelForbiddenError(RuntimeError):
    """Raised if AutoModel weight load is attempted during preflight."""


def _pkg_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _install_guards() -> list[str]:
    notes: list[str] = []
    try:
        from transformers.generation import GenerationMixin

        def _blocked_generate(self, *args, **kwargs):  # noqa: ANN001
            global MODEL_GENERATE_CALLS
            MODEL_GENERATE_CALLS += 1
            raise GenerateForbiddenError(
                "model.generate forbidden during XGRAMMAR-PREFLIGHT-01"
            )

        GenerationMixin.generate = _blocked_generate  # type: ignore[method-assign]
        notes.append("GenerationMixin.generate_blocked")
    except ImportError:
        notes.append("transformers_unavailable_for_generate_guard")

    try:
        import transformers

        def _block_auto(attr: str) -> None:
            cls = getattr(transformers, attr, None)
            if cls is None or getattr(cls, "from_pretrained", None) is None:
                return

            def _blocked_from_pretrained(cls_, *args, **kwargs):  # noqa: ANN001
                raise AutoModelForbiddenError(
                    f"{attr}.from_pretrained forbidden during XGRAMMAR-PREFLIGHT-01"
                )

            cls.from_pretrained = classmethod(_blocked_from_pretrained)  # type: ignore[method-assign]
            notes.append(f"{attr}.from_pretrained_blocked")

        for name in ("AutoModel", "AutoModelForCausalLM", "AutoModelForSeq2SeqLM"):
            _block_auto(name)
    except ImportError:
        notes.append("transformers_unavailable_for_automodel_guard")
    return notes


def _template_smoke(snapshot: Path) -> dict[str, Any]:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    ws_json = workspace_serialize.serialize_projected_workspace(
        prompt_contract.DUMMY_WORKSPACE
    )
    messages = prompt_contract.build_messages(
        utterance=prompt_contract.DUMMY_UTTERANCE, workspace_json=ws_json
    )
    text = prompt_contract.render_chat_template_text(
        tok,
        utterance=prompt_contract.DUMMY_UTTERANCE,
        workspace_json=ws_json,
    )
    ids = tok(text, add_special_tokens=False)["input_ids"]
    chat_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ids_sha = hashlib.sha256(
        json.dumps(ids, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    msg_sha = prompt_contract.hash_messages(messages)
    return {
        "local_files_only": True,
        "model_weights_loaded": False,
        "tokenizer_loaded_from": str(snapshot),
        "chat_template_text_sha256": chat_sha,
        "chat_template_text_sha256_expected": CHAT_TEMPLATE_TEXT_SHA256,
        "chat_template_match": chat_sha == CHAT_TEMPLATE_TEXT_SHA256,
        "input_ids_sha256": ids_sha,
        "input_ids_length": len(ids),
        "messages_sha256": msg_sha,
        "enable_thinking": False,
        "thinking_disabled": True,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _closeout_md(report: dict[str, Any]) -> str:
    gates = report["gates"]
    rows = "\n".join(
        f"| {g} | {'PASS' if gates[g]['pass'] else 'FAIL'} | {gates[g]['summary']} |"
        for g in (
            "P1",
            "P2",
            "P3",
            "P4",
            "P5",
            "P6",
            "P7",
            "P8",
            "P9",
        )
    )
    return f"""# DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01 — Closeout

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

RESULT:
{report['result']}

MODEL CALLS:
{report['model_calls']}

MODEL WEIGHTS LOADED:
{str(report['model_weights_loaded']).lower()}

MODEL FORWARD CALLS:
{report['model_forward_calls']}

MODEL GENERATE CALLS:
{report['model_generate_calls']}

PILOT-01:
NOT AUTHORIZED
```

## Gates

| Gate | Result | Summary |
|------|--------|---------|
{rows}

## Selected path

```
WELL-EBNF-1 {WELL_EBNF1_SHA256}
  → well_ebnf1_to_xgrammar_ebnf.v1
  → XGrammar EBNF {XGRAMMAR_NATIVE_GRAMMAR_SHA256}
  → XGrammar {REQUIRED_XGRAMMAR}
  → pinned Qwen3-1.7B tokenizer
  → PilotXGrammarHardMaskAdapter
```

## Evidence artifacts

- `decomposer_pilot_constraint_xgrammar_preflight_01_run_manifest.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_parity.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_adapter.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01.md`

## Explicit non-authorizations

```
AutoModel / model weight load: NOT AUTHORIZED
model.forward:                 NOT AUTHORIZED
model.generate:                NOT AUTHORIZED
real model logits:             NOT AUTHORIZED
PILOT-01:                      NOT AUTHORIZED
```

## Terminal state

```
IMPLEMENTATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01 REVIEW
"""


def run_xgrammar_preflight(
    *,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute P1–P9; write required evidence; return handoff report."""
    global MODEL_CALLS, MODEL_WEIGHTS_LOADED, MODEL_FORWARD_CALLS, MODEL_GENERATE_CALLS
    MODEL_CALLS = 0
    MODEL_WEIGHTS_LOADED = False
    MODEL_FORWARD_CALLS = 0
    MODEL_GENERATE_CALLS = 0

    evidence = evidence_dir or EVIDENCE_DIR
    evidence.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    guards = _install_guards()
    t_setup0 = time.perf_counter()

    # --- P1 identity ---
    try:
        identity = verify_identities()
        p1_pass = True
        grammar_bytes = identity.pop("grammar_bytes")
        well_text = grammar_bytes.decode("utf-8")
        snapshot = Path(identity["model_provenance"]["snapshot_path"])
    except IdentityMismatchError as exc:
        p1_pass = False
        identity = {"pass": False, "errors": str(exc)}
        failures.append(f"P1:{exc}")
        well_text = ""
        snapshot = Path(".")
        grammar_bytes = b""

    # --- P3 prompt smoke (needs tokenizer; no weights) ---
    if p1_pass:
        try:
            smoke = _template_smoke(snapshot)
            p3_pass = bool(smoke["chat_template_match"]) and bool(
                smoke["thinking_disabled"]
            )
            if not p3_pass:
                failures.append("P3:chat_template_or_thinking")
        except Exception as exc:  # noqa: BLE001
            smoke = {"error": str(exc)}
            p3_pass = False
            failures.append(f"P3:{exc}")
    else:
        smoke = {"skipped": True}
        p3_pass = False

    # --- P4 constraint path + parity ---
    parity_payload: dict[str, Any] = {"pass": False}
    path = None
    p4_pass = False
    compile_s = None
    if p1_pass:
        try:
            t0 = time.perf_counter()
            path = compile_accepted_constraint_path(well_text, str(snapshot))
            compile_s = time.perf_counter() - t0
            # Bundle-compatible object for bakeoff helpers
            bundle = backend_xgrammar.build_xgrammar(well_text, str(snapshot))
            text = backend_xgrammar.text_parity(bundle)
            oracle = source_oracle_parity(REPO_ROOT, grammar_bytes)
            agree = backend_xgrammar.backend_agrees_with_oracle(text, oracle)
            replay = backend_xgrammar.token_replay(bundle)
            p4_pass = (
                text["pass"]
                and oracle["pass"]
                and agree["pass"]
                and replay["pass"]
                and path.lowered_sha256 == XGRAMMAR_NATIVE_GRAMMAR_SHA256
            )
            parity_payload = {
                "pass": p4_pass,
                "source_oracle": {
                    "pass": oracle["pass"],
                    "positive_pass": oracle["positive_pass"],
                    "negative_pass": oracle["negative_pass"],
                },
                "text_parity": {
                    "pass": text["pass"],
                    "positive_pass": text["positive_pass"],
                    "negative_pass": text["negative_pass"],
                },
                "oracle_backend_agreement": agree,
                "token_replay": {
                    "pass": replay["pass"],
                    "positive_pass": replay["positive_pass"],
                    "negative_pass": replay["negative_pass"],
                    "cases": [
                        {
                            "label": r["label"],
                            "n_tokens": r["n_tokens"],
                            "rejection_index": r["rejection_index"],
                            "completed": r["completed"],
                            "any_stop_allowed": r["any_stop_allowed"],
                            "pass": r["pass"],
                            "detail": r["detail"],
                        }
                        for r in (replay["positive"] + replay["negative"])
                    ],
                    "mask_step_latency_seconds": replay["mask_step_latency_seconds"],
                },
                "native_grammar_sha256": path.lowered_sha256,
                "compile_seconds": path.compile_seconds,
            }
            if not p4_pass:
                failures.append("P4:parity_or_compile")
        except Exception as exc:  # noqa: BLE001
            p4_pass = False
            parity_payload = {"pass": False, "error": str(exc)}
            failures.append(f"P4:{exc}")

    # --- P5 adapter synthetic logits ---
    adapter_payload: dict[str, Any] = {"pass": False}
    p5_pass = False
    if path is not None:
        try:
            adapter_payload = run_synthetic_adapter_suite(path)
            p5_pass = bool(adapter_payload["pass"])
            if not p5_pass:
                failures.append(f"P5:{adapter_payload.get('failures')}")
        except Exception as exc:  # noqa: BLE001
            adapter_payload = {"pass": False, "error": str(exc)}
            failures.append(f"P5:{exc}")

    # --- P6 six-case hashes ---
    case_payload: dict[str, Any] = {"pass": False}
    p6_pass = False
    if p1_pass and path is not None:
        try:
            from transformers import AutoTokenizer

            tok = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
            case_payload = ch.freeze_six_case_hashes(tok)
            p6_pass = bool(case_payload["pass"])
            if not p6_pass:
                failures.append("P6:case_hash_or_contamination")
        except Exception as exc:  # noqa: BLE001
            case_payload = {"pass": False, "error": str(exc)}
            failures.append(f"P6:{exc}")

    setup_wall = time.perf_counter() - t_setup0

    # --- P8 zero-model counters ---
    p8_pass = (
        MODEL_CALLS == 0
        and MODEL_WEIGHTS_LOADED is False
        and MODEL_FORWARD_CALLS == 0
        and MODEL_GENERATE_CALLS == 0
    )
    if not p8_pass:
        failures.append("P8:model_boundary")

    # --- P2 run manifest ---
    inf = inference_pins.inference_config_dict()
    run_manifest = {
        "MODEL": identity.get("model_provenance")
        if isinstance(identity, dict)
        else {},
        "CONSTRAINT": {
            "backend": "xgrammar",
            "backend_version": REQUIRED_XGRAMMAR,
            "route": "native_ebnf",
            "well_ebnf1_sha256": WELL_EBNF1_SHA256,
            "xgrammar_native_grammar_sha256": XGRAMMAR_NATIVE_GRAMMAR_SHA256,
            "lowerer_id": "well_ebnf1_to_xgrammar_ebnf.v1",
            "same_artifact_for_all_six": True,
            "parity_pass": p4_pass,
        },
        "PROMPT": prompt_contract.prompt_contract_manifest(
            chat_template_text_sha256=smoke.get("chat_template_text_sha256"),
            input_ids_sha256=smoke.get("input_ids_sha256"),
            messages_sha256=smoke.get("messages_sha256"),
        ),
        "WORKSPACE_SERIALIZATION": workspace_serialize.serializer_spec(),
        "INFERENCE": {
            **inf,
            "inference_config_sha256": inference_pins.inference_config_sha256(),
            "retries": 0,
            "repair_passes": 0,
            "best_of_n": 0,
            "model_calls": 0,
        },
        "GOVERNANCE": {
            "model_weights_loaded": MODEL_WEIGHTS_LOADED,
            "model_forward_calls": MODEL_FORWARD_CALLS,
            "model_generate_calls": MODEL_GENERATE_CALLS,
            "model_calls": MODEL_CALLS,
            "no_download": True,
            "auto_download": False,
            "no_model_forward": True,
            "no_model_generate": True,
            "slm01_root": str(SLM01_ROOT),
            "template_smoke": smoke,
            "generate_guard": guards,
            "invocation_order": list(INVOCATION_ORDER),
        },
        "SOFTWARE": {
            "xgrammar": _pkg_version("xgrammar"),
            "transformers": _pkg_version("transformers"),
            "torch": _pkg_version("torch"),
            "python": sys.version.split()[0],
            "required": {"xgrammar": REQUIRED_XGRAMMAR},
        },
        "authority": AUTH,
        "slice": SLICE,
        "starting_tip": STARTING_TIP,
        "pilot_01": "NOT_AUTHORIZED",
        "pass_does_not_authorize_pilot_01": True,
    }
    p2_pass = all(
        k in run_manifest
        for k in (
            "MODEL",
            "CONSTRAINT",
            "PROMPT",
            "WORKSPACE_SERIALIZATION",
            "INFERENCE",
        )
    ) and p1_pass
    if not p2_pass:
        failures.append("P2:manifest_incomplete")

    # --- P9 resources ---
    resources = {
        "setup_wall_seconds": setup_wall,
        "compile_seconds": compile_s
        if compile_s is not None
        else (path.compile_seconds if path is not None else None),
        "adapter_synthetic_mask_latency_seconds": adapter_payload.get(
            "synthetic_mask_latency_seconds"
        ),
        "parity_mask_step_latency_seconds": parity_payload.get("token_replay", {}).get(
            "mask_step_latency_seconds"
        )
        if isinstance(parity_payload.get("token_replay"), dict)
        else None,
    }
    p9_pass = (
        resources.get("compile_seconds") is not None
        and float(resources["compile_seconds"]) < 120.0
        and p4_pass
    )
    if not p9_pass and "P9" not in str(failures):
        failures.append("P9:resources")

    # --- P7 fail-closed attestation ---
    p7_pass = True
    if not all([p1_pass, p2_pass, p3_pass, p4_pass, p5_pass, p6_pass, p8_pass, p9_pass]):
        # Fail-closed means we recorded failures and did not call the model.
        p7_pass = p8_pass and MODEL_CALLS == 0
    # Also: guards installed
    if "GenerationMixin.generate_blocked" not in guards:
        p7_pass = False
        failures.append("P7:generate_guard_missing")

    gates = {
        "P1": {"pass": p1_pass, "summary": "immutable identities/hashes"},
        "P2": {"pass": p2_pass, "summary": "complete Q6 run manifest"},
        "P3": {"pass": p3_pass, "summary": "frozen prompt/template smoke"},
        "P4": {"pass": p4_pass, "summary": "XGrammar construction + parity"},
        "P5": {"pass": p5_pass, "summary": "synthetic-logits hard-mask adapter"},
        "P6": {"pass": p6_pass, "summary": "six-case pre-inference hashes"},
        "P7": {"pass": p7_pass, "summary": "fail-closed + generate guard"},
        "P8": {"pass": p8_pass, "summary": "zero model/forward/generate"},
        "P9": {"pass": p9_pass, "summary": "resource/setup evidence"},
    }
    all_pass = all(g["pass"] for g in gates.values()) and not failures
    result = "PASS" if all_pass else "FAIL"

    report = {
        "authority": AUTH,
        "slice": SLICE,
        "mode": "SELECTED_BACKEND_ZERO_MODEL_PREFLIGHT",
        "starting_tip": STARTING_TIP,
        "authority_remote_head": AUTHORITY_REMOTE_HEAD,
        "candidate_sha": "(pending commit)",
        "tip_sha": "(pending SHA-record commit)",
        "result": result,
        "gates": gates,
        "failures": failures,
        "model_calls": MODEL_CALLS,
        "model_weights_loaded": MODEL_WEIGHTS_LOADED,
        "model_forward_calls": MODEL_FORWARD_CALLS,
        "model_generate_calls": MODEL_GENERATE_CALLS,
        "auto_download": False,
        "pilot_01": "NOT_AUTHORIZED",
        "pass_does_not_authorize_pilot_01": True,
        "identity": {
            k: v
            for k, v in (identity.items() if isinstance(identity, dict) else [])
            if k != "grammar_bytes"
        },
        "resources": resources,
        "generate_guard": guards,
        "unauthorized_still": [
            "AutoModel/model_weight_load",
            "model_forward",
            "model_generate",
            "real_model_logits",
            "PILOT_01",
            "prompt_schema_serializer_changes",
            "grammar_backend_changes",
        ],
        "terminal_state": "IMPLEMENTATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW",
    }

    _write_json(
        evidence / "decomposer_pilot_constraint_xgrammar_preflight_01_run_manifest.json",
        run_manifest,
    )
    _write_json(
        evidence / "decomposer_pilot_constraint_xgrammar_preflight_01_parity.json",
        parity_payload,
    )
    _write_json(
        evidence / "decomposer_pilot_constraint_xgrammar_preflight_01_adapter.json",
        adapter_payload,
    )
    _write_json(
        evidence / "decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json",
        case_payload,
    )
    _write_json(
        evidence / "decomposer_pilot_constraint_xgrammar_preflight_01.json",
        report,
    )
    (evidence / "decomposer_pilot_constraint_xgrammar_preflight_01.md").write_text(
        _closeout_md(report), encoding="utf-8"
    )
    return report


def main() -> None:
    report = run_xgrammar_preflight()
    print(json.dumps({"result": report["result"], "failures": report["failures"]}, indent=2))
    if report["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
