# WIR-OP-PLACE-CURVE

## Inputs
- `curve`: resolved curve ref
- `target`: absolute track or relative (`with` / `beside`)

## Required context
- Curve symbol present in workspace `available_curves` (for compiler)
- For absolute track: track exists in D0 or is a prior `local_ref`
- For relative `with`: reference curve already placed in D0

## Optional context
- Focus (unused by this op)

## Preconditions
- Target track resolvable
- Relative reference resolvable

## Ambiguity conditions (compiler, not lowerer)
- Family/alias maps to multiple workspace curves

## Lowering semantics
- If curve already placed: move to resolved track
- Else: append placement on resolved track
- Update track.curves membership

## Resulting LogDocument / DocumentState invariants
- `curve_on_track` for placed curve
- No duplicate curve entries

## Failure modes
- `PreconditionError` if track/curve reference missing for relative placement
