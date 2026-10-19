# WIR-OP-CONFIGURE-CURVE-DISPLAY

## Inputs
- `curve` resolved ref
- optional `min`, `max`, `direction`, `line_style`

## Required context
- Curve already placed in D0 (or earlier ops in the same program)

## Lowering semantics
- Update placement display fields in place

## Failure modes
- `PreconditionError` if curve not placed
