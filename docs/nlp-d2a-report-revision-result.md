# WellPlot NLP D2A Report Revision

## Scope

Authorization: `WELLPLOT-NLP-D2A-AUTH-001`

This slice exercises one report-worker revision through the public
`DirectNotebookSession.revise()` path. It changes only the existing report
title and does not authorize any broader report, section, provider, or model
work.

Request:

```text
Change the report title to "Gamma Ray Quality Control Review".
```

Initial title: `Original Well Log Report`

Final title: `Gamma Ray Quality Control Review`

## Deterministic Path

The acceptance test uses a deterministic planner and report backend, while
executing the real notebook adapter, report worker, canonical reconciler,
authoring service, persistence, reload, renderer, and frozen D0 LAS verifier.
The section compiler is a fail-if-called test double.

Public API:

```python
await DirectNotebookSession.revise(
    feedback='Change the report title to "Gamma Ray Quality Control Review".',
    logfile_path=fixture,
)
```

The worker produced only:

```python
report = wp.report(title="Gamma Ray Quality Control Review")
```

## Acceptance

Frozen D0 results:

```text
LAS-01  PASS
LAS-02  PASS
LAS-07  PASS
LAS-09  PASS
```

The canonical semantic diff is exactly:

```text
/title
/extensions/compatibility/legacy_document/header/title
```

The second path is the existing deterministic compatibility mirror for the
canonical report title. No section, track, binding, scale, remark, header
content, page, depth, output, source, fill, annotation, or presentation state
is changed.

Persistence evidence is provided by the public apply path writing the logfile,
reloading it with `load_authoring_document()`, and validating the final title.
The real renderer writes a non-empty PDF output.

## Adversarial Coverage

- An already-satisfied target title remains byte-identical, reports `no_op`,
  and receives no LAS-02 transition credit.
- The report worker is invoked exactly once, the section worker is not
  invoked, and the submitted intent contains only the title mutation.
- A controlled title change combined with an unrelated section-title mutation
  passes LAS-02 but fails LAS-07 and the workflow status.

## Verification

The D2A focused suite contains six tests and uses no provider, endpoint, or
real model calls. The starting checkpoint is
`df9852ad28ef53a33f7f66edabf110d5e7e5ab0a`; production source files remain
unchanged.
