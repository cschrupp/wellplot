# well_log_os

`well_log_os` is a Python library for building printable well-log layouts from LAS, DLIS, and in-memory scientific data.

It is designed for two equally important workflows:

- declarative log authoring with YAML templates/savefiles
- programmatic log authoring from Python, including notebooks and research pipelines

## Library Workflow

```mermaid
flowchart LR
    subgraph Inputs
        LAS[LAS / DLIS files]
        PD[pandas / numpy results]
        YAML[YAML templates / savefiles]
    end

    subgraph DataLayer[Data layer]
        DS[WellDataset]
        OPS[alignment / merge / validation]
    end

    subgraph Compose[Composition layer]
        BLD[LogBuilder]
        DOC[ProgrammaticLogSpec / LogDocument]
    end

    subgraph Render[Render layer]
        FULL[render_report]
        PART[render_section / render_track / render_window]
        BYTES[render_png_bytes / render_svg_bytes]
    end

    subgraph Outputs
        PDF[PDF report]
        IMG[PNG / SVG / notebook image]
        SAVE[report/document YAML]
    end

    LAS --> DS
    PD --> DS
    DS --> OPS
    OPS --> DS

    YAML --> DOC
    DS --> BLD
    BLD --> DOC
    DOC --> FULL
    DOC --> PART
    DOC --> BYTES
    DS --> FULL
    DS --> PART
    DS --> BYTES

    FULL --> PDF
    PART --> PDF
    BYTES --> IMG
    DOC --> SAVE
```

## What You Can Do

- ingest LAS and DLIS data into normalized datasets
- add computed channels from `numpy` and `pandas`
- align, sort, convert, and merge channels before rendering
- build layouts with YAML or with the Python API
- render full reports, sections, tracks, and bounded windows
- generate PDF reports and notebook-friendly PNG/SVG outputs
- serialize layout/report definitions back to YAML

## Start Here

- Read [Getting Started](getting-started.md)
- Install the package from [Installation](installation.md)
- Learn the core objects in [Concepts](concepts.md)
- Choose a [YAML Workflow](workflows/yaml-workflow.md) or a [Python API Workflow](workflows/python-api.md)
