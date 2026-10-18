"""llguidance Lark bakeoff adapter — construction may fail closed on pathology."""

from __future__ import annotations

import time
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_llguidance import (
    LOWERER_ID,
    lower_well_ebnf1_to_llguidance_lark,
    lowerer_source_sha256,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import sha256_bytes


def attempt_llguidance(
    well_text: str,
    snapshot_path: str,
) -> dict[str, Any]:
    """Lower + construct. On pathology/error, return rejected evidence (no raise)."""
    import importlib.metadata as md

    from transformers import AutoConfig, AutoTokenizer
    from llguidance import LLMatcher
    from llguidance.hf import from_tokenizer

    t_lower0 = time.perf_counter()
    try:
        lark = lower_well_ebnf1_to_llguidance_lark(well_text)
    except Exception as exc:
        return {
            "backend": "llguidance",
            "status": "REJECTED",
            "reject_gate": "G2",
            "reason": f"lowering_failed:{exc}",
            "package_version": md.version("llguidance"),
            "lowerer_id": LOWERER_ID,
            "lowerer_source_sha256": lowerer_source_sha256(),
        }
    lower_s = time.perf_counter() - t_lower0
    lark_sha = sha256_bytes(lark.encode("utf-8"))

    tok = AutoTokenizer.from_pretrained(snapshot_path, local_files_only=True)
    cfg = AutoConfig.from_pretrained(snapshot_path, local_files_only=True)
    t_tok0 = time.perf_counter()
    llt = from_tokenizer(tok, n_vocab=cfg.vocab_size)
    tok_s = time.perf_counter() - t_tok0

    gram = LLMatcher.grammar_from_lark(lark)
    validate_msg = LLMatcher.validate_grammar(gram, llt)

    t_m0 = time.perf_counter()
    try:
        matcher = LLMatcher(llt, gram, log_level=0)
        construct_s = time.perf_counter() - t_m0
    except Exception as exc:
        return {
            "backend": "llguidance",
            "status": "REJECTED",
            "reject_gate": "G7",
            "reason": f"matcher_construct_exception:{type(exc).__name__}:{exc}",
            "package_version": md.version("llguidance"),
            "lowerer_id": LOWERER_ID,
            "lowerer_source_sha256": lowerer_source_sha256(),
            "backend_native_grammar_sha256": lark_sha,
            "backend_native_grammar_bytes": len(lark.encode("utf-8")),
            "lower_seconds": lower_s,
            "tokenizer_wrap_seconds": tok_s,
            "validate_message": validate_msg or "",
        }

    if matcher.is_error():
        err = matcher.get_error()
        gate = "G7" if "u16::MAX" in err or "assertion failed" in err else "G4"
        return {
            "backend": "llguidance",
            "status": "REJECTED",
            "reject_gate": gate,
            "reason": f"matcher_error_state:{err}",
            "package_version": md.version("llguidance"),
            "lowerer_id": LOWERER_ID,
            "lowerer_source_sha256": lowerer_source_sha256(),
            "backend_native_grammar_sha256": lark_sha,
            "backend_native_grammar_bytes": len(lark.encode("utf-8")),
            "lower_seconds": lower_s,
            "tokenizer_wrap_seconds": tok_s,
            "construct_seconds": construct_s,
            "validate_message": validate_msg or "",
            "pathology": "grammar_symbol_table_overflow"
            if "u16::MAX" in err
            else None,
        }

    # Construction succeeded — caller may run parity (not expected for this grammar size).
    return {
        "backend": "llguidance",
        "status": "CONSTRUCTED",
        "package_version": md.version("llguidance"),
        "lowerer_id": LOWERER_ID,
        "lowerer_source_sha256": lowerer_source_sha256(),
        "backend_native_grammar_sha256": lark_sha,
        "backend_native_grammar_bytes": len(lark.encode("utf-8")),
        "lower_seconds": lower_s,
        "tokenizer_wrap_seconds": tok_s,
        "construct_seconds": construct_s,
        "validate_message": validate_msg or "",
        "matcher": matcher,
        "ll_tokenizer": llt,
        "lark": lark,
    }
