# WIR-OP-SET-INTERVAL

## Inputs
- `top`, `bottom`, `unit` (`m`|`ft`)

## Preconditions
- `top < bottom`

## Lowering semantics
- Replace document interval

## Failure modes
- `PreconditionError` on inverted interval
