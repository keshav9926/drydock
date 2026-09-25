# Placement — where the faults landed (§19.5 view 4, K3)

Per cell, across its seeds: where each fired fault landed and whether it fell inside K3's window — after the World receipt of the aimed tool, before the SUT's next committed record (for `before:tool_call`, before any receipt). A fault the artefacts cannot place is *unobservable* and counted as neither; a K3 clause with one in it is not computable.

Rows through 2026-09-19T13:20:53+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `v1/combined_week2_w1_shim` | 6241 | `251e52d` ×6241 |

## Per cell

| cell | trials (facts) | fired | in window | K3 ≥ 90 % | histogram | mis-aimed |
|---|---|---|---|---|---|---|
| `dbos.native.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.after:tool_return` | 30 (30) | 30 | 21/30 | **FAIL** (70%) | after:tool_return · after commit step 3 ✓ ×21<br>after:tool_return · after commit step 4 ✗ ×9 | no |
| `dbos.native.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.native.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.native.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.native.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 19/30 | **FAIL** (63%) | after:tool_return · after commit step 3 ✓ ×19<br>after:tool_return · after commit step 4 ✗ ×11 | no |
| `dbos.native.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.native.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.native.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.native.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.native.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.after:tool_return` | 30 (30) | 30 | 14/30 | **FAIL** (47%) | after:tool_return · after commit step 4 ✗ ×16<br>after:tool_return · after commit step 3 ✓ ×14 | **mis-aimed** |
| `dbos.pydantic_ai.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 16/30 | **FAIL** (53%) | after:tool_return · after commit step 3 ✓ ×16<br>after:tool_return · after commit step 4 ✗ ×14 | no |
| `dbos.pydantic_ai.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 3 ✓ ×30 | no |
| `dbos.pydantic_ai.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 3 ✓ ×30 | no |
| `keel.default.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · unobservable ×30 | no |
| `keel.default.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · unobservable ×30 | no |
| `keel.default.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · unobservable ×30 | no |
| `keel.default.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · unobservable ×30 | no |
| `keel.default.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · unobservable ×30 | no |
| `keel.default.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · unobservable ×30 | no |
| `keel.default.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · step 3.1 create_issue ✓ ×30 | no |
| `keel.default.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×30 | no |
| `langgraph.async.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step -1 ✓ ×30 | no |
| `langgraph.async.EXTERNAL.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after checkpoint step -1 ✓ ×29<br>after:tool_return · after checkpoint step 1 ✓ ×1 | no |
| `langgraph.async.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step -1 ✓ ×29<br>before:tool_call · after checkpoint step 0 ✓ ×1 | no |
| `langgraph.async.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.async.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.async.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.async.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step -1 ✓ ×28<br>after:tool_effect · after checkpoint step 0 ✓ ×1<br>after:tool_effect · after checkpoint step 1 ✓ ×1 | no |
| `langgraph.async.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step -1 ✓ ×28<br>after:tool_effect · after checkpoint step 0 ✓ ×1<br>after:tool_effect · after checkpoint step 1 ✓ ×1 | no |
| `langgraph.async.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step -1 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after checkpoint step -1 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step -1 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.async.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.async.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.async.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step -1 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step -1 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.async.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first checkpoint ×30 | no |
| `langgraph.exit.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first checkpoint ×30 | no |
| `langgraph.exit.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first checkpoint ×30 | no |
| `langgraph.exit.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first checkpoint ×30 | no |
| `langgraph.exit.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first checkpoint ×30 | no |
| `langgraph.exit.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first checkpoint ×30 | no |
| `langgraph.exit.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · before the first checkpoint ✓ ×30 | no |
| `langgraph.exit.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · before the first checkpoint ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.sync.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.sync.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.sync.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.sync.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.sync.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · after checkpoint step 0 ×30 | no |
| `langgraph.sync.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after checkpoint step 3 ✓ ×30 | no |
| `langgraph.sync.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after checkpoint step 3 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `restate.pydantic_ai.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `restate.pydantic_ai.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 6 ✓ ×30 | no |
| `restate.pydantic_ai.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 6 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.after:tool_return` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_return · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.model_500@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.model_timeout@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.provider_outage@before:model_call` | 30 (30) | 30 | 0/0 | not computable: 30 of 30 unobservable (no K3 window at before:model_call ×30) | before:model_call · before the first commit ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.tool_500@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.tool_delay@after:tool_effect` | 30 (30) | 30 | 30/30 | PASS (100%) | after:tool_effect · after commit step 17 ✓ ×30 | no |
| `temporal.pydantic_ai.IDEMPOTENT.tool_timeout@before:tool_call` | 30 (30) | 30 | 30/30 | PASS (100%) | before:tool_call · after commit step 17 ✓ ×30 | no |

## K3 between arms

| (variant, trigger) | in-window fraction by arm | K3 ≤ 10 points |
|---|---|---|
| EXTERNAL · after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · after:tool_return | `dbos.native` 70% · `dbos.pydantic_ai` 47% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | **FAIL** (53 points) |
| EXTERNAL · before:tool_call | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · model_500@before:model_call | `dbos.native` — · `dbos.pydantic_ai` — · `keel.default` — · `langgraph.async` — · `langgraph.exit` — · `langgraph.sync` — · `restate.pydantic_ai` — · `temporal.pydantic_ai` — | not computable: an arm has unobservable faults |
| EXTERNAL · model_timeout@before:model_call | `dbos.native` — · `dbos.pydantic_ai` — · `keel.default` — · `langgraph.async` — · `langgraph.exit` — · `langgraph.sync` — · `restate.pydantic_ai` — · `temporal.pydantic_ai` — | not computable: an arm has unobservable faults |
| EXTERNAL · pause_past_ttl@before:tool_call | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · provider_outage@before:model_call | `dbos.native` — · `dbos.pydantic_ai` — · `keel.default` — · `langgraph.async` — · `langgraph.exit` — · `langgraph.sync` — · `restate.pydantic_ai` — · `temporal.pydantic_ai` — | not computable: an arm has unobservable faults |
| EXTERNAL · sigterm_grace_ok@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · sigterm_grace_too_short@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · tool_500@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · tool_delay@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| EXTERNAL · tool_timeout@before:tool_call | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · after:tool_return | `dbos.native` 63% · `dbos.pydantic_ai` 53% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | **FAIL** (47 points) |
| IDEMPOTENT · before:tool_call | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · model_500@before:model_call | `dbos.native` — · `dbos.pydantic_ai` — · `keel.default` — · `langgraph.async` — · `langgraph.exit` — · `langgraph.sync` — · `restate.pydantic_ai` — · `temporal.pydantic_ai` — | not computable: an arm has unobservable faults |
| IDEMPOTENT · model_timeout@before:model_call | `dbos.native` — · `dbos.pydantic_ai` — · `keel.default` — · `langgraph.async` — · `langgraph.exit` — · `langgraph.sync` — · `restate.pydantic_ai` — · `temporal.pydantic_ai` — | not computable: an arm has unobservable faults |
| IDEMPOTENT · pause_past_ttl@before:tool_call | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · provider_outage@before:model_call | `dbos.native` — · `dbos.pydantic_ai` — · `keel.default` — · `langgraph.async` — · `langgraph.exit` — · `langgraph.sync` — · `restate.pydantic_ai` — · `temporal.pydantic_ai` — | not computable: an arm has unobservable faults |
| IDEMPOTENT · sigterm_grace_ok@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · sigterm_grace_too_short@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · tool_500@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · tool_delay@after:tool_effect | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
| IDEMPOTENT · tool_timeout@before:tool_call | `dbos.native` 100% · `dbos.pydantic_ai` 100% · `keel.default` 100% · `langgraph.async` 100% · `langgraph.exit` 100% · `langgraph.sync` 100% · `restate.pydantic_ai` 100% · `temporal.pydantic_ai` 100% | PASS (0 points) |
