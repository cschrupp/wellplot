# A09 D2 Feasibility Result

**Date:** 2026-11-03
**Accepted design:** D1 integrated catalog/source design at
`da23cd69792b4c75ed1da30bc0de35ca69ddcb38`
**Disposition:** Feasibility evidence delivered; implementation prerequisites
remain open
**Scope:** Provider-free, synthetic-only, documentation/evidence work

## Executive result

D2 established a feasible bounded-prefix path for supported synthetic LAS
1.2/2.0 headers and a safe way to create a small synthetic RP66-style DLIS
fixture for locked-reader probes. It confirmed that the canonical `dlisio`
reader still indexes the entire physical file, and that a supervised child can
be exercised with address-space/CPU limits plus a parent timeout. This is
mechanism evidence only; no production thresholds are justified.

Exact Qwen/llama.cpp request-token admission could not be established without
the deployed tokenizer, model/template and server implementation. Catalog
governance can be specified, but the available family files do not establish
licensed, domain-reviewed semantic mappings. Accordingly, no mappings are
approved and no numeric parser budgets are selected. **D2 is not a release to
implementation.**

## 1. LAS metadata-only feasibility

### Established behavior

The locked project environment has LASIO `0.32`. Installed-source inspection
confirms that `lasio.read(..., ignore_data=True)` skips parsing numeric samples
but still calls `find_sections_in_file()`, which reads lines until EOF to find
section markers. `readline()` also has no application-provided per-line bound.
The earlier synthetic 1/8/32 MiB tail measurements show the cost: about
0.72/5.71/23.99 seconds while peak RSS remained near the interpreter import
baseline. `ignore_data=True` alone is not bounded metadata inspection.

### Synthetic marker probe

A temporary chunked scanner prototype, not committed as production code, was
tested against generated inputs. It stopped at the data-section header and
passed only that prefix to LASIO with `ignore_data=True`:

| Input | Result |
| --- | --- |
| LAS 1.2, CRLF, `~A` | Two expected curve headers; data shape `(0, 2)` |
| LAS 2.0, LF, `~ASCII` | Two expected curve headers; data shape `(0, 2)` |
| LAS 2.0, CRLF, `~A (ASCII log data)` | Two expected curve headers; data shape `(0, 2)` |
| Comment/text mention of `~A`, `~V`, or LAS 3 `~Log_Data` | No supported data marker; `UNKNOWN` |
| Synthetic header record over test line bound | `UNKNOWN_LINE_LIMIT` |
| Prefix over test cumulative bound | `UNKNOWN_TOTAL_LIMIT` |

The marker rule was corrected against the [CWLS LAS 2.0 specification](https://www.cwls.org/wp-content/uploads/2014/09/LAS_20_Update_Jan2014.pdf): a section starts when `~` is the first non-space character; the first reserved character after it identifies the section and the rest of the marker line is comment text. Thus a descriptive suffix after `~A` is valid. LAS 3 `~Log_Data` is not admitted to the LASIO 0.32 candidate without separate qualification.

The scanner used finite test-only chunk, line and total-prefix values. Those
are not proposed runtime limits. The probe did not cover the full valid
encoding/line-ending/header-order space, adversarial inputs, wrap modes,
representative geology distributions, or production cold-I/O behavior. No
total source-file size cutoff is recommended or authorized.

**Classification:** LASIO EOF scan is `ESTABLISHED` by installed source;
bounded-prefix parsing is `EMPIRICALLY_SUPPORTED` for the listed synthetic
cases; a production adapter is an `ADAPTED` design candidate pending complete
matrix and budget review.

## 2. DLIS fixture and containment feasibility

`dlisio.dlis.load()` documentation states that it scans the complete physical
file to build an index because DLIS does not provide random access. Metadata
caching trades CPU for memory; it does not avoid the index scan. Sample-array
accessors such as `Frame.curves()` were not called during the D2 metadata
probe. See the [dlisio 1.0.4 API](https://dlisio.readthedocs.io/en/stable/dlis/api.html).

The separate [`well-id/dliswriter`](https://github.com/well-id/dliswriter)
project documents an MIT-licensed writer based on RP66 v1, but describes
itself as beta and is not a normative conformance validator. Its
[PyPI 1.2.0 wheel](https://pypi.org/project/dliswriter/1.2.0/) was downloaded
to `/tmp`; SHA-256 `0f86a7b37a6e01eacc81f62a86e67b870f1439fb359510b9b7e8255f3c4f0cc2`
matched the published wheel digest. It was not installed into the project
environment or dependency set.

The writer defaults `output_chunk_size` to `2**32` and preallocates a bytearray
of that size. The initial fixture attempt exposed this 4 GiB default and was
terminated before producing a fixture. An explicit 65,536-byte writer buffer
produced a 1,020-byte synthetic physical DLIS with one logical file, one
frame, and `DEPTH`/`GR` channels. `dlisio` 1.0.4 loaded it and returned the
expected source identities and frame-channel membership. No sample curve API
was invoked. The temporary fixture was deleted after the probe.

The same fixture was parsed in a child process with test-only `RLIMIT_AS` of
1 GiB, `RLIMIT_CPU` of 10 seconds, and a parent timeout of 15 seconds. It
exited successfully and emitted only a bounded metadata projection. Separately
recorded OS probes showed that address-space/CPU limits and parent process-group
termination are available. The WSL2 cgroup v2 mount is read-only and exposes
no writable per-job `memory.max`; `RLIMIT_AS` constrains virtual address space,
not measured RSS.

This proves only that a tiny generated file can be parsed in a supervised
process under test values. It does not establish RP66 conformance breadth,
large or malformed-file safety, multi-logical-file identity, scaling, peak
RSS, cache strategy, or suitable production limits. The writer's 4 GiB default
is a concrete warning that fixture-generation tools also need explicit
resource parameters.

**Classification:** full-file indexing and cache trade-off are `ESTABLISHED`
by dlisio documentation/source; the tiny generated fixture and child run are
`EMPIRICALLY_SUPPORTED`; supervised metadata parsing is an `ADAPTED` design
candidate. Production memory containment remains an open decision between an
accepted `RLIMIT_AS` contract and providing a writable delegated cgroup or
equivalent OS job limit.

## 3. Resource budgets

No finite production thresholds are selected. The existing LAS measurements
and one tiny DLIS fixture are not representative distributions; no inspection
latency SLO or supported metadata envelope has been declared. Arbitrary
thresholds would turn test caps into unsupported product policy.

Before implementation, the owner must declare the supported runtime envelope
and inspection SLO. A finite synthetic matrix should then measure separately:

- bounded LAS header bytes, records, line sizes, curve counts, encodings,
  marker variants, and sample-tail independence;
- DLIS physical bytes, visible/logical records, logical files, frames,
  channels, free-form metadata, cache mode, and malformed/corrupt cases;
- child startup separately from parser CPU and wall time, peak RSS and VSZ,
  limit-trigger behavior, parent cancellation, result bytes, and query count;
- repeated cold/warm runs, with exact tool/library/runtime identities.

Choose distinct finite limits for header bytes/records, metadata objects,
projected output bytes, query count, parser CPU, wall time, and process memory
from the measured supported envelope plus a reviewed margin. Any limit breach
must produce an incomplete result and channel-resolution `UNKNOWN`, never
`ABSENT`. Total LAS/DLIS source bytes are not themselves an admission ceiling.

**Disposition:** `RESOURCE_BUDGETS_OPEN`; no numbers are inferred from these
probes.

## 4. Exact Qwen/llama.cpp request-token accounting

Static inspection of `src/wellplot/agent/providers/openai_compat_v2.py` shows
that WellPlot sends the configured model, system/user messages, configured
request options, optional output-token bound, and a Pydantic-generated strict
`response_format: json_schema`. The deployed llama.cpp server build and exact
Qwen tokenizer/GGUF/template are not locally available. The project environment
also lacks the model-specific tokenizer tooling. Therefore exact token count,
context-window fit, and the server's JSON-schema-to-prompt/grammar conversion
are unestablished.

The [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
documents `/apply-template` and `/tokenize` as non-inference operations, but
they are POST calls and were not invoked. Current D2 did not use the endpoint.
An offline acceptance must bind the same GGUF tokenizer, chat template,
server build, frozen thinking-off options, rendered-message framing, response
schema conversion, output reservation, context capacity, and request
projection. If schema is compiled to a grammar rather than inserted into the
prompt, its cost needs a separate grammar/schema resource bound, not a
character-to-token estimate. The serialized request also needs an independent
byte ceiling.

**Disposition:** `TOKEN_BUDGET_UNAVAILABLE`; do not substitute generic
tokenizers, character ratios, previous response usage, or silent truncation.
This gate requires exact local artifacts/source or a separately authorized
non-generative server capability check.

## 5. Catalog governance

The four supplied `examples/families/*.json` files remain untrusted
reference/collision data. Their presence and prior collision audit establish
neither provenance, license, nor correctness. The existing channel aliases
are not versioned with per-rule evidence, and source-candidate aliases must
not bypass the accepted governed resolver.

Governance recommendation for an initial release: **zero active semantic
family-to-physical-channel mappings** until each rule is documented and
reviewed. Exact physical selectors explicitly supplied by the scientist
remain available. For every proposed mapping, require source URL/revision and
exact evidence location, license/redistribution status, request-term versus
physical-channel rule type, exact identities, units/source/frame scope,
exhaustiveness claim, collision analysis, named domain reviewer, software
schema reviewer, immutable release version, canonical digest, and regression
evidence. Activation creates a new content-addressed catalog release; it never
rewrites past resolution evidence. Missing/untrusted/stale data yields
`UNKNOWN` or clarification, not guessed equivalence or family-level
`ABSENT`.

No initial mapping is approved by this feasibility result. The zero-active-rule
recommendation requires independent/domain acceptance; it is not silently
promoted to the active baseline.

## Decision table

| Item | Evidence status | Result | Remaining gate |
| --- | --- | --- | --- |
| LAS bounded-prefix feasibility | Synthetic LAS 1.2/2.0 cases; installed LASIO source; CWLS marker rule | Candidate supported; not production-qualified | Complete format/adversarial matrix and budgets |
| DLIS fixture and child containment | Tiny generated fixture accepted by locked dlisio; test-only child limits | Feasible for provider-free tests | Scaling/corruption matrix and accepted memory contract |
| Numeric parser/resource limits | No SLO or representative distribution | Open; no constants selected | Measure supported envelope and review limits |
| Exact Qwen token accounting | Provider request source inspected; model/tokenizer/build absent | Blocked; exact count unavailable | Provision pinned local assets/source or authorize endpoint capability calls |
| Catalog governance | D1 invariants plus untrusted local catalogs | Governance process proposed; no mappings approved | Domain/license review and acceptance of release policy |

## References

- Canadian Well Logging Society, [LAS Version 2.0 specification](https://www.cwls.org/wp-content/uploads/2014/09/LAS_20_Update_Jan2014.pdf).
- LASIO 0.32, [reader source documentation](https://lasio.readthedocs.io/en/latest/_modules/lasio/reader.html) and [encoding documentation](https://lasio.readthedocs.io/en/latest/encodings.html).
- Equinor, [DLISIO 1.0.4 API](https://dlisio.readthedocs.io/en/stable/dlis/api.html) and [error handling](https://dlisio.readthedocs.io/en/stable/dlis/errors.html).
- Well ID, [dliswriter source](https://github.com/well-id/dliswriter) and [PyPI 1.2.0 artifact](https://pypi.org/project/dliswriter/1.2.0/).
- ggml-org, [llama.cpp server API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Boundaries and accounting

No production source, config, dependency, active baseline, D1 design, frozen
population/gold, D5/C02 evidence, or family JSON was modified. No scientific
LAS/DLIS asset was read for these probes. The generated LAS and DLIS
fixtures were temporary and contained only synthetic data. No provider,
generation, model, endpoint, smoke, scientific-turn, or C02 call occurred.

```text
provider generation calls = 0
model generation calls = 0
endpoint calls = 0
scientific turns = 0
C02 exposure = 0
production source changes = 0
active-baseline promotion = 0
```
