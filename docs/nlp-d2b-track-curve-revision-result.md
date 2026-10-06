# WellPlot NLP D2B Track and Curve Revision

## Scope

Authorization: `WELLPLOT-NLP-D2B-AUTH-001`

This slice exercises one source-grounded structural revision through the public
`DirectNotebookSession.revise()` path. It appends one normal track and one
curve binding to the existing `Main Log` section. No broader structural-editing
behavior is authorized.

Request:

```text
In the Main Log section, add a new normal track titled "Caliper QC" at the end,
28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear
scale from 6 to 12.
```

## Deterministic Path

The acceptance test uses a deterministic planner and section backend while
executing the real notebook adapter, deterministic source loader and
enrichment, `ProgramSectionCompiler`, canonical reconciliation/application,
persistence, reload, renderer, and frozen D0 verifier. A report compiler
double fails if report work is dispatched.

The declared source is the fixture LAS file. The section worker inspects its
actual bounded `ProgramGenerationRequest.user_prompt`, parses its structured
JSON payload, and proves that the existing target and at least one source
candidate are present. It then checks `CALI` with `kind=scalar` specifically
inside `section_context.sources[*].channels`, not merely anywhere in the
prompt text, before returning the deterministic program.

Inspected source identity: the declared temporary fixture source
`fixture.las`, loaded by `LogfileSourceLoader` from the logfile's section data
source. The worker request contains candidate `source-1`, the inspected channel
mnemonic `CALI` with scalar kind inside the source projection, the existing
target marker, the grounded existing-curve inventory, and the SDK entries for
`wp.track(section)` and `wp.curve(track)`.

## Fixture State

Existing section:

```text
id: main
title: Main Log
```

Before track IDs:

```text
depth, cbl, vdl, gr, cali, rt
```

Before track count: `6`

The existing `cali` track already contains one CALI binding. The new binding
therefore tests legitimate repeated use of one source channel with distinct
canonical binding identities.

After track IDs are:

```text
depth, cbl, vdl, gr, cali, rt, caliper-qc
```

After track count is `7`. The new canonical track ID is `caliper-qc`.

The new track has kind `normal`, title `Caliper QC`, and width `28` mm. It has
one curve binding with channel `CALI`, label `Caliper QC`, and linear scale
`6` to `12`, `reverse=false`. The existing CALI binding ID is
`main.cali.CALI.4`; the new CALI binding ID is `main.caliper-qc.CALI`. They
are distinct.

## Acceptance

Frozen D0 results:

```text
LAS-01  PASS
LAS-03  PASS
LAS-04  PASS
LAS-07  PASS
LAS-09  PASS
```

The exact canonical semantic diff consists of:

```text
/sections/0/tracks/6
/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/6
/extensions/compatibility/legacy_document/bindings/channels/5
```

The last two paths are the exact compatibility mirrors identified from normal
persistence. Existing tracks and report/document metadata remain unchanged.

The public path writes the revised logfile, reloads it through
`load_authoring_document()`, validates the canonical result, and renders a
non-empty output file.

## Adversarial Coverage

- An ungrounded `NOT_A_CHANNEL` program fails closed before persistence; the
  logfile remains byte-identical and no new track is accepted.
- A controlled valid new track plus an unrelated existing-track mutation
  passes LAS-03/LAS-04 but fails LAS-07 and workflow status.
- The successful path invokes one section worker and zero report workers, and
  the submitted intent contains only one existing-section fragment with one
  new track and one curve binding.
- The existing CALI binding remains unchanged while the new CALI binding has a
  distinct identity.

## Verification

The D2B focused suite contains `5 passed` tests. The adjacent delivery and
deterministic authoring suite contains `123 passed` and one reproduced baseline
failure in `tests/test_direct_notebook.py`, caused by the absent
`workspace/data/30-23a-3 8117_d.las` fixture. The full suite reports:

```text
2532 passed, 36 failed, 10 skipped, 11 subtests passed
```

The 36 full-suite failures are the existing historical/environment baseline
failures; there are zero new D2B-attributable failures. Ruff check, formatting
check, Python compilation, and `git diff --check` pass. The D2B focused suite
uses deterministic backends and makes zero provider, endpoint, or real model
calls. The starting baseline is
`2471c1025c9b4e854ccba7c23d5226d235ed0bcd`; production source files remain
unchanged.
