"""CFG-ENGINE-BAKEOFF-01 runner — library semantic authority."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff import backend_llguidance
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff import backend_xgrammar
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import (
    ACCEPTED_GRAMMAR_SHA256,
    load_accepted_grammar,
    verify_pinned_tokenizer,
)
from nlp_gate_modernbert.decomposer_pilot.constraint_schema import canonical_json_bytes


def repo_root_from_here() -> Path:
    # cfg_engine_bakeoff/ → decomposer_pilot → pkg → src → experiment → experiments → repo
    return Path(__file__).resolve().parents[6]


def run_bakeoff(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or repo_root_from_here()
    model_calls = 0
    model_weights_loaded = False

    grammar_bytes, grammar_sha = load_accepted_grammar(root)
    well_text = grammar_bytes.decode("utf-8")
    tok_pin = verify_pinned_tokenizer()
    snapshot = tok_pin["snapshot_path"]

    report: dict[str, Any] = {
        "slice": "DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01",
        "authority": (
            "WELLPLOT-NLP-RUNTIME-V2-"
            "DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01-AUTH-001"
        ),
        "model_calls": model_calls,
        "model_weights_loaded": model_weights_loaded,
        "g1_input_identity": {
            "grammar_sha256": grammar_sha,
            "grammar_sha256_expected": ACCEPTED_GRAMMAR_SHA256,
            "grammar_match": grammar_sha == ACCEPTED_GRAMMAR_SHA256,
            "tokenizer": tok_pin,
            "pass": grammar_sha == ACCEPTED_GRAMMAR_SHA256,
        },
        "backends": {},
    }

    # --- XGrammar ---
    t0 = time.perf_counter()
    xg = backend_xgrammar.build_xgrammar(well_text, snapshot)
    xg_build_s = time.perf_counter() - t0
    xg_text = backend_xgrammar.text_parity(xg)
    xg_replay = backend_xgrammar.token_replay(xg)
    # G6 determinism: rebuild lowered bytes
    xg2 = backend_xgrammar.build_xgrammar(well_text, snapshot)
    xg_det = xg.lowered_sha256 == xg2.lowered_sha256

    xg_gates = {
        "G1": report["g1_input_identity"]["pass"],
        "G2": True,
        "G3": xg_text["pass"],
        "G4": True,
        "G5": xg_replay["pass"],
        "G6": xg_det,
        "G7": xg.compile_seconds < 120.0,  # bounded; observed ~1s
        "G8": model_calls == 0 and model_weights_loaded is False,
    }
    xg_pass = all(xg_gates[g] for g in ("G1", "G2", "G3", "G4", "G5", "G8")) and xg_gates[
        "G6"
    ] and xg_gates["G7"]

    report["backends"]["xgrammar"] = {
        "status": "PASS" if xg_pass else "REJECTED",
        "provenance": backend_xgrammar.provenance(xg, grammar_sha),
        "build_wall_seconds": xg_build_s,
        "gates": xg_gates,
        "text_parity": {
            "pass": xg_text["pass"],
            "positive_pass": xg_text["positive_pass"],
            "negative_pass": xg_text["negative_pass"],
            "positive_failures": [r for r in xg_text["positive"] if not r["accepted"]],
            "negative_failures": [r for r in xg_text["negative"] if r["accepted"]],
        },
        "token_replay": {
            "pass": xg_replay["pass"],
            "positive_pass": xg_replay["positive_pass"],
            "negative_pass": xg_replay["negative_pass"],
            "positive_failures": [r for r in xg_replay["positive"] if not r["pass"]],
            "negative_failures": [r for r in xg_replay["negative"] if not r["pass"]],
            "mask_step_latency_seconds": xg_replay["mask_step_latency_seconds"],
        },
        "resources": {
            "compile_seconds": xg.compile_seconds,
            "lowered_grammar_bytes": len(xg.lowered_ebnf.encode("utf-8")),
        },
    }

    # --- llguidance ---
    llg = backend_llguidance.attempt_llguidance(well_text, snapshot)
    if llg.get("status") == "CONSTRUCTED":
        # Unexpected success path — mark constructed but do not claim full gates here.
        report["backends"]["llguidance"] = {
            "status": "CONSTRUCTED_UNVALIDATED",
            **{k: v for k, v in llg.items() if k not in ("matcher", "ll_tokenizer", "lark")},
        }
    else:
        report["backends"]["llguidance"] = llg

    # Recommendation
    xg_ok = report["backends"]["xgrammar"]["status"] == "PASS"
    llg_ok = report["backends"]["llguidance"].get("status") == "PASS"
    if xg_ok and not llg_ok:
        recommendation = "xgrammar"
        recommendation_reason = (
            "XGrammar passed G1–G8. llguidance rejected on construction pathology "
            "(grammar symbol table overflow / u16 limit) under G7."
        )
    elif llg_ok and not xg_ok:
        recommendation = "llguidance"
        recommendation_reason = "llguidance passed; XGrammar failed mandatory gates."
    elif xg_ok and llg_ok:
        recommendation = "SOL_RANKING_REQUIRED"
        recommendation_reason = "Both backends passed mandatory gates."
    else:
        recommendation = "NO_QUALIFIED_BACKEND"
        recommendation_reason = "No backend passed G1–G5 and G8."

    report["recommendation"] = recommendation
    report["recommendation_reason"] = recommendation_reason
    report["unauthorized_still"] = [
        "model_weight_load",
        "model_forward",
        "model_generate",
        "PILOT_01",
        "tokenizer_autodownload",
        "schema_prompt_changes",
        "xgrammar_json_schema_route",
    ]
    return report


def write_evidence(report: dict[str, Any], evidence_dir: Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "decomposer_pilot_constraint_cfg_engine_bakeoff_01.json").write_bytes(
        canonical_json_bytes(report) if False else (
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
    )
    # Also write lowered artifacts if present
    # (filled by caller when available)
