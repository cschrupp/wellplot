"""XGrammar native-EBNF bakeoff adapter (no JSON-Schema route)."""

from __future__ import annotations

import hashlib
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
        pos_results.append({"label": label, "accepted": ok, "expected": True, "pass": ok})
    for label, text in NEGATIVE:
        ok = bool(xgr.testing._is_grammar_accept_string(bundle.grammar, text))
        neg_results.append(
            {"label": label, "accepted": ok, "expected": False, "pass": not ok}
        )
    pos_pass = all(r["pass"] for r in pos_results)
    neg_pass = all(r["pass"] for r in neg_results)
    return {
        "positive": pos_results,
        "negative": neg_results,
        "positive_pass": pos_pass,
        "negative_pass": neg_pass,
        "pass": pos_pass and neg_pass,
    }


def backend_agrees_with_oracle(
    backend_text: dict[str, Any], oracle: dict[str, Any]
) -> dict[str, Any]:
    """G2/G3 bridge: backend acceptance must match independent oracle on corpus."""
    mismatches: list[dict[str, Any]] = []
    for br, orr in zip(backend_text["positive"], oracle["positive"], strict=True):
        if br["label"] != orr["label"]:
            mismatches.append({"side": "positive", "reason": "label_order"})
            continue
        if br["accepted"] != orr["oracle_accepted"]:
            mismatches.append(
                {
                    "side": "positive",
                    "label": br["label"],
                    "backend": br["accepted"],
                    "oracle": orr["oracle_accepted"],
                }
            )
    for br, orr in zip(backend_text["negative"], oracle["negative"], strict=True):
        if br["label"] != orr["label"]:
            mismatches.append({"side": "negative", "reason": "label_order"})
            continue
        if br["accepted"] != orr["oracle_accepted"]:
            mismatches.append(
                {
                    "side": "negative",
                    "label": br["label"],
                    "backend": br["accepted"],
                    "oracle": orr["oracle_accepted"],
                }
            )
    return {"pass": not mismatches, "mismatches": mismatches}


def _bit_allowed(bitmask, token_id: int) -> bool:
    word = int(bitmask[0, token_id // 32].item())
    return bool((word >> (token_id % 32)) & 1)


def _mask_digest(bitmask) -> str:
    # Deterministic digest of the full int32 bitmask tensor bytes.
    raw = bitmask.detach().cpu().numpy().tobytes()
    return hashlib.sha256(raw).hexdigest()


def _stop_allowed(matcher, bitmask) -> dict[str, bool]:
    return {int(s): _bit_allowed(bitmask, int(s)) for s in matcher.stop_token_ids}


def _replay_one(
    bundle: XGrammarBundle, text: str, *, expect_positive: bool
) -> dict[str, Any]:
    matcher = xgr.GrammarMatcher(bundle.compiled)
    bitmask = xgr.allocate_token_bitmask(1, bundle.vocab_size)
    ids = bundle.tokenizer.encode(text, add_special_tokens=False)
    step_digests: list[str] = []
    latencies: list[float] = []
    rejection_index: int | None = None
    rejection_reason: str | None = None

    for i, tid in enumerate(ids):
        t0 = time.perf_counter()
        matcher.fill_next_token_bitmask(bitmask)
        latencies.append(time.perf_counter() - t0)
        step_digests.append(_mask_digest(bitmask))
        if not _bit_allowed(bitmask, tid):
            rejection_index = i
            rejection_reason = f"blocked_token:{tid}"
            break
        if not matcher.accept_token(tid):
            rejection_index = i
            rejection_reason = f"accept_token_false:{tid}"
            break

    # Terminal mask after consuming prefix/all tokens (or after last successful accept)
    t0 = time.perf_counter()
    matcher.fill_next_token_bitmask(bitmask)
    latencies.append(time.perf_counter() - t0)
    terminal_digest = _mask_digest(bitmask)
    completed = bool(matcher.is_completed())
    stops = _stop_allowed(matcher, bitmask)
    any_stop_allowed = any(stops.values()) if stops else False

    if expect_positive:
        ok = (
            rejection_index is None
            and completed is True
            and any_stop_allowed is True
        )
        detail = "ok" if ok else (
            rejection_reason
            or f"completed={completed};stop_allowed={any_stop_allowed}"
        )
    else:
        # A: blocked text token, OR B: incomplete + stop/EOS not permitted
        if rejection_index is not None:
            ok = True
            detail = rejection_reason or "blocked"
        elif completed is False and any_stop_allowed is False:
            ok = True
            detail = "incomplete_and_stop_blocked"
        else:
            ok = False
            detail = (
                f"invalid_neg_pass_path:completed={completed};"
                f"stop_allowed={any_stop_allowed};"
                f"rejection_index={rejection_index}"
            )

    return {
        "pass": ok,
        "detail": detail,
        "n_tokens": len(ids),
        "rejection_index": rejection_index,
        "rejection_reason": rejection_reason,
        "completed": completed,
        "stop_token_allowed": stops,
        "any_stop_allowed": any_stop_allowed,
        "step_mask_digests": step_digests,
        "terminal_mask_digest": terminal_digest,
        "mask_step_latencies": latencies,
        # Semantic fingerprint for G6 (exclude timing)
        "semantic_trace": {
            "rejection_index": rejection_index,
            "rejection_reason": rejection_reason,
            "completed": completed,
            "any_stop_allowed": any_stop_allowed,
            "stop_token_allowed": stops,
            "step_mask_digests": step_digests,
            "terminal_mask_digest": terminal_digest,
            "n_tokens": len(ids),
            "pass": ok,
        },
    }


def token_replay(bundle: XGrammarBundle) -> dict[str, Any]:
    pos_rows = []
    neg_rows = []
    all_latencies: list[float] = []

    for label, text in POSITIVE:
        row = _replay_one(bundle, text, expect_positive=True)
        row = {"label": label, **row}
        pos_rows.append(row)
        all_latencies.extend(row.pop("mask_step_latencies"))

    for label, text in NEGATIVE:
        row = _replay_one(bundle, text, expect_positive=False)
        row = {"label": label, **row}
        neg_rows.append(row)
        all_latencies.extend(row.pop("mask_step_latencies"))

    pos_pass = all(r["pass"] for r in pos_rows)
    neg_pass = all(r["pass"] for r in neg_rows)
    return {
        "positive": pos_rows,
        "negative": neg_rows,
        "positive_pass": pos_pass,
        "negative_pass": neg_pass,
        "pass": pos_pass and neg_pass,
        "mask_step_latency_seconds": {
            "n": len(all_latencies),
            "mean": (sum(all_latencies) / len(all_latencies)) if all_latencies else None,
            "max": max(all_latencies) if all_latencies else None,
            "min": min(all_latencies) if all_latencies else None,
        },
    }


def compare_replay_semantics(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """G6: compare semantic traces (not latency) across two full replays."""
    mismatches: list[dict[str, Any]] = []
    for side in ("positive", "negative"):
        for ra, rb in zip(a[side], b[side], strict=True):
            if ra["label"] != rb["label"]:
                mismatches.append({"side": side, "reason": "label_mismatch"})
                continue
            if ra["semantic_trace"] != rb["semantic_trace"]:
                mismatches.append(
                    {
                        "side": side,
                        "label": ra["label"],
                        "reason": "semantic_trace_mismatch",
                    }
                )
    return {
        "pass": not mismatches,
        "mismatches": mismatches,
        "compared_cases": len(a["positive"]) + len(a["negative"]),
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
