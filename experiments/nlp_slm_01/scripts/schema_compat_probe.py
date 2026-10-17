#!/usr/bin/env python3
"""Early WELL-IR schema compatibility probe (Pydantic / Outlines / llama.cpp notes)."""

from __future__ import annotations

import json
from pathlib import Path

from well_ir.schema import well_ir_json_schema, write_json_schema

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmark" / "schema"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    schema_path = write_json_schema(OUT / "well_ir_v1.json")
    schema = well_ir_json_schema()

    pydantic_ok = True
    outlines_status = "NOT_INSTALLED"
    try:
        import outlines  # noqa: F401

        try:
            # Prefer compiling from Pydantic model when available
            from well_ir.envelopes import WellIrResult

            _ = WellIrResult
            outlines_status = "IMPORT_OK_COMPILE_DEFERRED_TO_RUNTIME"
        except Exception as exc:  # noqa: BLE001
            outlines_status = f"ERROR:{exc}"
    except ImportError:
        outlines_status = "NOT_INSTALLED"

    llama_status = "KNOWN_LIMITATIONS"
    notes = [
        "llama.cpp JSON-schema→grammar supports a subset of JSON Schema.",
        "Canonical WELL-IR schema remains authoritative; use a projection if needed.",
        "Do not weaken WELL-IR semantics solely for llama.cpp compatibility.",
    ]

    report = {
        "pydantic_validation": "PASS" if pydantic_ok else "FAIL",
        "outlines_compile": outlines_status,
        "llama_cpp_json_schema": llama_status,
        "schema_path": str(schema_path.relative_to(ROOT)),
        "schema_title": schema.get("title"),
        "notes": notes,
    }
    (OUT / "compat_probe.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
