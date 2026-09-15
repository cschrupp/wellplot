"""Code Mode v2 orchestration boundary.

CM-01 established this package boundary. The package now contains provider-
neutral planning/enrichment contracts and bounded workers that compile through
the restricted program kernel; LangGraph, MCP, public routing, persistence,
and compatibility code remain outside it.
"""
