# D5 Final 10-Turn Population Freeze

## Terminal

```yaml
population: D5-FINAL-10
status: FROZEN / PROVIDER-FREE
execution_checkpoint: abf5b5c7039fa6942cda076e6c47d780d600647b
provider_calls: 0
model_calls: 0
endpoint_calls: 0
```

The final evaluator is now able to select the accepted nine-turn D4
population plus the separately frozen, model-unseen `D5-C02:C01` case. The
existing D4 cases and gold files remain byte-identical. C02 is loaded from its
accepted standalone request and contract fixtures and is not added to smoke.

## Population

```text
D4-C01:C01
D4-L01:T1
D4-L01:T2
D4-L01:T3
D4-L01:T4
D4-L02:T1
D4-L02:T2
D4-L03:C01
D4-L04:C01
D5-C02:C01
```

The exact population binding is committed in
`tests/fixtures/d5_final_10_turn_population.json`.

```yaml
population_fixture_sha256: 57177a9010e380a8e6f986174785c4f16261b5214666f82c08cca4209b75dd21
d4_cases_fixture_sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
d4_gold_fixture_sha256: 99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968
c02_request_fixture_sha256: f9e746ab41dc420f30f0f19a11859926a9b6e7276a1e56552d56e4752fe93579
c02_contract_fixture_sha256: 26e2917178a119784328ea00ff2aefd8c5317b8177232de2fa2b733ca1d3e7e3
```

## Execution and Grading

The evaluator keeps the canonical path unchanged:

```text
existing provider boundary
  -> existing D4CampaignAdapter
  -> existing D5CampaignRunner
  -> existing persistence/reload/render path
```

Only population selection and grading dispatch are new. D4 turns continue to
use the unchanged D4 grader. C02 uses `d5_5_c02_contract_grader.py`, which
checks the frozen metadata, titles/remarks, section sources and track identity,
binding presentation, VDL raster/axis/grid settings, tail, persistence, and
rendered-artifact identity. It does not modify `verify_cbl_packet.py`.

Provider-free validation covers:

- exact ten-turn order and C02 append-only population assembly;
- exact request/contract/source/checkpoint identity binding;
- positive C02 contract grading;
- rejection of metadata and presentation mutations;
- D5 dispatch to C02 grading without altering D4 grading;
- existing D5 and D4 regression surfaces.

No C02 request has been sent to Qwen. The first model exposure remains the
later final evaluation.
