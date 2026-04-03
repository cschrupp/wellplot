# Report Pages

`well_log_os` supports report-level composition, not just strip rendering.

## Current report blocks

- `heading`
- `remarks`
- `tail`

These are built from the same report data model.

## Heading

Current heading behavior:

- the first page stays portrait
- the heading content is rotated where required
- the upper cover section and the lower detail block share one report definition
- detail tables support `open_hole` or `cased_hole`

## Remarks

`remarks` is a page-level notes block intended for:

- acquisition notes
- disclaimers
- summary comments
- pre-log context

## Tail

The tail is not a separate data model.

It is a compact summary view of the same report content used by the heading.

## Detail tables

Current authoring features include:

- split left-label cells
- split value subcells within parallel columns
- preserved empty cells
- optional per-cell formatting support in the model

## Example files

- `examples/cbl_report_pages.log.yaml`
- `examples/cbl_report_pages_open_hole.log.yaml`
