# Proxy / shim agreement — `v1_w1_shim` vs `v1_w1_proxy`

The same cells, measured from inside the SUT (`shim`) and from the network edge (`proxy`),
paired on `(cell, seed)` and folded over the seeds both ran. §29.1's agreement column: a
cell where the two instruments agree on every safety verdict and every raw count is a
window that is real and not an artefact of where the instrument sat; a cell where they
differ is a finding about the instrument, printed with both numbers.

No p-values. Agreement is a check on the harness, not a hypothesis about runtimes. A twin
whose two sides ran at different commits or under different config pins is printed with
what differs and left out of the tally: its difference may be the runtime, not the instrument.
`n` is the seeds both sides ran; seeds only one side ran are counted beside it and folded
into neither.

Rows through 2026-09-19T13:29:38+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_shim` | 6241 | `251e52d` ×6241 |
| `bench/results/v1_w1_proxy` | 4585 | `251e52d` ×4585 |

| cell | n | safety (shim) | safety (proxy) | dup_eff | dup_rcpt | recovery | latency | agree |
|---|---|---|---|---|---|---|---|---|
| `dbos.native.EXTERNAL.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.native.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 3.1s / 3.4s | yes |
| `dbos.native.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 21 / 0 | 21 / 0 | 30/30 / 30/30 | 3.0s / — | **no** — duplicate_effects 21/0; duplicate_receipts 21/0 |
| `dbos.native.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.4s | yes |
| `dbos.native.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `dbos.native.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.native.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `dbos.native.IDEMPOTENT.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.native.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 3.1s / 3.3s | yes |
| `dbos.native.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 19 / 0 | 30/30 / 30/30 | 3.1s / — | **no** — duplicate_receipts 19/0 |
| `dbos.native.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.0s / 3.3s | yes |
| `dbos.native.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `dbos.native.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.native.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `dbos.pydantic_ai.EXTERNAL.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.pydantic_ai.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 4.4s / 4.7s | yes |
| `dbos.pydantic_ai.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 14 / 0 | 14 / 0 | 30/30 / 30/30 | 4.4s / — | **no** — duplicate_effects 14/0; duplicate_receipts 14/0 |
| `dbos.pydantic_ai.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 4.5s / 4.5s | yes |
| `dbos.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `dbos.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `dbos.pydantic_ai.IDEMPOTENT.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.pydantic_ai.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 4.4s / 4.4s | yes |
| `dbos.pydantic_ai.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 16 / 0 | 30/30 / 30/30 | 4.7s / — | **no** — duplicate_receipts 16/0 |
| `dbos.pydantic_ai.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 4.4s / 4.5s | yes |
| `dbos.pydantic_ai.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `dbos.pydantic_ai.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `dbos.pydantic_ai.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `keel.default.EXTERNAL.baseline` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `keel.default.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.3s / 2.3s | yes |
| `keel.default.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.4s / — | yes |
| `keel.default.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.3s / 2.4s | yes |
| `keel.default.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 4 / 30 | 4 / 30 | 30/30 / 30/30 | 2.4s / 2.4s | **no** — duplicate_effects 4/30; duplicate_receipts 4/30 |
| `keel.default.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `keel.default.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `keel.default.IDEMPOTENT.baseline` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `keel.default.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.3s / 2.3s | yes |
| `keel.default.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 2.4s / — | **no** — duplicate_receipts 30/0 |
| `keel.default.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.4s / 2.4s | yes |
| `keel.default.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 18 / 30 | 30/30 / 30/30 | 2.4s / 2.4s | **no** — duplicate_receipts 18/30 |
| `keel.default.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.6s / 0.6s | yes |
| `keel.default.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `langgraph.async.EXTERNAL.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `langgraph.async.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 60 / 30 | 30/30 / 30/30 | 2.6s / 2.4s | **no** — duplicate_receipts 60/30 |
| `langgraph.async.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 29 | 60 / 30 | 30/30 / 30/30 | 2.5s / 2.4s | **no** — duplicate_effects 30/29; duplicate_receipts 60/30 |
| `langgraph.async.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 2.5s / 2.4s | **no** — duplicate_receipts 30/0 |
| `langgraph.async.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `langgraph.async.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 3.1s / 2.8s | yes |
| `langgraph.async.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `langgraph.async.IDEMPOTENT.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `langgraph.async.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 60 / 30 | 30/30 / 30/30 | 2.1s / 2.5s | **no** — duplicate_receipts 60/30 |
| `langgraph.async.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 60 / 34 | 30/30 / 30/30 | 2.2s / 2.4s | **no** — duplicate_receipts 60/34 |
| `langgraph.async.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 2.1s / 2.3s | **no** — duplicate_receipts 30/0 |
| `langgraph.async.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `langgraph.async.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 3.7s / 2.7s | yes |
| `langgraph.async.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `langgraph.exit.EXTERNAL.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `langgraph.exit.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 60 / 60 | 30/30 / 30/30 | 2.2s / 2.4s | yes |
| `langgraph.exit.EXTERNAL.kill@after:tool_return` | 9 (+21 shim only) | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 9 / 0 | 18 / 0 | 9/9 / 9/9 | 2.2s / — | **no** — duplicate_effects 9/0; duplicate_receipts 18/0 |
| `langgraph.exit.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.2s / 2.3s | yes |
| `langgraph.exit.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `langgraph.exit.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 2.6s / 2.4s | yes |
| `langgraph.exit.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `langgraph.exit.IDEMPOTENT.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `langgraph.exit.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 60 / 60 | 30/30 / 30/30 | 2.2s / 2.4s | yes |
| `langgraph.exit.IDEMPOTENT.kill@after:tool_return` | 5 (+25 shim only) | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 10 / 0 | 5/5 / 5/5 | 2.2s / — | **no** — duplicate_receipts 10/0 |
| `langgraph.exit.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.2s / 2.4s | yes |
| `langgraph.exit.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `langgraph.exit.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.7s / 2.4s | yes |
| `langgraph.exit.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `langgraph.sync.EXTERNAL.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `langgraph.sync.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 2.3s / 2.7s | yes |
| `langgraph.sync.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 0 | 30 / 0 | 30/30 / 30/30 | 2.3s / — | **no** — duplicate_effects 30/0; duplicate_receipts 30/0 |
| `langgraph.sync.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.3s / 2.8s | yes |
| `langgraph.sync.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `langgraph.sync.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 2.8s / 3.6s | yes |
| `langgraph.sync.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `langgraph.sync.IDEMPOTENT.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `langgraph.sync.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.6s / 3.2s | yes |
| `langgraph.sync.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 3.8s / — | **no** — duplicate_receipts 30/0 |
| `langgraph.sync.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.3s / 3.3s | yes |
| `langgraph.sync.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | yes |
| `langgraph.sync.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 3.4s / 3.6s | yes |
| `langgraph.sync.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `restate.pydantic_ai.EXTERNAL.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | 30 | S1✗ S2✓ S3✓ L1✓ L2✓ | S1✗ S2✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 3.7s / 3.7s | yes |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | 30 | S1✗ S2✓ S3✓ L1✓ L2✓ | S1✗ S2✓ S3✓ L1✓ L2✓ | 30 / 12 | 30 / 12 | 30/30 / 30/30 | 3.8s / 3.8s | **no** — duplicate_effects 30/12; duplicate_receipts 30/12 |
| `restate.pydantic_ai.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.7s / 3.7s | yes |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✗ S2✓ S3✓ L1✓ L2✓ | S1✗ S2✓ S3✓ L1✓ L2✓ | 45 / 50 | 45 / 50 | 30/30 / 30/30 | 19.3s / 21.5s | **no** — duplicate_effects 45/50; duplicate_receipts 45/50 |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✗ S2✓ S3✓ L1✓ L2✓ | S1✗ S2✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.1s / 0.1s | yes |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✗ S2✓ S3✓ L1✓ L2✓ | S1✗ S2✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `restate.pydantic_ai.IDEMPOTENT.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `restate.pydantic_ai.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 3.7s / 3.7s | yes |
| `restate.pydantic_ai.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 8 | 30/30 / 30/30 | 3.7s / 3.6s | **no** — duplicate_receipts 30/8 |
| `restate.pydantic_ai.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.7s / 3.7s | yes |
| `restate.pydantic_ai.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 51 / 50 | 30/30 / 30/30 | 22.3s / 22.0s | **no** — duplicate_receipts 51/50 |
| `restate.pydantic_ai.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.1s / 0.1s | yes |
| `restate.pydantic_ai.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ | S1✓ S2✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `temporal.pydantic_ai.EXTERNAL.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `temporal.pydantic_ai.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 5.6s / 5.4s | yes |
| `temporal.pydantic_ai.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 30 / 0 | 30 / 0 | 30/30 / 30/30 | 5.7s / — | **no** — duplicate_effects 30/0; duplicate_receipts 30/0 |
| `temporal.pydantic_ai.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 5.7s / 7.1s | yes |
| `temporal.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 47 / 50 | 47 / 50 | 30/30 / 30/30 | 5.6s / 6.3s | **no** — duplicate_effects 47/50; duplicate_receipts 47/50 |
| `temporal.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 1.1s / 1.1s | yes |
| `temporal.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |
| `temporal.pydantic_ai.IDEMPOTENT.baseline` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | yes |
| `temporal.pydantic_ai.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 5.9s / 5.1s | yes |
| `temporal.pydantic_ai.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 5.9s / — | **no** — duplicate_receipts 30/0 |
| `temporal.pydantic_ai.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 6.4s / 5.1s | yes |
| `temporal.pydantic_ai.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 51 / 50 | 30/30 / 30/30 | 6.5s / 6.3s | **no** — duplicate_receipts 51/50 |
| `temporal.pydantic_ai.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 1.1s / 1.1s | yes |
| `temporal.pydantic_ai.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | S1✓ S2✓ S3✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | yes |

## Cells with no twin

A fault only one mode can deliver, or a cell one side has not run yet. Listed, never
folded into the agreement count.

| cell | side | n | why |
|---|---|---|---|
| `dbos.native.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `dbos.native.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.native.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.native.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.native.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `dbos.native.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.native.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.pydantic_ai.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `dbos.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.pydantic_ai.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `dbos.pydantic_ai.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `dbos.pydantic_ai.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `dbos.pydantic_ai.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `keel.default.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `keel.default.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.async.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `langgraph.async.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.async.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.async.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.async.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `langgraph.async.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.async.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.exit.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `langgraph.exit.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.exit.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.exit.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.exit.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `langgraph.exit.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.exit.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `langgraph.sync.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `langgraph.sync.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `restate.pydantic_ai.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `restate.pydantic_ai.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `restate.pydantic_ai.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `restate.pydantic_ai.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `restate.pydantic_ai.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `temporal.pydantic_ai.EXTERNAL.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.EXTERNAL.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.EXTERNAL.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.EXTERNAL.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.EXTERNAL.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `temporal.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `temporal.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `temporal.pydantic_ai.IDEMPOTENT.model_500@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.IDEMPOTENT.model_timeout@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.IDEMPOTENT.provider_outage@before:model_call` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | v1_w1_shim | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `temporal.pydantic_ai.IDEMPOTENT.tool_delay@after:tool_effect` | v1_w1_shim | 30 | the other side has not run this cell |
| `temporal.pydantic_ai.IDEMPOTENT.tool_dropped_response@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `temporal.pydantic_ai.IDEMPOTENT.tool_malformed@after:tool_effect` | v1_w1_proxy | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |

## Reading it

87 of 112 comparable twinned cells agree. Every disagreement names what differs, in the order shim / proxy.

What the proxy realisation loses, per §11.2: `before:tool_call` fires on a request that
has already left the SUT (the shim's fires with nothing sent); `after:tool_return` is meant
to land before the SUT parses the bytes, but a kill from outside the process arrives only
after `taskkill`'s latency — often after the parse, sometimes after the run has finished,
which is what a proxy cell with fewer restarts than its shim twin shows (the shim's lands
inside the checkpoint write, via `call_soon`); a freeze parks the request at the proxy and forwards it at the thaw, and the
process frozen is the one named by `sut/pid-<n>` — which, in rows from before a Keel
successor wrote its pid under its own name, may have been the idle successor rather than the
worker holding the run. The `after:tool_effect` window — applied, receipted, nobody told —
is the same window in both.
