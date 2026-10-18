# DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01R2 — Design closeout (corrective rework)

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01R2

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01-REWORK-AUTH-001

MODE:
DESIGN / EVIDENCE-ONLY CORRECTION

PRIOR CANDIDATE:
9d785e55f29fb3d2809c445b422c0a5c5af6ee6d
RESULT: REVISE (F003, F004)

STARTING TIP:
5a753e485491b9c32331122ef248a01aa0bf0cc3

CANDIDATE SHA:
73d9c31852a394701320dd50fcc6c83944936df1

TIP:
(pending SHA-record commit)

PARENT:
DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01R
(REVISE — F001/F002 closed; F003/F004 open)

MODEL CALLS:
0

GENERATOR / ENGINE / PILOT-01:
NOT AUTHORIZED
```

## Corrective scope (01R2)

| ID | Correction |
|----|------------|
| F003 | Make JSON `well_ebnf_1` metasyntax exactly match Markdown (`Primary` / `Suffix`) |
| F004 | Freeze one canonical rule-order algorithm (no topological alternative) |
| CHARCLASS | Raw `-` is range syntax only; literal U+002D MUST be `\u002D` |
| R5 | MD and JSON express the same normative metasyntax |

Findings addressed this slice: **F003**, **F004**.  
Prior findings **F001**, **F002** remain closed. R3 numeric authority unchanged.

Everything else in Q1–Q10 / T11–T21 remains frozen. No implementation, install, construction probe, model call, or PILOT-01.

## Claim

This corrective rework makes the machine-readable WELL-EBNF-1 ledger a complete,
non-inferential rendering of the normative Markdown metasyntax, and removes the
last degree of freedom in canonical rule ordering for hash-addressed artifacts.

It still does **not** claim generator implementation, constructibility, backend
fit, model capability, or PILOT authorization.

## Grammar language relation (R4 — unchanged)

The WELL-EBNF-1 artifact is a **deliberately canonical generation surface** for
`ClosedNormalizedProgram` JSON texts. It is **not** required to equal every
byte string the pinned JSON parser accepts.

**Permitted canonical lexical narrowing (explicit only):**

1. Q2 — fixed property order for schema-closed objects  
2. Q10 — zero insignificant whitespace between structural tokens  
3. R3 — exclude non-JSON `NaN` / `Infinity` / `-Infinity` aliases from number productions  

No other narrowing may be introduced implicitly. No semantic repair. No silent widening.

Authority split:

```
grammar        → canonical structural + lexical generation surface
JSON parse     → materialize values
freeze_candidate → closed-model validation, canonicalization, finite numeric rejection
```

## Numeric lexical authority (R3 / Q6 / T15 — unchanged / accepted)

| Layer | Admits / rejects |
|-------|------------------|
| **Grammar** | Strict JSON-number syntax (ECMA-404 / RFC 8259 number). **Rejects** `NaN`, `Infinity`, `-Infinity`, `+Infinity`, and case variants. |
| **freeze_candidate** | Finite representability + model validity. Uses `json.dumps(..., allow_nan=False)`. Lexemes such as `1e309` may be **syntactically** grammar-legal JSON numbers; survival is freeze authority. |

Q6 “full numeric lexical fidelity” means the full **strict JSON-number** spelling
surface under the pinned path — **not** Python `json.loads` nonstandard
NaN/Infinity aliases.

Normative NUMBER sketch:

```
Number        ::= OptionalMinus Int Frac? Exp?
OptionalMinus ::= "-"?
Int           ::= "0" | [1-9][0-9]*
Frac          ::= "." [0-9]+
Exp           ::= [eE] [+-]? [0-9]+
```

Residual T15 integer-path wording does not block this slice: the current patched
schema contains no integer sites; a future integer construct fails closed until
its exact mapping is needed.

## WELL-EBNF-1 metasyntax (R1 / T11 / F003 / F004)

Dialect id: `WELL-EBNF-1` version `1.0.0`.

### Global file rules

| Rule | Requirement |
|------|-------------|
| Encoding | UTF-8 |
| Newlines | LF only (`U+000A`) |
| EOF | File **MUST** end with exactly one LF |
| Comments | **FORBIDDEN** |
| Tabs / CR | **FORBIDDEN** |
| Semantic actions / host code / engine directives | **FORBIDDEN** |

### Formal syntax (byte-level)

```
GrammarFile  ::= Rule (LF Rule)* LF
Rule         ::= Identifier SP "::=" SP Expression SP ";"
Identifier   ::= [A-Za-z_][A-Za-z0-9_]*
Expression   ::= Sequence (SP "|" SP Sequence)*
Sequence     ::= Atom (SP Atom)*
Atom         ::= Primary Suffix?
Primary      ::= Identifier
               | Literal
               | CharClass
               | "(" Expression ")"
Suffix       ::= "?" | "*" | "+" | "{" UnsignedInt "," UnsignedInt "}"
UnsignedInt  ::= "0" | [1-9][0-9]*
Literal      ::= '"' LitChar* '"'
CharClass    ::= "[" "^"? ClassItem+ "]"
ClassItem    ::= ClassAtom | ClassAtom "-" ClassAtom
```

- Each `Rule` is **exactly one physical line** (no wrapping).  
- `SP` = exactly one SPACE (`U+0020`).  
- No leading/trailing SP on a rule line; no blank lines between rules.  
- Suffix operators bind to the immediately preceding `Primary` with **no** space before the suffix.  
- `Primary{m,n}` means `m..n` inclusive repetitions; require `0 <= m <= n`.

### Escapes (in literals and char-class atoms)

```
Escape ::= "\\" ( "\\" | "\"" | "n" | "r" | "t" | "u" Hex4 | "U" Hex8 )
Hex4   ::= [0-9A-Fa-f]{4}
Hex8   ::= [0-9A-Fa-f]{8}
```

- `\uXXXX` — Unicode scalar `U+XXXX` for `0000..D7FF` or `E000..FFFF` (lone surrogates **illegal**).  
- `\UXXXXXXXX` — scalar in `00000000..0010FFFF` excluding surrogates.  
- Unescaped controls `U+0000..U+001F` are illegal in literals/class atoms.

### LitChar / ClassAtom

- Literal: any Unicode scalar except controls, `"` (`U+0022`), `\` (`U+005C`), or Escape.  
- Class atom: any Unicode scalar except controls, `]` (`U+005D`), `\` (`U+005C`), and raw `-` (`U+002D`).  
- Raw `-` inside a character class is **range syntax only**.  
- Literal U+002D inside a class **MUST** be emitted as `\u002D`. The first/last placement alternative is **FORBIDDEN**.

### Start symbol and rule order (F004)

- Exactly one production `START`.  
- T16: `START ::= ClosedNormalizedProgram ;` (root object nonterminal).  
- **Sole** canonical rule-order algorithm for WELL-EBNF-1 v1 source bytes:

  1. `START` first  
  2. all remaining rule identifiers ascending by UTF-8 byte sequence  

- No alternative topological ordering in the canonical WELL-EBNF-1 source artifact.  
- Backend-specific reordering, if ever needed, belongs only to a separately hashed
  deterministic engine-native lowering.

Pipeline:

```
schema
  → one canonical WELL-EBNF-1
  → zero or more backend-specific deterministic lowerings
```

### Identity

Two WELL-EBNF-1 artifacts are the same dialect text iff their **UTF-8 bytes are identical**.

Machine-readable copy: `well_ebnf_1` object in the JSON ledger (must match this section).

## Prior freezes preserved (Q1–Q5, Q7–Q10, T12–T14, T16–T21)

Unchanged except F003/F004/CHARCLASS clarifications above. See JSON `decisions` map for the full ledger.

Summary table:

| ID | Freeze |
|----|--------|
| Q1 | Mechanical generation; hand-patch forbidden |
| Q2 | Fixed key order; `produces_binds` map-like only |
| Q3 | `produces_binds` duplicate keys not CFG-guaranteed |
| Q4 | Exclusive XOR productions |
| Q5 | Decode-faithful nonempty |
| Q6 | Strict JSON-number (R3) |
| Q7 | Sequential optional slots |
| Q8 | Mechanical arrays; no invented caps |
| Q9 | Full strings except Q5 sites |
| Q10 | Zero insignificant whitespace |
| T11 | WELL-EBNF-1 fully specified; md/json congruent (F003) |
| T12–T14 | bool/null; enum/const; closed unions |
| T15 | integer/number from pinned path (R3 clarity) |
| T16–T17 | START root; empty tasks legal |
| T18–T20 | Provenance; fail-closed; engine requirements only |
| T21 | Paired evidence artifacts |

## Explicit non-authorizations

```
grammar / generator implementation:  NOT AUTHORIZED
dependency / engine install:         NOT AUTHORIZED
construction / tokenizer probe:      NOT AUTHORIZED
model load / forward / generate:     NOT AUTHORIZED
schema mutation / prompt / repair:   NOT AUTHORIZED
hand edits to derived grammar:       FORBIDDEN
PILOT-01:                            NOT AUTHORIZED
```

## Unresolved Human gates

1. Authorize **generator implementation** (separate AUTH).  
2. Authorize **engine construction probe** (separate AUTH).  
3. Authorize **PILOT-01** (separate AUTH).  
4. Escalate if preferred engine changes dependency / cost / latency envelope.  

WELL-EBNF-1 metasyntax is **not** a Human gate.

## Terminal state

```
DESIGN_TECHNICALLY_CLOSED_AWAITING_INDEPENDENT_REVIEW
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01R2 REVIEW
