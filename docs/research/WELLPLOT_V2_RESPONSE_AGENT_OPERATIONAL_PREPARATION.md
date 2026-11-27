# Response-Agent Operational Preparation

Status: provider-free smoke path qualified; exact runtime tokenization and
current readiness remain pending approved non-generative LAN access. No live
generation is authorized by this preparation record.

## Frozen Experiment Identities

| Artifact | SHA-256 |
| --- | --- |
| Response panel | `1b8351647ee6802beb46f9b5bd5992df5b806a588d7e6faaaf2e876205c97e0b` |
| Ordered rendered panel inputs | `ccf521c307f82f7f5ce75b7473d2b38f04a52342b79c461f85888053156e3185` |
| Instructions | `782a1cf6b463b57211d3231aeb62214b50a681d5e4e69b68e6781c2555d33bcd` |
| Response DTO schema | `7cfe35615916d50c78f293870b72d72538b8e71b91d54c6ada4dc14a469f74ea` |
| Independent rubric | `8f8c267f2941c26052ac59fec224135febb1e5d745f96f93717c4ed65983079f` |
| Smoke fixture file | `1b13499a54b1871ac91b8022ffe9f9bff95a2d5ebab9683e10d026781eb7f834` |
| Smoke fixture object | `963dedd3628539b6baf2072ade98ab671175120eaef939e4f8b92f4993a39674` |
| Smoke request | `8750e725c98bef1aba1523cb5cf5d8c14862e7fa733657152407eaaf8aeaf220` |
| Smoke rendered system/user pair | `cec4cca9ed0fbb7853dab32434d07bec815bb63e1eb6a3d01724d2f32ab0da24` |

The smoke asks whether a title change was saved. The verified outcome record
says the `North Ridge` candidate was privately verified but not published;
the saved document still has title `Mesa Draft`. The fixture does not include
the grading rubric or any measured-panel case.

## Exact Mock SDK Bodies

The following SHA-256 values are computed from `request.content` captured at
the existing D5 HTTP transport boundary in provider-free tests. The DTO,
prompt, structured schema, model, temperature, output cap and disabled-thinking
request fields are asserted in those tests.

| Request | SDK request-body SHA-256 |
| --- | --- |
| CR01 | `37326345487fb321a8f980b8090e2311c0dc435c9a90951b7c8ad605dfca15a0` |
| CR02 | `93b3351b5cd51106125e75a779daad275149ded6d003fbd975f5d2c25e85c60a` |
| CR03 | `98150428d59240dd7f0abeeb27189da61d07cb8ec9484d1d56d622a3f5063b35` |
| CR04 | `5a773fbae0f042fb2de13f2b65216a539aeeafd977f1a9763d61da433994b136` |
| CR05 | `92c6340cd829f78ef523040891a309d217c313964de4f0ff6ec4ed3451ee47db` |
| CR06 | `692888a18dfe199220e33cb7b37a7cfae063e554d00a2086b498c77f0896c91b` |
| Response smoke | `04d5eebc858897b7ba411c050e222ff94c830ff5065f181d1d425ce8816b8a81` |

These are mock-transport body identities, not actual runtime token counts.
No UTF-8 length or local tokenizer estimate is substituted for the deployed
runtime tokenizer.

## Provider-Free Qualification

The existing `planner-smoke` / `execute_live_planner_smoke()` path selects the
response DTO and the `response_agent` ledger role for the one frozen synthetic
fixture. Qualification covers valid and invalid first responses, rejects
planner/report-worker/section-worker roles, rejects a second logical call and
second physical attempt, verifies exact mock request-body identities and
sealed smoke custody, and proves no measured population, planner, worker,
authoring, mutation, or publication path is reached. SDK retries and native
corrections are zero.

Focused provider-free command:

```sh
PYTHONPATH="$PWD:$PWD/src" .venv/bin/pytest -q \
  tests/test_nlp_d5_live_semantic_qualification.py \
  -k 'response_agent_smoke_uses_role_bound_d5_custody or response_agent_campaign_uses_canonical_d5_observation_boundary or h1_operational_smoke_is_single_call'
```

Final D5 qualification for this preparation:

```text
PYTHONPATH="$PWD:$PWD/src" .venv/bin/pytest -q tests/test_nlp_d5_live_semantic_qualification.py
171 passed
```

Ruff, formatting, Python compilation, fixture JSON parsing and `git diff
--check` also passed. These are provider-free results; no live endpoint was
contacted.

## Pending Non-Generative LAN Qualification

The accepted specialist tokenization record used authenticated `/apply-template`
and `/tokenize` operations against the configured llama.cpp runtime. The same
method must be applied to the exact seven SDK bodies above, using the matching
model/template and structured response format. For each body, record template
rendering with and without the schema, verify the thinking-disabled suffix,
and count with the runtime tokenizer. All seven counts must be at most 60,000,
leaving 4,096 output tokens and 1,440 additional context tokens. Do not infer
counts from bytes.

Current runtime readiness/tokenization was not performed: repository
instructions require approved LAN execution for these requests, and this
execution environment does not expose the required sandbox escalation. No
endpoint was contacted. The prior accepted specialist record reports model
`qwen3.6-35b-a3b`, build `b12340-b8645ddda`, context 65,536, template digest
`55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c`, and
defaults digest
`5136c0f2b22a73572fe88f44e8cf32159ffb3b345ced2e33ba7507d612f7f8c3`; those
are historical expected values, not a current readiness observation.

The proposed authority remains non-executable pending that qualification and
independent smoke authorization. No current runtime identity or token count is
claimed here. A D5-consumable authority descriptor is not yet issued because
the current runtime identity, exact tokenization results, and post-commit
worktree/checkpoint binding are unavailable; a proposal must not be passed to
the launcher as executable authority.
