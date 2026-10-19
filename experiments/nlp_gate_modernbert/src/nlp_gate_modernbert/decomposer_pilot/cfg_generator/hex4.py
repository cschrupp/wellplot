"""Compact Hex4 grammars over Unicode scalar sets (for \\uXXXX productions)."""

from __future__ import annotations

from nlp_gate_modernbert.decomposer_pilot.cfg_generator.ast_nodes import (
    Alt,
    Atom,
    CharClass,
    CharRange,
    Group,
    Ident,
    Lit,
    Seq,
    alt,
    seq,
)


_HEX_CHARS = "0123456789ABCDEFabcdef"


def _hex_digit_class(allowed: set[str]) -> CharClass:
    # Collapse allowed hex digit characters into ranges where possible (ASCII order).
    codes = sorted({ord(c) for c in allowed})
    items: list[CharRange | int] = []
    i = 0
    while i < len(codes):
        lo = codes[i]
        hi = lo
        while i + 1 < len(codes) and codes[i + 1] == hi + 1:
            i += 1
            hi = codes[i]
        items.append(lo if lo == hi else CharRange(lo, hi))
        i += 1
    return CharClass(False, tuple(items))


def build_hex4_alt_for_codepoints(codepoints: set[int], rule_prefix: str) -> tuple[dict[str, Alt], str]:
    """Build rules recognizing exactly the 4 hex digits of each codepoint in the set.

    Uses a digit trie. Returns (rules, entry_rule_name).
    Both upper and lower hex spellings are admitted for A-F.
    """
    # Trie: map prefix -> set of next hex chars (canonical uppercase stored; both cases emitted)
    # Represent each codepoint as 4 uppercase hex digits; admit lower for A-F at match time.
    trie: dict[str, set[str]] = {"": set()}
    for cp in codepoints:
        if not (0 <= cp <= 0xFFFF):
            raise ValueError(f"hex4 codepoint out of range: {cp}")
        h = f"{cp:04X}"
        for i in range(4):
            prefix = h[:i]
            digit = h[i]
            trie.setdefault(prefix, set()).add(digit)
            trie.setdefault(h[: i + 1], set())

    rules: dict[str, Alt] = {}

    def node_name(prefix: str) -> str:
        if prefix == "":
            return rule_prefix
        return f"{rule_prefix}_{prefix}"

    for prefix, digits in sorted(trie.items(), key=lambda kv: (len(kv[0]), kv[0])):
        depth = len(prefix)
        if depth == 4:
            continue
        alts: list[Seq] = []
        for d in sorted(digits):
            cases = {d, d.lower()} if d.isalpha() else {d}
            dig_cc = _hex_digit_class(cases)
            child_prefix = prefix + d
            if depth == 3:
                # final digit — no child rule
                alts.append(seq(Atom(dig_cc)))
            else:
                child = node_name(child_prefix)
                alts.append(seq(Atom(dig_cc), Ident(child)))
        if not alts:
            # dead node (should not happen for prefixes that appear)
            continue
        rules[node_name(prefix)] = Alt(tuple(alts))

    return rules, rule_prefix


def build_hex4_alt_excluding(
    excluded: set[int],
    rule_prefix: str,
    *,
    also_exclude: set[int] | None = None,
) -> tuple[dict[str, Alt], str]:
    """Hex4 for all BMP codepoints except excluded ∪ also_exclude."""
    ban = set(excluded)
    if also_exclude:
        ban |= also_exclude
    allowed = {cp for cp in range(0x10000) if cp not in ban}
    return build_hex4_alt_for_codepoints(allowed, rule_prefix)


def hex4_range_rules(lo: int, hi: int, rule_prefix: str) -> tuple[dict[str, Alt], str]:
    return build_hex4_alt_for_codepoints(set(range(lo, hi + 1)), rule_prefix)
