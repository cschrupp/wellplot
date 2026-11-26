# Specialist measured-panel tokenization

Provider-free checkpoint: `007b43aa940843d876eef996a844d95c47e1b1c0`.
The canonical mock HTTP campaign supplied eight exact SDK bodies. On the
configured LAN endpoint, authenticated model listing returned
`qwen3.6-35b-a3b`; properties reported build `b12340-b8645ddda` and context
65,536. This checks reported runtime identity fields, not GGUF binary identity.

For each body, `/apply-template` rendered with and without
`response_format`. The rendered bytes matched in all eight comparisons,
including both specialist schemas, and all rendered prompts ended with the
empty thinking block. Counts use `/tokenize` with special-token insertion
and parsing enabled. No completion endpoint was called.

| Case | Input tokens | Exact mock SDK body SHA-256 |
| --- | ---: | --- |
| W01 | 1651 | `fde2d23a16db527bc08171846ad872f9a027c855e1d2f140c9a6a86ab469ed78` |
| W02 | 1677 | `534ff660a83709dfda5e42998540a682df09daefd6ecfdc39b20427acadf360b` |
| W03 | 1405 | `73c4bc33b4082186801a2ea2d148a3b465d6de80436f9d8ae9c66968bb65b2f5` |
| W04 | 2444 | `0d47de99e546810e32f8ce266b8d89223660bc5aee72f90a63bab4290cd82c1f` |
| W05 | 1882 | `757c29f377eb5430ab6f255608fc3746640f665cda06369c6847b9340f84d2c1` |
| W06 | 1864 | `bf16cfe9be739462213ff52795241ff46c0a3126549b053ee6847b216b2713cb` |
| W07 | 1886 | `c8e98b2fb9feea3018c662c29b64bf8c84ca1f2fb5e14492dc8f67e5a5e94a89` |
| W08 | 2046 | `3db61278de4dbc900a8bf44d82e004ce15378858fde4ea6b9620bcbbbfeaae4e` |

Both schemas added zero rendered prompt tokens on these requests. All eight
fit without truncation: the longest input is 2,444 tokens against the 60,000
input ceiling, leaving the required 4,096 output and 1,440 margin untouched.
This is not decoder-enforcement evidence or full readiness acceptance.

The mock SDK capture test passed. The two separate role smoke paths, their
tokenization results, and their authority descriptors are not qualified by
this record. No live authority was consumed; integrated H2 remains blocked.
