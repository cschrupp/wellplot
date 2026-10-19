# WIR-OP-DEFINE-FILL

## Inputs
- `curve` resolved ref
- `mode`: `to_upper_limit` | `to_lower_limit` | `baseline_split` | `between_curves`
- optional `threshold`, `baseline`, `other_curve`, `bind`

## Required context
- Curve placed in D0 / earlier ops
- For `between_curves`: `other_curve` placed

## Lowering semantics
- Append fill placement with stable WELL-IR fill symbol

## Failure modes
- `PreconditionError` if curve missing
