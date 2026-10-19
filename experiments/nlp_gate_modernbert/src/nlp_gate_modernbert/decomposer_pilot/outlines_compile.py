"""Compile Outlines JsonSchema + tokenizer-only outlines_core token guide (no generate)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def compile_json_schema(patched_schema_bytes: bytes) -> Any:
    """Build Outlines JsonSchema from exact patched UTF-8 JSON bytes.

    Raises on compile failure. Does not call model.generate / forward.
    """
    from outlines.types import JsonSchema

    text = patched_schema_bytes.decode("utf-8")
    # Pass exact string so Outlines does not re-serialize with ensure_ascii=True.
    return JsonSchema(text)


def compile_attestation(patched_schema_bytes: bytes) -> dict[str, Any]:
    js = compile_json_schema(patched_schema_bytes)
    schema_attr = getattr(js, "schema", None)
    return {
        "backend": "outlines.types.JsonSchema",
        "compiled": True,
        "schema_type": type(js).__qualname__,
        "schema_attr_present": schema_attr is not None,
        "input_bytes": len(patched_schema_bytes),
    }


def construct_token_level_constraint(
    *,
    persisted_schema_bytes: bytes,
    expected_schema_sha256: str,
    snapshot_path: Path,
) -> dict[str, Any]:
    """Build outlines_core Index + OutlinesCoreLogitsProcessor from persisted schema.

    Tokenizer-only: no AutoModelForCausalLM / weights / generate / forward / process_logits.
    """
    actual_sha = hashlib.sha256(persisted_schema_bytes).hexdigest()
    if actual_sha != expected_schema_sha256:
        raise ValueError(
            f"persisted schema sha mismatch: actual={actual_sha} "
            f"expected={expected_schema_sha256}"
        )

    from transformers import AutoTokenizer

    from outlines.backends.outlines_core import (
        OutlinesCoreBackend,
        OutlinesCoreLogitsProcessor,
    )
    from outlines.models.transformers import TransformerTokenizer
    from outlines_core import Index
    from outlines_core.json_schema import build_regex_from_schema

    tokenizer = AutoTokenizer.from_pretrained(
        str(snapshot_path), local_files_only=True
    )
    adapter = TransformerTokenizer(tokenizer)
    vocabulary = OutlinesCoreBackend.create_outlines_core_vocabulary(
        adapter.get_vocab(),
        adapter.eos_token_id,
        adapter.eos_token,
        adapter.convert_token_to_string,
    )
    schema_text = persisted_schema_bytes.decode("utf-8")
    regex = build_regex_from_schema(schema_text)
    index = Index(regex, vocabulary)
    processor = OutlinesCoreLogitsProcessor(index, "torch")

    vocab = adapter.get_vocab()
    return {
        "backend": "outlines_core",
        "construction": "PASS",
        "constraint_schema_sha256": actual_sha,
        "tokenizer_snapshot": str(Path(snapshot_path).resolve()),
        "tokenizer_class": type(tokenizer).__qualname__,
        "tokenizer_adapter_class": type(adapter).__qualname__,
        "local_files_only": True,
        "vocab_size": len(vocab),
        "eos_token_id": adapter.eos_token_id,
        "eos_token": adapter.eos_token,
        "pad_token_id": getattr(tokenizer, "pad_token_id", None),
        "bos_token_id": getattr(tokenizer, "bos_token_id", None),
        "vocabulary_class": type(vocabulary).__module__
        + "."
        + type(vocabulary).__qualname__,
        "index_type": type(index).__module__ + "." + type(index).__qualname__,
        "logits_processor_type": (
            type(processor).__module__ + "." + type(processor).__qualname__
        ),
        "tensor_library_name": "torch",
        "model_weights_loaded": False,
        "model_forward_calls": 0,
        "model_generate_calls": 0,
        "process_logits_invoked": False,
    }
