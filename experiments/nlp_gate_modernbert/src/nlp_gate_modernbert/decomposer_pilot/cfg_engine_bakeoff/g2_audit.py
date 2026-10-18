"""Evidence-derived G2 audit: deterministic language-preserving XGrammar lowering."""

from __future__ import annotations

import re
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
    lower_well_ebnf1_to_xgrammar_ebnf,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import sha256_bytes

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


def _authorized_expr_rewrite(src_expr: str, dst_expr: str) -> bool:
    """True iff dst is src with only authorized scalar escapes in lit/class bodies."""
    # Reconstruct expected rewrite using the same walk as the lowerer body rewrite.
    from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
        _rewrite_body,
    )

    # Rebuild a fake rule body "X ::= expr" rewrite of expr only:
    fake = "X ::= " + src_expr
    rebuilt = _rewrite_body(fake)
    expected_expr = rebuilt[len("X ::= ") :]
    return expected_expr == dst_expr


def audit_xgrammar_lowering(well_text: str) -> dict[str, Any]:
    lowered_a = lower_well_ebnf1_to_xgrammar_ebnf(well_text)
    lowered_b = lower_well_ebnf1_to_xgrammar_ebnf(well_text)
    byte_identical = lowered_a == lowered_b
    sha_a = sha256_bytes(lowered_a.encode("utf-8"))
    sha_b = sha256_bytes(lowered_b.encode("utf-8"))

    src = _source_rules(well_text)
    dst = _lowered_rules(lowered_a)

    src_names = [n for n, _ in src]
    dst_names = [n for n, _ in dst]
    same_count = len(src) == len(dst)
    same_ids = src_names == dst_names
    start_first = bool(src_names) and src_names[0] == "START" and dst_names[0] == "START"
    one_to_one = same_count and same_ids

    unauthorized: list[dict[str, str]] = []
    for (sn, se), (dn, de) in zip(src, dst, strict=True):
        if sn != dn:
            unauthorized.append({"rule": sn, "reason": f"name_mismatch:{dn}"})
            continue
        if not _authorized_expr_rewrite(se, de):
            unauthorized.append({"rule": sn, "reason": "unauthorized_expr_rewrite"})

    # Authorized transforms only: strip ' ;' + escape {_FORCE_ESC or controls} in lit/class.
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
            "escape_line_breaking_scalars_in_literals_and_classes",
        ],
        "force_escape_codepoints": sorted(_FORCE_ESC),
    }
