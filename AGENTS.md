# Repository Rules

## MCP Stabilization

During MCP stabilization, no runtime workaround may be added merely because a
provider emitted an unexpected tool call. First inspect the advertised MCP
schema. If the call is permitted or ambiguous under that schema, fix the
schema. A new regex intent heuristic, argument normalizer, fallback executor,
stage controller, or provider-specific branch requires a committed failing
live evaluation and must replace or delete equivalent complexity elsewhere.
