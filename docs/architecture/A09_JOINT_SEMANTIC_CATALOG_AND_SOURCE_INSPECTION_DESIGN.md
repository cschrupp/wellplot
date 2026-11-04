# A09 Joint Semantic Catalog and LAS/DLIS Inspection Design

**Status:** D1 integrated design candidate; independent review pending  
**Accepted foundation:** metadata-first design/F13-F14 at
`daef5d171828495b2f0dfcea25ae372f0bc39af4`  
**Scope:** semantic curve catalog, source metadata inspection, and their shared
authoring-context boundary  
**Implementation:** not authorized  
**Provider/model/endpoint/live/scientific/C02 activity:** none

## Decision Summary

Design two coordinated A09 workstreams behind one shared boundary:

1. `A09-CAT` defines versioned, provenance-bearing scientific family and
   recognition data. Supplied family JSON is an audit/reference corpus, not
   runtime authority.
2. `A09-SRC` defines bounded metadata-only LAS/DLIS inspection behind the
   existing source-loader and inspection contracts. It does not load numeric
   samples for semantic authoring.
3. The existing authoring-context path joins a request, a pinned catalog, a
   source revision, and inspected physical candidates. `PlotAuthoringContext`
   names this logical shared contract; it does not authorize a new parallel
   service or duplicate context object.
   Host code resolves an exact candidate and produces a compact contract for
   the existing planner/workers. The model never chooses by inventory order.

This is one extension to the current canonical authoring engine, not a new
resolver service, source-ingestion engine, workflow, scientific loader, or
execution path. Existing `LogfileSourceLoader`, enrichment, inspection,
`AuthoringDocumentIntent`, reconciliation, executor/service, YAML, and renderer
remain the owners of their current responsibilities.

The accepted four-state physical resolution (`UNIQUE`, `AMBIGUOUS`, `ABSENT`,
`UNKNOWN`) remains distinct from (a) semantic-family classification,
(b) renderer addressability, and (c) numerical sample availability. In
particular, a nonexhaustive catalog cannot prove a scientific family absent.

This design selects no production alias, presentation default, parser budget,
DLIS limit, or token threshold. Those require the separate D2 feasibility
gate. The supplied catalogs contain broad wildcard rules and conflicting
assignments; none is automatically promoted by this document.

## Decision Record

**DECISION:** Join governed semantic-family recognition and metadata-first
physical-channel inspection in the existing authoring-context path; retain
host-owned exact resolution and existing canonical execution.

**PROJECT SCOPE:** Interpret a scientist's curve request and safely bind it to
an addressable LAS/DLIS channel without sending numerical samples or an
unbounded source inventory to the model.

**EXTERNAL EVIDENCE:** The accepted A09 metadata-first design records the
LAS/LASIO, DLISIO, and llama.cpp source review and version caveats. LAS curve
metadata precedes samples; DLISIO exposes metadata objects separately from
sample APIs but scans/indexes the physical file. The design relies on the
accepted source references there, not on a new claim that parsing cost is
independent of file size.

**ESTABLISHED PRACTICE:** Separate metadata from bulk measurements; use stable
compound identity where names are non-unique; keep untrusted source text out
of privileged instructions; make ambiguity explicit; and bind decisions to
the source/catalog revision that produced them.

**WELLPLOT DIFFERENCE:** LAS/DLIS channel names are not globally unique,
renderer addressability is narrower than metadata discoverability, and the
supplied family data is nonexhaustive, contains patterns/unknown provenance,
and is not safe as an automatic semantic authority.

**OPTIONS CONSIDERED:** (A) let the model match channels from raw metadata;
(B) add a separate catalog/inspection agent; (C) resolve deterministically in
the existing host authoring context and pass only a request-scoped result to
the existing graph. Select C. A permits hallucinated identity and ordering
effects; B duplicates lifecycle and validation; C preserves K-01/K-02 and the
accepted F13/F14 boundary.

**SELECTED APPROACH:** Treat catalog entries as governed data; inspect only
source metadata; let the host resolve typed physical/family requests; require
unique identity plus existing renderer addressability before binding; keep
sample availability independent and normally `NOT_CHECKED`.

**EVIDENCE CLASS:** `ADAPTED` for host-mediated metadata resolution and
source-revision binding; `ESTABLISHED` for not equating metadata declaration
with sample availability and for refusing arbitrary first-match selection;
`EMPIRICALLY_SUPPORTED` only for the local JSON audit counts in the linked
feasibility record; `NOVEL` for the combined four-axis resolution projection
and its exact integration into WellPlot's current context contract.

**RISKS:** Catalog licensing/provenance is unknown; legacy wildcard
assignments collide; units and measurement labels are heterogeneous; DLIS
resource behavior is unmeasured; a complete token count is unavailable without
the matching Qwen/tokenizer/template; existing source aliases currently lack
trust metadata; and the existing renderer cannot address every metadata
identity.

**REVERSIBLE:** Yes. Keep the proposed data schema and resolver behind current
authoring contracts; do not change scientific loaders or bindings in this
design tranche.

**VALIDATION:** Provider-free deterministic JSON audit, exact identity and
catalog-collision fixtures, LAS/DLIS synthetic inspection matrix, addressable
versus unaddressable cases, source-revision invalidation, complete-request
token admission, and single-engine reachability attestation.

**STOP / REVISIT:** Stop before implementation if source/catalog identity
cannot be pinned, if any semantic match depends on unreviewed wildcard or
similarity inference, if exact metadata identity cannot map to the existing
renderer, or if parser/token budgets cannot fail closed without converting
incomplete evidence into `ABSENT`.

## Canonical Ownership and Data Flow

```text
scientist request
    -> existing SemanticPlanner proposes a typed scoped request
    -> existing LogfileSourceLoader/inspection boundary returns metadata
    -> host pins SemanticCurveCatalog version and source revision
    -> host performs deterministic candidate resolution
    -> existing PlotAuthoringContext carries compact grounded facts
    -> existing canonical worker/validation/lowering/reconciliation path
    -> existing AuthoringExecutor/Service and YAML persistence
    -> existing renderer
```

The planner may propose the requested scientific role, a literal channel
identifier, and explicit constraints. It cannot select a physical candidate,
declare the inventory complete, override catalog provenance, assert renderer
addressability, or claim samples were verified. These are host-owned facts.
Candidate/source aliases are descriptive only unless a separately approved
catalog rule authorizes them.

The source inspector is implemented behind `LogfileSourceLoader`; the
existing `AuthoringInspectionFacade` and `AuthoringContextSnapshot` are
integration points, not alternatives. Catalog lookup/resolution is a
deterministic host operation called by the existing context/enrichment path.
Unless a later implementation review establishes otherwise, the logical
`PlotAuthoringContext` is represented by extending/reusing these current
contracts, not by adding a parallel standalone context abstraction.
Do not add an autonomous inspector, second `SemanticEnricher`, catalog-backed
worker, or alternate binder.

One scientist message remains one transaction under the existing A08
publication semantics. All request obligations must resolve and validate
before canonical publication. Ambiguity, incomplete inspection, stale source
revision, or evidence-integrity failure blocks the whole message; do not
publish a partial subset. Structural changes do not require sample loading.
Each successfully completed message persists one canonical revision and
refreshes the displayed state using the existing route.

## Proposed Normalized Catalog Contract and JSON Schema

The following is a normalized JSON-shaped proposal, not a committed runtime
schema or catalog. The all-zero digest is an invalid placeholder, not an
identity. IDs and mappings are examples of field shape only; no example entry
authorizes a scientific equivalence.

```json
{
  "schema_version": "1",
  "catalog_id": "wellplot.semantic-curve-catalog",
  "catalog_version": "unreleased",
  "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "source_provenance": [
    {
      "source_id": "supplied-families-json",
      "path": "examples/families/FamiliesList.json",
      "sha256": "a0ed208e5db33a335dd94a587054934fb22a364b46828930d34f108013e773dd",
      "license_status": "UNKNOWN",
      "redistribution_status": "NOT_APPROVED"
    }
  ],
  "families": [
    {
      "id": "example.stable-family-id",
      "label": "Example family label",
      "parent_ids": [],
      "concept_kind": "physical_quantity",
      "measurement_type": "example-measurand",
      "compatible_unit_ids": [],
      "supported_visualization_types": [],
      "absence_scope": "OPEN_WORLD",
      "presentation_preset_id": null
    }
  ],
  "recognition_rules": [
    {
      "id": "example.rule-id",
      "family_id": "example.stable-family-id",
      "matcher": {
        "kind": "exact_mnemonic",
        "value": "EXAMPLE"
      },
      "source_scope": [],
      "unit_constraints": [],
      "status": "candidate",
      "provenance_ids": [],
      "review": null
    }
  ],
  "presentation_presets": []
}
```

### Catalog field rules

- `family.id` is stable, machine-readable identity; labels and translations
  are not identities. `concept_kind` distinguishes physical quantities from
  categorical/status/quality/metadata/derived concepts and array/waveform
  types. A nonphysical concept is not automatically a supported track type.
- Measurement type and unit compatibility are separate. Units require
  normalized identifiers, dimensions, and explicit reviewed conversions
  before they can constrain or transform a request. Unknown or missing units
  never imply compatibility. No conversion constants are selected here.
- `absence_scope` defaults to `OPEN_WORLD`. Only an explicitly reviewed,
  scoped, exhaustive mapping can support family-level `ABSENT`; a catalog
  miss normally means `UNCLASSIFIED` or `UNKNOWN`.
- Matcher kinds are finite: exact physical mnemonic, exact reviewed request
  alias, or a restricted glob. Glob syntax, normalization, and scope must be
  versioned. Regex, substring, edit-distance, vendor-guessing, and implicit
  case/punctuation expansion are not authorized. Wildcard rules are
  `candidate` until each is individually reviewed and collision-tested.
- `status` is `candidate`, `reviewed`, or `deprecated`. Only `reviewed` rules
  with valid provenance may authorize automatic semantic matches. Candidate
  rules may be shown as explicitly untrusted suggestions and must never
  create a binding or prove absence.
- Provenance records must identify the source artifact and exact rule/value
  support, licensing status, review owner/role, decision date, scope, and
  catalog release. Missing, stale, or invalid provenance makes the rule
  ineligible. Catalog release version and canonical digest are pinned in the
  resolution snapshot and custody.
- Any collision between eligible reviewed rules yields ambiguity; catalog
  order, rule order, mnemonic sorting, or specificity must not silently
  select a winner. A narrower rule can exclude candidates only when its
  scoped semantics are explicit and reviewed, not as a hidden priority.
- Presentation presets are separate from recognition. They may describe only
  fields supported by the existing renderer and only after review. Effective
  precedence is: explicit scientist value, preserved existing value, approved
  family preset, then current generic default. Axis reversal is a semantic
  direction, not an implicit consequence of a numeric range. Presets never
  change channel identity or scientific classification.

### Representative preset shape (non-authoritative)

```json
{
  "id": "example.reviewed-preset",
  "supported_visualization_type": "scalar_curve",
  "scale": {
    "kind": "linear",
    "minimum": null,
    "maximum": null,
    "reverse": null
  },
  "style": {
    "color": null,
    "line_style": null,
    "line_width": null
  },
  "renderer_capability_version": "required-before-release",
  "status": "candidate",
  "provenance_ids": []
}
```

Null means unspecified, not a default value. This example is not an instruction
to create or select values.

### Structural JSON Schema sketch

This draft-2020-12 fragment makes the catalog envelope and rule vocabulary
machine-checkable. It is intentionally not a production schema: domain
validation (provenance validity, scope, unit dimensions, collisions, and
renderer capability) remains host-side policy and must be designed/reviewed
before implementation.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "catalog_id", "catalog_version", "content_sha256",
    "source_provenance", "families", "recognition_rules",
    "presentation_presets"
  ],
  "properties": {
    "schema_version": {"const": "1"},
    "catalog_id": {"type": "string", "minLength": 1},
    "catalog_version": {"type": "string", "minLength": 1},
    "content_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "source_provenance": {"type": "array", "items": {"type": "object"}},
    "families": {"type": "array", "items": {"$ref": "#/$defs/family"}},
    "recognition_rules": {"type": "array", "items": {"$ref": "#/$defs/rule"}},
    "presentation_presets": {"type": "array", "items": {"type": "object"}}
  },
  "$defs": {
    "family": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "label", "concept_kind", "absence_scope"],
      "properties": {
        "id": {"type": "string", "minLength": 1},
        "label": {"type": "string", "minLength": 1},
        "parent_ids": {"type": "array", "items": {"type": "string"}},
        "concept_kind": {
          "enum": ["physical_quantity", "categorical", "status", "quality",
                   "metadata", "derived", "array", "waveform", "unknown"]
        },
        "measurement_type": {"type": ["string", "null"]},
        "compatible_unit_ids": {"type": "array", "items": {"type": "string"}},
        "supported_visualization_types": {"type": "array", "items": {"type": "string"}},
        "absence_scope": {"enum": ["OPEN_WORLD", "REVIEWED_CLOSED_SCOPE"]},
        "presentation_preset_id": {"type": ["string", "null"]}
      }
    },
    "rule": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "family_id", "matcher", "status", "provenance_ids"],
      "properties": {
        "id": {"type": "string", "minLength": 1},
        "family_id": {"type": "string", "minLength": 1},
        "matcher": {
          "type": "object",
          "additionalProperties": false,
          "required": ["kind", "value"],
          "properties": {
            "kind": {"enum": ["exact_mnemonic", "exact_alias", "restricted_glob"]},
            "value": {"type": "string", "minLength": 1}
          }
        },
        "source_scope": {"type": "array", "items": {"type": "string"}},
        "unit_constraints": {"type": "array", "items": {"type": "string"}},
        "status": {"enum": ["candidate", "reviewed", "deprecated"]},
        "provenance_ids": {"type": "array", "items": {"type": "string"}},
        "review": {"type": ["object", "null"]}
      }
    }
  }
}
```

Cross-reference checks, digest verification, duplicate IDs, matcher collision
analysis, and reviewed-provenance enforcement are deliberately not delegated
to JSON Schema. They are deterministic domain validation requirements, not
additional model semantics.

## Proposed Source Metadata Contract

```json
{
  "source": {
    "source_id": "existing-host-source-identity",
    "format": "LAS",
    "revision": "existing-snapshot-revision",
    "parser": {"name": "locked-parser", "version": "locked-version"}
  },
  "inspection": {
    "status": "INCOMPLETE",
    "inventory_complete": false,
    "scope": "source-and-selected-logical-file/frame scope",
    "diagnostics": []
  },
  "channels": [
    {
      "physical_id": {},
      "mnemonic": "verbatim source mnemonic",
      "unit": "verbatim source unit or null",
      "dimension": "known dimension or UNKNOWN",
      "kind": "scalar",
      "description": {"value": null, "trust": "UNTRUSTED_NOT_FOR_MODEL"},
      "addressability": "UNKNOWN",
      "sample_availability": "NOT_CHECKED"
    }
  ]
}
```

Identity requirements:

- LAS identity includes pinned source revision, curve ordinal, and verbatim
  mnemonic; normalized text is an additional matching key, never a replacement
  for physical identity.
- DLIS identity includes pinned source revision, logical-file identity,
  frame identity, and compound channel identity (object type, name, origin,
  and copy number as exposed by the locked DLISIO version). Frame and logical
  file are not inferred from mnemonic. If the locked API cannot establish a
  component, identity/addressability is `UNKNOWN`.
- Absolute paths and raw descriptions do not enter model context. Source
  identity/revision reuses the existing snapshot mechanism; this design does
  not mandate a full-file hash of multi-gigabyte sources.
- `inventory_complete` is true only after the selected source scope was fully
  enumerated and the parser completed within accepted limits. Partial output
  is never presented as a complete inventory.
- `addressability` is independently computed against the existing renderer
  and binding interface. A metadata-unique but renderer-unaddressable channel
  is not automatically bindable. No renderer/scientific-loader change is
  part of D1.
- `sample_availability` defaults to `NOT_CHECKED`. Declared metadata is not
  evidence that values exist, are readable, or contain usable samples.

### Structural source JSON Schema sketch

This structural fragment documents the required separation and status
vocabulary. The format-specific physical-ID fields shown in the preceding
contract remain subject to the locked parser API review at D2.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["source", "inspection", "channels"],
  "properties": {
    "source": {
      "type": "object",
      "required": ["source_id", "format", "revision", "parser"],
      "properties": {
        "source_id": {"type": "string", "minLength": 1},
        "format": {"enum": ["LAS", "DLIS"]},
        "revision": {"type": "string", "minLength": 1},
        "parser": {"type": "object"}
      }
    },
    "inspection": {
      "type": "object",
      "required": ["status", "inventory_complete"],
      "properties": {
        "status": {"enum": ["COMPLETE", "INCOMPLETE", "UNSUPPORTED", "FAILED", "RESOURCE_LIMIT"]},
        "inventory_complete": {"type": "boolean"},
        "scope": {"type": "string"},
        "diagnostics": {"type": "array", "items": {"type": "string"}}
      }
    },
    "channels": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["physical_id", "mnemonic", "addressability", "sample_availability"],
        "properties": {
          "physical_id": {"type": "object"},
          "mnemonic": {"type": "string", "minLength": 1},
          "unit": {"type": ["string", "null"]},
          "dimension": {"type": ["string", "null"]},
          "kind": {"enum": ["scalar", "array", "categorical", "unknown"]},
          "addressability": {"enum": ["ADDRESSABLE", "UNADDRESSABLE", "UNKNOWN"]},
          "sample_availability": {
            "enum": ["NOT_CHECKED", "VERIFIED_AVAILABLE", "VERIFIED_UNAVAILABLE", "UNKNOWN"]
          }
        }
      }
    }
  }
}
```

The production schema must additionally reject an `inventory_complete=true`
claim unless inspection status is `COMPLETE`; JSON Schema alone may encode
that consistency condition, but host validation must enforce it regardless.

## Shared Resolution Contract

The host resolution result carries at least:

```json
{
  "request_target_kind": "EXPLICIT_PHYSICAL | SEMANTIC_FAMILY | UNRESOLVED",
  "physical_resolution": "UNIQUE | AMBIGUOUS | ABSENT | UNKNOWN",
  "classification_status": "REVIEWED_MATCH | CANDIDATE_ONLY | UNCLASSIFIED | UNKNOWN",
  "addressability": "ADDRESSABLE | UNADDRESSABLE | UNKNOWN",
  "sample_availability": "NOT_CHECKED | VERIFIED_AVAILABLE | VERIFIED_UNAVAILABLE | UNKNOWN",
  "source_revision": "pinned-revision",
  "catalog_version": "pinned-version-or-null-for-literal-only",
  "candidate_physical_ids": [],
  "selected_physical_id": null,
  "evidence_refs": []
}
```

These fields are orthogonal. A selected literal vendor mnemonic may be
`physical_resolution=UNIQUE`, `classification_status=UNCLASSIFIED`,
`addressability=ADDRESSABLE`, and `sample_availability=NOT_CHECKED`; it can
still be plotted by explicit user choice. Conversely, a reviewed semantic
match is not bindable if physical resolution is ambiguous or addressability
is unknown.

### Interpretation and resolution table

| Request/evidence | Physical resolution | Classification | Action |
| --- | --- | --- | --- |
| Explicit source/frame-qualified physical identity; one exact object | `UNIQUE` | reviewed match or `UNCLASSIFIED` | Continue only if `ADDRESSABLE`; preserve literal identity. |
| Explicit physical mnemonic; complete scoped inventory, no exact match | `ABSENT` | independent | Report literal channel absent; do not substitute a family alias. |
| Explicit physical mnemonic; duplicate exact candidates | `AMBIGUOUS` | independent | Ask which physical object/source/frame; no first match. |
| Reviewed family term; one eligible reviewed rule and one compatible physical candidate | `UNIQUE` | `REVIEWED_MATCH` | Continue only if `ADDRESSABLE`. |
| Reviewed family term; two or more eligible physical candidates | `AMBIGUOUS` | `REVIEWED_MATCH` | Ask user to select; no order/specificity fallback. |
| Reviewed family term; zero candidates; catalog is open-world/nonexhaustive | `UNKNOWN` | `UNCLASSIFIED` or `UNKNOWN` | Do not claim family absent; ask for a literal channel or clarification. |
| Reviewed family term; zero candidates; inventory complete and mapping explicitly exhaustive | `ABSENT` | `REVIEWED_MATCH` | Report no mapped physical candidate in that declared scope. |
| Unrecognized family term, no explicit literal channel | `UNKNOWN` | `UNCLASSIFIED` | Ask clarification; unknown taxonomy is not unsupported physical data. |
| Any parser limit/error/incomplete inventory/stale source or catalog digest | `UNKNOWN` | `UNKNOWN` | Block publication and re-inspect; never convert to absence. |
| Metadata-unique candidate that current renderer cannot select exactly | `UNIQUE` | as resolved | `UNADDRESSABLE` blocks automatic binding; explain limitation. |

`ABSENT` describes a completed, scoped physical search or an explicitly
closed-world family mapping, never a failure to recognize a term in an open
catalog. The existing accepted four-state contract is retained; the
classification field prevents taxonomy status from being conflated with
physical presence.

### Bare-token interpretation

The phrase `GR` can mean a literal channel mnemonic or a Gamma Ray concept.
Interpretation must not depend on a hidden model preference. The host may
classify a request as explicit physical only when the user supplies an
unambiguous physical selector (for example a source/frame-qualified channel
selection or an explicit phrase such as “channel mnemonic GR”). Natural
language family terms are matched through reviewed catalog terms. If a bare
token is simultaneously a physical mnemonic and a catalog family term, or
available evidence cannot distinguish the two interpretations, return an
interpretation ambiguity and ask the user. Do not silently privilege exact
spelling over semantic role or vice versa.

### Unit and source constraints

- A unit is evidence, not a semantic alias. Unit compatibility can narrow a
  reviewed family candidate only through a reviewed dimension/conversion
  table. An unknown unit cannot be assumed compatible.
- A conflicting unit rejects that semantic-family candidate or makes the
  result unresolved; it does not rewrite the source unit. No implicit
  conversion is performed unless an explicitly reviewed conversion is later
  implemented and recorded.
- Source/frame constraints are applied before candidate matching and must be
  user-authorized or derived from an already canonical source binding. The
  planner cannot widen source scope.
- Exact physical selection does not require a semantic family classification.
  This preserves open-world support for vendor channels unknown to the
  catalog.

## Catalog Audit of Supplied Reference JSON

The audit is deterministic and read-only over the four supplied files under
`examples/families/`. These files are currently untracked local inputs and
were not edited, staged, or copied into production. Their embedded content
does not identify a license, redistribution grant, authoritative version,
review owner, or mapping provenance. Their use here is limited to structural
and collision analysis; no conclusion about legal redistribution is made.

SHA-256 identities at audit time:

| File | SHA-256 |
| --- | --- |
| `FamiliesList.json` | `a0ed208e5db33a335dd94a587054934fb22a364b46828930d34f108013e773dd` |
| `FamilyAssignment.json` | `10bc93065cde0bfe024aa7e996aaa234eeaa5b61cbe9e13241b87ebdc76ddbac` |
| `FamiliesCompatibilityList.json` | `9dea89814aa22fa8ac738c7e7041eca91a7a5fc9da1ba6feaf8dbb1eb1958874` |
| `FamilyAssignment_CoreDb.json` | `af7e1e06ac3500f150fa53d7eec578b38d5a623621520658b0ee569c1d15120b` |

| Dataset | Rows | Findings |
| --- | ---: | --- |
| `FamiliesList.json` | 2,181 | 2,181 distinct `Family` values and 57 `MainFamily` values. `Scale` missing in 432 rows; `Min` in 690; `Max` in 693; `ColorLogview` in 1,709; `LineType` in 2,060; `Thickness` in 2,055; `Palette` in 2,083; `Unit` blank in one. These fields are optional/heterogeneous, not safe global defaults. |
| `FamilyAssignment.json` | 2,839 | 2,778 distinct variable strings; 1,505 rules contain `*` or `?` (including four universal `*` rules); 1,984 unit values are wildcard `*`. 329 pattern rows have fewer than four non-wildcard characters. Seventeen case-insensitive literal keys have differing family/unit pairs: 11 span different family labels and six retain one family label but differ in unit constraints. |
| `FamiliesCompatibilityList.json` | 210 | 36 distinct main families; 209 of its family labels do not exactly match a `FamiliesList.Family` label. It appears to express a different compatibility projection and cannot safely be joined by label alone. Thirty-five rows lack `Unit`. |
| `FamilyAssignment_CoreDb.json` | 1,186 | 1,163 distinct variable strings; 900 rules contain wildcards; 1,136 units are wildcard `*`. It shares 753 exact `(Family, Variable, Unit)` triples with the general assignment file; provenance/version relationship is not embedded. One duplicate `(Family, Variable, Unit)` group occurs for `CBL Amplitude/DCBL/*`. |

The structural audit also found:

- Conflict-count method: exclude variable strings containing `*` or `?`,
  trim and case-fold the remaining variable strings, and group distinct exact
  `(Family, Unit)` pairs. This yields 17 keys with differing pairs. Counting
  distinct family labels case-insensitively splits them into 11 multi-family
  keys and six same-family/different-unit keys. Thus 17 is not a count of 17
  distinct family-label conflicts. Examples of the 11 include `K` (Bulk
  Modulus (Dynamic), Permeability, Potassium Concentration), `C1` (Caliper 1,
  Mud Gas C1), `AZ` (Pad A Azimuth, Z Acceleration), and `PORE` (Effective
  Porosity, Pore Pressure). Examples of same-family unit differences include
  `ACF` and `FLPE`, where `*` and `unitless` differ. Four universal `*`
  patterns assign an unconstrained mnemonic to four unrelated families; they
  are non-discriminating and cannot be eligible for automatic matching.
- Matching the general assignment wildcard rules against the corpus's own
  distinct literal strings with case-sensitive `fnmatchcase`, while excluding
  the universal `*` patterns, yields 60 strings with cross-family wildcard
  matches. Examples include
  `A40L` (conductivity/resistivity attenuation/deep resistivity), `DPTRAZ_ROT`
  (true dip azimuth/inclination), `SPPA_HY` (spontaneous potential/standpipe
  pressure), and `DTS` (compressional and shear slowness). This is a corpus
  collision screen, not an assertion that every candidate mapping is
  scientifically wrong.
- In the compatibility list, labels such as `Acoustic Amplitude (Array)`
  have no exact family-label match in the main list. No suffix-stripping or
  fuzzy join is safe without provenance.
- Family labels mix physical quantities and operational, categorical, or
  descriptive concepts, including `Date`, `Date Time`, `Zone Name`, `Rig
  Status`, `Tool Status`, and `Quality Indicator`. A normalized schema needs
  explicit `concept_kind`; labels alone do not establish physical
  measurands or renderer support.
- Units include heterogeneous spellings/case and many absent or wildcard
  values (for example `gAPI`, `gapi`, `mS/m`, `ms/m`, `ohm.m`, `OHM-M`,
  `ft3/ft3`, `v/v`, `unitless`). These are not normalized dimensions or
  approved conversion rules. Do not infer compatibility from string
  similarity or normalize case without a unit-specific rule.
- Presentation metadata is sparse and string-valued. It does not establish
  which settings are current renderer capabilities, scientifically
  appropriate defaults, or licensed for redistribution.

Consequences: these datasets are useful for generating regression and
collision candidates, not direct production import. The initial reviewed set
must be hand-audited with provenance for GR, SP, depth, resistivity, neutron
porosity, bulk density, sonic, caliper, and representative array/waveform
types. It must include both positive mappings and negative/ambiguous
examples; no family alias or presentation value is approved here.

## Deterministic Matching Policy

1. Pin source identity/revision and catalog version/digest before resolving.
2. Establish request interpretation (`EXPLICIT_PHYSICAL`, `SEMANTIC_FAMILY`,
   or unresolved). Ambiguous interpretation asks the scientist; the model
   cannot promote its own guess to authority.
3. For explicit physical requests, compare exact normalized mnemonic and
   requested source/frame identity against a complete scoped inventory.
   Preserve all physical identities. Zero exact matches is `ABSENT` only if
   complete; multiple is `AMBIGUOUS`; incomplete is `UNKNOWN`.
4. For semantic-family requests, consider only `reviewed` exact aliases or
   individually reviewed, bounded rules whose provenance, scope, and catalog
   digest validate. Candidate rules are suggestions only. Apply explicit
   source/frame and compatible-unit constraints without guessing.
5. Multiple eligible physical candidates means `AMBIGUOUS`, irrespective of
   source order, JSON order, catalog order, or pattern length. A unit conflict
   does not authorize choosing another candidate silently.
6. A nonexhaustive catalog with no family candidate yields `UNKNOWN` /
   `UNCLASSIFIED`, not family-level `ABSENT`. A closed-world absence claim is
   possible only for a specifically reviewed catalog scope plus complete
   matching inventory.
7. Check exact renderer addressability after physical uniqueness. If not
   `ADDRESSABLE`, stop before binding. Do not substitute a same-mnemonic
   channel.
8. Revalidate source and catalog revisions before publication. Any stale
   identity invalidates the resolution and blocks the complete message.
9. Keep samples `NOT_CHECKED` unless an existing separately authorized
   deterministic operation establishes them. No sample arrays or statistics
   enter the semantic prompt.

## Bounded Model Projection

The existing context composer will receive only the request-scoped projection
needed for the current operation: selected source/frame display-safe identity,
complete/incomplete status, exact mnemonic, unit and known dimension,
resolution status, authorized candidate IDs when ambiguity requires a user
choice, addressability, and pinned catalog version. It will not receive the
whole catalog, file paths, raw descriptions, parser diagnostics with source
text, sample values, or full inventories unless the existing operation
strictly needs a bounded candidate list.

Context admission counts the complete rendered provider input: system and
user messages, framing/template tokens, request-specific contracts, and the
structured-output mechanism as actually implemented by the exact runtime.
Completion reservation and runtime context margin are separate. Serialized
request bytes remain a secondary cap. If the exact tokenizer/template or
structured grammar accounting is unavailable, fail closed with the
preflight-unavailable outcome; do not truncate mandatory facts, use a
character/token heuristic, or invoke a model to discover fit.

## Provider-Free D1 Qualification Matrix

| Case | Required deterministic outcome |
| --- | --- |
| Unique explicit mnemonic | Exact physical identity selected; classification may remain `UNCLASSIFIED`; require `ADDRESSABLE` to bind. |
| One unique reviewed family candidate | `UNIQUE` + `REVIEWED_MATCH` + `ADDRESSABLE`; snapshot pins both revisions. |
| GR-family request with `GR_STGC` and `GR_CORR` both reviewed/in scope | `AMBIGUOUS`; no sorting/first-match selection. |
| Unknown vendor mnemonic explicitly selected | Literal `UNIQUE` if present/addressable; never rejected solely for missing family classification. |
| Bare `GR` could be physical or family term | Interpretation ambiguity; ask user. |
| Broad wildcard collision, including sonic-family patterns | Candidate-only or rejected rule; if reviewed matches collide, `AMBIGUOUS`; never prioritize by order. |
| Unit conflict or missing unit for semantic request | Exclude only by reviewed dimension rules; otherwise `UNKNOWN`/clarification; no assumed conversion. |
| Physical channel present but renderer-unaddressable | Metadata `UNIQUE`, addressability `UNADDRESSABLE`; block automatic binding. |
| Incomplete LAS/DLIS inventory | `UNKNOWN`; never `ABSENT`; no publication. |
| Recognized family has no hit in nonexhaustive catalog | `UNKNOWN`/`UNCLASSIFIED`; do not claim family absent. |
| Explicit scale/color overrides preset | Preserve explicit values; preset does not overwrite. |
| Large channel inventory | Host filters to request-specific bounded projection; token admission uses complete exact request accounting. |
| Four-track conversational sequence | Each completed message persists one canonical revision and refreshed state. |
| Existing six-track section receives two additions | Preserve all six and append exactly two resolved additions, no sample loading. |
| Source revision changes after inspection | Revalidation invalidates resolution; no publication until reinspection. |
| Catalog digest invalid/unavailable | Literal exact selection may continue if source evidence is complete; family inference fails closed. |
| Catalog candidate alias or malicious source description | Cannot alter host authority; free text excluded from model projection. |

All cases are provider-free; this matrix is a design acceptance target, not a
claim that tests currently exist or pass.

## D1/D2 Gates and Open Decisions

### D1 integrated design gate

Independent review should decide whether the contracts, status separation,
matching policy, catalog schema, ownership, and matrix are adequate. D1
acceptance does not authorize code, alias promotion, budgets, provider calls,
or scientific work.

### D2 feasibility closure required before implementation

- Establish the supported LAS 1.2/2.0 metadata envelope and scanner/parser
  correctness, including encoding, duplicate curve mnemonics, malformed
  headers, long records, and completeness behavior.
- Obtain a valid synthetic RP66 fixture/generator; measure DLISIO CPU, wall,
  RSS/VSZ and metadata growth in a supervised child. Decide whether the
  canonical WSL2 runtime's `RLIMIT_AS`/`RLIMIT_CPU` plus process-group kill is
  adequate or a delegated cgroup/job limit is required.
- Define service latency/resource objectives, run the bounded representative
  matrix, and only then propose finite parser, metadata-object, output-byte,
  query, CPU, wall, and memory budgets. No arbitrary total-source-byte cap.
- Obtain exact Qwen model/tokenizer/template and matching llama.cpp structured
  output implementation for complete request-token accounting, or separately
  authorize a non-generative runtime capability check. No endpoint work under
  this D1 authorization.
- Establish source/license/redistribution provenance for any catalog records
  that could be shipped. Define domain-review owner, catalog release/digest
  process, evidence standard, and deprecation/correction policy.
- Review trusted alias provenance and source-provided alias trust before any
  semantic role matching can be enabled. Existing `AuthoringChannelAlias`
  and candidate alias fields do not presently encode those governance facts.

These items are not solved by the JSON audit or by D1 acceptance. A09 remains
open until D2 and later implementation/qualification gates are separately
accepted.

## Invariant Preservation

| Invariant | D1 design constraint |
| --- | --- |
| K-01 one canonical engine | Reuse existing planner, workers, reconciliation, executor, service, YAML, and renderer. |
| K-02 host owns source identity | Model proposes semantic request only; host resolves source/frame/channel identity. |
| K-03 structure is not semantic correctness | Keep provider validity, semantic resolution, and host application as separate outcomes. |
| F13 metadata/addressability distinction | Metadata uniqueness cannot imply renderer addressability. |
| F14 trusted aliases | Only versioned, provenance-reviewed rules authorize semantic equivalence. |
| Four-state source resolution | Preserve `UNIQUE`/`AMBIGUOUS`/`ABSENT`/`UNKNOWN`; classification/addressability/samples remain separate dimensions. |
| Snapshot integrity | Source and catalog revisions are pinned and revalidated before publication. |
| Open-world physical support | Unknown taxonomy does not block explicit physical channel selection. |
| No sample leakage | No sample arrays/statistics in planner/worker context. |
| A08 transaction boundary | Ambiguity/incomplete evidence blocks the whole message; no partial YAML publication. |
| Renderer and scientific loader stability | No A09 change to full-data loaders, renderer semantics, or binding schema. |

## Scope, Status, and References

This D1 document is a review candidate layered on the accepted metadata-first
design; it does not amend that historical record. If independently accepted,
record the relationship in A09 development memory/backlog. Do not promote new
invariants to `docs/agent-code-mode-current-baseline.md` before acceptance
and the required Knowledge Delta process.

The audit input identities and limitations are recorded above and in
`docs/evaluations/agent-code-mode/A09-resource-budget-feasibility.md`.
Relevant primary references already reviewed in the accepted A09 design
include CWLS LAS 2.0, LASIO 0.31 documentation plus locked 0.32 source,
DLISIO API/sample-access documentation plus locked 1.0.4 source, and the
llama.cpp server documentation. Those references establish parser/API
behavior only; they do not establish WellPlot budgets, alias equivalence,
license rights, or production support. See the accepted design's References
section for exact links. The proposed structural schema uses the official
[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) vocabulary.
The unit proposal may evaluate [UCUM](https://ucum.org/ucum) as a machine
syntax for recognized units, but adopting UCUM would not validate the source
catalog's unit strings, prove semantic compatibility, or authorize
conversions; these remain D2/domain-review decisions.

```text
provider calls = 0
model calls = 0
endpoint calls = 0
scientific turns = 0
C02 exposure = 0
production source changes = 0
```
