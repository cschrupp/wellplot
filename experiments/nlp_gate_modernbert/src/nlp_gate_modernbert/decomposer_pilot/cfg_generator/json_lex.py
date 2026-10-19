"""Shared JSON lexical nonterminals (Q5/Q6/Q9/T12) for WELL-EBNF-1 emission."""

from __future__ import annotations

import sys
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_generator.ast_nodes import (
    Alt,
    Atom,
    CharClass,
    CharRange,
    Ident,
    Lit,
    Seq,
    alt,
    opt,
    plus,
    seq,
    star,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_generator.hex4 import (
    build_hex4_alt_excluding,
    build_hex4_alt_for_codepoints,
    hex4_range_rules,
)

# Pattern frozen on ClosedSemanticQuery text/local_ref in the patched schema.
NONEMPTY_PATTERN = ".*\\S.*"


def python_strip_whitespace_codepoints() -> list[int]:
    """Code points c where chr(c).strip() == '' (excludes surrogates)."""
    out: list[int] = []
    for cp in range(0x110000):
        if 0xD800 <= cp <= 0xDFFF:
            continue
        if chr(cp).strip() == "":
            out.append(cp)
    return out


def _ranges_from_codepoints(cps: list[int]) -> tuple[CharRange | int, ...]:
    if not cps:
        return ()
    cps = sorted(cps)
    items: list[CharRange | int] = []
    lo = hi = cps[0]
    for cp in cps[1:]:
        if cp == hi + 1:
            hi = cp
        else:
            items.append(lo if lo == hi else CharRange(lo, hi))
            lo = hi = cp
    items.append(lo if lo == hi else CharRange(lo, hi))
    return tuple(items)


def _rule(expr: Alt | Seq) -> Alt:
    return expr if isinstance(expr, Alt) else Alt((expr,))


def install_json_lexicals(rules: dict[str, Alt], provenance: dict[str, Any]) -> None:
    """Install JsonString, NonemptyJsonString, JsonNumber, true/false/null into rules."""
    ws = python_strip_whitespace_codepoints()
    ws_bmp = {cp for cp in ws if cp <= 0xFFFF}
    provenance["python_version"] = sys.version.split()[0]
    provenance["python_strip_whitespace_codepoints"] = list(ws)
    provenance["q5_nonempty_pattern"] = NONEMPTY_PATTERN

    # R4: lone surrogate \\uXXXX halves are illegal as standalone atoms.
    # Valid high+low surrogate pairs remain legal via JsonSurrogatePair.
    surrogates = set(range(0xD800, 0xE000))
    provenance["r4_surrogate_lexical_narrowing"] = {
        "statement": (
            "Ordinary \\uXXXX surrogate halves are NOT legal standalone JSON string "
            "atoms on the canonical generation surface. Valid high+low surrogate "
            "pairs remain legal. Unpaired high/low surrogate escapes are grammar-rejected."
        ),
        "permitted_canonical_lexical_narrowing": True,
    }

    # BMP \\uXXXX excluding surrogates (used by ordinary JsonUnicodeEscape).
    bmp_non_sur_rules, bmp_non_sur = build_hex4_alt_excluding(
        surrogates, "JsonBmpNonSurHex4"
    )
    rules.update(bmp_non_sur_rules)

    # Non-whitespace BMP \\uXXXX (exclude strip-whitespace and surrogates)
    non_ws_hex_rules, non_ws_hex = build_hex4_alt_excluding(
        ws_bmp, "NonWsHex4", also_exclude=surrogates
    )
    rules.update(non_ws_hex_rules)

    ws_hex_rules, ws_hex = build_hex4_alt_for_codepoints(ws_bmp, "WsHex4")
    rules.update(ws_hex_rules)

    high_sur_rules, high_sur = hex4_range_rules(0xD800, 0xDBFF, "HighSurHex4")
    low_sur_rules, low_sur = hex4_range_rules(0xDC00, 0xDFFF, "LowSurHex4")
    rules.update(high_sur_rules)
    rules.update(low_sur_rules)

    rules["JsonSurrogatePair"] = _rule(
        seq(Lit("\\u"), Ident(high_sur), Lit("\\u"), Ident(low_sur))
    )

    # Unescaped characters (UTF-8 scalars except " \ controls; surrogates illegal unescaped)
    json_unescaped_forbidden = {0x22, 0x5C} | set(range(0x00, 0x20)) | surrogates
    non_ws_unescaped_forbidden = json_unescaped_forbidden | set(ws)
    non_ws_unescaped_cps = [
        cp for cp in range(0x110000) if cp not in non_ws_unescaped_forbidden
    ]
    ws_unescaped_cps = [cp for cp in ws if cp not in json_unescaped_forbidden]

    rules["NonWsUnescaped"] = _rule(
        seq(Atom(CharClass(False, _ranges_from_codepoints(non_ws_unescaped_cps))))
    )
    rules["WsUnescaped"] = _rule(
        seq(Atom(CharClass(False, _ranges_from_codepoints(ws_unescaped_cps))))
    )
    rules["JsonUnescaped"] = alt(Ident("NonWsUnescaped"), Ident("WsUnescaped"))

    rules["NonWsSimpleEscape"] = alt(
        Lit('\\"'),
        Lit("\\\\"),
        Lit("\\/"),
        Lit("\\b"),
    )
    rules["WsSimpleEscape"] = alt(
        Lit("\\f"),
        Lit("\\n"),
        Lit("\\r"),
        Lit("\\t"),
    )
    rules["JsonSimpleEscape"] = alt(
        Ident("NonWsSimpleEscape"), Ident("WsSimpleEscape")
    )

    rules["NonWsUnicodeEscape"] = _rule(seq(Lit("\\u"), Ident(non_ws_hex)))
    rules["WsUnicodeEscape"] = _rule(seq(Lit("\\u"), Ident(ws_hex)))
    # R4: no lone surrogate halves via ordinary \\uXXXX.
    rules["JsonUnicodeEscape"] = _rule(seq(Lit("\\u"), Ident(bmp_non_sur)))

    rules["NonWsDecodeAtom"] = alt(
        Ident("NonWsUnescaped"),
        Ident("NonWsSimpleEscape"),
        Ident("NonWsUnicodeEscape"),
        Ident("JsonSurrogatePair"),
    )
    rules["JsonAtom"] = alt(
        Ident("JsonUnescaped"),
        Ident("JsonSimpleEscape"),
        Ident("JsonUnicodeEscape"),
        Ident("JsonSurrogatePair"),
    )

    rules["JsonString"] = _rule(
        seq(Lit('"'), star(Ident("JsonAtom")), Lit('"'))
    )
    rules["NonemptyJsonString"] = _rule(
        seq(
            Lit('"'),
            star(Ident("JsonAtom")),
            Ident("NonWsDecodeAtom"),
            star(Ident("JsonAtom")),
            Lit('"'),
        )
    )

    digit = CharClass(False, (CharRange(0x30, 0x39),))
    nonzero = CharClass(False, (CharRange(0x31, 0x39),))
    rules["JsonDigits"] = alt(
        Lit("0"),
        seq(Atom(nonzero), star(Atom(digit))),
    )
    rules["JsonFrac"] = _rule(seq(Lit("."), plus(Atom(digit))))
    rules["JsonExp"] = _rule(
        seq(
            Atom(CharClass(False, (0x65, 0x45))),
            opt(Atom(CharClass(False, (0x2B, 0x2D)))),
            plus(Atom(digit)),
        )
    )
    rules["JsonNumber"] = _rule(
        seq(
            opt(Lit("-")),
            Ident("JsonDigits"),
            opt(Ident("JsonFrac")),
            opt(Ident("JsonExp")),
        )
    )

    rules["JsonTrue"] = _rule(seq(Lit("true")))
    rules["JsonFalse"] = _rule(seq(Lit("false")))
    rules["JsonNull"] = _rule(seq(Lit("null")))
    rules["JsonBool"] = alt(Ident("JsonTrue"), Ident("JsonFalse"))
