# A09 — Metadata Inspection and Resource-Budget Feasibility

**Date:** 2026-11-03; decision follow-up 2026-11-04
**Status:** Provider-free feasibility package; decisions remain open
**Accepted design:** `daef5d171828495b2f0dfcea25ae372f0bc39af4`
**A09 implementation:** Not released by this package
**Live/provider/scientific/C02 activity:** None
**D1 joint design:** Accepted at `da23cd69792b4c75ed1da30bc0de35ca69ddcb38`; acceptance record at `docs/architecture/A09_D1_ACCEPTANCE_RECORD.md`

## Decision Summary

The accepted design direction is feasible within the existing canonical
inspection and authoring architecture, but this package does not authorize
implementation or select production budgets.

| Question | Evidence and disposition |
| --- | --- |
| LAS metadata without samples | LASIO 0.32 `ignore_data=True` skips samples but scans to EOF. A synthetic LAS 1.2/2.0 prefix matrix parses expected headers with empty arrays; scanner remains a prototype. |
| DLIS metadata and resource behavior | DLISIO 1.0.4 indexes the full file. A preserved 2,364-byte synthetic corpus covers two logical files, repeated mnemonics/copy numbers, and multiple frames; strict-error child probes distinguish parser failures from successful empty inventories. Scale/RSS behavior remains unmeasured. |
| Enforceable process limits | WSL2 supports `RLIMIT_AS`, `RLIMIT_CPU`, and parent process-group wall termination. The read-only cgroup mount provides no per-job RSS cap. Mechanisms were exercised, not selected as production policy. |
| Finite inspection/metadata budgets | Existing synthetic probes do not represent production distributions. Provisional p95 qualification targets were proposed on 2026-11-04; no target is measured or accepted as a production SLO, and no numeric resource threshold is justified. |
| Qwen/llama.cpp token accounting | Exact count remains unavailable without matching tokenizer/model/template and server source/build; no endpoint calls were made. |
| Alias provenance/versioning | Existing aliases lack per-rule provenance/version. Governance is proposed; no semantic-family mappings are approved from the supplied JSON inputs. Project owner nominated for initial domain review; role acceptance pending. |

For bounded provider-free functional implementation, the preconditions are the
accepted D1 ownership/resolution contract, basic parser isolation, exact source
identity, four-state deterministic resolution, fail-closed behavior, and finite
provisional safety limits reviewed before implementation. Expanded scaling,
production resource budgets, exact model-token accounting, domain-approved
production mappings, and latency-target qualification are later
provider-backed/production-readiness gates. The provisional targets are not
measured or approved as production SLOs. No arbitrary source-file size
ceiling is proposed.

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

### LAS marker and limit matrix (2026-11-03)

A temporary scanner prototype was exercised against generated LAS 1.2/2.0
headers only. The inputs covered LAS 1.2 CRLF with `~A`, LAS 2.0 LF with
`~ASCII`, CRLF with `~A (ASCII log data)`, leading spaces before a marker,
non-marker text mentioning `~A`, comment lines containing `~A`, other section
markers, the LAS 3 `~Log_Data` marker, an over-limit header line, and an
over-limit cumulative prefix. The accepted marker line was included in the
prefix passed to LASIO 0.32 `ignore_data=True`; all three valid inputs returned
the expected `DEPT`/`GR` curve metadata and `data.shape == (0, 2)`. Comment or
ordinary-text mentions, non-A section markers, and `~Log_Data` did not complete
the inventory. Line/prefix budget exhaustion returned `UNKNOWN` in the
prototype rather than an empty inventory.

The scanner predicate was aligned with the CWLS LAS 2.0 rule: a tilde at the
first non-space position begins a section, the first reserved character after
it selects the section, and the rest of that line is a comment. Therefore
`~A` plus a descriptive suffix is still an A/data-section marker; it must not
be rejected merely for not matching the exact strings `~A` or `~ASCII`. The
CWLS 2.0 standard says the data section is last and that section line suffix
is comment text. LAS 3 `~Log_Data` remains unsupported by this LASIO 0.32
candidate unless separately qualified.

This finite prototype corrects the earlier proof-of-concept's blind spot, but
is not a production scanner and does not cover all legal encodings, header
ordering, wrapped variants, malformed section grammar, or arbitrary long
records. No numeric production budget is inferred from its test-only line and
prefix caps. Its source was an ephemeral command, not a repository edit.

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

The `dlisio` package itself exposes no writer/fixture-generation API. A
separately maintained writer was subsequently found and used only from an
isolated `/tmp` target; repository DLIS assets were not used. One tiny
synthetic fixture established parser compatibility and exercised a supervised
metadata projection, but it is not a scaling or conformance corpus.

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

### Synthetic RP66 fixture and contained parse probe (2026-11-03)

The upstream `well-id/dliswriter` 1.2.0 project is an MIT-licensed, beta
Python writer that states it is based on RP66 v1 and documents generated mock
channels and frames. Its PyPI wheel was downloaded to `/tmp`, not installed in
the project environment or added as a dependency. The wheel SHA-256 matched
the PyPI-published digest:

```text
0f86a7b37a6e01eacc81f62a86e67b870f1439fb359510b9b7e8255f3c4f0cc2
```

Its default `output_chunk_size` is `2**32`, and its implementation
preallocates that entire bytearray. The first tiny-file attempt therefore
demonstrated an unsafe fixture-writer default for this constrained host; it
was stopped before a fixture was emitted. Passing an explicit 65,536-byte
output buffer produced a 1,020-byte synthetic physical DLIS containing one
logical file, one frame, and two channels (`DEPTH`, `GR`). The locked
`dlisio` 1.0.4 reader successfully indexed it and returned the expected
logical-file/frame/channel metadata. No `Frame.curves()` or
`Channel.curves()` API was called. The fixture was deleted after the test.

The same fixture was then parsed in a subprocess with test-only
`RLIMIT_AS=1 GiB`, `RLIMIT_CPU=10 s`, and a parent 15-second timeout. The child
exited successfully with the bounded metadata projection. These deliberately
test-only limits are not proposed production values. Combined with the
previous OS-mechanism probe (CPU/address-space limits and parent process-group
termination), this establishes that the available runtime can exercise the
containment mechanism on a valid minimal fixture. It does not establish limits
for large, malformed, multi-file, or adversarial DLIS inputs, nor direct RSS
containment: `RLIMIT_AS` limits virtual address space, and the current WSL2
cgroup mount is read-only with no per-job `memory.max`.

`dliswriter` is an independent generator, not a normative RP66 conformance
validator. The test demonstrates a useful fixture path accepted by `dlisio`,
not full RP66 conformance or compatibility with WellPlot's renderer. A bounded
fixture matrix and DLIS scaling/resource sweep remain necessary before
production budgets can be selected. No real production DLIS was used.

The expanded multi-logical/multi-frame fixture and strict-error corruption
results are in `docs/evaluations/agent-code-mode/A09-D2-feasibility-result.md`.
A valid 80-byte storage-unit label with no logical files is returned by
`dlisio` as an empty successful result, even with every `ErrorHandler`
severity configured to raise. The host must reject an empty logical-file
inventory as incomplete/`UNKNOWN`; a clean subprocess exit alone cannot
certify completeness. The fixture is preserved at
`tests/fixtures/a09_d2_metadata/multifile_repeated_mnemonics.dlis` with
SHA-256 `b98beba2bc6fedb70794da63d68dd09ac94abe02191fbfb53e6acd2eb85c08b9`.

## Inspection and Metadata Budget Derivation

### Provisional latency targets are not accepted limits

The synthetic LAS/DLIS measurements establish only observed points. They do
not establish supported geological-file distributions, WSL cold-I/O behavior,
or scaled DLIS costs. The following owner-proposed p95 targets bound
qualification only; none is measured or approved as a production SLO:

| Qualification stratum | Provisional end-to-end p95 target |
| --- | ---: |
| LAS 1.2/2.0 bounded metadata inspection, up to 1,000 channels | 2 seconds |
| DLIS RP66 v1 cold inspection, up to 250 MiB | 30 seconds |
| DLIS RP66 v1 cold inspection, larger tier up to 1 GiB | 90 seconds |
| Valid cached metadata for an unchanged source | 1 second |

The DLIS sizes are benchmark strata, not source-size admission ceilings.
Larger files remain eligible for bounded inspection and must not be rejected
solely by total bytes. A target miss is a performance result, not a safety
limit. Only separately reviewed resource limits may terminate inspection, and
their breach must return incomplete/`UNKNOWN` rather than `ABSENT`.

Before production-readiness, run a pre-bounded provider-free qualification
matrix on the current canonical WSL2/local-storage runtime, pinning
parser/library versions and recording exact source identities. This is not a
gate to initial functional implementation. Include subprocess startup in
end-to-end latency, while also reporting startup and parser time separately.
The matrix must include:

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
- p50/p95/p99 and per-run latency for each distinct file-size and cache tier;
  do not pool unlike strata. Record the measurement sample count and method
  before execution.

Initial implementation must use finite provisional safety controls for the
parser child, header/metadata projection, query count, and serialized context.
Their values must be explicitly proposed and reviewed before implementation;
they are safety controls, not optimized production budgets. A limit breach
returns typed incomplete evidence and channel resolution `UNKNOWN`. It never
implies that the whole source is absent or invalid. Keep serialized
inspection-context bytes as a separate bound from source/header and
parser-process budgets. Production values should later be reviewed against the
declared service SLO and measured supported distribution, with explicit
safety margin and failure semantics.

### What remains unmeasured

- LAS metadata performance on non-synthetic or representative multi-gigabyte
  sources; only controlled synthetic tails were used.
- The bounded-prefix scanner under adversarial encodings, complete supported
  LAS 1.2/2.0 marker/line-ending variants, and representative large records.
- DLIS scaling across logical files, frames, channels, records, and sparse or
  large sample regions; the single tiny fixture is only a compatibility probe.
- Peak RSS/VSZ, cache-on/cache-off effects, and native failure behavior for
  DLIS under production-appropriate process limits.
- Representative performance distributions and feasibility of the provisional
  latency targets; no production-selected numeric resource budget.
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

The public llama.cpp server interface documents `/apply-template` and
`/tokenize` as non-inference operations, which is a plausible later
measurement mechanism. Those are POST requests and were not called. The
deployed server build, exact GGUF tokenizer/template and how that build converts
OpenAI `response_format: json_schema` into prompt text versus grammar are not
available locally. Current WellPlot code sends system/user messages, the
Pydantic schema in `response_format`, output limit when configured, and frozen
request options; that source-level shape alone cannot establish final rendered
tokens or schema grammar cost. Consequently token admission remains blocked,
not approximated.

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

**D2 governance recommendation:** the first governed catalog release should
contain no active semantic-family-to-physical-channel mappings until each
mapping has a domain-reviewed evidence record. Exact physical-channel
selection remains usable through the explicit user request and does not
require alias inference. The supplied `examples/families/*.json` files remain
untrusted reference/collision inputs: their local presence does not establish
authorship, license, provenance, or scientific correctness. The current
evidence does not justify promoting GR/SP or any other family aliases, so no
initial scientific mapping is approved by this feasibility work.

For any future mapping, require a proposal record with source citation and
revision, exact evidence location, license/redistribution status, normalized
request term, exact physical identities, unit/source/frame constraints,
scope/exhaustiveness claim, conflict analysis, and named domain reviewer.
Separate two-person semantic and software-schema review; accept only into an
immutable release after positive, collision, ambiguity, stale-digest, and
fail-closed tests pass. Version each release and bind canonical content digest
and release ID into the existing snapshot/custody contract. Updates create a
new release; they never rewrite evidence or silently change an old resolution.
Missing, unreviewed, stale, or unavailable catalog data must leave semantic
classification `UNKNOWN`/clarification-required and must not block an exact
physical selector solely because a family mapping is absent.

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

The accepted integrated D1 design is in
`docs/architecture/A09_JOINT_SEMANTIC_CATALOG_AND_SOURCE_INSPECTION_DESIGN.md`.
It separates request-term aliases from physical-channel rules, and semantic
classification from four-state physical resolution, renderer addressability,
and sample availability. It proposes normalized catalog and source-metadata
shapes, a two-stage deterministic resolver, direct catalog-digest custody, and
a provider-free acceptance matrix. Its narrow F14 amendment for ambiguous
bare-token interpretation and exhaustive-scope family absence was accepted at
D1; the original historical design remains unchanged. This acceptance does
not close any D2 feasibility item or authorize implementation.

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
| LAS parser | LASIO 0.32 scans EOF; synthetic 1.2/2.0 bounded-prefix cases parse headers with empty arrays; marker semantics anchored to CWLS | Keep bounded prefix adapter as candidate, LASIO as header parser; return `UNKNOWN` on limits | Functional implementation: basic supported syntax and finite provisional safety controls. Production readiness: adversarial/representative matrix and evidenced operational budgets |
| DLIS parser | Preserved 2,364-byte synthetic multi-logical/multi-frame fixture; strict-error truncated cases fail, SUL-only succeeds empty | Keep metadata-only traversal in supervised child; require non-empty complete inventory; no sample APIs or project writer dependency | Basic isolation and finite provisional limits before implementation; expanded scale/memory qualification for production readiness |
| Resource budgets | Synthetic probes; provisional p95 targets proposed, not measured/accepted | Separate provisional safety controls from optimized production limits | Functional implementation: review finite provisional safety controls. Production readiness: measure each stratum on canonical WSL2/local storage and approve operational limits |
| Token budget | Existing request shape understood, exact tokenizer/template unavailable | Exact same-build/model tokenization; separate grammar cap and byte cap | Local tokenizer/build availability or separate non-generative authorization |
| Aliases | Static catalog is unversioned; candidate aliases lack explicit trust marking | Content-addressed, provenance-bearing, scope-aware closed-world registry | Review governance and compatibility correction before enabling role resolution |
| MCP source-inspection integration (F17) | `_request_context()` eagerly loads every declared source; enrichment may load selected sources again | One request-scoped, source-revision-bound projection; inspect lazily only when semantic obligations require source evidence | Include both MCP and enrichment call sites in implementation; preserve snapshot checks and canonical publication |

### D2 feasibility disposition (2026-11-03)

The bounded D2 work established the LAS prefix strategy and marker semantics
for a small synthetic matrix, found and validated an isolated synthetic DLIS
fixture path, inspected the canonical provider request construction, and
produced a fail-closed catalog-governance recommendation. It did **not** close
resource-budget selection or exact model-token accounting. The full D2 result
and evidence classification are recorded in
`docs/evaluations/agent-code-mode/A09-D2-feasibility-result.md`.

The D2 planning candidate was subsequently accepted at
`8dec3f37adcb8a90948cb7312ee3ec4a6fbde685`. F17 adds the MCP eager-versus-lazy
inspection integration requirement; it does not reopen D1. The D2 result
contains the provisional finite safety profile, lifecycle gate split, exact
existing-component map, and F17 resolution plan. The safety profile remains a
proposal awaiting implementation authorization, not production policy.

| Area | D2 status | Remaining gate |
| --- | --- | --- |
| LAS metadata-first feasibility | Established on synthetic 1.2/2.0 cases; scanner remains a prototype | Before implementation: bounded correctness behavior and finite provisional safety limits. Production readiness: expanded/adversarial and representative qualification |
| DLIS fixture/containment feasibility | Expanded synthetic multi-file/multi-frame fixture and strict corruption probes pass; no scale or production-limit evidence | Before implementation: supervised parser isolation, complete-inventory contract, finite provisional safety limits. Production readiness: 250 MiB/1 GiB scaling and hardened containment |
| Numeric resource budgets | Open; provisional latency targets are qualification-only; prior probes do not establish representative distributions | Not a functional-implementation gate. Measure against targets and approve enforceable production limits before production readiness |
| Exact Qwen/llama.cpp token accounting | Blocked: exact local tokenizer/build/template absent; endpoint prohibited | Not required for provider-free implementation; required before affected provider-backed qualification |
| Catalog governance | Policy proposed; no scientific mappings approved; project owner nominated as initial domain reviewer, acceptance pending | Synthetic mappings may support isolated tests. Accept reviewer role and approve evidence-backed production rules before activation, with independent schema review |

Do not treat D2 feasibility as permission to implement source inspection,
catalog mappings, parser limits, token admission, or a second loader. No
baseline promotion, provider/model/endpoint call, live smoke, scientific
qualification, or C02 activity is authorized by this record.

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
