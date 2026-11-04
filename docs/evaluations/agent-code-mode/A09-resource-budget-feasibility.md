# A09 — Metadata Inspection and Resource-Budget Feasibility

**Date:** 2026-11-03
**Status:** Provider-free feasibility package; decisions remain open
**Accepted design:** `daef5d171828495b2f0dfcea25ae372f0bc39af4`
**A09 implementation:** Not released by this package
**Live/provider/scientific/C02 activity:** None
**D1 joint design:** `docs/architecture/A09_JOINT_SEMANTIC_CATALOG_AND_SOURCE_INSPECTION_DESIGN.md` (review pending)

## Decision Summary

The accepted design direction is feasible within the existing canonical
inspection and authoring architecture, but this package does not authorize
implementation or select production budgets.

| Question | Evidence and disposition |
| --- | --- |
| LAS metadata without samples | LASIO 0.32 `ignore_data=True` leaves an empty data array, but its section finder scans to EOF. A streaming, bounded prefix-to-data-section adapter is a feasible candidate; its edge cases need tests before implementation. |
| DLIS metadata and resource behavior | DLISIO 1.0.4 scans/indexes the entire physical file. Metadata access can avoid curve arrays, but no valid synthetic DLIS generator/fixture was available, so parser time/RSS was not measured. |
| Enforceable process limits | WSL2 supports process `RLIMIT_AS`, `RLIMIT_CPU`, and parent-enforced process-group wall termination. A cgroup-v2 mount is present but read-only here; no finite memory cap is configured for the current scope. Limits were mechanism probes, not selected budgets. |
| Finite inspection/metadata budgets | Synthetic LAS sweeps characterize some parser costs, but do not represent adversarial or representative production metadata and do not justify final numeric thresholds. |
| Qwen/llama.cpp token accounting | Not measurable exactly here without a matching tokenizer/model/template implementation. No such local assets or tools were found; endpoint calls were outside scope. |
| Alias provenance/versioning | Existing catalog is static and unversioned. Source candidate aliases can participate directly in matching. A versioned, provenance-bearing, fail-closed catalog policy is required before semantic-role matching is enabled. |

The next implementation gate requires review of the candidate LAS prefix
approach, DLIS process-boundary policy, measurement plan, token-counting
feasibility, and alias governance. No arbitrary source-file size ceiling is
proposed.

The four supplied family-reference JSON files were also structurally audited
read-only for D1. Counts, SHA-256 identities, wildcard/collision examples,
missing metadata, unit ambiguity, and licensing/provenance limitations are
recorded in the D1 design. They are local input data, were not edited or
copied into production, and are not runtime-authoritative. The audit is a
collision screen, not scientific validation of each row. Observed family/unit
assignments and broad wildcard overlaps prevent direct promotion of these
datasets into a trusted catalog.

Conflict-count methodology was reconciled: for `FamilyAssignment.json`,
exclude variable strings containing `*` or `?`, trim and case-fold the
remaining variable keys, then count distinct exact `(Family, Unit)` pairs.
This produces 17 keys with differing pairs. Eleven have multiple family labels
(case-insensitive); six retain one family label and differ only in unit
constraints. The 17 figure is therefore not 17 distinct scientific-family
conflicts. Wildcard collision screening separately applies case-sensitive
`fnmatchcase` to distinct literal strings and excludes universal `*` patterns.

## Accepted Decision Recorded

The metadata-first architecture, including F13 and F14, was accepted at exact
checkpoint `daef5d171828495b2f0dfcea25ae372f0bc39af4`. It requires separate
metadata resolution, existing-renderer addressability, and numerical sample
availability; a `UNIQUE` metadata result alone cannot authorize a binding.
Semantic equivalence requires a trusted alias mapping; mnemonic resemblance
does not establish equivalence.

This is a design acceptance, not A09 implementation acceptance. No active
baseline promotion is made here. The accepted design is recorded in
`docs/evaluations/agent-code-mode/A09-development-memory.md` and
`docs/backlog.md`.

## Environment and Method

All parser measurements used temporary synthetic LAS files under `/tmp`, the
locked project virtual environment, and provider-free local code. No repository
scientific LAS/DLIS fixture, runtime endpoint, credential, provider, model, or
campaign was accessed.

Observed environment:

- Python `3.12.7`, Linux `6.18.33.2-microsoft-standard-WSL2`.
- Locked packages: LASIO `0.32`, DLISIO `1.0.4`, OpenAI SDK `2.34.0`.
- `tokenizers`, `transformers`, `tiktoken`, and `llama_cpp` are not installed
  in `.venv`.
- No `llama-server`, `llama-tokenize`, or Qwen GGUF/tokenizer file was found
  in the probed standard binary directories, repository, or user cache.
- `/sys/fs/cgroup` is cgroup v2 and mounted read-only. The current
  `/init.scope` reports `memory.max=max`; per-job cgroup limits cannot be
  configured from this execution.
- `resource.RLIMIT_AS` and `resource.RLIMIT_CPU` are available. A constrained
  child allocation probe hit `MemoryError`; a CPU-loop probe was terminated
  by the OS at its deliberately tiny test limit; a sleeping child was killed
  by its parent process-group timeout. These prove control mechanisms exist,
  not that the probe values are suitable production limits.

### Synthetic LAS construction

The sample-tail cases used a small LAS 2.0 header with `DEPT` and `GR`, a
`~ASCII` marker, and repeated `0 0\n` rows sized to 1, 8, and 32 MiB total.
Each parser timing/RSS observation ran in a fresh `.venv/bin/python` process
with `lasio.read(path, ignore_data=True)`. `ru_maxrss` is reported in KiB by
Linux. The parser-import baseline, in three fresh processes, was 36,200–36,380
KiB.

Header-volume cases used a synthetic `~Other` record containing 4 KiB, 256
KiB, or 2,048 KiB of one unwrapped text line. Curve-count cases used unique
synthetic curve names plus `DEPT`, from 10 through 5,000 non-index curves.
These intentionally synthetic distributions are characterization inputs,
not representative geological metadata or a statistical sample.

## LASIO 0.32 Findings

Installed-source inspection establishes:

- `lasio.read()` documents `ignore_data=True` as parsing headers without
  reading actual sample data.
- `LASFile.read()` calls `find_sections_in_file()` before its
  `if not ignore_data` data-parsing branch.
- `find_sections_in_file()` repeatedly calls `readline()` until EOF and checks
  each line for a section marker. Thus `ignore_data=True` avoids parsing and
  retaining sample arrays, but does not avoid scanning sample-tail bytes.
- `open_with_codecs()` defaults encoding detection to 4,000 characters, but
  when `autodetect_encoding_chars` is falsy it reads the entire file for
  detection. The metadata call must not accidentally select this unbounded
  mode.
- `readline()` has no per-line byte bound here. A very large single header/data
  line can therefore allocate proportionally before application-level checks.

Relevant installed-source locations:

- `.venv/lib/python3.12/site-packages/lasio/reader.py:134-205` — encoding
  detection; `:266-300` — EOF section scan.
- `.venv/lib/python3.12/site-packages/lasio/las.py:351` — data parsing is
  skipped when `ignore_data=True`.

### Observations

| Synthetic input | Bytes | `ignore_data=True` elapsed | Peak RSS | Data shape |
| --- | ---: | ---: | ---: | --- |
| 1 MiB sample tail | 1,048,576 | 0.723753 s | 36,328 KiB | Not captured in first run |
| 8 MiB sample tail | 8,388,608 | 5.706277 s | 36,308 KiB | Not captured in first run |
| 32 MiB sample tail | 33,554,432 | 23.986041 s | 36,420 KiB | Not captured in first run |
| 4 KiB single header record | 4,267 | 0.001528 s | 36,328 KiB | Not captured in first run |
| 256 KiB single header record | 262,315 | 0.002557 s | 36,932 KiB | Not captured in first run |
| 2,048 KiB single header record | 2,097,323 | 0.008560 s | 42,700 KiB | Not captured in first run |
| 10 non-index channels + DEPT | 492 | 0.001653 s | 36,676 KiB | `(0, 11)` |
| 100 non-index channels + DEPT | 3,732 | 0.006312 s | 36,608 KiB | `(0, 101)` |
| 1,000 non-index channels + DEPT | 37,032 | 0.227126 s | 37,340 KiB | `(0, 1001)` |
| 5,000 non-index channels + DEPT | 189,032 | 4.958656 s | 41,084 KiB | `(0, 5001)` |

The 1/8/32 MiB sample-tail timings show a strong input-scan cost while peak
RSS remains near the import baseline. The 2 MiB unwrapped header record raised
peak RSS by roughly 6 MiB over the import baseline. The 5,000-channel
synthetic header took about 5 seconds and added about 5 MiB over baseline.
Cold/warm page-cache state and machine scheduling were not controlled; these
single-run timings are not p95/p99 service measurements and must not be used
as production thresholds.

### Bounded-prefix feasibility probe

A provider-free proof-of-concept streamed lines only until the synthetic
`~ASCII` marker, passed that prefix as a text stream to LASIO with
`ignore_data=True`, and asserted `data.shape == (0, 2)`. Prefix length was
159 bytes for all sample-tail sizes. Thirty in-process runs per file yielded:

| Whole synthetic file | Prefix bytes | Median scan + parse | p95 | Max |
| ---: | ---: | ---: | ---: | ---: |
| 1 MiB | 159 | 0.304 ms | 0.478 ms | 1.106 ms |
| 8 MiB | 159 | 0.283 ms | 0.357 ms | 0.668 ms |
| 32 MiB | 159 | 0.273 ms | 0.322 ms | 0.383 ms |

This proves the existing LASIO header parser can parse a terminated synthetic
prefix without samples; it does not validate a production scanner. The probe
used `readline()`, so it is not safe for an adversarially long line. Any
implementation must scan in bounded chunks, enforce cumulative header/record
budgets, support the declared LAS 1.2/2.0 encodings and line endings, and
return an incomplete/`UNKNOWN` result when a scan budget is exceeded. It must
recognize the data-section marker without treating ordinary header text as a
marker. LAS 3 remains outside the locked parser's fully supported set unless
separately verified. No total source-file-size check is needed for this path.

**Candidate feasibility decision:** Do not call `lasio.read(path,
ignore_data=True)` directly on an unbounded complete file for semantic
inspection. Keep LASIO as the canonical header parser, but feed it a bounded
prefix ending at the supported data-section marker. The scanner and limits
remain design-only and require independent review and regression tests.

## DLISIO 1.0.4 and Process Containment

Installed-source inspection establishes:

- `dlisio.dlis.load()` documents that it scans the entire physical file and
  constructs an index because DLIS does not provide random access.
- `LogicalFile.cache_metadata(False)` disables object caching to trade memory
  for CPU/reconstruction work; it does not remove the full-file indexing
  requirement or provide a time/memory ceiling.
- `Frame.curves()` and `Channel.curves()` materialize numerical values as
  NumPy arrays and must not be used in metadata inspection.
- The installed package exposes a compiled native `dlisio.core` extension.
  There is no writer/fixture-generation API in the inspected package surface,
  and repository DLIS files are non-synthetic and were intentionally not
  used. Consequently, DLIS parser wall-time, peak RSS, metadata scaling, and
  multi-logical-file identity behavior have **not** been empirically measured
  in this package.

Relevant locations:

- `.venv/lib/python3.12/site-packages/dlisio/dlis/load.py:8-17` — full scan
  and index.
- `.../dlis/file.py:384-398` — metadata cache trade-off.
- `.../dlis/frame.py:295-316` and `.../dlis/channel.py:206+` — sample APIs.
- `src/wellplot/io/dlis.py:284-324` — current renderer loader selects
  `logical_files[0]` and calls `frame.curves()`.
- `src/wellplot/model/dataset.py:234-250` — channels are keyed by mnemonic.

### Candidate containment for the canonical WSL2 runtime

The feasible A09 candidate is a supervised, read-only parser subprocess
behind the existing canonical inspection facade, not a new service or
ingestion engine:

1. Parent passes a resolved source path and a bounded metadata-only task; child
   performs deterministic parser inspection and returns a bounded
   serializable projection. No samples, unrestricted parser objects, or
   arbitrary source bytes cross the boundary.
2. Child applies finite `RLIMIT_CPU` and `RLIMIT_AS` before importing/using
   DLISIO. `RLIMIT_AS` constrains virtual address space, including native
   allocations, and therefore caps the addressable process footprint; it is
   not a direct RSS/cgroup measurement. A limit-triggered allocation/parser
   failure is a bounded inspection failure, not `ABSENT`.
3. Parent enforces a monotonic wall-clock deadline and kills the isolated
   process group on expiry. Require a clean successful exit, bounded output,
   and complete inventory marker before returning metadata. Never promote
   partial child output to a complete inventory.
4. Keep the child from spawning unrestricted descendants; if the parser or
   runtime later requires them, ensure limits are inherited and the process
   group remains killable.

The OS probes demonstrate `RLIMIT_AS`, `RLIMIT_CPU`, and parent wall-time
termination in this WSL2 environment. They do not establish suitable numeric
limits or test DLISIO under them. cgroup v2 exposes memory controllers in the
mount, but the mount is read-only here and the current scope has
`memory.max=max`; per-job cgroup RSS enforcement is unavailable in this
execution context. Before adoption, review whether `RLIMIT_AS` plus a child
process is an adequate memory contract for native DLISIO allocations. If a
direct RSS/cgroup limit is mandatory, the supported runtime must provide a
writable delegated cgroup or equivalent OS job limit. That is an explicit
prerequisite, not an assumed capability.

**Unresolved DLIS evidence:** A valid, synthetic RP66 fixture or generator is
needed to exercise logical-file/frame/channel scaling and failure behavior
without touching scientific fixtures. Only after that exists can a bounded
sweep report CPU time, wall time, peak RSS, metadata object counts, and
cache-on/cache-off behavior. No real production DLIS is authorized for this
decision package.

## Inspection and Metadata Budget Derivation

### Measured bounds are not accepted limits

The synthetic LAS measurements establish only observed points. They do not
establish supported geological-file distributions, WSL cold-I/O behavior,
DLIS costs, or a user-facing latency objective. Therefore **no numeric
production budget is proposed or approved here**.

Before implementation, decide a supported runtime envelope and inspection
SLO, then run a pre-bounded provider-free matrix that includes:

- LAS 1.2/2.0 headers with varied encoding/line endings and header order;
- sample tails growing independently of header size, including sparse and
  sequentially written files;
- long unwrapped records, many channel records, malformed section markers,
  and metadata with hostile free-form strings;
- valid synthetic DLIS with controlled logical-file, frame, channel, and
  record counts, malformed/corrupt variants, and sparse/large sample regions;
- cold and warm reads, repeated trials, and process startup separated from
  parser time;
- peak process RSS/VSZ and OS-limit outcomes, wall/CPU time, scanned bytes,
  metadata records, output bytes, and query count.

Derive separate finite controls for header bytes/records, metadata objects,
projected output bytes, read/query count, CPU, wall time, and process memory.
Choose the limits from the declared service SLO and measured distribution of
the supported synthetic envelope, with explicit safety margin and failure
semantics. A limit breach returns a typed incomplete result and channel
resolution `UNKNOWN`. It never implies that the whole source is absent or
invalid. Keep serialized inspection-context bytes as a separate bound from
source/header and parser-process budgets.

### What remains unmeasured

- LAS metadata performance on non-synthetic or representative multi-gigabyte
  sources; only controlled synthetic tails were used.
- The bounded-prefix scanner under adversarial encodings, line endings,
  section marker variants, and large records.
- Any valid DLIS parse timing, RSS, cache strategy, or native failure under
  process limits.
- A production-selected numeric budget and target inspection latency.
- Queue/concurrency interaction under more than the current one concurrent
  agent call; no concurrency experiment was run.

## Complete Qwen/llama.cpp Request-Token Accounting

Static source inspection of the canonical provider path shows:

- `OpenAICompatibleBackendV2` constructs a Chat Completions request with the
  configured model, system/user messages, optional output-token limit, and
  configured `extra_body` request options.
- It adds a Pydantic-generated strict `response_format: json_schema` object
  before dispatch.
- The planner serializes its structured context into the user message.
- Provider-reported `prompt_tokens` are read from the response only after a
  generation; that is not preflight admission.

This interface description is not an exact token count. `tokenizers`,
`transformers`, `tiktoken`, `llama_cpp`, llama.cpp binaries, and local Qwen
model/tokenizer files were not found in the probed environment. Contacting the
runtime `/tokenize`, `/apply-template`, or other endpoint is outside this
provider-free package. Therefore exact Qwen counts, schema grammar accounting,
and context-window fit are **not established**.

### Required accounting contract

For the configured Qwen model, exact preflight must count the final rendered
chat input using the same GGUF tokenizer and chat template as the deployed
llama.cpp build, including the frozen template options (thinking disabled).
Count system/user messages and all framing/special tokens after template
application. Include schema text in prompt tokens only if the deployed
structured-output implementation actually injects it into the rendered
prompt. If JSON Schema is compiled to a constrained-decoding grammar rather
than prompt text, treat it as a separate bounded grammar/schema resource
dimension; do not pretend its JSON bytes are prompt tokens. Verify the exact
`response_format` conversion in the deployed build source. Reserve the
configured maximum completion tokens and runtime-specific context margin
against the model context capacity. Enforce a separate serialized-request byte
cap as a transport/memory backstop.

The offline acceptance artifact must bind tokenizer/model/build/template
identity, input request projection digest, rendered-prompt token count,
structured grammar identity/size, output reservation, context capacity, and
the final admission decision. If the matching local tokenizer/template is not
available, fail preflight as `TOKEN_BUDGET_UNAVAILABLE`; do not use character
ratios, generic tokenizer packages, prior response usage, or silent
truncation.

**Feasibility result:** Exact Qwen request-token accounting cannot be
completed under current local assets and the no-endpoint constraint. The
remaining decision requires provision of the exact tokenizer/model/template
implementation locally or a separately authorized non-generative runtime
capability check; neither occurred here.

## Trusted Alias Catalog Governance

Source inspection found the current alias catalog in
`src/wellplot/mcp/service.py` as a static tuple. Its Gamma Ray entry lists
`GR`, `SGR`, and `CGR`, not `GR_STGC` or `GR_CORR`; entries do not carry
per-mapping provenance or a version. `_candidate_matches()` in
`src/wellplot/authoring_context.py` first matches candidate-provided aliases
directly, then the catalog. `AuthoringChannelCandidate.aliases` can be
populated from inspection mappings without an explicit trust/provenance
field. Thus the currently inspected contract does not yet prove that every
alias used for semantic resolution is trusted.

### Proposed policy, not implementation

- A catalog release has a stable semantic version and canonical content
  digest; both are included in source-resolution snapshots and custody.
- Keep request-language interpretation rules separate from
  concept-to-physical-channel classification rules. The former maps exact
  normalized scientist terms to a stable concept; the latter independently
  maps inspected physical mnemonics/patterns to that concept under source,
  unit, and identity constraints. Each assertion has its own provenance and
  review, even if they share a family registry and resolver.
- A physical-channel rule may declare an exhaustive source/frame scope only
  with explicit evidence and domain review. Only that scoped exhaustiveness,
  together with a complete inventory, can support family-level `ABSENT`.
  Domain-qualified review is required; name similarity is insufficient.
- If a catalog is unavailable, digest-invalid, or lacks a mapping, exact
  physical mnemonic matching may proceed where the user supplied that exact
  identity. Role-based inference returns `UNKNOWN`/clarification. No catalog
  error may expand a candidate set.
- Candidate/source aliases are descriptive evidence only unless their origin
  is explicitly trusted and covered by an approved provenance policy; they
  cannot silently bypass the governed catalog.
- `ABSENT` for a semantic role requires both complete channel inventory and an
  authoritative closed-world declaration that the role mapping is exhaustive
  for the relevant scope. Otherwise zero alias hits is `UNKNOWN`, not
  `ABSENT`.
- If an approved Gamma Ray role maps both `GR_STGC` and `GR_CORR` in scope,
  an unqualified role request returns `AMBIGUOUS`. The current catalog does
  not establish either equivalence.

Before implementation, freeze the catalog schema, source-evidence quality
rule, review owner, update/version procedure, closed-world scope, and fallback
status. Add provider-free positive, collision, missing-catalog, stale-digest,
untrusted-source-alias, incomplete-inventory, and GR ambiguity regressions.

The integrated D1 proposal is in
`docs/architecture/A09_JOINT_SEMANTIC_CATALOG_AND_SOURCE_INSPECTION_DESIGN.md`.
It separates request-term aliases from physical-channel rules, and semantic
classification from four-state physical resolution, renderer addressability,
and sample availability. It proposes normalized catalog and source-metadata
shapes, a two-stage deterministic resolver, direct catalog-digest custody, and
a provider-free acceptance matrix. It also proposes a narrow amendment to
accepted F14 bare-token and family-absence semantics; that amendment is pending
independent D1 acceptance and does not close any D2 feasibility item or
authorize implementation.

### Supplied family JSON audit disposition

The D1 audit examined `FamiliesList.json`, `FamilyAssignment.json`,
`FamiliesCompatibilityList.json`, and `FamilyAssignment_CoreDb.json` using
read-only JSON parsing and deterministic exact/glob collision checks. It
identified broad/universal wildcard assignments, exact mnemonic strings
assigned to multiple families or incompatible unit labels, sparse presentation
fields, taxonomy labels that include nonphysical/status concepts, compatibility
labels that do not exactly join to the family list, and no embedded license or
rule-provenance/version data. Exact row counts and digests are in the D1 design.

Disposition: retain as a reference/collision corpus only. Do not import rows,
presentation defaults, unit conversions, or family assignments as production
authority. No redistribution conclusion is made; obtain provenance/license
review before copying substantial data into a shipped catalog. Curate the
initial GR/SP/depth/resistivity/neutron-porosity/bulk-density/sonic/caliper and
array/waveform rules individually, with domain evidence and collision tests.

## Decision Register

| Decision | Current evidence | Proposed disposition | Remaining gate |
| --- | --- | --- | --- |
| LAS parser | Stock API avoids sample arrays but scans tail; prefix proof-of-concept works on synthetic LAS 2.0 | Continue with bounded prefix scanner feeding LASIO; retain full loaders elsewhere | Review scanner limits and matrix before implementation |
| DLIS parser | Full-file index is confirmed; no synthetic parser measurements | Metadata-only object traversal in a supervised child; no sample APIs | Review RLIMIT_AS/CPU plus wall timeout semantics and obtain valid synthetic RP66 fixture |
| Resource budgets | Synthetic LAS scaling only; no service SLO or DLIS distribution | Derive per-resource budgets from measured supported matrix; choose no constants in code now | Human/architecture review of measured proposal before implementation |
| Token budget | Existing request shape understood, exact tokenizer/template unavailable | Exact same-build/model tokenization; separate grammar cap and byte cap | Local tokenizer/build availability or separate non-generative authorization |
| Aliases | Static catalog is unversioned; candidate aliases lack explicit trust marking | Content-addressed, provenance-bearing, scope-aware closed-world registry | Review governance and compatibility correction before enabling role resolution |

### Suggested finite next study

The next provider-free feasibility increment should be limited to:

1. A bounded LAS 1.2/2.0 matrix for the prefix scanner and header/curve
   budgets, with repeated cold/warm timing and OS RSS measurements.
2. A separately generated minimal synthetic RP66 fixture (or a documented
   blocker if a safe generator cannot be built without broad parser work),
   followed by metadata-only DLIS subprocess tests under child limits.
3. A review of whether the current WSL2 `RLIMIT_AS` contract is acceptable or
   a writable delegated memory cgroup is required.
4. Offline provision of the exact Qwen GGUF/tokenizer and matching llama.cpp
   source/build for input-template/schema accounting. No endpoint calls.
5. Alias catalog governance acceptance before any new role mapping is added.

Do not broaden this into production code, real-source asset inspection, model
execution, or scientific qualification. If a required asset/capability cannot
be obtained under these constraints, preserve the bounded blocker and request
separate authority rather than substituting evidence.

## Execution Accounting

```text
provider generation calls = 0
model generation calls = 0
endpoint calls = 0
scientific turns = 0
C02 exposure = 0
production source changes = 0
```

The synthetic LAS files were temporary and contained no source/scientific
data. Their measurements are summarized above; no historical evidence or
campaign artifact was modified.
