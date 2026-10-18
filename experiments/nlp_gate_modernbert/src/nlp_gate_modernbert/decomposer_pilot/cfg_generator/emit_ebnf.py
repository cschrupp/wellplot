"""Serialize IR to canonical WELL-EBNF-1 UTF-8 bytes."""

from __future__ import annotations

from nlp_gate_modernbert.decomposer_pilot.cfg_generator.ast_nodes import (
    Alt,
    Atom,
    CharClass,
    CharRange,
    Group,
    Ident,
    Lit,
    Optional,
    Plus,
    Repeat,
    Seq,
    Star,
)


def _escape_char_for_literal(cp: int) -> str:
    if cp in (0x22, 0x5C):  # " \
        return "\\" + chr(cp)
    if cp == 0x0A:
        return "\\n"
    if cp == 0x0D:
        return "\\r"
    if cp == 0x09:
        return "\\t"
    if 0 <= cp <= 0x1F:
        return f"\\u{cp:04X}"
    if cp > 0xFFFF:
        return f"\\U{cp:08X}"
    return chr(cp)


def _escape_class_atom(cp: int) -> str:
    # Raw '-' forbidden as literal; ']' and '\' must escape; controls via \u
    if cp == 0x2D:  # -
        return "\\u002D"
    if cp == 0x5D:  # ]
        return "\\u005D"
    if cp == 0x5C:  # \
        return "\\\\"
    if cp == 0x0A:
        return "\\n"
    if cp == 0x0D:
        return "\\r"
    if cp == 0x09:
        return "\\t"
    if 0 <= cp <= 0x1F:
        return f"\\u{cp:04X}"
    if cp > 0xFFFF:
        return f"\\U{cp:08X}"
    return chr(cp)


def emit_literal(text: str) -> str:
    body = "".join(_escape_char_for_literal(ord(ch)) for ch in text)
    return f'"{body}"'


def emit_charclass(cc: CharClass) -> str:
    parts: list[str] = []
    for item in cc.items:
        if isinstance(item, CharRange):
            if item.lo == item.hi:
                parts.append(_escape_class_atom(item.lo))
            else:
                parts.append(
                    f"{_escape_class_atom(item.lo)}-{_escape_class_atom(item.hi)}"
                )
        else:
            parts.append(_escape_class_atom(item))
    inner = "".join(parts)
    if cc.negated:
        return f"[^{inner}]"
    return f"[{inner}]"


def emit_primary(primary: Ident | Lit | CharClass | Group) -> str:
    if isinstance(primary, Ident):
        return primary.name
    if isinstance(primary, Lit):
        return emit_literal(primary.text)
    if isinstance(primary, CharClass):
        return emit_charclass(primary)
    return f"({emit_expr(primary.expr)})"


def emit_atom(atom: Atom) -> str:
    base = emit_primary(atom.primary)
    if atom.suffix is None:
        return base
    if isinstance(atom.suffix, Optional):
        return base + "?"
    if isinstance(atom.suffix, Star):
        return base + "*"
    if isinstance(atom.suffix, Plus):
        return base + "+"
    if isinstance(atom.suffix, Repeat):
        return f"{base}{{{atom.suffix.m},{atom.suffix.n}}}"
    raise TypeError(f"unknown suffix: {atom.suffix!r}")


def emit_seq(s: Seq) -> str:
    return " ".join(emit_atom(a) for a in s.atoms)


def emit_expr(expr: Alt) -> str:
    return " | ".join(emit_seq(s) for s in expr.sequences)


def emit_rule(name: str, expr: Alt) -> str:
    return f"{name} ::= {emit_expr(expr)} ;"


def emit_grammar_file(rules: dict[str, Alt]) -> bytes:
    """Canonical rule order: START first, then remaining Identifiers by UTF-8 bytes."""
    if "START" not in rules:
        raise ValueError("grammar missing START")
    names = ["START"] + sorted((n for n in rules if n != "START"), key=lambda s: s.encode("utf-8"))
    lines = [emit_rule(n, rules[n]) for n in names]
    text = "\n".join(lines) + "\n"
    return text.encode("utf-8")
