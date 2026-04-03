# Rendering

The render layer supports both full and partial outputs.

## Full reports

Use:

- `render_report(...)`

This is the main entry point when you want a complete PDF report or a full in-memory figure list.

## Partial renders

Use:

- `render_section(...)`
- `render_track(...)`
- `render_window(...)`

These helpers filter the same logical report/document structure before rendering. They do not create a separate rendering model.

## Notebook outputs

Use:

- `render_png_bytes(...)`
- `render_svg_bytes(...)`
- `render_section_png(...)`
- `render_track_png(...)`
- `render_window_png(...)`

These are intended for notebooks and web contexts where writing an intermediate file is not desirable.

## Continuous vs paginated pages

The page model supports:

- paginated output for normal report generation
- `page.continuous: true` for single continuous-depth pages

Track headers can also be controlled explicitly, including whether a bottom header row is shown.

## Practical recommendation

Use full-report rendering for:

- printable output
- review packets
- stable saved artifacts

Use partial rendering for:

- QC views
- notebook inspection
- iterative interpretation work
- track-specific debugging
