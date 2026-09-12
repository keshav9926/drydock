# Keel conformance (`hook` mode, deterministic, pass/fail)

Keel's own crash-window enumeration, run against Keel. **Never unioned with the
cross-runtime matrix**: a boundary only one runtime exposes is not a fair column (§14.5).
No `n`, no confidence interval, no confirmation tier — with `MemoryJournal` and a
`FakeClock` these are deterministic, so a cell passes or it fails and a flake is a bug.

`window` is what the journal and the World held at the instant of the fault, which is the
§8.3 recovery table read backwards, and `disposal` is how the successor closed the step
the fault interrupted — the per-class column of that same table, demonstrated rather than
asserted. `applied` and `receipts` are what the World actually did and what it was asked
to do, printed whatever the verdicts say: the gap between them is what the receiver's
idempotency bought, and the runtime gets no credit for it.

| boundary | fault | class | window | disposal | applied | receipts | status | S1 | S3 | S4 | S5 | L1 | C1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `before:intent_commit` | `crash` | PURE | no row/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:intent_commit` | `crash` | IDEMPOTENT | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:intent_commit` | `crash` | EXTERNAL | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:intent_commit` | `journal_error` | PURE | no row/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:intent_commit` | `journal_error` | IDEMPOTENT | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:intent_commit` | `journal_error` | EXTERNAL | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:intent_commit` | `crash` | PURE | running/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:intent_commit` | `crash` | IDEMPOTENT | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:intent_commit` | `crash` | EXTERNAL | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:attempt_commit` | `crash` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `crash` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `crash` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `journal_error` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `journal_error` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `journal_error` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `after:attempt_commit` | `crash` | PURE | running/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:attempt_commit` | `crash` | IDEMPOTENT | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:attempt_commit` | `crash` | EXTERNAL | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:effect_exec` | `crash` | PURE | running/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:effect_exec` | `crash` | IDEMPOTENT | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:effect_exec` | `crash` | EXTERNAL | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:effect_exec` | `raise` | PURE | settled/untouched | FAILED | 0 | 0 | FAILED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:effect_exec` | `raise` | IDEMPOTENT | settled/untouched | FAILED | 0 | 0 | FAILED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:effect_exec` | `raise` | EXTERNAL | settled/untouched | FAILED | 0 | 0 | FAILED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:effect_exec` | `crash` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:effect_exec` | `crash` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:effect_exec` | `crash` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:effect_exec` | `raise` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `after:effect_exec` | `raise` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `after:effect_exec` | `raise` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:outcome_commit` | `crash` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:outcome_commit` | `crash` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:outcome_commit` | `crash` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:outcome_commit` | `journal_error` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:outcome_commit` | `journal_error` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:outcome_commit` | `journal_error` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:outcome_commit` | `crash` | PURE | settled/sent | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:outcome_commit` | `crash` | IDEMPOTENT | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `after:outcome_commit` | `crash` | EXTERNAL | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:lease_heartbeat` | `crash` | PURE | settled/sent | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:lease_heartbeat` | `crash` | IDEMPOTENT | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:lease_heartbeat` | `crash` | EXTERNAL | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:lease_heartbeat` | `sleep` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:lease_heartbeat` | `sleep` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:lease_heartbeat` | `sleep` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:lease_release` | `crash` | PURE | settled/sent | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:lease_release` | `crash` | IDEMPOTENT | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |
| `before:lease_release` | `crash` | EXTERNAL | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | PASS |

## N/A, with the reason

A fault this mode cannot deliver is named, never skipped and never folded into a
pass — the same discipline the matrix applies to a runtime that cannot supply an
invariant's inputs.

| boundary | fault | why |
|---|---|---|
| `after:effect_exec` | `raise` | an ordinary exception here is indistinguishable from the tool's own, so the engine records STEP_FAILED and closes the very window the boundary exists to open. A fault that produces an outcome is not a crash; `hooks.Crash` is what this boundary takes |
| `before:attempt_commit` | `crash` | fires only for attempt >= 2; `tool_chain_1_effect` has no retryable first attempt and `NO_RETRY` is the default policy, so the boundary is unreachable in this workload |
| `before:attempt_commit` | `journal_error` | same: the boundary is unreachable in this workload |
| `before:lease_heartbeat` | `sleep` | a pause the event loop can serve is not a pause. In one process the zombie and its successor share a loop, so the fence is proven directly in tests/unit/test_fence.py rather than through a sleep no scheduler will honour |

## Provenance

Generated 2026-09-12T13:24:11+00:00. 36 cells run, 12 N/A, 0 failed.

The seven remaining boundaries — `before/after:signal_consume`, `during:approval_wait`,
`before:child_spawn`, `during:child_wait`, `before:segment_write` and
`during:stream(chunk=k)` — are absent rather than stubbed, and arrive with the mechanisms
they name (§28.6). §29.2's *all seventeen hook boundaries* is the honest completion date.
