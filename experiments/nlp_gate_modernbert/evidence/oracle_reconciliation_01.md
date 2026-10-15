# ORACLE-01 — Oracle / governance reconciliation

```
SLICE:
ORACLE-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-ORACLE-RECONCILIATION-01-AUTH-001

STARTING SHA:
9809b5f8c20506288b7018336617c6136a15041d

ACCEPTED MB-02R SUBJECT:
c2f158b8222e3c1b4ae3ae737c2544fc3b25f994

CASES:
D5GAP-0125
GOLD-0061
GOLD-0062
GOLD-0063

HISTORICAL GOLD:
PRESERVED / UNMODIFIED

RESOLVER BEHAVIOR:
UNCHANGED

SCOPE-CONTRACT CASES:
UNTOUCHED

STATUS:
STOP FOR INDEPENDENT ORACLE-01 REVIEW
```

Machine-readable authority: `oracle_reconciliation_01.json`.

## Method

For each case, historical SLM-03 gold was left untouched. Successor truth was derived only from:

- fixture / projected workspace reference facts
- canonical WellPlot between-fill same-track resolution
- MB-01R decision-authority labels (as historical audit metadata)
- MB-02R frozen Q5 precedence and public-envelope mapping

No resolver, NormalizedRequest, scope-gap, encoder, or corpus-mutation work was performed.

## Results

| case_id | conflict_class | historical | successor |
|---------|----------------|------------|-----------|
| D5GAP-0125 | POLICY_PRECEDENCE_CONFLICT | ambiguous / CARDINALITY | unsupported / reference_not_found / NOT_FOUND |
| GOLD-0061 | ORACLE_DEFECT | ok | unsupported / capability_not_available / FILL_CROSS_TRACK |
| GOLD-0062 | ORACLE_DEFECT | ok | unsupported / capability_not_available / FILL_CROSS_TRACK |
| GOLD-0063 | ORACLE_DEFECT | ok | unsupported / capability_not_available / FILL_CROSS_TRACK |

`NEEDS_SEPARATE_IR_DECISION`: **0**  
`HISTORICALLY_VALID_BUT_SUPERSEDED`: **0**

### D5GAP-0125

- neutron → 0 matches; density → 2 matches (RHOB, RHOZ)
- Frozen Q5: `NOT_FOUND > CARDINALITY`
- Successor: `unsupported` + `reference_not_found` + `DETERMINISTIC_NOT_FOUND`
- Historical ambiguous/CARDINALITY preserved; superseded for successor evaluation only
- Follow-up: none for MB-02R; precedence changes need a future policy authority

### GOLD-0061 / 0062 / 0063

- Unique curve matches on **different tracks** in each fixture
- Canonical renderer requires same-track `between_curves` resolution
- Historical `ok` is an **ORACLE_DEFECT** (not a later policy supersession)
- Successor: `unsupported` + `capability_not_available` + detail `between_fill_requires_same_track` + `DETERMINISTIC_PRECONDITION` / `FILL_CROSS_TRACK`
- Follow-up: none for MB-02R; do not weaken R6

## Explicitly not done

- resolver changes
- historical gold mutation
- six `SCOPE_CONTRACT_GAP` cases
- MB-03 / T5 / LangGraph / SLM-04 / encoder bake-off
