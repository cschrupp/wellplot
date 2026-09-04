###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Serialization helpers for provider prompt context."""

from __future__ import annotations

import json


def compact_prompt_json(value: object) -> str:
    """Serialize prompt context without whitespace that adds no semantic value."""
    return json.dumps(value, default=str, separators=(",", ":"))
