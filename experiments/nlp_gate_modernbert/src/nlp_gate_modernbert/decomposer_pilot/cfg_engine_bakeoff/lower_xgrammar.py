"""Deterministic WELL-EBNF-1 → XGrammar EBNF lowering (syntax only)."""

from __future__ import annotations

import hashlib

LOWERER_ID = "well_ebnf1_to_xgrammar_ebnf.v1"
# Scalars that break XGrammar's single-line class/literal lexer when raw.
_FORCE_ESC = frozenset({0x0A, 0x0D, 0x2028, 0x2029})


def lowerer_source_sha256() -> str:
    from pathlib import Path

    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def lower_well_ebnf1_to_xgrammar_ebnf(well_text: str) -> str:
    """Strip WELL-EBNF-1 rule terminators; escape line-breaking scalars in lit/class.

    Preserves START as the root rule name (pass root_rule_name='START' to XGrammar).
    """
    out_lines: list[str] = []
    for line in well_text.split("\n"):
        if not line:
            continue
        if not line.endswith(" ;"):
            raise ValueError(f"WELL-EBNF-1 rule missing terminator: {line[:64]!r}")
        body = line[:-2]
        out_lines.append(_rewrite_body(body))
    return "\n".join(out_lines) + "\n"


def _rewrite_body(body: str) -> str:
    res: list[str] = []
    i = 0
    mode: str | None = None
    while i < len(body):
        ch = body[i]
        if mode is None:
            if ch == '"':
                mode = "lit"
                res.append(ch)
                i += 1
                continue
            if ch == "[":
                mode = "cls"
                res.append(ch)
                i += 1
                continue
            res.append(ch)
            i += 1
            continue
        if mode == "lit":
            if ch == "\\":
                res.append(body[i : i + 2])
                i += 2
                continue
            if ch == '"':
                mode = None
                res.append(ch)
                i += 1
                continue
            o = ord(ch)
            if o in _FORCE_ESC or o < 0x20:
                res.append(f"\\u{o:04X}")
                i += 1
                continue
            res.append(ch)
            i += 1
            continue
        # class
        if ch == "\\":
            if i + 1 < len(body) and body[i + 1] == "u" and i + 6 <= len(body):
                res.append(body[i : i + 6])
                i += 6
                continue
            if i + 1 < len(body) and body[i + 1] == "U" and i + 10 <= len(body):
                res.append(body[i : i + 10])
                i += 10
                continue
            res.append(body[i : i + 2])
            i += 2
            continue
        if ch == "]":
            mode = None
            res.append(ch)
            i += 1
            continue
        o = ord(ch)
        if o in _FORCE_ESC or o < 0x20:
            res.append(f"\\u{o:04X}")
            i += 1
            continue
        res.append(ch)
        i += 1
    return "".join(res)
