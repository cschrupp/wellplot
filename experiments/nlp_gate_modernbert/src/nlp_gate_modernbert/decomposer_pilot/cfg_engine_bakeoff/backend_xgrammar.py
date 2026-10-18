"""XGrammar native-EBNF bakeoff adapter (no JSON-Schema route)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import xgrammar as xgr
from transformers import AutoConfig, AutoTokenizer

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.fixtures import (
    NEGATIVE,
    POSITIVE,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
    LOWERER_ID,
    lower_well_ebnf1_to_xgrammar_ebnf,
    lowerer_source_sha256,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import sha256_bytes


@dataclass
class XGrammarBundle:
    lowered_ebnf: str
    lowered_sha256: str
    grammar: Any
    tokenizer_info: Any
    compiled: Any
    tokenizer: Any
    vocab_size: int
    compile_seconds: float
    package_version: str


def build_xgrammar(
    well_text: str,
    snapshot_path: str,
    *,
    model_weights_loaded: bool = False,
) -> XGrammarBundle:
    if model_weights_loaded:
        raise RuntimeError("model_weights_loaded must be false")
    import importlib.metadata as md

    lowered = lower_well_ebnf1_to_xgrammar_ebnf(well_text)
    lowered_sha = sha256_bytes(lowered.encode("utf-8"))
    grammar = xgr.Grammar.from_ebnf(lowered, root_rule_name="START")
    tok = AutoTokenizer.from_pretrained(snapshot_path, local_files_only=True)
    cfg = AutoConfig.from_pretrained(snapshot_path, local_files_only=True)
    info = xgr.TokenizerInfo.from_huggingface(tok, vocab_size=cfg.vocab_size)
    compiler = xgr.GrammarCompiler(info)
    t0 = time.perf_counter()
    compiled = compiler.compile_grammar(grammar)
    compile_s = time.perf_counter() - t0
    return XGrammarBundle(
        lowered_ebnf=lowered,
        lowered_sha256=lowered_sha,
        grammar=grammar,
        tokenizer_info=info,
        compiled=compiled,
        tokenizer=tok,
        vocab_size=int(cfg.vocab_size),
        compile_seconds=compile_s,
        package_version=md.version("xgrammar"),
    )


def text_parity(bundle: XGrammarBundle) -> dict[str, Any]:
    pos_results = []
    neg_results = []
    for label, text in POSITIVE:
        ok = bool(xgr.testing._is_grammar_accept_string(bundle.grammar, text))
        pos_results.append({"label": label, "accepted": ok, "expected": True})
    for label, text in NEGATIVE:
        ok = bool(xgr.testing._is_grammar_accept_string(bundle.grammar, text))
        neg_results.append({"label": label, "accepted": ok, "expected": False})
    pos_pass = all(r["accepted"] for r in pos_results)
    neg_pass = all(not r["accepted"] for r in neg_results)
    return {
        "positive": pos_results,
        "negative": neg_results,
        "positive_pass": pos_pass,
        "negative_pass": neg_pass,
        "pass": pos_pass and neg_pass,
    }


def _bit_allowed(bitmask, token_id: int) -> bool:
    # bitmask shape (1, ceil(vocab/32)), dtype int32; bit 1 = allowed
    word = int(bitmask[0, token_id // 32].item())
    return bool((word >> (token_id % 32)) & 1)


def token_replay(bundle: XGrammarBundle) -> dict[str, Any]:
    pos_rows = []
    neg_rows = []
    latencies: list[float] = []

    for label, text in POSITIVE:
        matcher = xgr.GrammarMatcher(bundle.compiled)
        bitmask = xgr.allocate_token_bitmask(1, bundle.vocab_size)
        ids = bundle.tokenizer.encode(text, add_special_tokens=False)
        ok = True
        detail = "ok"
        for tid in ids:
            t0 = time.perf_counter()
            matcher.fill_next_token_bitmask(bitmask)
            latencies.append(time.perf_counter() - t0)
            if not _bit_allowed(bitmask, tid):
                ok = False
                detail = f"blocked_token:{tid}"
                break
            if not matcher.accept_token(tid):
                ok = False
                detail = f"accept_token_false:{tid}"
                break
        pos_rows.append(
            {
                "label": label,
                "pass": ok,
                "detail": detail,
                "n_tokens": len(ids),
            }
        )

    for label, text in NEGATIVE:
        matcher = xgr.GrammarMatcher(bundle.compiled)
        bitmask = xgr.allocate_token_bitmask(1, bundle.vocab_size)
        ids = bundle.tokenizer.encode(text, add_special_tokens=False)
        rejected_before_end = False
        detail = "completed_without_block"
        for i, tid in enumerate(ids):
            t0 = time.perf_counter()
            matcher.fill_next_token_bitmask(bitmask)
            latencies.append(time.perf_counter() - t0)
            if not _bit_allowed(bitmask, tid):
                rejected_before_end = True
                detail = f"blocked_at_index:{i}:token:{tid}"
                break
            if not matcher.accept_token(tid):
                rejected_before_end = True
                detail = f"accept_false_at_index:{i}:token:{tid}"
                break
        # Also reject if full string is grammar-accepted (should not for negatives)
        if not rejected_before_end:
            if xgr.testing._is_grammar_accept_string(bundle.grammar, text):
                detail = "full_string_still_accepted"
            else:
                # tokens consumed but string not accepted — still a rejection path
                rejected_before_end = True
                detail = "tokens_consumed_but_string_rejected"
        neg_rows.append(
            {
                "label": label,
                "pass": rejected_before_end,
                "detail": detail,
                "n_tokens": len(ids),
            }
        )

    pos_pass = all(r["pass"] for r in pos_rows)
    neg_pass = all(r["pass"] for r in neg_rows)
    return {
        "positive": pos_rows,
        "negative": neg_rows,
        "positive_pass": pos_pass,
        "negative_pass": neg_pass,
        "pass": pos_pass and neg_pass,
        "mask_step_latency_seconds": {
            "n": len(latencies),
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            "max": max(latencies) if latencies else None,
            "min": min(latencies) if latencies else None,
        },
    }


def provenance(bundle: XGrammarBundle, source_grammar_sha: str) -> dict[str, Any]:
    return {
        "backend": "xgrammar",
        "route": "native_ebnf",
        "package_version": bundle.package_version,
        "lowerer_id": LOWERER_ID,
        "lowerer_source_sha256": lowerer_source_sha256(),
        "source_grammar_sha256": source_grammar_sha,
        "backend_native_grammar_sha256": bundle.lowered_sha256,
        "compile_seconds": bundle.compile_seconds,
        "vocab_size": bundle.vocab_size,
    }
