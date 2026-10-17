"""DECOMPOSER-PILOT-PREFLIGHT-01R orchestrator: pins + parity; model_calls=0; no generate."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot import constraint_schema as cs
from nlp_gate_modernbert.decomposer_pilot import inference_pins
from nlp_gate_modernbert.decomposer_pilot import model_provenance
from nlp_gate_modernbert.decomposer_pilot import outlines_compile
from nlp_gate_modernbert.decomposer_pilot import parity as parity_mod
from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.decomposer_pilot import workspace_serialize
from nlp_gate_modernbert.paths import EVIDENCE_DIR, SLM01_ROOT

AUTH = "WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-PREFLIGHT-01-REWORK-AUTH-001"
SLICE = "DECOMPOSER-PILOT-PREFLIGHT-01R"
DESIGN_TIP = "d180050eddee5bb8e4f1a9a370fe1a8c83ddd7bc"
PRIOR_PREFLIGHT_01_CANDIDATE = "4d140dc1c0805ee77dbb906ea3f2866cf15f1152"
STARTING_TIP = "1d84071576704909c9dce7e24011eb813009201c"

REQUIRED_OUTLINES = "1.3.3"
REQUIRED_OUTLINES_CORE = "0.2.14"

MODEL_CALLS = 0


class GenerateForbiddenError(RuntimeError):
    """Raised if any code path attempts model.generate during preflight."""


def _pkg_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _install_generate_guard() -> list[str]:
    """Best-effort spy: block transformers GenerationMixin.generate (HF 5.x path)."""
    notes: list[str] = []
    try:
        from transformers.generation import GenerationMixin
    except ImportError:
        notes.append("transformers_unavailable_for_generate_guard")
        return notes

    original = getattr(GenerationMixin, "generate", None)
    if original is None:
        notes.append("GenerationMixin.generate_missing")
        return notes

    def _blocked(self, *args, **kwargs):  # noqa: ANN001
        raise GenerateForbiddenError(
            "model.generate is forbidden during DECOMPOSER-PILOT-PREFLIGHT-01R"
        )

    GenerationMixin.generate = _blocked  # type: ignore[method-assign]
    notes.append("GenerationMixin.generate_blocked")
    _ = original
    return notes


def _software_pins() -> dict[str, Any]:
    return {
        "outlines": _pkg_version("outlines"),
        "outlines_core": _pkg_version("outlines-core"),
        "transformers": _pkg_version("transformers"),
        "pydantic": _pkg_version("pydantic"),
        "torch": _pkg_version("torch"),
        "jsonschema": _pkg_version("jsonschema"),
        "python": sys.version.split()[0],
        "required": {
            "outlines": REQUIRED_OUTLINES,
            "outlines_core": REQUIRED_OUTLINES_CORE,
        },
    }


def _check_software(software: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if software.get("outlines") != REQUIRED_OUTLINES:
        errors.append(
            f"outlines version {software.get('outlines')!r} != {REQUIRED_OUTLINES!r}"
        )
    if software.get("outlines_core") != REQUIRED_OUTLINES_CORE:
        errors.append(
            f"outlines-core version {software.get('outlines_core')!r} != {REQUIRED_OUTLINES_CORE!r}"
        )
    return errors


def _template_smoke(snapshot: Path) -> dict[str, Any]:
    """Load tokenizer only; apply_chat_template + tokenize fixed dummy; no model weights."""
    from transformers import AutoTokenizer

    from nlp_gate_modernbert.decomposer_pilot.workspace_serialize import (
        serialize_projected_workspace,
    )

    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    ws_json = serialize_projected_workspace(prompt_contract.DUMMY_WORKSPACE)
    messages = prompt_contract.build_messages(
        utterance=prompt_contract.DUMMY_UTTERANCE,
        workspace_json=ws_json,
    )
    messages_sha = prompt_contract.hash_messages(messages)
    chat_text = prompt_contract.render_chat_template_text(
        tokenizer,
        utterance=prompt_contract.DUMMY_UTTERANCE,
        workspace_json=ws_json,
    )
    chat_sha = hashlib.sha256(chat_text.encode("utf-8")).hexdigest()
    encoded = tokenizer(chat_text, add_special_tokens=False)
    input_ids = encoded["input_ids"]
    ids_bytes = json.dumps(input_ids, separators=(",", ":")).encode("utf-8")
    ids_sha = hashlib.sha256(ids_bytes).hexdigest()
    return {
        "messages_sha256": messages_sha,
        "chat_template_text_sha256": chat_sha,
        "input_ids_sha256": ids_sha,
        "input_ids_length": len(input_ids),
        "tokenizer_loaded_from": str(snapshot),
        "local_files_only": True,
        "model_weights_loaded": False,
    }


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _handoff_md(
    *,
    result: str,
    candidate_sha: str | None,
    starting_tip: str,
    tip_sha: str | None,
    failures: list[str],
    model_calls: int,
) -> str:
    fail_block = "\n".join(f"- {f}" for f in failures) if failures else "- (none)"
    return f"""# DECOMPOSER-PILOT-PREFLIGHT-01R — STOP handoff

```
SLICE:
{SLICE}

AUTHORITY:
{AUTH}

PARENT DESIGN:
decomposer_pilot_design_01 @ {DESIGN_TIP}

PRIOR PREFLIGHT-01 CANDIDATE:
{PRIOR_PREFLIGHT_01_CANDIDATE}
RESULT: REVISE

STARTING TIP:
{starting_tip}

CANDIDATE SHA:
{candidate_sha or "(pending commit)"}

TIP:
{tip_sha or "(pending SHA-record commit)"}

MODEL CALLS:
{model_calls}

PILOT-01:
NOT_AUTHORIZED

RESULT:
{result}
```

## Claim

PREFLIGHT-01R PASS proves only that the pinned experimental machinery is
reproducible and structurally viable. It provides **zero** model-performance
evidence and does **not** authorize DECOMPOSER-PILOT-01.

Rework corrections: R1 non-whitespace XOR pattern; R2 outlines_core token-guide
construction (tokenizer-only); R3 serializer wording + patch/canonicalization pins.

## Failures

{fail_block}

## Evidence artifacts

- `decomposer_pilot_preflight_01_run_manifest.json`
- `decomposer_pilot_preflight_01_parity.json`
- `decomposer_pilot_preflight_01_constraint.schema.json`
- `decomposer_pilot_preflight_01.md`

## Explicit non-authorization

```
DECOMPOSER-PILOT-01:     NOT AUTHORIZED
model.generate:          NOT AUTHORIZED
model download:          NOT AUTHORIZED
CFG fallback:            NOT AUTHORIZED
backend swap:            NOT AUTHORIZED
prompt sealed-six tune:  NOT AUTHORIZED
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-PREFLIGHT-01R REVIEW
"""


def run_preflight(
    *,
    evidence_dir: Path | None = None,
    snapshot_path: Path | None = None,
    starting_sha: str | None = None,
    skip_template_smoke: bool = False,
    skip_token_guide: bool = False,
) -> dict[str, Any]:
    """Run all preflight pins; write four evidence artifacts; return result dict.

    On any failure: write FAIL evidence and return without self-repair.
    """
    global MODEL_CALLS
    MODEL_CALLS = 0

    evidence = Path(evidence_dir or EVIDENCE_DIR)
    evidence.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    guard_notes = _install_generate_guard()

    software = _software_pins()
    failures.extend(_check_software(software))

    model_pin: dict[str, Any] | None = None
    try:
        model_pin = model_provenance.collect_model_provenance(snapshot_path)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"model_provenance:{exc}")

    constraint_meta: dict[str, Any] | None = None
    patched_bytes: bytes | None = None
    patched_schema: dict[str, Any] | None = None
    patched_sha: str | None = None
    try:
        patched_schema, patched_bytes, raw_sha, patched_sha = cs.build_constraint_artifact()
        out_path = evidence / cs.CONSTRAINT_ARTIFACT_NAME
        out_path.write_bytes(patched_bytes)
        # Re-read persisted bytes and verify hash (exact-artifact contract).
        persisted = out_path.read_bytes()
        persisted_sha = hashlib.sha256(persisted).hexdigest()
        if persisted_sha != patched_sha:
            raise RuntimeError(
                f"persisted constraint hash mismatch after write: "
                f"{persisted_sha} != {patched_sha}"
            )
        patched_bytes = persisted
        constraint_meta = {
            "path": str(out_path),
            "raw_pydantic_schema_sha256": raw_sha,
            "patched_constraint_schema_sha256": patched_sha,
            "constraint_source": (
                "ClosedNormalizedProgram.model_json_schema() + XOR oneOf patch "
                "with pattern .*\\S.* on text/local_ref"
            ),
            "bytes_written": len(patched_bytes),
            "same_artifact_for_all_six": True,
            **cs.constraint_identity(),
        }
    except Exception as exc:  # noqa: BLE001
        failures.append(f"constraint_schema:{exc}")

    outlines_att: dict[str, Any] | None = None
    outlines_compiled = None
    if patched_bytes is not None:
        try:
            outlines_compiled = outlines_compile.compile_json_schema(patched_bytes)
            outlines_att = outlines_compile.compile_attestation(patched_bytes)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"outlines_compile:{exc}")

    parity_result: dict[str, Any] | None = None
    if patched_schema is not None:
        try:
            # Prefer schema loaded from persisted artifact for parity.
            persisted_path = evidence / cs.CONSTRAINT_ARTIFACT_NAME
            if persisted_path.is_file():
                patched_schema = json.loads(persisted_path.read_text(encoding="utf-8"))
            parity_result = parity_mod.run_parity_suite(
                patched_schema=patched_schema,
                outlines_compiled=outlines_compiled,
            )
            if not parity_result.get("pass"):
                failed_ids = [
                    p["probe_id"] for p in parity_result["probes"] if not p["pass"]
                ]
                failures.append(f"parity_failed:{failed_ids}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"parity:{exc}")

    token_level: dict[str, Any] | None = None
    if (
        not skip_token_guide
        and patched_bytes is not None
        and patched_sha is not None
        and model_pin is not None
    ):
        try:
            token_level = outlines_compile.construct_token_level_constraint(
                persisted_schema_bytes=patched_bytes,
                expected_schema_sha256=patched_sha,
                snapshot_path=Path(model_pin["snapshot_path"]),
            )
            if token_level.get("construction") != "PASS":
                failures.append("token_level_constraint:construction_not_pass")
        except Exception as exc:  # noqa: BLE001
            token_level = {
                "backend": "outlines_core",
                "construction": "FAIL",
                "constraint_schema_sha256": patched_sha,
                "tokenizer_snapshot": model_pin.get("snapshot_path"),
                "local_files_only": True,
                "model_weights_loaded": False,
                "model_forward_calls": 0,
                "model_generate_calls": 0,
                "process_logits_invoked": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            failures.append(f"token_level_constraint:{exc}")
    elif not skip_token_guide and model_pin is None:
        failures.append("token_level_constraint:missing_model_pin")

    serializer_spec = workspace_serialize.serializer_spec()
    inference = inference_pins.inference_config_dict()
    inference_sha = inference_pins.inference_config_sha256()

    template_smoke: dict[str, Any] | None = None
    if not skip_template_smoke and model_pin is not None:
        try:
            template_smoke = _template_smoke(Path(model_pin["snapshot_path"]))
        except Exception as exc:  # noqa: BLE001
            failures.append(f"template_smoke:{exc}")

    prompt_manifest = prompt_contract.prompt_contract_manifest(
        chat_template_text_sha256=(template_smoke or {}).get("chat_template_text_sha256"),
        input_ids_sha256=(template_smoke or {}).get("input_ids_sha256"),
        messages_sha256=(template_smoke or {}).get("messages_sha256"),
    )

    if MODEL_CALLS != 0:
        failures.append(f"model_calls_nonzero:{MODEL_CALLS}")

    result = "PASS" if not failures else "FAIL"
    sha = starting_sha or STARTING_TIP
    if starting_sha is None:
        try:
            import subprocess

            sha = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(SLM01_ROOT.parents[1]),
                    text=True,
                ).strip()
            )
        except Exception:  # noqa: BLE001
            sha = STARTING_TIP

    run_manifest: dict[str, Any] = {
        "authority": AUTH,
        "slice": SLICE,
        "parent_design_tip": DESIGN_TIP,
        "prior_candidate": PRIOR_PREFLIGHT_01_CANDIDATE,
        "prior_preflight_01_result": "REVISE",
        "starting_tip": STARTING_TIP,
        "starting_sha": sha,
        "result": result,
        "model_calls": MODEL_CALLS,
        "pilot_01": "NOT_AUTHORIZED",
        "pass_does_not_authorize_pilot_01": True,
        "failures": failures,
        "generate_guard": guard_notes,
        "MODEL": model_pin,
        "SOFTWARE": software,
        "CONSTRAINT": {
            **(constraint_meta or {}),
            "backend": "Outlines outlines_core via HF Transformers tokenizer path",
            "backend_versions": {
                "outlines": software.get("outlines"),
                "outlines_core": software.get("outlines_core"),
            },
            "outlines_compile": outlines_att,
            "parity_pass": (parity_result or {}).get("pass"),
        },
        "TOKEN_LEVEL_CONSTRAINT": token_level,
        "PROMPT": prompt_manifest,
        "WORKSPACE_SERIALIZATION": serializer_spec,
        "INFERENCE": {
            **inference,
            "inference_config_sha256": inference_sha,
        },
        "GOVERNANCE": {
            "no_model_generate": True,
            "no_model_forward": True,
            "no_download": True,
            "no_backend_swap": True,
            "no_cfg_fallback": True,
            "no_sealed_six_prompt_tuning": True,
            "model_weights_loaded": False,
            "template_smoke": template_smoke,
            "slm01_root": str(SLM01_ROOT),
            "rework": ["R1_nonempty_pattern", "R2_token_guide", "R3_provenance_pins"],
        },
    }

    _write_json(evidence / "decomposer_pilot_preflight_01_run_manifest.json", run_manifest)
    if parity_result is not None:
        _write_json(evidence / "decomposer_pilot_preflight_01_parity.json", parity_result)
    else:
        _write_json(
            evidence / "decomposer_pilot_preflight_01_parity.json",
            {"suite": "decomposer_pilot_preflight_01_parity", "pass": False, "probes": []},
        )

    md = _handoff_md(
        result=result,
        candidate_sha=None,
        starting_tip=STARTING_TIP,
        tip_sha=None,
        failures=failures,
        model_calls=MODEL_CALLS,
    )
    (evidence / "decomposer_pilot_preflight_01.md").write_text(md, encoding="utf-8")

    return {
        "result": result,
        "failures": failures,
        "model_calls": MODEL_CALLS,
        "evidence_dir": str(evidence),
        "run_manifest": run_manifest,
        "parity": parity_result,
        "token_level": token_level,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=SLICE)
    parser.add_argument("--evidence-dir", type=Path, default=None)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--skip-template-smoke", action="store_true")
    parser.add_argument("--skip-token-guide", action="store_true")
    args = parser.parse_args(argv)
    out = run_preflight(
        evidence_dir=args.evidence_dir,
        snapshot_path=args.snapshot,
        skip_template_smoke=args.skip_template_smoke,
        skip_token_guide=args.skip_token_guide,
    )
    print(
        json.dumps(
            {
                "result": out["result"],
                "failures": out["failures"],
                "model_calls": out["model_calls"],
            },
            indent=2,
        )
    )
    return 0 if out["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
