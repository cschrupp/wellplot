"""JSON Schema export from canonical Pydantic WELL-IR models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .envelopes import WellIrResult
from .version import WELL_IR_SCHEMA_ID, WELL_IR_VERSION


def well_ir_json_schema() -> dict[str, Any]:
    """Return JSON Schema derived from the Pydantic WellIrResult union."""
    schema = TypeAdapter(WellIrResult).json_schema()
    schema["$id"] = WELL_IR_SCHEMA_ID
    schema["title"] = f"WELL-IR {WELL_IR_VERSION}"
    return schema


def write_json_schema(destination: str | Path) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(well_ir_json_schema(), indent=2) + "\n", encoding="utf-8")
    return path
