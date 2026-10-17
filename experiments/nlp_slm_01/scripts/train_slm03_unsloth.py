#!/usr/bin/env python3
"""SLM-03: Unsloth QLoRA fine-tune of Qwen3-1.7B on D5-grounded trainable SFT.

Run with Unsloth Studio Python (CUDA), e.g.:
  ~/.unsloth/studio/unsloth_studio/bin/python scripts/train_slm03_unsloth.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Unsloth must import before transformers/trl
import unsloth  # noqa: F401
from unsloth import FastLanguageModel
from datasets import Dataset
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runners.common import SYSTEM_PROMPT, assemble_user_payload  # noqa: E402
from well_ir.version import WELL_IR_VERSION  # noqa: E402

DEFAULT_MODEL = (
    ROOT
    / "artifacts"
    / "modelscope_cache"
    / "models"
    / "Qwen--Qwen3-1.7B"
    / "snapshots"
    / "master"
)


def rows_to_dataset(path: Path, tokenizer) -> Dataset:
    texts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": assemble_user_payload(row["utterance"], row["workspace"], row["d0"]),
            },
            {"role": "assistant", "content": json.dumps(row["output"], sort_keys=True)},
        ]
        try:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
                enable_thinking=False,
            )
        except TypeError:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
        texts.append(text)
    return Dataset.from_dict({"text": texts})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--train", type=Path, default=ROOT / "artifacts/exports/dev_sft.jsonl")
    parser.add_argument("--val", type=Path, default=ROOT / "artifacts/exports/val_sft.jsonl")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "artifacts/adapters/slm03_qwenv17_qlora",
    )
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=20251013)
    args = parser.parse_args()

    if not args.model.exists():
        raise SystemExit(f"Base model missing: {args.model}")
    if not args.train.exists():
        raise SystemExit(f"Train export missing: {args.train}")

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Loading 4-bit base from {args.model}", flush=True)
    print(f"WELL_IR_VERSION={WELL_IR_VERSION}", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.model),
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
        dtype=None,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
    )

    train_ds = rows_to_dataset(args.train, tokenizer)
    val_ds = rows_to_dataset(args.val, tokenizer) if args.val.exists() else None
    print(f"train_rows={len(train_ds)} val_rows={len(val_ds) if val_ds else 0}", flush=True)

    sft_args = SFTConfig(
        output_dir=str(args.out),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        logging_steps=5,
        save_strategy="epoch",
        eval_strategy="epoch" if val_ds is not None else "no",
        load_best_model_at_end=bool(val_ds is not None),
        metric_for_best_model="eval_loss" if val_ds is not None else None,
        greater_is_better=False if val_ds is not None else None,
        warmup_ratio=0.05,
        seed=args.seed,
        max_length=args.max_seq_length,
        dataset_text_field="text",
        packing=False,
        report_to=[],
        fp16=False,
        bf16=True,
        optim="adamw_8bit",
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=sft_args,
    )
    trainer.train()
    model.save_pretrained(str(args.out))
    tokenizer.save_pretrained(str(args.out))

    meta = {
        "experiment": "SLM-03",
        "corpus_revision": "d5-grounded-300-r1",
        "base_model_path": str(args.model.resolve()),
        "base_model_id": "Qwen/Qwen3-1.7B",
        "train_export": str(args.train),
        "val_export": str(args.val) if args.val else None,
        "n_train": len(train_ds),
        "n_val": len(val_ds) if val_ds else 0,
        "max_seq_length": args.max_seq_length,
        "epochs": args.epochs,
        "lr": args.lr,
        "seed": args.seed,
        "method": "unsloth_qlora_4bit",
        "lora_r": 16,
        "lora_alpha": 32,
        "enable_thinking": False,
        "well_ir_version": WELL_IR_VERSION,
        "trainable_support_levels": [
            "d5_current",
            "d5_context_lowerable",
            "envelope_only",
        ],
        "prompt": "SLM-03 SYSTEM_PROMPT 1.2-candidate + single-turn user payload (Q1-style)",
    }
    (args.out / "slm03_train_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "ok", "adapter": str(args.out), **meta}, indent=2))


if __name__ == "__main__":
    main()
