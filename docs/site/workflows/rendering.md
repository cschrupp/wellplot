# Rendering

The render layer supports both full and partial outputs.

## Full report

- `render_report(...)`

## Partial renders

- `render_section(...)`
- `render_track(...)`
- `render_window(...)`

## Notebook-friendly outputs

- `render_png_bytes(...)`
- `render_svg_bytes(...)`
- `render_section_png(...)`
- `render_track_png(...)`
- `render_window_png(...)`

## Current principle

Partial rendering filters the same logical layout before rendering. It is not a separate layout system.
