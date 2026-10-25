# D5-C02 Held-Out Construction Freeze

## Terminal

```yaml
case: D5-C02:C01
status: FROZEN / MODEL-UNSEEN
freeze_checkpoint: abf5b5c7039fa6942cda076e6c47d780d600647b
provider_calls: 0
model_calls: 0
endpoint_calls: 0
```

This artifact freezes one new CBL/VDL construction request for a later final
evaluation. It is separate from the existing D4 population and is not included
in smoke execution. The request has not been sent to Qwen or any other model.

## Artifact Digests

The digests below are SHA-256 values over the exact committed file bytes,
including their final newline:

```yaml
request_fixture:
  path: tests/fixtures/d5_c02_held_out_request.json
  sha256: f9e746ab41dc420f30f0f19a11859926a9b6e7276a1e56552d56e4752fe93579
contract_fixture:
  path: tests/fixtures/d5_c02_held_out_contract.json
  sha256: 8cf0a76101b693f0711d0681a30f9a9dce103e5677861ce582c6b64a3413ab78
```

## Source Identity

The case uses the already provisioned Main/Repeat DLIS pair. No source bytes
were changed or generated for this freeze.

```yaml
main_pass:
  path: workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
  sha256: 3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7
  bytes: 111573216
  channels: 69
repeat_pass:
  path: workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
  sha256: a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640
  bytes: 3294924
  channels: 72
```

The required channels are present in both sources: `CBL`, `VDL`,
`ECGR_STGC`, `TT`, `TENS`, `MTEM`, `STIT`, `TDSP`, and `VSEC`. The complete
sorted inventories are committed in the contract fixture.

## Held-Out Contract

C02 preserves the C01 capability envelope while changing the request surface:

- report metadata, service-title wording/order, and remark wording are new;
- main and repeat sections remain explicit but use different track widths;
- normal, reference, and array tracks are retained;
- scalar bindings include repeated `CBL` channel use with new labels;
- scale endpoints, reverse semantics, colors, line styles, and line widths are new;
- VDL uses a new raster label, `magma` colormap, track scale, colorbar label,
  sample-axis values, and mixed grid visibility;
- persistence, reload, render, and deterministic contract verification remain
  required outcomes.

The contract is independently structured rather than copied from the existing
C01 gold. It records source selection, track identity/kind/width, binding
identity and presentation, raster/axis settings, and the required end-to-end
verification dimensions.

## Non-Rediscovery Classification

```yaml
source_channel_availability: ESTABLISHED
existing_cbl_vdl_capability_envelope: EMPIRICALLY_SUPPORTED
new_request_and_contract_values: ADAPTED
new_model-unseen_case_as_a_final_population_member: NOVEL
```

The `NOVEL` item is the population decision only: C02 is intentionally held
out from implementation tuning and first becomes model-visible in the final
evaluation. It does not introduce a new engine, semantic path, verifier
architecture, provider, or production behavior.

## Validation

Provider-free validation is implemented in
`tests/test_d5_c02_held_out_freeze.py` and verifies:

- C02 is absent from the existing D4 case population;
- request and contract identity agree and bind the freeze checkpoint;
- the full requested capability envelope is represented;
- exact source bytes, sizes, channel counts, and complete inventories match;
- all required channels are available in both DLIS sources;
- request labels, titles, track dimensions, and presentation values are
  represented by the independent contract;
- track and binding structures are internally consistent.

Validation result at freeze:

```text
6 passed
0 provider/model/endpoint calls
```

No production source, C01/D4 fixture, existing CBL verifier, smoke selection,
prompt, schema, or runtime configuration was changed. The next permitted model
exposure is the final evaluation; C02 must not be added to smoke or used to
tune WellPlot before that evaluation.
