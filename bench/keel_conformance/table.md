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

| boundary | fault | class | window | disposal | applied | receipts | status | S1 | S3 | S4 | S5 | S7 | S8 | S9 | L1 | C1 | C2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `before:intent_commit` | `crash` | PURE | no row/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:intent_commit` | `crash` | IDEMPOTENT | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:intent_commit` | `crash` | EXTERNAL | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:intent_commit` | `journal_error` | PURE | no row/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:intent_commit` | `journal_error` | IDEMPOTENT | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:intent_commit` | `journal_error` | EXTERNAL | no row/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:intent_commit` | `crash` | PURE | running/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:intent_commit` | `crash` | IDEMPOTENT | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:intent_commit` | `crash` | EXTERNAL | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:attempt_commit` | `crash` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `crash` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `crash` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `journal_error` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `journal_error` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:attempt_commit` | `journal_error` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `after:attempt_commit` | `crash` | PURE | running/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:attempt_commit` | `crash` | IDEMPOTENT | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:attempt_commit` | `crash` | EXTERNAL | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:effect_exec` | `crash` | PURE | running/untouched | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:effect_exec` | `crash` | IDEMPOTENT | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:effect_exec` | `crash` | EXTERNAL | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:effect_exec` | `raise` | PURE | settled/untouched | FAILED | 0 | 0 | FAILED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:effect_exec` | `raise` | IDEMPOTENT | settled/untouched | FAILED | 0 | 0 | FAILED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:effect_exec` | `raise` | EXTERNAL | settled/untouched | FAILED | 0 | 0 | FAILED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:effect_exec` | `crash` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:effect_exec` | `crash` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:effect_exec` | `crash` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:effect_exec` | `raise` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `after:effect_exec` | `raise` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `after:effect_exec` | `raise` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:outcome_commit` | `crash` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:outcome_commit` | `crash` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:outcome_commit` | `crash` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:outcome_commit` | `journal_error` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:outcome_commit` | `journal_error` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:outcome_commit` | `journal_error` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:outcome_commit` | `crash` | PURE | settled/sent | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:outcome_commit` | `crash` | IDEMPOTENT | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `after:outcome_commit` | `crash` | EXTERNAL | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:lease_heartbeat` | `crash` | PURE | settled/sent | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:lease_heartbeat` | `crash` | IDEMPOTENT | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:lease_heartbeat` | `crash` | EXTERNAL | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:lease_heartbeat` | `sleep` | PURE | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:lease_heartbeat` | `sleep` | IDEMPOTENT | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:lease_heartbeat` | `sleep` | EXTERNAL | N/A | — | — | — | — | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| `before:lease_release` | `crash` | PURE | settled/sent | COMPLETED | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:lease_release` | `crash` | IDEMPOTENT | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `before:lease_release` | `crash` | EXTERNAL | settled/sent | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | N/A |
| `during:approval_wait` | `crash` | GATED | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | N/A |
| `before:signal_consume` | `crash` | GATED | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | N/A |
| `before:signal_consume` | `journal_error` | GATED | running/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | N/A |
| `after:signal_consume` | `crash` | GATED | settled/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | N/A |
| `after:signal_consume` | `journal_error` | GATED | settled/untouched | COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | N/A |
| `before:child_spawn` | `crash` | DELEGATED | no row/untouched | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | PASS | N/A | PASS | PASS | N/A |
| `before:child_spawn` | `journal_error` | DELEGATED | no row/untouched | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | PASS | N/A | PASS | PASS | N/A |
| `during:child_wait` | `crash` | DELEGATED | running/untouched | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | PASS | N/A | PASS | PASS | N/A |
| `before:segment_write` | `crash` | SEGMENTED | no segment/sent | segments=1 | 4 | 4 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | PASS |
| `before:segment_write` | `journal_error` | SEGMENTED | no segment/sent | segments=1 | 4 | 4 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | PASS |
| `during:stream(chunk=1)` | `crash` | MODEL | running/untouched | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `crash` | PURE | running/sent | COMPLETED | 0 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `crash` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `crash` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `raise` | MODEL | running/untouched | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `raise` | PURE | running/sent | COMPLETED partial | 0 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `raise` | IDEMPOTENT | running/sent | COMPLETED | 1 | 2 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |
| `during:stream(chunk=1)` | `raise` | EXTERNAL | running/sent | RESOLVED_COMPLETED | 1 | 1 | COMPLETED | PASS | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | N/A |

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

54 cells run, 12 N/A, 0 failed. Regenerate with `uv run pytest tests/conformance -q`.

All seventeen boundaries exist: the ten of the write path (§28.6), the three the inbox and
approvals brought with them (§4.10), the two delegation brought (§4.11), the continuation
boundary (§4.9), and `during:stream(chunk=k)` with STREAMS (§10.7) — §29.2's *all seventeen
hook boundaries*.

S8 is judged here and nowhere else yet: these cells hold every journal in the tree, and the
matrix's collector reads one per trial, so the matrix prints N/A with that reason (§15.11).
C2 is N/A wherever the workload never crosses a continuation boundary. S9 is judged in its
sim form (§12.4: Σ charged ≥ Σ provider-billed, abandoned attempts included) on the stream
cells only — the one boundary where a chunk can move a charge — and is N/A elsewhere.
