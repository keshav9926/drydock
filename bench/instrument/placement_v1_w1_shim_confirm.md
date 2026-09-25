# Placement — where the faults landed (§19.5 view 4, K3)

Per cell, across its seeds: where each fired fault landed and whether it fell inside K3's window — after the World receipt of the aimed tool, before the SUT's next committed record (for `before:tool_call`, before any receipt). A fault the artefacts cannot place is *unobservable* and counted as neither; a K3 clause with one in it is not computable.

Rows through 2026-09-19T22:44:10+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `v1_w1_shim_confirm` | 2119 | `251e52d` ×2119 |

## Per cell

| cell | trials (facts) | fired | in window | K3 ≥ 90 % | histogram | mis-aimed |
|---|---|---|---|---|---|---|
| `dbos.native.EXTERNAL.after:tool_return` | 300 (300) | 300 | 239/300 | **FAIL** (80%) | after:tool_return · after commit step 3 ✓ ×239<br>after:tool_return · after commit step 4 ✗ ×61 | no |
| `dbos.pydantic_ai.EXTERNAL.after:tool_return` | 300 (300) | 300 | 205/300 | **FAIL** (68%) | after:tool_return · after commit step 3 ✓ ×205<br>after:tool_return · after commit step 4 ✗ ×95 | no |
| `keel.default.EXTERNAL.after:tool_return` | 300 (300) | 300 | 300/300 | PASS (100%) | after:tool_return · step 3.1 create_issue ✓ ×300 | no |
| `keel.default.EXTERNAL.pause_past_ttl@before:tool_call` | 300 (300) | 300 | 300/300 | PASS (100%) | before:tool_call · step 3.1 create_issue ✓ ×300 | no |

## K3 between arms

| (variant, trigger) | in-window fraction by arm | K3 ≤ 10 points |
|---|---|---|
| EXTERNAL · after:tool_return | `dbos.native` 80% · `dbos.pydantic_ai` 68% · `keel.default` 100% | **FAIL** (32 points) |
