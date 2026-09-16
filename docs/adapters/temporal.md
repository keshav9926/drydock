# Adapter: Temporal (`agent_code = pydantic_ai`)

The same workload, the same World, the same shim, the same spec file — written once as a Pydantic AI
`Agent` and made durable by Pydantic AI's `TemporalDurability` capability, which is what §13.5 asks of
every engine arm that Pydantic AI covers. Nothing in the adapter is Temporal-specific agent code: the
workflow body is `agent.run()` and the approval wait.

Source: [`crashproof/adapters/temporal.py`](../../crashproof/adapters/temporal.py).

Versions under test: `temporalio 1.33.0`, `pydantic-ai-slim 2.43.0`, Temporal CLI `1.9.1`
(Server `1.32.0`), Python 3.13. Every one of them is in `config_pin` on every row.

## Cell naming

The adapter is `temporal`; its one config is `pydantic_ai`. Cells read
`temporal.pydantic_ai.<variant>.<trigger>` — the same `runtime.config` shape as `langgraph.sync`, with
§13.5's `agent_code` axis in the config slot. `agent_code: native` is refused at construction: a native
Temporal adapter is a V2 item (§13.5) and counts in no V1 cell.

## Declarations

| | |
|---|---|
| `recovery_mechanism` | **`engine`** — the dev server re-dispatches; the restarted worker is told nothing |
| `key_sources` | `none` (F0) and `framework` (F1) |
| `claims` | PURE `at_least_once` · IDEMPOTENT `effectively_once` · EXTERNAL `at_least_once` |
| Per-trial dependency | `temporal server start-dev --db-filename <trial>/sut/temporal.db` on a free port, headless, never killed during the trial (§22.3) |
| Durable unit | one Activity per model request and per tool call, as `TemporalDurability` makes them: `agent__crashproof__model_request`, `agent__crashproof__toolset__world__call_tool` |
| `worker_count` | 1 — the server is the successor |

The claims are the fact sheet's (Appendix B, Temporal): *"Activities are at-least-once: 'The Activity
function completes successfully, but the Worker crashes just before it notifies the Temporal Service
... the Activity will be retried.' 'Temporal recommends that Activities be idempotent.'"*
([activity-definition](https://docs.temporal.io/activity-definition),
[detecting-activity-failures](https://docs.temporal.io/encyclopedia/detecting-activity-failures)). The
IDEMPOTENT class claims more only because the documented key below is "guaranteed to be consistent
across retry attempts", so a receiver that honours it applies once — the receiver does the work, as
it does for Keel's IDEMPOTENT band. An EXTERNAL duplicate is the documented semantics, printed raw.

The agent itself is the capability's documented form in 2.43 — `Agent(..., capabilities=[TemporalDurability(...)])`,
registered on the worker with `AgentPlugin(agent)` and `PydanticAIPlugin()` on the client. The
older `TemporalAgent` wrapper is deprecated. The provider is a `FunctionModel` whose response is chosen
by the workload script from the ordered `ToolReturnPart`s already in the request (§13.2) — never a
counter, never result content — and its `tool_call_id`s are a function of that key. Inside each
activity the call goes through the shim exactly as every other arm's does
(`shim.model_call(node, ...)`, `shim.tool_call(name, endpoint, args, effect_key=...)`), so the kill
windows sit inside the durable unit.

## `key_source` formula

```
effect_key = f"{activity.info().workflow_run_id}:{activity.info().activity_id}"
```

Fact sheet, `stable_step_identity`: *"You can use a combination of the Workflow Run ID and the
Activity ID as an idempotency key since this is guaranteed to be consistent across retry attempts but
unique among Workflow Executions."* The tool body runs inside its tool-call activity, so
`temporalio.activity.info()` — "Current activity's info" (`temporalio 1.33.0` docstring) — is
available to it. It is sent only when the variant's `key_source` is `framework` and the class is
IDEMPOTENT; W1's EXTERNAL variant sends nothing (F0).

| Variant | Endpoint | `dedup` | Key sent | Level |
|---|---|---|---|---|
| EXTERNAL | `issues.create` | `false` | none | **F0** |
| IDEMPOTENT | `issues.upsert` | `true, natural: true` | `Idempotency-Key: <run_id>:<activity_id>` | **F1** |

## What a restart does

Nothing, from the worker's side, and that is the point of `engine`.

1. The worker dies (or freezes). The server does not notice — *"The Temporal Server doesn't detect
   failures when a Worker loses communication with the Server or crashes"* (fact sheet).
2. The open activity's heartbeat timeout (2 s) or start-to-close timeout (5 s) expires. In the smoke
   it is always the heartbeat: the next attempt's `ActivityTaskStarted` carries
   `last_failure = "activity Heartbeat timeout"`.
3. The RetryPolicy schedules attempt 2 after its 1 s initial interval; whichever worker polls the task
   queue runs it — the restarted one, spawned with the same argv.
4. A workflow task that was bound for the dead worker's sticky queue waits out
   `sticky_queue_schedule_to_start_timeout` (SDK default 10 s: "How long a workflow task is allowed to
   sit on the sticky queue before it is timed out and moved to the non-sticky queue") and is then
   replayed from history on the new worker. That 10 s, not the activity timeouts, dominates the wall
   time of every kill cell in the smoke (one `WORKFLOW_TASK_TIMED_OUT` in each kill history).

**Who starts the workflow.** The adapter, once, at `submit`, with workflow id
`crashproof-<trial dir name>` (each trial has its own server). In Temporal a client starts a workflow
and a worker polls a task queue; those are different programs. Starting it from the first
incarnation instead would make the worker behave differently on its first life than on its second —
process memory by another name — so the worker never starts, signals or queries anything, and
`worker_argv` is `python -m crashproof.adapters.temporal` every time (§13.3 rules 2, 3).
`on_worker_restart` is a no-op.

**Kills and freezes on Windows.** The Temporal Python SDK's core is a Rust extension *in the worker
process*, not a separate process, so `os._exit(137)` and the supervisor's `taskkill /F /T` end all of
it. A `pause_past_ttl` freeze (`NtSuspendProcess`) stops every thread, the Rust core's heartbeat
included — confirmed by the smoke: the frozen worker is never restarted, yet the server times its
attempt out on *heartbeat* and retries it.

## Pins

| Pin | Value | Why |
|---|---|---|
| `start_to_close_timeout` | 5 s | §13.4; the ceiling on one attempt. Equal to the World client's socket timeout (5 s) |
| `heartbeat_timeout` | 2 s | §13.4; detection. Set on model **and** tool activities — Pydantic's default gives tools none and models 30 s. Safe here because no activity blocks its event loop: the shim does the call on a thread (Pydantic docs: "Don't set a `heartbeat_timeout` on activities that can block the event loop") |
| RetryPolicy | `initial_interval=1s, backoff_coefficient=2.0, maximum_interval=100s, maximum_attempts=0` | Temporal's documented default, spelled out. `TemporalDurability` appends its non-retryable types (`UserError`, `PydanticUserError`, `UnexpectedModelBehavior`, `FallbackExceptionGroup`, payload-size errors) |
| Client-side retries | none | Pydantic docs: "it's recommended to not use transport retries and to turn off your provider API client's own retry logic". The provider is a `FunctionModel` with no HTTP client, and the World client never retries — so there is nothing to multiply |
| Heartbeat throttle | SDK default, `0.8 × heartbeat_timeout` | how stale the server's last beat can be when the freeze lands |
| Workflow task timeout | 10 s (default) | printed |
| Sticky queue schedule-to-start | 10 s (SDK default) | see "What a restart does", step 4 |
| `pause_past_ttl` pause | 3 s (supervisor default) | 1.5 × the heartbeat timeout — past it, but not §13.4's `[2×, 4×]` draw, which the harness does not implement for any arm yet |

## W5 — the human in the loop

**The gate.** A gated tool is declared `requires_approval=True` ("Whether this tool requires
human-in-the-loop approval", `pydantic_ai.tools.Tool`, 2.43) — which tools are gated is the workload's
`gated_tools()`, not the adapter's choice. The agent's `output_type` includes `DeferredToolRequests`,
which "will be used as the output of the agent run if the model called any deferred tools"
(`pydantic_ai.tools.DeferredToolRequests`, 2.43).

**The wait.** When `agent.run()` returns `DeferredToolRequests`, the workflow waits on Temporal's
documented message-passing primitive: an `approve` **signal** and
`workflow.wait_condition(lambda: decided, timeout=expires_in)` (fact sheet: "workflow awaits with
workflow.wait_condition(lambda: self.approved). While waiting the workflow task completes and no worker
slot is held"). `timeout` creates a Temporal timer, so **expiry is a durable timer** from the run
input's `expires_in` (5 s); when it fires first, the run returns `not done: approval expired` and
nothing is deployed.

**The continuation.** On a grant the run continues with Pydantic AI's documented pair,
`agent.run(message_history=..., deferred_tool_results=DeferredToolResults(approvals={id: True}))`.
Tool calls that already ran in the interrupted response are not run again: the continuation marks
every call with a `ToolReturnPart` in the history as `'skip'` (`_agent_graph._handle_deferred_tool_results`,
2.43). W5-pre's `before_approval` call is in the same model response as the gated one, so it runs as
its own activity before the run ends asking — and the continuation skips it.

**Status.** `status()` is `describe()` on the workflow, and WAITING is a memo the workflow upserts when
it parks (`workflow.upsert_memo`) and clears when it stops waiting. `describe()` needs no worker, so a
worker killed while parked cannot hide the park from the harness or make the status call hang.

**The human, and the duplicate click.** `approve()` sends the `approve` signal with
`{"decision": "granted", "by": "harness"}`. §11.4 C's second, unkeyed click is the same signal sent
again. Temporal records both (`WORKFLOW_EXECUTION_SIGNALED` twice in the history), the handler appends
both, and the wait is satisfied by the first; the second reaches nothing. A signal to a workflow that
has already closed is refused by the server; `approve()` returns `False` for it rather than raising.
Temporal signals carry no approval id, so there is no "granted twice under one id" to be had — the
decision is the workflow code's, and it reads the first.

## What is N/A, and why

| Invariant | Verdict | Reason |
|---|---|---|
| S2 | **judged** | `committed_effects` is read from Temporal's own history: the `external_ref` in the result of every `ActivityTaskCompleted` of a non-PURE tool-call activity. No counter is added — the World's label is in the result the activity returned, and the completed event is the engine's durable record of it |
| S4 | N/A | The verifier reads a Keel-shaped journal (`STEP_ATTEMPT_STARTED` with timestamps). Temporal's `ActivityTaskStarted` is not a write-ahead record: in the smoke histories it lands immediately before its `ActivityTaskCompleted`, after events that arrived while the attempt was running (a signal, a workflow task), so it cannot be placed before a receipt — and translating history into Keel events would be the adapter inventing a journal |
| S5 | N/A | same: no Keel step lifecycle is exported |
| S7 | N/A | S7 is judged from `APPROVAL_REQUESTED/DECIDED` journal events. Temporal's history has the signals, the timer and the gated activity, but no approval id binding one to the other; the per-effect result is still on the page (`deploy.service#1` applied count) |
| C1 | **judged** | `temporalio.worker.Replayer` replays the trial's fetched history against the workflow code with the same plugins; a replay failure (nondeterminism) is FAIL. No activity runs during replay |

## Smoke — one seed per cell, against §13.7's predictions

`bench/specs/smoke_temporal.yaml`, `smoke_temporal_w5.yaml`, `smoke_temporal_w5_pre.yaml`, seed 7, 18
trials, every one valid, COMPLETED, S1/S2/S3/L1/L2/C1 PASS. One seed is a check that each cell runs and
lands where it was aimed, not a rate.

| cell | applied / receipts | model calls (baseline 3) | restarts | what re-dispatched | §13.7 predicted |
|---|---|---|---|---|---|
| EXTERNAL `before:tool_call` (T1) | 1 / 1 | 3 | 1 | attempt 2 after "activity Heartbeat timeout" | 0 dup / +0 — **held** |
| EXTERNAL `after:tool_effect` (T2) | **2** / 2 | 3 | 1 | same | 1 / +0 — **held** |
| EXTERNAL `after:tool_return` (T3) | **2** / 2 | 3 | 1 | same | 1 / +0 — **held** (H1: T2 ≡ T3) |
| EXTERNAL `pause_past_ttl@before:tool_call` (T4) | **2** / 2 | 3 | **0** | the frozen worker's own attempt timed out on heartbeat; after the thaw it sent its request *and* ran the retry | 1 / +0, "2 receipts, 2 applied" — **held** |
| IDEMPOTENT T1 | 1 / 1 | 3 | 1 | heartbeat timeout | — |
| IDEMPOTENT T2, T3, T4 | **1 / 2** each | 3 | 1, 1, 0 | heartbeat timeout; both receipts carry the same `<run_id>:4` key | H3: one applied at F1 — **held** |
| W5 `approval_delay` (duplicate click) | deploy 1 | 3 | 0 | two `WORKFLOW_EXECUTION_SIGNALED`; the second reached nothing | H7: 1 — **held** |
| W5 `kill_while_waiting` | deploy 1 | 3 | 1 | the grant waited out the dead worker's 10 s sticky queue | H7: 1 / +0 — **held** |
| W5 `approval_expiry` | deploy 0 | 2 | 0 | the 5 s timer fired: `not done: approval expired` | nothing deployed, COMPLETED |
| W5 `kill@after:tool_effect` | deploy **2** | 3 | 1 | heartbeat timeout | T2 behind a gate: 1 dup |
| W5-pre `approval_delay`, `kill_while_waiting` | notify **1**, deploy 1 | 3 | 0, 1 | the continuation skips the `notify` that already ran | tier-2 H7 predicts 2 only for pre-interrupt re-run; Pydantic AI's deferred-tool continuation does not re-run — **1**, like Keel |

Two things the rows say that the prediction table does not:

- **Detection is the heartbeat, every time** — `last_failure` is "activity Heartbeat timeout" on every
  retried attempt, never start-to-close. `recovery_latency_ms` is 4.4–5.8 s
  for kills (≤ 2 s heartbeat + 1 s retry interval + worker start) and 3.1 s for the freeze. The trial's
  wall time is ~21 s against a 6 s baseline because the completed retry's workflow task sits on the dead
  worker's sticky queue for the SDK's 10 s `sticky_queue_schedule_to_start_timeout`
  (`WORKFLOW_TASK_TIMED_OUT` in each kill history) — not the workflow task timeout §13.4 names.
- **`kill_while_waiting` decided a grant after its deadline had passed on the server, and granted.**
  The grant signal arrived 0.6–0.7 s into the park; the workflow task carrying it waited 10 s on
  the dead worker's sticky queue; the 5 s expiry timer fired in the meantime (`TIMER_FIRED` after the
  signal in both histories). The one activation that saw both delivered the signal first, so
  `wait_condition` was satisfied and the deploy ran. By arrival order that is right; it is not what
  Keel does, which judges expiry by the store's clock at drain time. Whether a run resolves an approval
  that arrived on time but was processed late in favour of the human is a semantic the two arms differ
  on — printed, not scored.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the framework does not do itself (the RetryPolicy is
Temporal's default), no dedup in the adapter, no key other than the documented one. The worker's argv
never changes and carries no id. The model is the workload script, selected by request content alone.
