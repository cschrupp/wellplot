"""Frozen inference configuration pins (PREFLIGHT-01 Q3/Q4)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Generation budget: generated tokens only; identical for all six; no adaptive extension.
MAX_NEW_TOKENS = 1024

# Provenance seed under greedy decode (do_sample=False). Same for all six; no per-case reseeding.
SEED = 20261016

TEMPERATURE = 0.0
DO_SAMPLE = False
THINKING_ENABLED = False

# Device/dtype policy for PILOT-01 (recorded at preflight; no model load here).
DTYPE_POLICY = "float16_if_cuda_else_float32"
DEVICE_POLICY = "cuda_if_available_else_cpu"

# RNG init order for PILOT-01 (when inference is authorized):
RNG_POLICY = (
    "random.seed(SEED); "
    "numpy.random.seed(SEED); "
    "torch.manual_seed(SEED); "
    "torch.cuda.manual_seed_all(SEED) if cuda"
)

INFERENCE_CONFIG_VERSION = "decomposer_pilot_preflight_01.inference.v1"


def resolve_runtime_device_dtype() -> dict[str, Any]:
    """Record intended runtime device/dtype without loading model weights."""
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        dtype = "float16" if cuda else "float32"
        device = "cuda" if cuda else "cpu"
        torch_version = getattr(torch, "__version__", None)
    except ImportError:  # pragma: no cover
        cuda = False
        dtype = "float32"
        device = "cpu"
        torch_version = None
    return {
        "cuda_available": cuda,
        "device": device,
        "dtype": dtype,
        "torch_version": torch_version,
        "dtype_policy": DTYPE_POLICY,
        "device_policy": DEVICE_POLICY,
    }


def inference_config_dict() -> dict[str, Any]:
    runtime = resolve_runtime_device_dtype()
    return {
        "version": INFERENCE_CONFIG_VERSION,
        "max_new_tokens": MAX_NEW_TOKENS,
        "seed": SEED,
        "temperature": TEMPERATURE,
        "do_sample": DO_SAMPLE,
        "thinking_enabled": THINKING_ENABLED,
        "thinking_disable_mechanism": "apply_chat_template(..., enable_thinking=False)",
        "rng_policy": RNG_POLICY,
        "runtime": runtime,
        "adapters": "NONE",
        "auto_download": False,
        "fallback_model": "NONE",
    }


def inference_config_sha256() -> str:
    payload = json.dumps(
        inference_config_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
