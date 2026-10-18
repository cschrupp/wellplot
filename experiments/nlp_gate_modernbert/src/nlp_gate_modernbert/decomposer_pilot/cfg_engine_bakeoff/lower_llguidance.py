"""Deterministic WELL-EBNF-1 → llguidance Lark lowering (syntax only)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

LOWERER_ID = "well_ebnf1_to_llguidance_lark.v1"

_FORCE_ESC = frozenset({0x0A, 0x0D, 0x2028, 0x2029})


def lowerer_source_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def lower_well_ebnf1_to_llguidance_lark(well_text: str) -> str:
    """Convert WELL-EBNF-1 rules to llguidance Lark syntax.

    - START → start
    - ``Name ::= expr ;`` → ``Name: expr``
    - Character classes become Lark regex terminals ``/[...]/``
    - String literals preserved with Lark-safe escapes
    - ``\\u002D`` (and other escaped class atoms) become regex-safe forms
    """
    rules: list[str] = []
    for line in well_text.split("\n"):
        if not line:
            continue
        if not line.endswith(" ;"):
            raise ValueError(f"WELL-EBNF-1 rule missing terminator: {line[:64]!r}")
        body = line[:-2]
        name, _, expr = body.partition(" ::= ")
        if not _ or not name or not expr:
            raise ValueError(f"bad rule header: {line[:64]!r}")
        # llguidance Lark rejects CamelCase identifiers; lowercase is language-preserving.
        lark_name = "start" if name == "START" else name.lower()
        rules.append(f"{lark_name}: {_expr_to_lark(expr)}")
    return "%llguidance {}\n\n" + "\n".join(rules) + "\n"


def _expr_to_lark(expr: str) -> str:
    # Split alternatives on ' | ' outside of strings/classes/groups.
    alts = _split_top(expr, " | ")
    return " | ".join(_sequence_to_lark(a) for a in alts)


def _sequence_to_lark(seq: str) -> str:
    atoms = _split_top(seq, " ")
    return " ".join(_atom_to_lark(a) for a in atoms)


def _atom_to_lark(atom: str) -> str:
    # Primary + optional suffix
    primary, suffix = _split_suffix(atom)
    core = _primary_to_lark(primary)
    return core + (suffix or "")


def _split_suffix(atom: str) -> tuple[str, str | None]:
    if atom.endswith("?"):
        return atom[:-1], "?"
    if atom.endswith("*"):
        return atom[:-1], "*"
    if atom.endswith("+"):
        return atom[:-1], "+"
    m = re.fullmatch(r"(.+)\{(\d+),(\d+)\}", atom)
    if m:
        return m.group(1), "{" + m.group(2) + "," + m.group(3) + "}"
    return atom, None


def _primary_to_lark(primary: str) -> str:
    if primary.startswith('"') and primary.endswith('"'):
        return _literal_to_lark(primary)
    if primary.startswith("[") and primary.endswith("]"):
        return _class_to_lark_regex(primary)
    if primary.startswith("(") and primary.endswith(")"):
        return "(" + _expr_to_lark(primary[1:-1]) + ")"
    # identifier — lowercase for llguidance Lark identifier rules
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", primary):
        return "start" if primary == "START" else primary.lower()
    raise ValueError(f"unhandled primary: {primary[:80]!r}")


def _literal_to_lark(lit: str) -> str:
    # lit includes surrounding quotes; decode WELL escapes then re-emit Lark string
    inner = lit[1:-1]
    chars: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\":
            if i + 1 >= len(inner):
                raise ValueError("truncated escape in literal")
            n = inner[i + 1]
            mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
            if n in mapping:
                chars.append(mapping[n])
                i += 2
                continue
            if n == "u" and i + 6 <= len(inner):
                chars.append(chr(int(inner[i + 2 : i + 6], 16)))
                i += 6
                continue
            if n == "U" and i + 10 <= len(inner):
                chars.append(chr(int(inner[i + 2 : i + 10], 16)))
                i += 10
                continue
            raise ValueError(f"bad literal escape at {inner[i:i+4]!r}")
        chars.append(inner[i])
        i += 1
    # Lark double-quoted string
    out = ['"']
    for ch in chars:
        o = ord(ch)
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or o in _FORCE_ESC:
            out.append(f"\\u{{{o:04x}}}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _class_to_lark_regex(cc: str) -> str:
    """Convert WELL-EBNF CharClass to Lark `/.../` regex character class."""
    assert cc[0] == "[" and cc[-1] == "]"
    body = cc[1:-1]
    negated = False
    if body.startswith("^"):
        negated = True
        body = body[1:]
    # Decode class items to list of (lo,hi) or singleton, then emit regex-safe.
    items: list[tuple[int, int]] = []
    i = 0

    def read_atom(s: str, j: int) -> tuple[int, int]:
        if j >= len(s):
            raise ValueError("truncated class atom")
        if s[j] == "\\":
            if j + 1 >= len(s):
                raise ValueError("truncated escape")
            n = s[j + 1]
            if n in "nrt\\\"\\]":
                mapping = {
                    "n": 0x0A,
                    "r": 0x0D,
                    "t": 0x09,
                    "\\": 0x5C,
                    '"': 0x22,
                    "]": 0x5D,
                }
                if n in mapping:
                    return mapping[n], j + 2
            if n == "u" and j + 6 <= len(s):
                return int(s[j + 2 : j + 6], 16), j + 6
            if n == "U" and j + 10 <= len(s):
                return int(s[j + 2 : j + 10], 16), j + 10
            raise ValueError(f"bad class escape {s[j:j+4]!r}")
        return ord(s[j]), j + 1

    while i < len(body):
        lo, i = read_atom(body, i)
        if i < len(body) and body[i] == "-" and i + 1 < len(body) and body[i + 1] != "]":
            i += 1
            hi, i = read_atom(body, i)
            items.append((lo, hi))
        else:
            items.append((lo, lo))

    def esc_cp(cp: int) -> str:
        if cp in (ord("\\"), ord("]"), ord("^"), ord("-"), ord("/")):
            return "\\" + chr(cp)
        if 0x20 <= cp <= 0x7E and cp not in (ord("["),):
            return chr(cp)
        return f"\\u{{{cp:04x}}}"

    parts = ["[^" if negated else "["]
    for lo, hi in items:
        if lo == hi:
            parts.append(esc_cp(lo))
        else:
            parts.append(esc_cp(lo) + "-" + esc_cp(hi))
    parts.append("]")
    return "/" + "".join(parts) + "/"


def _split_top(s: str, sep: str) -> list[str]:
    """Split on sep not inside quotes, classes, or groups."""
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    depth = 0
    mode: str | None = None
    while i < len(s):
        if mode is None and depth == 0 and s.startswith(sep, i):
            parts.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        ch = s[i]
        if mode is None:
            if ch == '"':
                mode = "lit"
                buf.append(ch)
                i += 1
                continue
            if ch == "[":
                mode = "cls"
                buf.append(ch)
                i += 1
                continue
            if ch == "(":
                depth += 1
                buf.append(ch)
                i += 1
                continue
            if ch == ")":
                depth -= 1
                buf.append(ch)
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if mode == "lit":
            buf.append(ch)
            if ch == "\\" and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                mode = None
            i += 1
            continue
        if mode == "cls":
            buf.append(ch)
            if ch == "\\" and i + 1 < len(s):
                buf.append(s[i + 1])
                i += 2
                continue
            if ch == "]":
                mode = None
            i += 1
            continue
    parts.append("".join(buf))
    return parts
