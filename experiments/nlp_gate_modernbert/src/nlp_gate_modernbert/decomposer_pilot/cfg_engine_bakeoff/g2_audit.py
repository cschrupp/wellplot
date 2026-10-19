"""Independent G2 audit: language-preserving XGrammar lowering proof.

Accepts already-produced XGrammar EBNF. Does not import or call the lowerer.
"""

from __future__ import annotations

import re
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import sha256_bytes

# Explicitly authorized scalars that may be rewritten to \uXXXX inside lit/class.
_FORCE_ESC = frozenset({0x0A, 0x0D, 0x2028, 0x2029})
_RULE_HEAD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*) ::= ")


def _source_rules(well_text: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    for line in well_text.split("\n"):
        if not line:
            continue
        if not line.endswith(" ;"):
            raise ValueError(f"source rule missing terminator: {line[:64]!r}")
        body = line[:-2]
        m = _RULE_HEAD.match(body)
        if not m:
            raise ValueError(f"bad source rule: {line[:64]!r}")
        name = m.group(1)
        expr = body[m.end() :]
        rules.append((name, expr))
    return rules


def _lowered_rules(lowered_text: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    for line in lowered_text.split("\n"):
        if not line:
            continue
        m = _RULE_HEAD.match(line)
        if not m:
            raise ValueError(f"bad lowered rule: {line[:64]!r}")
        name = m.group(1)
        expr = line[m.end() :]
        rules.append((name, expr))
    return rules


def _is_authorized_scalar(cp: int) -> bool:
    return cp in _FORCE_ESC or cp < 0x20


def _u4_escape(cp: int) -> str:
    return f"\\u{cp:04X}"


def _expr_authorized_only(src_expr: str, dst_expr: str) -> str | None:
    """Return None if dst differs from src only by authorized lit/class escapes.

    Outside literals/classes, expressions must be byte-identical.
    Inside literals/classes, a source scalar in the authorized set may appear in
    the target either unchanged or as \\uXXXX (uppercase hex). All other
    characters and pre-existing escape sequences must match byte-for-byte.
    """
    si = 0
    di = 0
    mode: str | None = None
    n_s = len(src_expr)
    n_d = len(dst_expr)

    while si < n_s and di < n_d:
        sc = src_expr[si]
        dc = dst_expr[di]

        if mode is None:
            if sc != dc:
                return f"outside_mismatch@{si}"
            if sc == '"':
                mode = "lit"
            elif sc == "[":
                mode = "cls"
            si += 1
            di += 1
            continue

        if mode == "lit":
            if sc == "\\":
                if si + 1 >= n_s or di + 1 >= n_d:
                    return f"lit_escape_truncated@{si}"
                if src_expr[si : si + 2] != dst_expr[di : di + 2]:
                    return f"lit_escape_mismatch@{si}"
                si += 2
                di += 2
                continue
            if sc == '"':
                if dc != '"':
                    return f"lit_close_mismatch@{si}"
                mode = None
                si += 1
                di += 1
                continue
            o = ord(sc)
            if _is_authorized_scalar(o):
                esc = _u4_escape(o)
                if dst_expr.startswith(esc, di):
                    si += 1
                    di += len(esc)
                    continue
                if dc == sc:
                    si += 1
                    di += 1
                    continue
                return f"unauthorized_lit_scalar@{si}"
            if sc != dc:
                return f"lit_char_mismatch@{si}"
            si += 1
            di += 1
            continue

        # character class
        if sc == "\\":
            # Preserve escape units identically (\\uXXXX, \\UXXXXXXXX, or \\X).
            if (
                si + 6 <= n_s
                and src_expr[si + 1] == "u"
                and di + 6 <= n_d
                and src_expr[si : si + 6] == dst_expr[di : di + 6]
            ):
                si += 6
                di += 6
                continue
            if (
                si + 10 <= n_s
                and src_expr[si + 1] == "U"
                and di + 10 <= n_d
                and src_expr[si : si + 10] == dst_expr[di : di + 10]
            ):
                si += 10
                di += 10
                continue
            if si + 1 >= n_s or di + 1 >= n_d:
                return f"cls_escape_truncated@{si}"
            if src_expr[si : si + 2] != dst_expr[di : di + 2]:
                return f"cls_escape_mismatch@{si}"
            si += 2
            di += 2
            continue
        if sc == "]":
            if dc != "]":
                return f"cls_close_mismatch@{si}"
            mode = None
            si += 1
            di += 1
            continue
        o = ord(sc)
        if _is_authorized_scalar(o):
            esc = _u4_escape(o)
            if dst_expr.startswith(esc, di):
                si += 1
                di += len(esc)
                continue
            if dc == sc:
                si += 1
                di += 1
                continue
            return f"unauthorized_cls_scalar@{si}"
        if sc != dc:
            return f"cls_char_mismatch@{si}"
        si += 1
        di += 1

    if si != n_s or di != n_d:
        return f"length_mismatch:src@{si}/{n_s}:dst@{di}/{n_d}"
    if mode is not None:
        return f"unclosed_{mode}"
    return None


def audit_xgrammar_lowering(
    well_text: str,
    lowered_ebnf: str,
    *,
    lowered_ebnf_replay: str | None = None,
) -> dict[str, Any]:
    """Independently audit already-produced XGrammar EBNF against WELL-EBNF-1 source.

    Parameters
    ----------
    well_text:
        Accepted WELL-EBNF-1 source grammar.
    lowered_ebnf:
        Already-produced XGrammar-native EBNF (caller-supplied; not generated here).
    lowered_ebnf_replay:
        Optional second production for byte-identical determinism proof.
    """
    sha_a = sha256_bytes(lowered_ebnf.encode("utf-8"))
    if lowered_ebnf_replay is None:
        byte_identical = True
        sha_b = sha_a
    else:
        byte_identical = lowered_ebnf == lowered_ebnf_replay
        sha_b = sha256_bytes(lowered_ebnf_replay.encode("utf-8"))

    src = _source_rules(well_text)
    dst = _lowered_rules(lowered_ebnf)

    src_names = [n for n, _ in src]
    dst_names = [n for n, _ in dst]
    same_count = len(src) == len(dst)
    same_ids = src_names == dst_names
    start_first = bool(src_names) and src_names[0] == "START" and bool(dst_names) and dst_names[0] == "START"
    one_to_one = same_count and same_ids

    unauthorized: list[dict[str, str]] = []
    if not same_count:
        unauthorized.append(
            {
                "rule": "*",
                "reason": f"rule_count_mismatch:src={len(src)}:dst={len(dst)}",
            }
        )
    elif not same_ids:
        for i, (sn, dn) in enumerate(zip(src_names, dst_names, strict=False)):
            if sn != dn:
                unauthorized.append(
                    {"rule": sn, "reason": f"name_mismatch:dst={dn}:index={i}"}
                )
                break
        if len(src_names) != len(dst_names):
            unauthorized.append({"rule": "*", "reason": "identifier_list_length"})
    else:
        for (sn, se), (dn, de) in zip(src, dst, strict=True):
            if sn != dn:
                unauthorized.append({"rule": sn, "reason": f"name_mismatch:{dn}"})
                continue
            reason = _expr_authorized_only(se, de)
            if reason is not None:
                unauthorized.append({"rule": sn, "reason": reason})

    authorized_only = not unauthorized

    passed = (
        byte_identical
        and sha_a == sha_b
        and same_count
        and same_ids
        and start_first
        and one_to_one
        and authorized_only
    )
    return {
        "pass": passed,
        "audit_mode": "independent_source_vs_produced_target",
        "source_rule_count": len(src),
        "target_rule_count": len(dst),
        "same_rule_count": same_count,
        "same_rule_identifiers": same_ids,
        "start_first": start_first,
        "one_to_one_mapping": one_to_one,
        "authorized_syntax_rewrites_only": authorized_only,
        "unauthorized_rewrites": unauthorized[:20],
        "repeated_lowering_byte_identical": byte_identical,
        "lowered_sha256": sha_a,
        "lowered_sha256_replay": sha_b,
        "authorized_transform_set": [
            "strip_rule_terminator_sp_semicolon",
            "escape_authorized_scalars_in_literals_and_classes",
        ],
        "force_escape_codepoints": sorted(_FORCE_ESC),
        "control_scalar_escape": "cp < 0x20",
    }
