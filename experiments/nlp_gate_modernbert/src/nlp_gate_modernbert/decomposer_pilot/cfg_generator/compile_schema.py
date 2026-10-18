"""Mechanical JSON Schema → WELL-EBNF-1 IR transforms (Q1–Q10 / T11–T20)."""

from __future__ import annotations

import json
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_generator.ast_nodes import (
    Alt,
    Atom,
    Group,
    Ident,
    Lit,
    Optional,
    Seq,
    Star,
    alt,
    seq,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_generator.errors import GeneratorFail
from nlp_gate_modernbert.decomposer_pilot.cfg_generator.json_lex import NONEMPTY_PATTERN

IGNORE_KEYS = frozenset({"title", "default"})

HANDLED_KEYS = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "anyOf",
        "const",
        "enum",
        "items",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "type",
        "title",
        "default",
    }
)

MAP_LIKE_ALLOWLIST = frozenset(
    {
        "#/$defs/ClosedNormalizedTask/properties/produces_binds",
    }
)


def _as_alt(expr: Alt | Seq) -> Alt:
    return expr if isinstance(expr, Alt) else Alt((expr,))


def _check_unknown_keywords(
    node: dict[str, Any], path: str, coverage: dict[str, Any]
) -> None:
    unknown = set(node.keys()) - HANDLED_KEYS
    for k in sorted(unknown):
        coverage["unrecognized_semantic_keywords"].append({"path": path, "keyword": k})
        raise GeneratorFail(
            "UNSUPPORTED_SCHEMA_CONSTRUCT",
            f"unrecognized semantic keyword {k!r} at {path}",
        )


def _safe_ident(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    if not safe or safe[0].isdigit():
        safe = "N_" + safe
    return safe


class SchemaCompiler:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.rules: dict[str, Alt] = {}
        self.ledger: list[dict[str, str]] = []
        self.coverage: dict[str, Any] = {
            "schema_constructs_encountered": [],
            "schema_constructs_transformed": [],
            "schema_constructs_rejected": [],
            "unrecognized_semantic_keywords": [],
            "silently_ignored_semantic_keywords": [],
        }
        self._nt_seq = 0
        self._compiling: set[str] = set()

    def _note(self, path: str, construct: str, transform: str) -> None:
        self.coverage["schema_constructs_encountered"].append(
            {"path": path, "construct": construct}
        )
        self.coverage["schema_constructs_transformed"].append(
            {"path": path, "construct": construct, "transform": transform}
        )
        self.ledger.append({"path": path, "transform": transform})

    def _fresh(self, prefix: str) -> str:
        self._nt_seq += 1
        return _safe_ident(f"{prefix}_{self._nt_seq}")

    def compile_root(self) -> None:
        root_name = "ClosedNormalizedProgram"
        self._note("$", "root_object", "CLOSED_OBJECT")
        self.rules[root_name] = self._compile_object(self.schema, "$", root_name)
        self.rules["START"] = _as_alt(seq(Ident(root_name)))
        self._note("START", "start_symbol", "START_ROOT")
        for name in self.schema.get("$defs", {}):
            self._ensure_def(name)

    def _ensure_def(self, name: str) -> str:
        if name in self.rules or name in self._compiling:
            return name
        defs = self.schema.get("$defs", {})
        if name not in defs:
            raise GeneratorFail("ref_resolution_failure", name)
        self._compiling.add(name)
        path = f"#/$defs/{name}"
        # compile_node populates self.rules[name] for named constructs; do not
        # overwrite with a self-reference wrapper.
        self.compile_node(defs[name], path, preferred_name=name)
        if name not in self.rules:
            raise GeneratorFail(
                "UNSUPPORTED_SCHEMA_CONSTRUCT",
                f"$defs/{name} did not install a named rule",
            )
        self._compiling.discard(name)
        return name

    def compile_node(
        self, node: dict[str, Any], path: str, *, preferred_name: str | None = None
    ) -> Alt:
        _check_unknown_keywords(node, path, self.coverage)

        if "$ref" in node:
            return self._compile_ref(node, path)
        if "oneOf" in node:
            return self._compile_one_of(node, path, preferred_name=preferred_name)
        if "anyOf" in node:
            return self._compile_any_of(node, path, preferred_name=preferred_name)
        if "enum" in node:
            return self._compile_enum(node, path)
        if "const" in node:
            return self._compile_const(node, path)

        t = node.get("type")
        if t == "object" or ("properties" in node and t is None):
            nt = preferred_name or self._fresh("Object")
            if nt not in self.rules:
                self.rules[nt] = self._compile_object(node, path, nt)
            return _as_alt(seq(Ident(nt)))
        if t == "array":
            return self._compile_array(node, path, preferred_name=preferred_name)
        if t == "string":
            return self._compile_string(node, path)
        if t == "number":
            self._note(path, "number", "JSON_NUMBER")
            return _as_alt(seq(Ident("JsonNumber")))
        if t == "integer":
            raise GeneratorFail(
                "q6_or_t15_numeric_unrepresentable",
                f"integer site at {path}",
            )
        if t == "boolean":
            self._note(path, "boolean", "JSON_BOOL")
            return _as_alt(seq(Ident("JsonBool")))
        if t == "null":
            self._note(path, "null", "JSON_NULL")
            return _as_alt(seq(Ident("JsonNull")))

        raise GeneratorFail("UNSUPPORTED_SCHEMA_CONSTRUCT", f"unhandled node at {path}")

    def _compile_ref(self, node: dict[str, Any], path: str) -> Alt:
        ref = node["$ref"]
        self._note(path, "$ref", f"REF({ref})")
        if not ref.startswith("#/$defs/"):
            raise GeneratorFail("ref_resolution_failure", ref)
        name = ref[len("#/$defs/") :]
        if "/" in name or not name:
            raise GeneratorFail("ref_resolution_failure", ref)
        self._ensure_def(name)
        return _as_alt(seq(Ident(name)))

    def _compile_one_of(
        self, node: dict[str, Any], path: str, *, preferred_name: str | None
    ) -> Alt:
        branches = node["oneOf"]
        if not isinstance(branches, list) or len(branches) < 2:
            raise GeneratorFail("unrepresentable_xor", path)
        self._note(path, "oneOf", "XOR_OBJECT_ALTERNATIVES")
        nt = preferred_name or self._fresh("OneOf")
        alts: list[Seq] = []
        for i, branch in enumerate(branches):
            bpath = f"{path}/oneOf[{i}]"
            br_nt = _safe_ident(f"{nt}_branch_{i}")
            compiled = self.compile_node(branch, bpath, preferred_name=br_nt)
            if br_nt not in self.rules:
                self.rules[br_nt] = compiled
            alts.append(seq(Ident(br_nt)))
        result = Alt(tuple(alts))
        self.rules[nt] = result
        return _as_alt(seq(Ident(nt)))

    def _compile_any_of(
        self, node: dict[str, Any], path: str, *, preferred_name: str | None
    ) -> Alt:
        branches = node["anyOf"]
        if not isinstance(branches, list) or not branches:
            raise GeneratorFail("UNSUPPORTED_SCHEMA_CONSTRUCT", f"empty anyOf at {path}")

        null_i = None
        for i, b in enumerate(branches):
            if isinstance(b, dict) and b.get("type") == "null" and set(b) <= {
                "type",
                "title",
            }:
                null_i = i
                break

        if null_i is not None and len(branches) == 2:
            other = branches[1 - null_i]
            self._note(path, "anyOf", "NULLABLE")
            nt = preferred_name or self._fresh("Nullable")
            inner_nt = _safe_ident(f"{nt}_Value")
            inner = self.compile_node(other, f"{path}/anyOf/non_null", preferred_name=inner_nt)
            if inner_nt not in self.rules:
                self.rules[inner_nt] = inner
            self.rules[nt] = alt(Ident(inner_nt), Ident("JsonNull"))
            self.ledger[-1]["transform"] = f"NULLABLE({inner_nt})"
            return _as_alt(seq(Ident(nt)))

        self._note(path, "anyOf", "CLOSED_UNION_ANYOF")
        nt = preferred_name or self._fresh("AnyOf")
        alts: list[Seq] = []
        for i, branch in enumerate(branches):
            bpath = f"{path}/anyOf[{i}]"
            br_nt = _safe_ident(f"{nt}_branch_{i}")
            compiled = self.compile_node(branch, bpath, preferred_name=br_nt)
            if br_nt not in self.rules:
                self.rules[br_nt] = compiled
            alts.append(seq(Ident(br_nt)))
        self.rules[nt] = Alt(tuple(alts))
        return _as_alt(seq(Ident(nt)))

    def _compile_enum(self, node: dict[str, Any], path: str) -> Alt:
        values = node["enum"]
        if not isinstance(values, list) or not values:
            raise GeneratorFail("UNSUPPORTED_SCHEMA_CONSTRUCT", f"empty enum at {path}")
        self._note(path, "enum", "ENUM_LITERALS")
        parts = [
            seq(Lit(json.dumps(v, ensure_ascii=False, separators=(",", ":"))))
            for v in values
        ]
        return Alt(tuple(parts))

    def _compile_const(self, node: dict[str, Any], path: str) -> Alt:
        self._note(path, "const", "CONST_LITERAL")
        lit = json.dumps(node["const"], ensure_ascii=False, separators=(",", ":"))
        return _as_alt(seq(Lit(lit)))

    def _compile_string(self, node: dict[str, Any], path: str) -> Alt:
        pattern = node.get("pattern")
        if pattern is not None:
            if pattern != NONEMPTY_PATTERN:
                raise GeneratorFail(
                    "unsupported_pattern_or_string_constraint",
                    f"pattern {pattern!r} at {path}",
                )
            self._note(path, "string+pattern", "NONEMPTY_JSON_STRING_Q5")
            return _as_alt(seq(Ident("NonemptyJsonString")))
        self._note(path, "string", "JSON_STRING")
        return _as_alt(seq(Ident("JsonString")))

    def _compile_array(
        self, node: dict[str, Any], path: str, *, preferred_name: str | None
    ) -> Alt:
        if "items" not in node:
            raise GeneratorFail(
                "UNSUPPORTED_SCHEMA_CONSTRUCT", f"array without items at {path}"
            )
        self._note(path, "array", "ARRAY")
        nt = preferred_name or self._fresh("Array")
        item_nt = _safe_ident(f"{nt}_Item")
        item_expr = self.compile_node(
            node["items"], f"{path}/items", preferred_name=item_nt
        )
        if item_nt not in self.rules:
            self.rules[item_nt] = item_expr

        more = Atom(
            Group(
                Alt(
                    (
                        Seq(
                            (
                                Atom(Lit(",")),
                                Atom(Ident(item_nt)),
                            )
                        ),
                    )
                )
            ),
            Star(),
        )
        nonempty = Seq((Atom(Ident(item_nt)), more))
        body = Atom(Group(Alt((nonempty,))), Optional())
        arr_expr = Alt((Seq((Atom(Lit("[")), body, Atom(Lit("]")))),))
        self.rules[nt] = arr_expr
        self.ledger[-1]["transform"] = f"ARRAY({item_nt})"
        return _as_alt(seq(Ident(nt)))

    def _compile_object(self, node: dict[str, Any], path: str, nt: str) -> Alt:
        _check_unknown_keywords(node, path, self.coverage)
        props = node.get("properties")
        addl = node.get("additionalProperties", None)

        # Map-like: no property bag, additionalProperties is a schema (Q2/Q3).
        if not props and isinstance(addl, dict):
            if path not in MAP_LIKE_ALLOWLIST:
                raise GeneratorFail(
                    "UNSUPPORTED_SCHEMA_CONSTRUCT",
                    f"map-like object not on allowlist: {path}",
                )
            self._note(path, "map_object", "MAP")
            return self._compile_map(addl, path, nt)

        if props is None:
            props = {}

        if addl not in (False, None):
            raise GeneratorFail(
                "UNSUPPORTED_SCHEMA_CONSTRUCT",
                f"unsupported additionalProperties at {path}: {addl!r}",
            )

        required = set(node.get("required") or [])
        order = list(props.keys())
        self._note(path, "closed_object", f"CLOSED_OBJECT_SLOTS({','.join(order)})")

        prop_value_nts: dict[str, str] = {}
        for key, schema in props.items():
            ppath = f"{path}/properties/{key}"
            vnt = _safe_ident(f"{nt}_prop_{key}")
            expr = self.compile_node(schema, ppath, preferred_name=vnt)
            if vnt not in self.rules:
                self.rules[vnt] = expr
            prop_value_nts[key] = vnt

        n = len(order)

        def slot(i: int, state: str) -> str:
            return _safe_ident(f"{nt}_S{i}_{state}")

        for i in range(n + 1):
            for state in ("NoPrior", "HasPrior"):
                name = slot(i, state)
                if i == n:
                    self.rules[name] = _as_alt(seq(Lit("}")))
                    continue
                key = order[i]
                key_lit = json.dumps(key, ensure_ascii=False)
                vnt = prop_value_nts[key]
                is_req = key in required
                next_no = slot(i + 1, "NoPrior")
                next_has = slot(i + 1, "HasPrior")

                if state == "NoPrior":
                    emit = Seq(
                        (
                            Atom(Lit(key_lit)),
                            Atom(Lit(":")),
                            Atom(Ident(vnt)),
                            Atom(Ident(next_has)),
                        )
                    )
                    if is_req:
                        self.rules[name] = Alt((emit,))
                    else:
                        self.rules[name] = alt(seq(Ident(next_no)), emit)
                else:
                    emit = Seq(
                        (
                            Atom(Lit(",")),
                            Atom(Lit(key_lit)),
                            Atom(Lit(":")),
                            Atom(Ident(vnt)),
                            Atom(Ident(next_has)),
                        )
                    )
                    if is_req:
                        self.rules[name] = Alt((emit,))
                    else:
                        self.rules[name] = alt(seq(Ident(next_has)), emit)

        return Alt(
            (Seq((Atom(Lit("{")), Atom(Ident(slot(0, "NoPrior"))))),)
        )

    def _compile_map(self, value_schema: dict[str, Any], path: str, nt: str) -> Alt:
        val_nt = _safe_ident(f"{nt}_Value")
        val = self.compile_node(
            value_schema, f"{path}/additionalProperties", preferred_name=val_nt
        )
        if val_nt not in self.rules:
            self.rules[val_nt] = val

        more = Atom(
            Group(
                Alt(
                    (
                        Seq(
                            (
                                Atom(Lit(",")),
                                Atom(Ident("JsonString")),
                                Atom(Lit(":")),
                                Atom(Ident(val_nt)),
                            )
                        ),
                    )
                )
            ),
            Star(),
        )
        nonempty = Seq(
            (
                Atom(Ident("JsonString")),
                Atom(Lit(":")),
                Atom(Ident(val_nt)),
                more,
            )
        )
        body = Atom(Group(Alt((nonempty,))), Optional())
        self.ledger[-1]["transform"] = f"MAP(JSON_STRING, {val_nt})"
        return Alt((Seq((Atom(Lit("{")), body, Atom(Lit("}")))),))
