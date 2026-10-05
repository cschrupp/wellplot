# SI-V2R SR7-P1 Live Comparison Result

## Status

`SI_V2R_SR7_P1B_ACCEPTED`

SR7-P1 is closed. The independently reviewed terminal comparison result is:

`CONFIGURATION_A_DIRECTIONALLY_BETTER`

This record is append-only closure evidence for the accepted live comparison.
It does not modify the frozen P0 contract or P1 harness and does not authorize
another provider run or any production promotion.

## Accepted execution provenance

- P1A/P1B execution checkpoint: `7255e2ec9a48e26845d457245c00d890970bc667`
- Accepted P0 harness checkpoint: `8f30a33c9bcf5fbbce179996a6ea6b0f9a9da78f`
- Logical evidence rows: `96`
- Evidence SHA-256: `fbd404f401dfd77acf08cf1ff0b173083e0cd5e44d7b30850de600724a9d2599`
- Journal SHA-256: `fbd404f401dfd77acf08cf1ff0b173083e0cd5e44d7b30850de600724a9d2599`
- Summary SHA-256: `628278063e4f9416d031506365cacc317590b28d9819bfc4ccfff022398f3875`
- Population integrity: `PASS`
- Configuration drift: `NO`
- Infrastructure failure: `NO`
- Infrastructure retries: `0`
- Terminal artifact: absent, consistent with a completed non-inconclusive run

The evidence and journal were independently observed to be byte-for-byte
identical and to contain the complete 96-row frozen schedule with unique
configuration/case/attempt keys and execution-order indices `0..95`.

## Frozen comparison population

The comparison used the frozen 24-case SI-V2R population, two matched attempts
per configuration, the frozen 14 semantic dimensions, and the accepted ownership
mask:

- `95` `PRIMARY_MODEL_OBLIGATION` case×dimension rows
- `37` `RAW_MODEL_DIAGNOSTIC` rows
- `1` `MASKED_UNRESOLVED_CONTRACT` row
- `203` `NOT_APPLICABLE` rows

Primary accuracy was computed only from dimensions marked
`PRIMARY_MODEL_OBLIGATION`. Raw diagnostics, masked dimensions, and
not-applicable dimensions did not enter the primary accuracy denominator.

## Compared configurations

### Configuration A — current baseline

- provider class: OpenAI-compatible local serving
- requested model: `qwen3.6-35b-a3b`
- configuration fingerprint: `154513f15bba419aae7ce87c8a0e26a601f45829281e385c599d597fc810711a`
- temperature: `0`
- `max_tokens`: `16384`
- structured output: strict JSON Schema
- comparison role: `CURRENT_BASELINE`

### Configuration B — candidate

- provider: NVIDIA hosted API
- requested model: `nvidia/nemotron-3-super-120b-a12b`
- configuration fingerprint: `a473cc25db1415373b81d7775c263170d7c6388fa45caa5572b11308e8b7d980`
- temperature: `1.0`
- `top_p`: `0.95`
- `reasoning_effort`: `low`
- `max_tokens`: `16384`
- structured output: strict JSON Schema
- comparison role: `CANDIDATE`

The conclusion is about these complete model-plus-serving configurations. It is
not an isolated model-weights comparison.

## Independently reproduced results

| Metric | Configuration A | Configuration B |
| --- | ---: | ---: |
| Logical attempts | 48 | 48 |
| Physical provider calls | 60 | 80 |
| Structural retries | 12 | 32 |
| Initial canonical PASS | 36/48 (`75.0%`) | 16/48 (`33.3%`) |
| Final canonical PASS | 42/48 (`87.5%`) | 27/48 (`56.25%`) |
| Terminal structural failures | 6 | 21 |
| Primary correct / evaluable | 136/156 | 78/111 |
| Primary dimension accuracy | `87.18%` | `70.27%` |
| Primary case wins | 8 | 2 |

Case-level relations across the 24 frozen cases were:

- `A_BETTER`: `8`
- `B_BETTER`: `2`
- `UNCHANGED`: `6`
- `NOT_COMPARABLE`: `8`

The frozen directional classifier requires the selected configuration to win on
all three governing criteria. Configuration A satisfied all three:

1. primary case wins: `8 > 2`;
2. primary dimension accuracy: `87.18% > 70.27%`;
3. terminal structural failures: `6 <= 21`.

Therefore the accepted classifier output is
`CONFIGURATION_A_DIRECTIONALLY_BETTER`.

## Structural-validation observation

All `44` initial structural failures in the accepted evidence were valid JSON
and passed the exact JSON Schema stage but failed canonical Pydantic validation.
The failures therefore localized to the canonical/relational contract boundary,
not JSON parsing or JSON-Schema acceptance. Structural retries were preserved as
bounded evidence rather than being reclassified as configuration drift when the
returned model identity matched the frozen configuration.

This reproduces at population scale the failure class localized earlier in
SR7-C1, while also showing a materially different incidence between the two
serving configurations.

## Interpretation

The accepted evidence supports one bounded conclusion:

> On the frozen 24-case SI-V2R study and under the exact frozen serving,
> decoding, schema, prompt, retry, ownership, and scoring contracts,
> Configuration A is directionally better than Configuration B.

The result provides empirical support for retaining Configuration A as the
preferred SR7 candidate for any future V2R work. It does not establish that
Qwen model weights are generally superior to Nemotron, that either configuration
generalizes beyond this population, or that V2R is production-ready.

## Preserved boundaries

SR7-P1 grants no authorization for:

- rerunning the accepted 24-case comparison;
- changing the frozen P0 population, mask, grader, schedule, prompts, schema,
  gold corpus, configuration fingerprints, or scoring policy;
- promoting V2R into production routing;
- modifying the current production planner, graph, workers, MCP, CM58 behavior,
  ADR-CM57, or public APIs;
- treating this result as a general model benchmark or model-only causal claim.

No provider, endpoint, model, worker, or program call is performed by this
closure record, and no production source is changed.

## Next boundary

SR7 is complete. Any production-readiness, deployment-provenance, dormant
integration, shadow-system qualification, or promotion work requires a new,
separately reviewed decision record and explicit authorization.
