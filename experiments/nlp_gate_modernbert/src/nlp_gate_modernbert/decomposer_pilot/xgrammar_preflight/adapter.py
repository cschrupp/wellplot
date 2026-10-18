"""Exact future-pilot XGrammar → Transformers hard-mask adapter (synthetic logits only)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

import torch
import xgrammar as xgr
from transformers import AutoConfig, AutoTokenizer

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
    LOWERER_ID,
    lower_well_ebnf1_to_xgrammar_ebnf,
    lowerer_source_sha256,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import sha256_bytes
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.constants import (
    ADAPTER_ID,
    MASKED_LOGIT_VALUE,
    REQUIRED_XGRAMMAR,
    XGRAMMAR_NATIVE_GRAMMAR_SHA256,
)


class AdapterFailClosedError(RuntimeError):
    """Invalid transition or unauthorized adapter use."""


@dataclass
class CompiledConstraintPath:
    lowered_ebnf: str
    lowered_sha256: str
    grammar: Any
    compiled: Any
    tokenizer: Any
    tokenizer_info: Any
    vocab_size: int
    compile_seconds: float
    package_version: str
    lowerer_id: str
    lowerer_source_sha256: str
    snapshot_path: str


def compile_accepted_constraint_path(
    well_text: str, snapshot_path: str
) -> CompiledConstraintPath:
    """Compile accepted WELL-EBNF-1 → XGrammar against the pinned local tokenizer."""
    import importlib.metadata as md

    ver = md.version("xgrammar")
    if ver != REQUIRED_XGRAMMAR:
        raise AdapterFailClosedError(
            f"xgrammar version {ver!r} != required {REQUIRED_XGRAMMAR!r}"
        )
    lowered = lower_well_ebnf1_to_xgrammar_ebnf(well_text)
    lowered_sha = sha256_bytes(lowered.encode("utf-8"))
    if lowered_sha != XGRAMMAR_NATIVE_GRAMMAR_SHA256:
        raise AdapterFailClosedError(
            f"native grammar sha mismatch: got {lowered_sha} "
            f"expected {XGRAMMAR_NATIVE_GRAMMAR_SHA256}"
        )
    grammar = xgr.Grammar.from_ebnf(lowered, root_rule_name="START")
    tok = AutoTokenizer.from_pretrained(snapshot_path, local_files_only=True)
    cfg = AutoConfig.from_pretrained(snapshot_path, local_files_only=True)
    info = xgr.TokenizerInfo.from_huggingface(tok, vocab_size=cfg.vocab_size)
    compiler = xgr.GrammarCompiler(info)
    t0 = time.perf_counter()
    compiled = compiler.compile_grammar(grammar)
    compile_s = time.perf_counter() - t0
    return CompiledConstraintPath(
        lowered_ebnf=lowered,
        lowered_sha256=lowered_sha,
        grammar=grammar,
        compiled=compiled,
        tokenizer=tok,
        tokenizer_info=info,
        vocab_size=int(cfg.vocab_size),
        compile_seconds=compile_s,
        package_version=ver,
        lowerer_id=LOWERER_ID,
        lowerer_source_sha256=lowerer_source_sha256(),
        snapshot_path=snapshot_path,
    )


class PilotXGrammarHardMaskAdapter:
    """Hard-mask adapter intended for PILOT-01 Transformers generate().

    Preflight may only exercise this with synthetic logits. No model.forward /
    model.generate / real model logits.
    """

    def __init__(self, path: CompiledConstraintPath):
        self.path = path
        self._matcher: Any | None = None
        self._bitmask: Any | None = None
        self.reset()

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    def reset(self) -> None:
        self._matcher = xgr.GrammarMatcher(self.path.compiled)
        self._bitmask = xgr.allocate_token_bitmask(1, self.path.vocab_size)

    def fill_next_token_bitmask(self) -> Any:
        assert self._matcher is not None and self._bitmask is not None
        self._matcher.fill_next_token_bitmask(self._bitmask)
        return self._bitmask

    def _bit_allowed(self, token_id: int) -> bool:
        assert self._bitmask is not None
        word = int(self._bitmask[0, token_id // 32].item())
        return bool((word >> (token_id % 32)) & 1)

    def mask_digest(self) -> str:
        assert self._bitmask is not None
        raw = self._bitmask.detach().cpu().numpy().tobytes()
        return hashlib.sha256(raw).hexdigest()

    def apply_synthetic_logits(self, logits: torch.Tensor) -> torch.Tensor:
        """Apply hard mask to synthetic logits in-place (returns same tensor)."""
        if logits.dim() == 1:
            scores = logits.unsqueeze(0).contiguous()
            squeeze = True
        elif logits.dim() == 2:
            scores = logits.contiguous()
            squeeze = False
        else:
            raise AdapterFailClosedError(f"logits rank {logits.dim()} unsupported")
        if scores.shape[-1] < self.path.vocab_size:
            raise AdapterFailClosedError("logits vocab dim too small")
        self.fill_next_token_bitmask()
        device_type = scores.device.type
        work = scores if device_type == "cuda" else scores.to("cpu")
        assert self._bitmask is not None
        xgr.apply_token_bitmask_inplace(
            work, self._bitmask.to(work.device), vocab_size=self.path.vocab_size
        )
        if device_type != "cuda":
            scores.copy_(work.to(scores.device))
        return scores.squeeze(0) if squeeze else scores

    def accept_token(self, token_id: int) -> None:
        assert self._matcher is not None
        self.fill_next_token_bitmask()
        if not self._bit_allowed(int(token_id)):
            raise AdapterFailClosedError(f"blocked_token:{token_id}")
        if not self._matcher.accept_token(int(token_id)):
            raise AdapterFailClosedError(f"accept_token_false:{token_id}")

    def is_completed(self) -> bool:
        assert self._matcher is not None
        return bool(self._matcher.is_completed())

    def stop_token_allowed(self) -> dict[int, bool]:
        self.fill_next_token_bitmask()
        assert self._matcher is not None
        return {
            int(s): self._bit_allowed(int(s)) for s in self._matcher.stop_token_ids
        }

    def any_stop_allowed(self) -> bool:
        stops = self.stop_token_allowed()
        return any(stops.values()) if stops else False

    def transformers_logits_processor(self) -> Any:
        """Fresh HF LogitsProcessor for a future authorized generate() call."""
        return xgr.contrib.hf.LogitsProcessor(self.path.compiled)

    def has_repair_or_normalize(self) -> bool:
        return False


def run_synthetic_adapter_suite(path: CompiledConstraintPath) -> dict[str, Any]:
    """P5: synthetic-logits hard-mask / completion / reset evidence."""
    adapter = PilotXGrammarHardMaskAdapter(path)
    latencies: list[float] = []
    failures: list[str] = []

    # --- Reset determinism: two fresh adapters, identical first mask ---
    a1 = PilotXGrammarHardMaskAdapter(path)
    a2 = PilotXGrammarHardMaskAdapter(path)
    t0 = time.perf_counter()
    a1.fill_next_token_bitmask()
    latencies.append(time.perf_counter() - t0)
    a2.fill_next_token_bitmask()
    reset_identical = a1.mask_digest() == a2.mask_digest()
    if not reset_identical:
        failures.append("reset_mask_not_deterministic")

    # --- Synthetic logits: allowed stay finite; disallowed → -inf ---
    adapter.reset()
    logits = torch.full((path.vocab_size,), 1.0, dtype=torch.float32)
    t0 = time.perf_counter()
    masked = adapter.apply_synthetic_logits(logits.clone())
    latencies.append(time.perf_counter() - t0)
    adapter.fill_next_token_bitmask()
    # Sample a few allowed and blocked positions
    allowed_sample: list[int] = []
    blocked_sample: list[int] = []
    for tid in range(0, min(path.vocab_size, 4096)):
        if adapter._bit_allowed(tid):
            if len(allowed_sample) < 8:
                allowed_sample.append(tid)
        elif len(blocked_sample) < 8:
            blocked_sample.append(tid)
        if len(allowed_sample) >= 8 and len(blocked_sample) >= 8:
            break
    allowed_ok = all(torch.isfinite(masked[t]).item() for t in allowed_sample)
    blocked_ok = all(
        masked[t].item() == MASKED_LOGIT_VALUE or masked[t].item() == float("-inf")
        for t in blocked_sample
    )
    if not allowed_ok:
        failures.append("allowed_logits_not_finite")
    if not blocked_ok:
        failures.append("disallowed_logits_not_masked")

    # --- Positive string advances to completed + stop ---
    from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.fixtures import (
        POSITIVE,
    )

    pos_label, pos_text = POSITIVE[0]
    adapter.reset()
    ids = path.tokenizer.encode(pos_text, add_special_tokens=False)
    pos_ok = True
    completed = False
    stop_ok = False
    try:
        for tid in ids:
            t0 = time.perf_counter()
            adapter.accept_token(int(tid))
            latencies.append(time.perf_counter() - t0)
        completed = adapter.is_completed()
        stop_ok = adapter.any_stop_allowed()
        if not completed or not stop_ok:
            pos_ok = False
            failures.append(
                f"positive_incomplete:{pos_label}:completed={completed}:stop={stop_ok}"
            )
    except AdapterFailClosedError as exc:
        pos_ok = False
        failures.append(f"positive_accept_failed:{pos_label}:{exc}")

    # --- Invalid transition fail-closed ---
    adapter.reset()
    adapter.fill_next_token_bitmask()
    blocked_tid = next(
        (t for t in range(path.vocab_size) if not adapter._bit_allowed(t)), None
    )
    invalid_fail_closed = False
    if blocked_tid is None:
        failures.append("no_blocked_token_found")
    else:
        try:
            adapter.accept_token(int(blocked_tid))
            failures.append("blocked_token_accepted")
        except AdapterFailClosedError:
            invalid_fail_closed = True

    # --- HF processor path exists (not invoked via generate) ---
    proc = adapter.transformers_logits_processor()
    hf_processor_type = type(proc).__name__

    # Exercise HF processor with synthetic scores only (no model)
    adapter_hf = PilotXGrammarHardMaskAdapter(path)
    proc2 = adapter_hf.transformers_logits_processor()
    syn_ids = torch.zeros((1, 1), dtype=torch.long)  # prefills without accepting
    syn_scores = torch.full((1, path.vocab_size), 2.0, dtype=torch.float32)
    t0 = time.perf_counter()
    out_scores = proc2(syn_ids, syn_scores.clone())
    latencies.append(time.perf_counter() - t0)
    hf_masked = bool(torch.isneginf(out_scores).any().item())
    if not hf_masked:
        failures.append("hf_processor_did_not_mask")

    passed = (
        reset_identical
        and allowed_ok
        and blocked_ok
        and pos_ok
        and invalid_fail_closed
        and hf_masked
        and not adapter.has_repair_or_normalize()
        and not failures
    )
    return {
        "pass": passed,
        "adapter_id": ADAPTER_ID,
        "package_version": path.package_version,
        "lowered_sha256": path.lowered_sha256,
        "compile_seconds": path.compile_seconds,
        "vocab_size": path.vocab_size,
        "reset_mask_deterministic": reset_identical,
        "allowed_logits_remain_finite": allowed_ok,
        "disallowed_logits_masked_to_neginf": blocked_ok,
        "positive_case": {
            "label": pos_label,
            "n_tokens": len(ids),
            "pass": pos_ok,
            "completed": pos_ok and completed,
            "stop_allowed": pos_ok and stop_ok,
        },
        "invalid_transition_fail_closed": invalid_fail_closed,
        "hf_logits_processor": {
            "type": hf_processor_type,
            "synthetic_call_masked": hf_masked,
            "generate_invoked": False,
        },
        "no_repair_or_normalize": True,
        "failures": failures,
        "synthetic_mask_latency_seconds": {
            "n": len(latencies),
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            "max": max(latencies) if latencies else None,
            "min": min(latencies) if latencies else None,
        },
    }
