"""Independent WELL-EBNF-1 parse + recognition oracle (test-only).

Must not import the generator package, schema transforms, or freeze_candidate.
Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass


class WellEbnf1Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Lit:
    text: str  # decoded


@dataclass(frozen=True, slots=True)
class _Class:
    negated: bool
    # list of (lo, hi) inclusive
    ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _NT:
    name: str


Symbol = _Lit | _Class | _NT


@dataclass(frozen=True, slots=True)
class _Prod:
    lhs: str
    rhs: tuple[Symbol, ...]


class WellEbnf1Grammar:
    def __init__(self, productions: list[_Prod], start: str = "START") -> None:
        self.start = start
        self.productions = productions
        self.by_lhs: dict[str, list[_Prod]] = {}
        for p in productions:
            self.by_lhs.setdefault(p.lhs, []).append(p)
        if start not in self.by_lhs:
            raise WellEbnf1Error(f"missing start symbol {start}")


def _parse_hex(s: str, i: int, n: int) -> tuple[int, int]:
    if i + n > len(s):
        raise WellEbnf1Error("truncated hex escape")
    h = s[i : i + n]
    if any(c not in "0123456789abcdefABCDEF" for c in h):
        raise WellEbnf1Error(f"bad hex: {h}")
    return int(h, 16), i + n


def _decode_escape(s: str, i: int) -> tuple[int, int]:
    # s[i] is backslash
    if i + 1 >= len(s):
        raise WellEbnf1Error("truncated escape")
    c = s[i + 1]
    if c == "\\":
        return 0x5C, i + 2
    if c == '"':
        return 0x22, i + 2
    if c == "n":
        return 0x0A, i + 2
    if c == "r":
        return 0x0D, i + 2
    if c == "t":
        return 0x09, i + 2
    if c == "u":
        cp, j = _parse_hex(s, i + 2, 4)
        if 0xD800 <= cp <= 0xDFFF:
            raise WellEbnf1Error("lone surrogate in WELL-EBNF-1 escape")
        return cp, j
    if c == "U":
        cp, j = _parse_hex(s, i + 2, 8)
        if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            raise WellEbnf1Error("illegal U escape")
        return cp, j
    raise WellEbnf1Error(f"unknown escape \\{c}")


def _parse_literal(s: str, i: int) -> tuple[_Lit, int]:
    if i >= len(s) or s[i] != '"':
        raise WellEbnf1Error("expected string literal")
    i += 1
    out: list[str] = []
    while i < len(s):
        ch = s[i]
        if ch == '"':
            return _Lit("".join(out)), i + 1
        if ch == "\\":
            cp, i = _decode_escape(s, i)
            out.append(chr(cp))
            continue
        if ord(ch) < 0x20:
            raise WellEbnf1Error("raw control in literal")
        out.append(ch)
        i += 1
    raise WellEbnf1Error("unterminated literal")


def _parse_class_atom(s: str, i: int) -> tuple[int, int]:
    if i >= len(s):
        raise WellEbnf1Error("truncated class atom")
    if s[i] == "\\":
        return _decode_escape(s, i)
    if s[i] in "]":
        raise WellEbnf1Error("unexpected ]")
    if s[i] == "-":
        raise WellEbnf1Error("raw '-' is range syntax only")
    return ord(s[i]), i + 1


def _parse_charclass(s: str, i: int) -> tuple[_Class, int]:
    if i >= len(s) or s[i] != "[":
        raise WellEbnf1Error("expected [")
    i += 1
    negated = False
    if i < len(s) and s[i] == "^":
        negated = True
        i += 1
    ranges: list[tuple[int, int]] = []
    if i >= len(s) or s[i] == "]":
        raise WellEbnf1Error("empty char class")
    while i < len(s) and s[i] != "]":
        lo, i = _parse_class_atom(s, i)
        if i < len(s) and s[i] == "-" and i + 1 < len(s) and s[i + 1] != "]":
            i += 1
            hi, i = _parse_class_atom(s, i)
            if hi < lo:
                raise WellEbnf1Error("inverted range")
            ranges.append((lo, hi))
        else:
            ranges.append((lo, lo))
    if i >= len(s) or s[i] != "]":
        raise WellEbnf1Error("unterminated class")
    return _Class(negated, tuple(ranges)), i + 1


def _class_matches(cc: _Class, cp: int) -> bool:
    hit = any(lo <= cp <= hi for lo, hi in cc.ranges)
    return (not hit) if cc.negated else hit


@dataclass
class _Primary:
    kind: str  # ident|lit|class|group
    value: object


@dataclass
class _AtomAst:
    primary: _Primary
    suffix: str | None  # ? * + or {m,n}
    repeat: tuple[int, int] | None = None


def parse_well_ebnf1(text: str | bytes) -> WellEbnf1Grammar:
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if not text.endswith("\n"):
        raise WellEbnf1Error("grammar must end with LF")
    if "\r" in text or "\t" in text:
        raise WellEbnf1Error("TAB/CR forbidden")
    lines = text.split("\n")
    if lines[-1] != "":
        raise WellEbnf1Error("internal split error")
    lines = lines[:-1]
    if not lines:
        raise WellEbnf1Error("empty grammar")

    raw_rules: dict[str, list[list[_AtomAst]]] = {}

    for line_no, line in enumerate(lines, 1):
        if not line or line != line.strip(" ") or "  " in line:
            # allow exactly the Rule form; no leading/trailing SP; single SP separators
            pass
        if line.startswith(" ") or line.endswith(" "):
            raise WellEbnf1Error(f"line {line_no}: leading/trailing SP forbidden")
        if "\t" in line:
            raise WellEbnf1Error(f"line {line_no}: TAB forbidden")
        # Identifier SP ::= SP Expression SP ;
        try:
            name, rest = line.split(" ::= ", 1)
        except ValueError as exc:
            raise WellEbnf1Error(f"line {line_no}: missing ::= ") from exc
        if not _is_ident(name):
            raise WellEbnf1Error(f"line {line_no}: bad identifier {name}")
        if not rest.endswith(" ;"):
            raise WellEbnf1Error(f"line {line_no}: must end with ' ;'")
        expr = rest[: -len(" ;")]
        alts = _parse_expression(expr, line_no)
        if name in raw_rules:
            raise WellEbnf1Error(f"duplicate rule {name}")
        raw_rules[name] = alts

    # Order check: START first, then UTF-8 ascending
    names = list(raw_rules.keys())
    if names[0] != "START":
        raise WellEbnf1Error("START must be first rule")
    rest = names[1:]
    if rest != sorted(rest, key=lambda s: s.encode("utf-8")):
        raise WellEbnf1Error("rules after START must be UTF-8 ascending")

    prods = _desugar(raw_rules)
    return WellEbnf1Grammar(prods, start="START")


def _is_ascii_ident_char_first(c: str) -> bool:
    return ("A" <= c <= "Z") or ("a" <= c <= "z") or c == "_"


def _is_ascii_ident_char(c: str) -> bool:
    return _is_ascii_ident_char_first(c) or ("0" <= c <= "9")


def _is_ident(s: str) -> bool:
    """WELL-EBNF-1 Identifier ::= [A-Za-z_][A-Za-z0-9_]* (ASCII only)."""
    if not s:
        return False
    if not _is_ascii_ident_char_first(s[0]):
        return False
    return all(_is_ascii_ident_char(c) for c in s[1:])


def _parse_unsigned_int(s: str) -> int:
    """UnsignedInt ::= \"0\" | [1-9][0-9]* — reject leading zeros."""
    if s == "0":
        return 0
    if not s or s[0] == "0" or not s.isdigit():
        raise WellEbnf1Error(f"bad UnsignedInt: {s!r}")
    if not all("0" <= c <= "9" for c in s):
        raise WellEbnf1Error(f"bad UnsignedInt: {s!r}")
    return int(s)


def _parse_expression(expr: str, line_no: int) -> list[list[_AtomAst]]:
    # Sequence ( SP | SP Sequence )*
    parts = expr.split(" | ")
    return [_parse_sequence(p, line_no) for p in parts]


def _parse_sequence(seq_s: str, line_no: int) -> list[_AtomAst]:
    if not seq_s:
        raise WellEbnf1Error(f"line {line_no}: empty sequence")
    atoms: list[_AtomAst] = []
    i = 0
    s = seq_s
    while i < len(s):
        if s[i] == " ":
            raise WellEbnf1Error(f"line {line_no}: unexpected space")
        atom, i = _parse_atom(s, i, line_no)
        atoms.append(atom)
        if i < len(s):
            if s[i] != " ":
                raise WellEbnf1Error(f"line {line_no}: expected SP between atoms")
            i += 1
            if i >= len(s) or s[i] == " ":
                raise WellEbnf1Error(f"line {line_no}: bad SP")
    return atoms


def _parse_atom(s: str, i: int, line_no: int) -> tuple[_AtomAst, int]:
    primary, i = _parse_primary(s, i, line_no)
    suffix = None
    repeat = None
    if i < len(s) and s[i] in "?*+{":
        if s[i] == "{":
            j = s.find("}", i)
            if j < 0:
                raise WellEbnf1Error(f"line {line_no}: bad repeat")
            body = s[i + 1 : j]
            try:
                m_s, n_s = body.split(",", 1)
                m = _parse_unsigned_int(m_s)
                n = _parse_unsigned_int(n_s)
            except WellEbnf1Error as exc:
                raise WellEbnf1Error(f"line {line_no}: bad repeat body: {exc}") from exc
            if n < m:
                raise WellEbnf1Error(f"line {line_no}: bad repeat bounds")
            suffix = "{}"
            repeat = (m, n)
            i = j + 1
        else:
            suffix = s[i]
            i += 1
    return _AtomAst(primary, suffix, repeat), i


def _parse_primary(s: str, i: int, line_no: int) -> tuple[_Primary, int]:
    if i >= len(s):
        raise WellEbnf1Error(f"line {line_no}: unexpected end")
    if s[i] == '"':
        lit, i = _parse_literal(s, i)
        return _Primary("lit", lit), i
    if s[i] == "[":
        cc, i = _parse_charclass(s, i)
        return _Primary("class", cc), i
    if s[i] == "(":
        depth = 1
        j = i + 1
        while j < len(s) and depth:
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
            elif s[j] == '"':
                _, j2 = _parse_literal(s, j)
                j = j2
                continue
            elif s[j] == "[":
                _, j2 = _parse_charclass(s, j)
                j = j2
                continue
            j += 1
        if depth != 0:
            raise WellEbnf1Error(f"line {line_no}: unbalanced group")
        inner = s[i + 1 : j - 1]
        alts = _parse_expression(inner, line_no)
        return _Primary("group", alts), j
    # identifier — ASCII [A-Za-z_][A-Za-z0-9_]* only
    j = i
    while j < len(s) and _is_ascii_ident_char(s[j]):
        j += 1
    name = s[i:j]
    if not _is_ident(name):
        raise WellEbnf1Error(f"line {line_no}: bad ident at {i}")
    return _Primary("ident", name), j


def _desugar(raw: dict[str, list[list[_AtomAst]]]) -> list[_Prod]:
    prods: list[_Prod] = []
    extras: list[_Prod] = []
    counter = 0

    def fresh(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"__aux_{prefix}_{counter}"

    def emit_seq(lhs: str, atoms: list[_AtomAst]) -> None:
        rhs: list[Symbol] = []
        for atom in atoms:
            syms = lower_atom(atom)
            rhs.extend(syms)
        prods.append(_Prod(lhs, tuple(rhs)))

    def lower_atom(atom: _AtomAst) -> list[Symbol]:
        nonlocal extras
        base_syms = lower_primary(atom.primary)
        if atom.suffix is None:
            return base_syms
        # Wrap base as a single NT if needed
        if len(base_syms) == 1 and isinstance(base_syms[0], _NT) and atom.suffix != "{}":
            base_nt = base_syms[0].name
        else:
            base_nt = fresh("base")
            extras.append(_Prod(base_nt, tuple(base_syms)))

        if atom.suffix == "?":
            opt = fresh("opt")
            extras.append(_Prod(opt, (_NT(base_nt),)))
            extras.append(_Prod(opt, ()))
            return [_NT(opt)]
        if atom.suffix == "*":
            st = fresh("star")
            extras.append(_Prod(st, ()))
            extras.append(_Prod(st, (_NT(base_nt), _NT(st))))
            return [_NT(st)]
        if atom.suffix == "+":
            pl = fresh("plus")
            st = fresh("star")
            extras.append(_Prod(st, ()))
            extras.append(_Prod(st, (_NT(base_nt), _NT(st))))
            extras.append(_Prod(pl, (_NT(base_nt), _NT(st))))
            return [_NT(pl)]
        if atom.suffix == "{}":
            assert atom.repeat is not None
            m, n = atom.repeat
            # Unroll to alternatives of length m..n
            choice = fresh("rep")
            for k in range(m, n + 1):
                extras.append(_Prod(choice, tuple([_NT(base_nt)] * k)))
            return [_NT(choice)]
        raise WellEbnf1Error(f"bad suffix {atom.suffix}")

    def lower_primary(p: _Primary) -> list[Symbol]:
        if p.kind == "lit":
            assert isinstance(p.value, _Lit)
            return [_Lit(p.value.text)]
        if p.kind == "class":
            assert isinstance(p.value, _Class)
            return [p.value]
        if p.kind == "ident":
            assert isinstance(p.value, str)
            return [_NT(p.value)]
        if p.kind == "group":
            alts = p.value
            assert isinstance(alts, list)
            g = fresh("grp")
            for alt_atoms in alts:
                # each alt becomes a production of g
                rhs: list[Symbol] = []
                for atom in alt_atoms:
                    rhs.extend(lower_atom(atom))
                extras.append(_Prod(g, tuple(rhs)))
            return [_NT(g)]
        raise WellEbnf1Error(f"bad primary {p.kind}")

    for lhs, alts in raw.items():
        for atoms in alts:
            emit_seq(lhs, atoms)
    prods.extend(extras)
    return prods


@dataclass(frozen=True, slots=True)
class _Item:
    prod: _Prod
    dot: int
    origin: int


def recognize(grammar: WellEbnf1Grammar, text: str) -> bool:
    """Earley recognition of text against grammar.start (full match)."""
    n = len(text)
    charts: list[set[_Item]] = [set() for _ in range(n + 1)]

    for prod in grammar.by_lhs.get(grammar.start, []):
        charts[0].add(_Item(prod, 0, 0))

    for i in range(n + 1):
        changed = True
        while changed:
            changed = False
            snapshot = list(charts[i])
            for item in snapshot:
                # completion / scan / prediction
                if item.dot < len(item.prod.rhs):
                    sym = item.prod.rhs[item.dot]
                    if isinstance(sym, _NT):
                        for prod in grammar.by_lhs.get(sym.name, []):
                            ni = _Item(prod, 0, i)
                            if ni not in charts[i]:
                                charts[i].add(ni)
                                changed = True
                    elif isinstance(sym, _Lit):
                        lit = sym.text
                        if text.startswith(lit, i):
                            ni = _Item(item.prod, item.dot + 1, item.origin)
                            j = i + len(lit)
                            if ni not in charts[j]:
                                charts[j].add(ni)
                                # will process when outer loop reaches j; force local if j==i (empty lit)
                                if j == i:
                                    changed = True
                    elif isinstance(sym, _Class):
                        if i < n and _class_matches(sym, ord(text[i])):
                            ni = _Item(item.prod, item.dot + 1, item.origin)
                            if ni not in charts[i + 1]:
                                charts[i + 1].add(ni)
                else:
                    # complete
                    for prev in list(charts[item.origin]):
                        if prev.dot < len(prev.prod.rhs):
                            sym = prev.prod.rhs[prev.dot]
                            if isinstance(sym, _NT) and sym.name == item.prod.lhs:
                                ni = _Item(prev.prod, prev.dot + 1, prev.origin)
                                if ni not in charts[i]:
                                    charts[i].add(ni)
                                    changed = True

    for item in charts[n]:
        if (
            item.prod.lhs == grammar.start
            and item.dot == len(item.prod.rhs)
            and item.origin == 0
        ):
            return True
    return False


def accepts(grammar_bytes: bytes | str, candidate: str) -> bool:
    grammar = parse_well_ebnf1(grammar_bytes)
    return recognize(grammar, candidate)
