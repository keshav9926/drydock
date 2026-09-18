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
older `TemporalAgent` wrapper is deprecated. The agent is not written here: it is
[`crashproof/adapters/pydantic_ai_agent.py`](../../crashproof/adapters/pydantic_ai_agent.py), the one
Pydantic AI agent every engine arm runs (DBOS's `pydantic_ai` row builds the same one), and Temporal
supplies only its key, no tool wrapping, and `TemporalDurability`. `tests/unit/test_pydantic_ai_agent.py`
pins that both arms answer the same history with the same response. The provider is a `FunctionModel` whose response is chosen
by the workload script from the ordered `ToolReturnPart`s already in the request (§13.2) — never a
counter, never result content — and its `tool_call_id`s are `<node>:<index>`, a function of that key. Inside each
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
   `sticky_queue_schedule_to_start_timeout` ("How long a workflow task is allowed to sit on the sticky
   queue before it is timed out and moved to the non-sticky queue where it may be picked up by any
   worker", `temporalio.worker.Worker`, 1.33.0) and is then replayed from history on the new worker.
   **Pinned to 2 s, the heartbeat.** At the SDK's 10 s default the first smoke's every kill history has
   one `WORKFLOW_TASK_TIMED_OUT` and the kill cells ran ~21 s against a 6 s baseline: a Temporal kill
   cell was measuring an SDK default hiding behind the pinned detection timeout, which §13.4 and H6
   say is what detection latency is supposed to be. It is a documented worker option, so pinning it
   is configuration, not help.

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
| Sticky queue schedule-to-start | 2 s (SDK default 10 s) | `Worker(sticky_queue_schedule_to_start_timeout=...)`, documented; the 10 s default put ~10 s on every kill cell that was not detection — see "What a restart does", step 4 |
| `pause_past_ttl` pause | seeded `pause_factor ∈ [2, 4]` × `detection_timeout_s` = the 2 s heartbeat (§13.4) | the supervisor's draw; the applied pause is on the fault row (`pause_ms`). Seed 7 applied 7.10 s (EXTERNAL) and 7.08 s (IDEMPOTENT) |

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
| W7, `model_stream_truncate` | not declared, though expressible (buffered) | pydantic-ai-slim 2.43.0: `agent.run_stream()` "cannot be used inside a Temporal workflow. Set an `event_stream_handler` on the agent and use `agent.run()` instead", and the handler "runs inside activities" — so a streamed model call is expressible, consumed inside the model-request activity, and the history records only the completed response: §14.1's "Temporal buffers stream inside the activity (reported as 'buffered')". The binding is not built; the activity would call the shim's `model_stream` to reach `during:model_stream(chunk=k)` |

## Smoke — one seed per cell, against §13.7's predictions

`bench/specs/smoke_temporal.yaml`, `smoke_temporal_w5.yaml`, `smoke_temporal_w5_pre.yaml`, seed 7, 18
trials, every one valid, COMPLETED, S1/S2/S3/L1/L2/C1 PASS. One seed is a check that each cell runs and
lands where it was aimed, not a rate. Run on the shared agent with the sticky queue pinned to 2 s and
§13.4's pause draw; where a number moved from the first smoke (sticky queue at the 10 s default, a flat
3 s pause) the old value is in brackets.

| cell | applied / receipts | model calls (baseline 3) | restarts | wall s (baseline 6.1) | what re-dispatched | §13.7 predicted |
|---|---|---|---|---|---|---|
| EXTERNAL `before:tool_call` (T1) | 1 / 1 | 3 | 1 | 12.8 [22.8] | attempt 2 after "activity Heartbeat timeout" | 0 dup / +0 — **held** |
| EXTERNAL `after:tool_effect` (T2) | **2** / 2 | 3 | 1 | 12.6 [20.7] | same | 1 / +0 — **held** |
| EXTERNAL `after:tool_return` (T3) | **2** / 2 | 3 | 1 | 12.3 [21.6] | same | 1 / +0 — **held** (H1: T2 ≡ T3) |
| EXTERNAL `pause_past_ttl@before:tool_call` (T4), pause **7.10 s** [3 s] | **3 / 3** [2 / 2] | 3 | **0** | 13.4 [10.8] | the completed attempt is **3** [2]; all three requests landed within 90 ms of the thaw | 1 dup, "2 receipts, 2 applied" — **held at 3 s, not at 7.1 s: 2 dups** |
| IDEMPOTENT T1 | 1 / 1 | 3 | 1 | 12.7 | heartbeat timeout | — |
| IDEMPOTENT T2, T3 | **1 / 2** each | 3 | 1, 1 | 12.5, 13.0 | heartbeat timeout; both receipts carry the same `<run_id>:4` key | H3: one applied at F1 — **held** |
| IDEMPOTENT T4, pause 7.08 s | **1 / 3** [1 / 2] | 3 | 0 | 13.4 | three receipts, one key | H3 — **held** |
| W5 `approval_delay` (duplicate click) | deploy 1 | 3 | 0 | 6.6 | two `WORKFLOW_EXECUTION_SIGNALED`; the second reached nothing | H7: 1 — **held** |
| W5 `kill_while_waiting` | deploy 1 | 3 | 1 | 11.7 [17.9] | the grant's workflow task left the dead worker's sticky queue after 2 s [10 s] | H7: 1 / +0 — **held** |
| W5 `approval_expiry` | deploy 0 | 2 | 0 | 10.9 | the 5 s timer fired: `not done: approval expired` | nothing deployed, COMPLETED |
| W5 `kill@after:tool_effect` | deploy **2** | 3 | 1 | 14.0 [20.6] | heartbeat timeout | T2 behind a gate: 1 dup |
| W5-pre `approval_delay`, `kill_while_waiting` | notify **1**, deploy 1 | 3 | 0, 1 | 6.5, 11.4 [—, 17.0] | the continuation skips the `notify` that already ran | tier-2 H7 predicts 2 only for pre-interrupt re-run; Pydantic AI's deferred-tool continuation does not re-run — **1**, like Keel |

Three things the rows say that the prediction table does not:

- **Detection is the heartbeat, every time** — `last_failure` is "activity Heartbeat timeout" on every
  retried attempt, never start-to-close. `recovery_latency_ms` is 4.1–4.6 s for the W1 kills
  (≤ 2 s heartbeat + 1 s retry interval + worker start) [4.4–5.8 s]. Kill-cell wall time fell from
  ~21 s to ~12.5 s when the sticky queue was pinned: the ~8 s difference was the SDK default, not the
  engine. Every kill history still has one `WORKFLOW_TASK_TIMED_OUT`, now 2 s after it was scheduled.
- **The zombie count grows with the pause.** §13.7 predicts one duplicate: the timed-out attempt
  completes after the thaw and the retry fires too. That is what a 3 s freeze did. A 7.1 s freeze
  spans more than one heartbeat-plus-backoff cycle, and the attempt that completed is attempt 3: attempt
  1 and attempt 2 both timed out while the worker was frozen, and after the thaw the worker sent three
  requests within 90 ms. History records only the attempt that closed, so which frozen attempts reached
  the worker is inferred from the receipts, not read from Temporal. At F0 on `dedup: false` that is two
  duplicates, within `at_least_once`; at F1 all three carry one key and the receiver applies once. The
  duplicate count at T4 is a function of `pause / (heartbeat + backoff)` — the reason §13.4 draws the
  pause rather than fixing it, and the reason a 30-seed run of this cell will show a spread.
- **`kill_while_waiting` still decides a grant after its deadline fired on the server, and grants.**
  The grant signal arrives 0.65–0.77 s into the park. With the sticky queue at 2 s the grant's workflow
  task is available to any worker 2.7 s into the park [10.7 s], but the restarted worker is not polling
  yet — Python plus Temporal plus Pydantic AI import in ~5 s — so the 5 s expiry timer fires first
  (`TIMER_FIRED` 0.4–0.9 s before the worker's next workflow-task completion in both histories). The one
  activation that sees both delivers the signal first, `wait_condition` is satisfied, and the deploy
  runs. The race is no longer the SDK default; it is worker start time against `expires_in`. By arrival
  order the grant is right; Keel judges expiry by the store's clock at drain time. Whether an approval
  that arrived on time but was processed late resolves in the human's favour is a semantic the two arms
  differ on — printed, not scored.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the framework does not do itself (the RetryPolicy is
Temporal's default), no dedup in the adapter, no key other than the documented one. The worker's argv
never changes and carries no id. The model is the workload script, selected by request content alone.
