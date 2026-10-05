# WellPlot NLP Completion Plan

## Status

`CURRENT_DELIVERY_CONTRACT`

Baseline: `81147fb9ef45a04fa6e42348536e94cde21f1c25`

This document defines the current delivery direction for WellPlot natural-language authoring. It does not rewrite or invalidate the Semantic IR / V2R research record. Historical evaluation documents remain immutable evidence. Research candidates remain candidates until they satisfy the integrated authoring contract defined here.

This planning slice is documentation-only. It authorizes no provider, endpoint, model, worker, or program calls and no production implementation or routing change.

## Delivery Objective

Given a scientist's natural-language description, declared data sources, and optional existing WellPlot document, WellPlot must construct or revise the requested well-log plot correctly, preserve unrelated content, and produce a validated persisted and rendered artifact.

The current milestone is NLP authoring over the working WellPlot engine. It is not a UI milestone and it is not a plotting-engine rewrite.

The intended responsibility flow is:

```text
scientist request
+ inspected source inventory
+ optional current WellPlot document
        |
        v
interpret requested construction or changes
        |
        v
validated authoring intent
        |
        v
deterministic reconciliation into WellPlot operations
        |
        v
existing authoring / execution machinery
        |
        v
validate -> persist -> render
```

The model may interpret scientific intent. WellPlot code must continue to own mechanically derivable structure, canonical validation, mutation safety, persistence, and rendering. Host code must not repair missing scientific meaning by guessing.

## Non-Goals

The delivery programme does not currently include:

- UI implementation;
- renderer redesign;
- rewriting the working plotting/domain engine;
- adding another agent hierarchy;
- historical regrading of Semantic IR / V2R experiments;
- open-ended model tournaments;
- automatic promotion of V2R, `TypedSectionCompiler`, or any other research component;
- production cutover solely because an intermediate planner or semantic-IR benchmark passes.

## Canonical Delivery Workflows

### `CBL-CONSTRUCT` — one substantial construction request

The CBL notebook is the construction acceptance workflow. One substantial scientist request, using declared source data through the public notebook-facing API, must construct the requested artifact without manual repair of intermediate planner state.

The final WellPlot document and render must satisfy the request, including where requested:

- report heading/title and remarks;
- main and repeat sections;
- section ordering;
- ordered track construction;
- repeated source/channel bindings and requested multiplicity;
- reference/depth overlays and their intended semantics;
- raster/image-track configuration;
- curve/raster presentation settings;
- scales, labels, styles, and widths;
- valid persistence;
- successful final rendering/export.

Passing a planner representation is not sufficient. The persisted and rendered document is the acceptance object.

### `LAS-REVISE` — successive revisions of an existing document

The LAS notebook is the revision acceptance workflow. Successive natural-language requests must revise an existing WellPlot document while preserving unrelated state.

The workflow must cover, at minimum:

- loading and grounding against current document state;
- changing requested report/header values;
- adding a track;
- adding a curve/binding;
- changing an existing scale;
- adding a fill;
- preserving unrelated tracks, bindings, report content, and presentation;
- persisting and rendering after the revision sequence.

Construction success does not establish revision correctness. Both workflows are required.

When a target is ambiguous, the system must fail closed and request clarification or return an actionable ambiguity result without mutation. When a requested source/channel is unavailable, it must honor any explicit conditional instruction or return an actionable error; it must not silently substitute data.

## Requirement-to-Code Checklist

Status values used below:

- `COVERED`: deterministic acceptance coverage already exists for the requirement;
- `PARTIAL`: relevant machinery exists, but integrated notebook acceptance is incomplete;
- `MISSING`: no adequate integrated acceptance assertion has yet been established;
- `RESEARCH_CANDIDATE`: evidence exists in a research component, but it is not the delivery implementation by default.

| ID | Workflow | Requirement | Canonical WellPlot responsibility | Responsible NLP / host layer | Current status | Independent acceptance assertion |
| --- | --- | --- | --- | --- | --- | --- |
| `CBL-01` | CBL | Report heading/title | report document fields | report interpretation + deterministic authoring | `PARTIAL` | persisted report fields equal requested values |
| `CBL-02` | CBL | Remarks/report content | report remarks/content | report interpretation + deterministic authoring | `PARTIAL` | requested remarks/content present exactly once in correct owner |
| `CBL-03` | CBL | Main/repeat sections and order | ordered section document structure | planner/intent + reconciliation | `PARTIAL` | section count, identity, and order match request |
| `CBL-04` | CBL | Track construction and order | section track structure | section intent + deterministic reconciliation | `PARTIAL` | track count/type/order match requested scientific layout |
| `CBL-05` | CBL | Bindings and multiplicity | source/channel bindings | source grounding + authoring operations | `PARTIAL` | every requested binding exists with correct multiplicity/source/channel |
| `CBL-06` | CBL | Reference/depth overlays | reference-track semantics and bindings | semantic intent + deterministic reconciliation | `RESEARCH_CANDIDATE` | final document preserves requested reference meaning and target |
| `CBL-07` | CBL | Raster/image settings | raster track/binding configuration | section interpretation + authoring operations | `PARTIAL` | requested raster source/channel/settings appear in final document |
| `CBL-08` | CBL | Scales, labels, styles, widths | presentation fields on tracks/features | intent + authoring operations | `MISSING` | final fields equal explicit user settings without collateral changes |
| `CBL-09` | CBL | Persistence and render/export | canonical document + renderer | host execution | `COVERED/PARTIAL` | persisted document validates and expected PDF/render succeeds |
| `LAS-01` | LAS | Ground against existing state | existing document snapshot | context/enrichment boundary | `PARTIAL` | intended target resolves from current document without reconstruction loss |
| `LAS-02` | LAS | Header/report mutation | report fields | revision intent + deterministic authoring | `PARTIAL` | only requested report/header field changes |
| `LAS-03` | LAS | Add track | section track structure | revision intent + reconciliation | `PARTIAL` | requested track added at intended location; prior tracks unchanged |
| `LAS-04` | LAS | Add curve/binding | feature/binding structure | source grounding + revision operations | `PARTIAL` | requested curve/binding added with correct source/channel |
| `LAS-05` | LAS | Change scale | feature/track scale fields | revision intent + mutation operation | `PARTIAL` | requested scale changes; unrelated scales remain byte/semantic equivalent |
| `LAS-06` | LAS | Add fill | fill feature/operation | revision intent + authoring operation | `MISSING` | requested fill created with correct targets/settings and valid render |
| `LAS-07` | LAS | Preserve unrelated content | all unaffected document state | reconciliation/mutation safety | `MISSING` | before/after diff contains only authorized semantic changes |
| `LAS-08` | LAS | Ambiguity and missing-source behavior | no-op/error boundary | source grounding + reconciliation | `MISSING` | ambiguous/missing target produces clarification/actionable error and zero unintended mutation |
| `LAS-09` | LAS | Persist/render after sequence | canonical document + renderer | host execution | `MISSING` | every accepted revision leaves a valid persisted/renderable document |

The table is the delivery backlog. Implementation work must reference one or more checklist IDs and must move those IDs toward deterministic integrated acceptance.

## Current Component Position

The current public notebook execution path remains based on the existing code-mode architecture and program compilers. That working path is the starting point, not something to replace wholesale.

The typed-section work and V2R work are valuable research evidence, but neither is automatically the delivery architecture:

- `TypedSectionCompiler` is a reconstruction-oriented candidate and does not currently provide the complete revision behavior required by `LAS-REVISE`;
- its documented representability envelope does not cover all presentation controls, fills, reference-overlay details, or revision semantics required by the notebook contract;
- V2R established useful semantic-ownership and model/serving evidence, but SR7 explicitly did not authorize production promotion.

Component selection must therefore answer a delivery question: **which existing components close the notebook requirements with the smallest maintainable change while preserving the working WellPlot engine?**

Prefer reuse of existing renderer, authoring service, source inspection, reconciliation, persistence, validation, and safety mechanisms. Do not replace working layers simply to make a research architecture uniform.

## Deterministic Acceptance Strategy

The existing CBL verifier is the starting point for final-document assertions. It should be reused and extended where the notebook contract requires assertions it does not yet make.

The LAS workflow needs an equivalent before/after acceptance harness. Its core invariant is not merely that the requested change appears; unrelated state must remain unchanged.

Expected answers belong only in deterministic tests/verifiers. They must never be placed in provider prompts or runtime context.

Three acceptance layers are mandatory:

### 1. Execution correctness

- source and channel references resolve;
- operations are valid;
- canonical document validation passes;
- persistence succeeds;
- rendering/export succeeds.

### 2. Scientific fidelity

- requested channels and sources are correct;
- units and scales are correct;
- direction/sample-axis behavior is correct;
- multiplicity and reference semantics are correct;
- explicit presentation settings are preserved.

### 3. Revision preservation

- unrelated tracks and bindings are unchanged;
- unrelated report content is unchanged;
- unrelated styling/presentation is unchanged;
- failed or ambiguous requests do not partially mutate the document.

A renderable PDF is not sufficient if it is scientifically wrong. A correct planner or semantic-IR object is not sufficient if execution produces the wrong document.

## Delivery Sequence

The sequence below replaces open-ended research progression with bounded delivery slices.

### D0 — Acceptance contract and deterministic verifiers

Purpose: make the two notebook workflows executable as delivery tests before changing the implementation.

Required work:

- turn this checklist into executable deterministic assertions;
- reuse/extend `scripts/verify_cbl_packet.py` for `CBL-CONSTRUCT`;
- add an LAS before/after verifier and fixtures for `LAS-REVISE`;
- classify every checklist item as implemented, missing, or currently failing against the baseline;
- preserve expected outcomes only in tests/verifiers;
- make zero provider/model calls.

Exit condition: independent review agrees that the verifiers measure the final scientist-visible requirements rather than intermediate planner objects.

**Stop after D0 for review.** D0 is not authorized by creation of this document.

### D1 — Minimal LAS revision vertical

Purpose: prove one complete revision path through the public notebook API.

Candidate first vertical:

- change one known report/header value or one known curve scale;
- persist the document;
- prove the requested value changed;
- prove unrelated state did not change;
- render successfully.

No broader refactor is justified unless this vertical demonstrates a concrete blocker.

### D2 — Complete LAS revision sequence

Extend the same integrated path to:

- track addition;
- curve/binding addition;
- scale mutation;
- fill creation;
- preservation invariants;
- ambiguity and unavailable-source handling;
- persistence/render after each accepted revision.

### D3 — Complete CBL one-shot construction

One substantial CBL request through the public notebook API must satisfy the complete deterministic CBL verifier and render successfully.

Implementation may be developed incrementally, but acceptance remains the substantial one-request workflow.

### D4 — Bounded integrated live acceptance

Only after D0-D3 deterministic coverage is complete should a new live acceptance campaign be proposed.

Any such campaign must freeze before inference:

- representative real source files;
- task population and unseen wording/value/source variations;
- call/retry budget;
- success criteria;
- evidence format;
- stop conditions.

It must measure final user outcomes, including:

- correct scientific artifact without correction;
- correct artifact after explicit clarification/correction;
- safe/actionable failure;
- undetected incorrect output;
- unintended mutation;
- latency, retry frequency, and cost where relevant.

Planner accuracy alone cannot substitute for these outcomes.

## Engineering Rules That Prevent Drift

1. Every task must close a named checklist requirement, integration defect, or release-relevant failure.
2. Every implementation change must reference the affected checklist IDs.
3. No UI work, renderer redesign, additional agent hierarchy, historical regrading, or model tournament is part of this programme unless separately authorized as a release blocker.
4. No new experiment is justified unless its possible outcomes change a specific named implementation or release decision that deterministic inspection/testing cannot answer.
5. V2R, typed workers, and other research artifacts remain candidates until they satisfy the integrated notebook contract.
6. A failed acceptance test becomes a bounded engineering issue, explicit scope reduction, or candidate rejection; it does not automatically authorize another research series.
7. Ambiguity fails closed. Missing scientific meaning is never filled by host-side guessing.
8. Preserve one current delivery-status document. Historical research evidence remains immutable but does not control the current delivery sequence unless a current requirement explicitly depends on it.
9. Do not create a new Semantic-IR research branch merely because a notebook delivery test fails.
10. The scientist-visible persisted/rendered artifact is the acceptance object; intermediate representations are diagnostic evidence only.

## Release Boundary

Completion of this plan does not itself authorize production promotion.

The release decision comes only after integrated deterministic coverage and a separately authorized live acceptance campaign demonstrate that the supported workflows meet agreed scientific-correctness, mutation-safety, and usefulness criteria.

If a requested operation cannot be made reliable within the bounded delivery budget, explicitly exclude it from the supported release rather than hiding the limitation behind repair logic or another open-ended research programme.

## Immediate Next Boundary

The next candidate activity is **D0 — Acceptance contract and deterministic verifiers**.

D0 remains **NOT AUTHORIZED** by this document. No implementation, provider/model call, production routing change, or further experiment follows automatically from this planning commit.