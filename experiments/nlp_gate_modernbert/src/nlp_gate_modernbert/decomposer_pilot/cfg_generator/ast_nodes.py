"""Internal WELL-EBNF-1 expression IR (generator-only)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ident:
    name: str


@dataclass(frozen=True, slots=True)
class Lit:
    text: str  # decoded string content; emitter adds quotes/escapes


@dataclass(frozen=True, slots=True)
class CharRange:
    lo: int  # inclusive Unicode scalar
    hi: int  # inclusive


@dataclass(frozen=True, slots=True)
class CharClass:
    negated: bool
    items: tuple[CharRange | int, ...]  # int = singleton; ranges use CharRange


@dataclass(frozen=True, slots=True)
class Group:
    expr: Expr


@dataclass(frozen=True, slots=True)
class Optional:
    pass


@dataclass(frozen=True, slots=True)
class Star:
    pass


@dataclass(frozen=True, slots=True)
class Plus:
    pass


@dataclass(frozen=True, slots=True)
class Repeat:
    m: int
    n: int


Suffix = Optional | Star | Plus | Repeat


@dataclass(frozen=True, slots=True)
class Atom:
    primary: Ident | Lit | CharClass | Group
    suffix: Suffix | None = None


@dataclass(frozen=True, slots=True)
class Seq:
    atoms: tuple[Atom, ...]


@dataclass(frozen=True, slots=True)
class Alt:
    sequences: tuple[Seq, ...]


Expr = Alt


def seq(*parts: Ident | Lit | CharClass | Group | Atom | Seq | Alt) -> Seq:
    atoms: list[Atom] = []
    for p in parts:
        if isinstance(p, Atom):
            atoms.append(p)
        elif isinstance(p, Seq):
            atoms.extend(p.atoms)
        elif isinstance(p, Alt):
            atoms.append(Atom(Group(p)))
        else:
            atoms.append(Atom(p))
    return Seq(tuple(atoms))


def alt(*sequences: Seq | Atom | Ident | Lit | CharClass | Group | Alt) -> Alt:
    out: list[Seq] = []
    for s in sequences:
        if isinstance(s, Seq):
            out.append(s)
        elif isinstance(s, Alt):
            out.extend(s.sequences)
        elif isinstance(s, Atom):
            out.append(Seq((s,)))
        else:
            out.append(Seq((Atom(s),)))
    return Alt(tuple(out))


def _as_primary(
    primary: Ident | Lit | CharClass | Group | Alt | Atom,
) -> Ident | Lit | CharClass | Group:
    if isinstance(primary, Atom):
        if primary.suffix is not None:
            return Group(Alt((Seq((primary,)),)))
        return primary.primary
    if isinstance(primary, Alt):
        return Group(primary)
    return primary


def opt(primary: Ident | Lit | CharClass | Group | Alt | Atom) -> Atom:
    return Atom(_as_primary(primary), Optional())


def star(primary: Ident | Lit | CharClass | Group | Alt | Atom) -> Atom:
    return Atom(_as_primary(primary), Star())


def plus(primary: Ident | Lit | CharClass | Group | Alt | Atom) -> Atom:
    return Atom(_as_primary(primary), Plus())