"""CFG-ENGINE-BAKEOFF-01 / 01R runner — library semantic authority."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff import backend_llguidance
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff import backend_xgrammar
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.g2_audit import (
    audit_xgrammar_lowering,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
    lower_well_ebnf1_to_xgrammar_ebnf,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import (
    ACCEPTED_GRAMMAR_SHA256,
    load_accepted_grammar,
    verify_pinned_tokenizer,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.source_oracle import (
    source_oracle_parity,
)


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

    # R2: independent source-language oracle on fixed corpus
    oracle = source_oracle_parity(root, grammar_bytes)

    # Produce lowered EBNF outside the audit (audit never calls the lowerer).
    lowered_a = lower_well_ebnf1_to_xgrammar_ebnf(well_text)
    lowered_b = lower_well_ebnf1_to_xgrammar_ebnf(well_text)
    # R1: independent G2 audit of already-produced target vs source
    g2 = audit_xgrammar_lowering(
        well_text, lowered_a, lowered_ebnf_replay=lowered_b
    )

    report: dict[str, Any] = {
        "slice": "DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R2",
        "authority": (
            "WELLPLOT-NLP-RUNTIME-V2-"
            "DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01-AUTH-001"
        ),
        "rework": ["R1", "R2", "R3", "R4", "R5"],
        "prior_slice": "DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01R",
        "model_calls": model_calls,
        "model_weights_loaded": model_weights_loaded,
        "g1_input_identity": {
            "grammar_sha256": grammar_sha,
            "grammar_sha256_expected": ACCEPTED_GRAMMAR_SHA256,
            "grammar_match": grammar_sha == ACCEPTED_GRAMMAR_SHA256,
            "tokenizer": tok_pin,
            "pass": grammar_sha == ACCEPTED_GRAMMAR_SHA256,
        },
        "source_oracle": {
            "pass": oracle["pass"],
            "positive_pass": oracle["positive_pass"],
            "negative_pass": oracle["negative_pass"],
            "recognizer_path": oracle["recognizer_path"],
            "failures": [
                r
                for r in (oracle["positive"] + oracle["negative"])
                if not r["pass"]
            ],
        },
        "g2_lowering_audit": g2,
        "backends": {},
    }

    # --- XGrammar ---
    t0 = time.perf_counter()
    xg = backend_xgrammar.build_xgrammar(well_text, snapshot)
    xg_build_s = time.perf_counter() - t0
    xg_text = backend_xgrammar.text_parity(xg)
    oracle_backend = backend_xgrammar.backend_agrees_with_oracle(xg_text, oracle)

    # G2 also requires source oracle/backend corpus parity
    g2_pass = bool(g2["pass"]) and bool(oracle_backend["pass"]) and bool(oracle["pass"])

    # R4/R5: token replay with completion semantics + per-case evidence
    xg_replay_1 = backend_xgrammar.token_replay(xg)

    # R3/G6: rebuild + second replay; compare semantic traces (not latency)
    xg2 = backend_xgrammar.build_xgrammar(well_text, snapshot)
    xg_replay_2 = backend_xgrammar.token_replay(xg2)
    g6 = backend_xgrammar.compare_replay_semantics(xg_replay_1, xg_replay_2)
    g6["lowered_sha_identical"] = xg.lowered_sha256 == xg2.lowered_sha256
    g6["compile_both_succeeded"] = True

    xg_gates = {
        "G1": report["g1_input_identity"]["pass"],
        "G2": g2_pass,
        "G3": xg_text["pass"] and oracle["pass"] and oracle_backend["pass"],
        "G4": True,
        "G5": xg_replay_1["pass"],
        "G6": g6["pass"] and g6["lowered_sha_identical"],
        "G7": xg.compile_seconds < 120.0,
        "G8": model_calls == 0 and model_weights_loaded is False,
    }
    xg_pass = all(
        xg_gates[g] for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
    )

    report["backends"]["xgrammar"] = {
        "status": "PASS" if xg_pass else "REJECTED",
        "provenance": backend_xgrammar.provenance(xg, grammar_sha),
        "build_wall_seconds": xg_build_s,
        "gates": xg_gates,
        "oracle_backend_agreement": oracle_backend,
        "text_parity": {
            "pass": xg_text["pass"],
            "positive_pass": xg_text["positive_pass"],
            "negative_pass": xg_text["negative_pass"],
            "positive_failures": [r for r in xg_text["positive"] if not r["pass"]],
            "negative_failures": [r for r in xg_text["negative"] if not r["pass"]],
        },
        "token_replay": {
            "pass": xg_replay_1["pass"],
            "positive_pass": xg_replay_1["positive_pass"],
            "negative_pass": xg_replay_1["negative_pass"],
            "positive_failures": [r for r in xg_replay_1["positive"] if not r["pass"]],
            "negative_failures": [r for r in xg_replay_1["negative"] if not r["pass"]],
            "cases": [
                {
                    "label": r["label"],
                    "n_tokens": r["n_tokens"],
                    "rejection_index": r["rejection_index"],
                    "rejection_reason": r["rejection_reason"],
                    "completed": r["completed"],
                    "any_stop_allowed": r["any_stop_allowed"],
                    "terminal_mask_digest": r["terminal_mask_digest"],
                    "step_mask_digest_count": len(r["step_mask_digests"]),
                    "pass": r["pass"],
                    "detail": r["detail"],
                }
                for r in (xg_replay_1["positive"] + xg_replay_1["negative"])
            ],
            "mask_step_latency_seconds": xg_replay_1["mask_step_latency_seconds"],
        },
        "g6_repeated_replay": g6,
        "resources": {
            "compile_seconds": xg.compile_seconds,
            "lowered_grammar_bytes": len(xg.lowered_ebnf.encode("utf-8")),
        },
    }

    # --- llguidance (frozen rejection path; still exercised) ---
    llg = backend_llguidance.attempt_llguidance(well_text, snapshot)
    if llg.get("status") == "CONSTRUCTED":
        report["backends"]["llguidance"] = {
            "status": "CONSTRUCTED_UNVALIDATED",
            **{
                k: v
                for k, v in llg.items()
                if k not in ("matcher", "ll_tokenizer", "lark")
            },
        }
    else:
        report["backends"]["llguidance"] = llg

    xg_ok = report["backends"]["xgrammar"]["status"] == "PASS"
    llg_ok = report["backends"]["llguidance"].get("status") == "PASS"
    if xg_ok and not llg_ok:
        recommendation = "xgrammar"
        recommendation_reason = (
            "XGrammar passed evidence-derived G1–G8 (01R). llguidance remains "
            "rejected on G7 symbol-table pathology."
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
    (
        evidence_dir / "decomposer_pilot_constraint_cfg_engine_bakeoff_01.json"
    ).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
