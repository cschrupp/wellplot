# DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01 — Design closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01-AUTH-001

MODE:
DESIGN / INTERVIEW ONLY

PARENT:
DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01R
ACCEPTED / CLOSED
XGrammar JSON-Schema route: REJECTED
CANDIDATE: b249b810908cbc0283e62f18e8780a4a4f7144d3

STARTING TIP:
9d4318953b28de651429983b2d097ed0707fa545

CANDIDATE SHA:
d441534e97954a2e5f74c047c9be64b550ac5f1e

TIP:
9e7f873256b7baf56c08de18fbb907beca81797a

MODEL CALLS:
0

GENERATOR IMPLEMENTATION:
NOT AUTHORIZED

ENGINE INSTALL / PROBE:
NOT AUTHORIZED

PILOT-01:
NOT AUTHORIZED
```

## Claim

This slice freezes a **deterministic grammar representation design** for hard
token-level enforcement of the already-frozen patched `ClosedNormalizedProgram`
language (including XOR and decode-faithful non-whitespace).

It does **not** claim:

- generator implementation
- grammar constructibility on a tokenizer
- backend compatibility
- model capability
- PILOT authorization

## Provenance chain (Q1)

```
frozen ClosedNormalizedProgram + documented XOR/non-whitespace patch
        ↓
persisted decomposer_pilot_preflight_01_constraint.schema.json (hash verify)
        ↓
deterministic grammar generator
        ↓
canonical WELL-EBNF-1 bytes (+ optional deterministic engine lowering)
        ↓
SHA-256 + generator identity
```

SOURCE OF TRUTH: frozen closed schema / contract.  
GRAMMAR: derived artifact only. HAND EDITS: forbidden.

## Frozen decisions Q1–Q10

| ID | Freeze |
|----|--------|
| Q1 | Mechanically generated grammar; hand-patch forbidden |
| Q2 | Fixed schema property order for closed objects; **only** `produces_binds` is map-like (any member order) |
| Q3 | `produces_binds`: `{}` or `{"json-string":"track"}(+)*`; duplicate keys **not** CFG-guaranteed; JSON parse + `freeze_candidate()` authoritative |
| Q4 | XOR = exclusive `TextQuery \| LocalRefQuery` productions; generator FAIL if cannot emit exactly |
| Q5 | Decode-faithful `NONEMPTY_JSON_STRING` ≡ `str(value).strip()!=""`; raw `.*\S.*` forbidden |
| Q6 | Full pinned-parser JSON-number lexical language; no deliberate spelling subset |
| Q7 | Sequential optional slots + NoPrior/HasPrior commas; defaults never grammar-materialized |
| Q8 | Arrays `[] \| [T(,T)*]`; schema cardinality only; shared `$ref`; no invented caps |
| Q9 | Full JSON strings for plain `type:string`; Q5 nonempty **only** on `text`/`local_ref` |
| Q10 | Zero insignificant whitespace; separators `,` and `:` |

## Frozen decisions T11–T20 (SOL)

| ID | Freeze |
|----|--------|
| T11 | **WELL-EBNF-1** — WellPlot-owned restricted engine-neutral EBNF (not vague “ISO-ish”). Exact textual syntax is part of the design contract before generator implementation. Optional deterministic engine lowering is a second pure transform. |
| T12 | `true` / `false` / `null` only |
| T13 | enum/const = mechanical exact JSON literals from schema order |
| T14 | Closed union whitelist; other combinators → `GENERATOR_FAIL`; no silent widen |
| T15 | `integer`/`number` from pinned authoritative parse path; no assumed regex |
| T16 | `START ::= ClosedNormalizedProgram` sole entry |
| T17 | `tasks:[]` grammar-legal |
| T18 | Full provenance pins (dialect, hashes, generator, schema, Python/Unicode/JSON/Pydantic identities) |
| T19 | Fail-closed catalogue; no WARN_AND_CONTINUE / APPROXIMATE / JSON-Schema fallback / repair |
| T20 | Engine **requirements** only; no selection/install/probe |

### WELL-EBNF-1 requirements (T11)

UTF-8; LF only; deterministic rule order and formatting; named productions;
sequence/alternation/grouping/optionality/repetition; quoted literals;
mechanical Unicode scalar/range terminals for Q5/Q9; **no** semantic actions,
host code, or engine directives.

Exact metasyntax text is a pre-implementation design deliverable (see unresolved
Human gates). This closeout freezes dialect **identity + requirements**.

### Engine requirements (T20) — not selected

Must consume WELL-EBNF-1 or a language-preserving lowering; hard token mask with
pinned Qwen tokenizer; preserve Q2–Q10/T15; fail closed; pin probe provenance;
prove practical constructibility. Candidates (deferred): XGrammar grammar mode,
llguidance, other. **No JSON-Schema oneOf substitute.**

## Explicit non-authorizations

```
grammar implementation:              NOT AUTHORIZED
generator implementation:            NOT AUTHORIZED
dependency / engine install:         NOT AUTHORIZED
tokenizer / construction probe:      NOT AUTHORIZED
model load / forward / generate:     NOT AUTHORIZED
schema mutation:                     NOT AUTHORIZED
prompt changes:                      NOT AUTHORIZED
repair / postprocessing:             NOT AUTHORIZED
hand edits to derived grammar:       FORBIDDEN
PILOT-01:                            NOT AUTHORIZED
```

## Unresolved Human gates (after this closeout)

1. Authorize **generator implementation** (separate AUTH) — after independent design review and WELL-EBNF-1 metasyntax solidification as needed.
2. Authorize **engine construction probe** (separate AUTH).
3. Authorize **PILOT-01** (separate AUTH).
4. Escalate if preferred engine changes dependency / cost / latency envelope.

## Terminal state

```
DESIGN_TECHNICALLY_CLOSED_AWAITING_INDEPENDENT_REVIEW
```

Machine-readable ledger: `decomposer_pilot_constraint_cfg_design_01.json`.

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-CFG-DESIGN-01 REVIEW
