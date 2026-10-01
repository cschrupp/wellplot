# SI-V2.1 External Architecture Research

This record separates external facts from WellPlot-specific inferences. URLs
are primary documentation or papers; no provider-specific behavior is used as
an architectural premise.

## Vega-Lite

Source: https://vega.github.io/vega-lite/docs/ and https://vega.github.io/vega-lite/.

External fact: Vega-Lite is a high-level declarative visualization grammar
whose compiler lowers concise specifications into more detailed Vega
specifications. The compiler derives components such as axes, legends, and
scales from explicit encodings and documented rules.

Applied lesson: Keep model output at semantic intent and let deterministic
lowering derive structural bundles and defaults that are uniquely implied.

Does not transfer: WellPlot's source resolution, capability parent graph,
scientific track distinctions, and authoring persistence rules are domain
contracts, not Vega-Lite defaults.

## Flint

Source: https://arxiv.org/abs/2607.20775.

External fact: The work presents a semantics-driven visualization IR that
keeps data meaning explicit so a compiler can derive visualization
configuration instead of relying only on surface representation.

Applied lesson: Preserve domain semantics as orthogonal intent and make
derivation explicit and testable.

Does not transfer: The Flint language and its domain are not WellPlot's
capability registry, source model, or section-worker contract. This is
analogy, not a dependency or proof of WellPlot behavior.

## PICARD

Source: https://aclanthology.org/2021.emnlp-main.779/.

External fact: PICARD constrains autoregressive decoding by incrementally
parsing candidate output and rejecting tokens that cannot produce a valid
formal-language continuation.

Applied lesson: Syntax validity and semantic validity are separate
boundaries. A provider-facing schema can enforce shape, but deterministic
semantic validation and lowering remain necessary.

Does not transfer: SI-V2 does not implement constrained decoding, grammar
integration, or a llama.cpp/OpenAI-specific schema adapter.

## Compiler IR Practice

The general compiler pattern used here is a high-level semantic representation,
semantic analysis, deterministic lowering, and validation of the lower-level
contract. SI-V2 adapts that pattern to an existing Pydantic SemanticPlan and
registry rather than introducing a new executable backend.

## Comparison

| Source/pattern | Semantic responsibility | Deterministic responsibility | Ambiguity handling | WellPlot adaptation |
| --- | --- | --- | --- | --- |
| Vega-Lite | data/mark/encoding meaning | axes, scales, detailed Vega structure | specification must resolve meaning | capability bundles and parent closure |
| Flint | domain semantic structure | visualization configuration | semantic model retains meaning | orthogonal curve/raster/reference features |
| PICARD | intended formal output | parser/schema acceptance | reject invalid continuations | fail closed after IR lowering and plan validation |
| Compiler IR | language meaning | typed lowering and validation | type/semantic error | SemanticIRV2 to SemanticPlan |

The selected WellPlot design is ADAPTED, not claimed as a direct copy of any
external system.
