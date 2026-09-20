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
2. The open activity's heartbeat timeout (2 s) or start-to-close timeout (5 s) expires. For a dead
   or frozen worker it is always the heartbeat: the next attempt's `ActivityTaskStarted` carries
   `last_failure = "activity Heartbeat timeout"` — every recorded retry in the ten kill and freeze
   cells of the table below (W1's T1–T4 in both variants, W5's `kill@after:tool_effect`, the composed
   re-ask cell), 300/300, 120/120 in the four `sigterm_*` cells, and 180 more in the proxy set's
   `kill@after:tool_effect`, `kill@before:tool_call` and `pause_past_ttl` cells, both variants. The
   cells that time out on start-to-close are the
   `tool_timeout` ones — EXTERNAL and IDEMPOTENT in both modes, four cells across the two sets — where
   the worker is alive and the response is withheld past 5 s. Which end withholds it differs by mode:
   the shim arms the hold at the World ("armed at the World by the shim, which knows which endpoint",
   `crashproof/faults/injectors/base.py`, §11.5), while the proxy forwards the request, lets the World
   apply and receipt it, and then says nothing (`crashproof/proxy/server.py`, its own client timeout at
   3600 s so "the SUT's timeout ends a hold, never ours"). Either way it is the activity's 5 s ceiling
   that ends the attempt: `activity StartToClose timeout` 30/30 in each, 120/120.
3. The RetryPolicy schedules attempt 2 after its 1 s initial interval; whichever worker polls the task
   queue runs it — the restarted one, spawned with the same argv.
4. A workflow task that was bound for the dead worker's sticky queue waits out
   `sticky_queue_schedule_to_start_timeout` ("How long a workflow task is allowed to sit on the sticky
   queue before it is timed out and moved to the non-sticky queue where it may be picked up by any
   worker", `temporalio.worker.Worker`, 1.33.0) and is then replayed from history on the new worker.
   **Pinned to 2 s, the heartbeat.** The arm was smoked twice at one seed before the release
   (`bench/specs/smoke_temporal.yaml`, `smoke_temporal_w5.yaml`, `smoke_temporal_w5_pre.yaml`, seed 7,
   18 trials, every one COMPLETED — a single-seed run kept for its histories, whose rows are on no
   published page): the first smoke at the SDK's 10 s default with a flat 3 s pause,
   the second with the queue pinned and §13.4's drawn pause. At the 10 s default every kill history in
   the first smoke has one `WORKFLOW_TASK_TIMED_OUT` — the workflow task waiting out the SDK default
   before any worker could replay it, on top of the detection the cell exists to measure: a Temporal
   kill cell was measuring an SDK default hiding behind the pinned detection
   timeout, which §13.4 and H6 say is what detection latency is supposed to be. It is a documented
   worker option, so pinning it is configuration, not help. Neither smoke's numbers are published —
   one seed, no row set — so nothing below is quoted from them but the histories they left.

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
included — confirmed 120/120 in the release's four `pause_past_ttl` cells (both variants in both
modes): the frozen worker is never restarted (`restarts` 0 in every trial), yet the server times its
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
| Sticky queue schedule-to-start | 2 s (SDK default 10 s) | `Worker(sticky_queue_schedule_to_start_timeout=...)`, documented; at the 10 s default a kill cell waits that timeout out before another worker can replay the stranded workflow task, and none of it is detection — see "What a restart does", step 4 |
| `pause_past_ttl` pause | seeded `pause_factor ∈ [2, 4]` × `detection_timeout_s` = the 2 s heartbeat (§13.4) | the supervisor's draw; the applied pause is on the fault row (`pause_ms`). The shim set's two cells draw 30 each: 4.04–8.00 s, median 5.49 s (EXTERNAL) and 4.31–7.98 s, median 6.36 s (IDEMPOTENT); the proxy pair's 60 are a different set of draws |

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

## Release — 30 seeds per cell, against §13.7's predictions

The v1 release run at `keel_commit 251e52d`: `bench/specs/week2_w1_shim.yaml`, `week2_w5.yaml`,
`week2_w5_pre.yaml` and `release_reask.yaml`, seeds 7–36, rows in `bench/results/v1_{w1_shim,w5,w5_pre,reask}/`
and pages `bench/reports/v1_*.md`. This arm has 36 cells there, 1080 trials, **0 void**, every one
COMPLETED, S1/S2/S3/L1/L2/C1 PASS, L1 30/30 [0.89–1.00] in every cell. No cell of this arm was
selected for the confirmation tier (§15.3, `bench/confirm/v1.yaml`), so every number here is the
30-seed screening tier; where the same page prints n = 300 it is another arm's confirmed cell. The
table is the cells §13.7's two tables name for this arm — T1–T4, the kill and freeze columns of the
first (its other two were not run in this arm: T5 `pause_past_ttl@after:tool_effect` has a cell in no
v1 set at all, and the only M1 `kill@after:model_return` cells anywhere in the release are Keel's two
W7 STREAMS ones on `bench/reports/v1_w7.md`, not a W1 cell of any arm) — and `sigterm_grace_ok`,
`sigterm_grace_too_short`, `tool_timeout`, `tool_500` and `model_500` from the second; the shim set's
other 8 (the two baselines, `model_timeout`, `provider_outage`, `tool_delay`) are on the page. Wall and
recovery latency are medians over the 30, with the cell's baseline (τ₀) and the range beside them.

| cell | applied / receipts | model calls (τ₀ 3) | restarts | wall s (τ₀) | recovery latency s | what re-dispatched | §13.7 predicted |
|---|---|---|---|---|---|---|---|
| EXTERNAL `before:tool_call` (T1) | 1 / 1 ×30 | 3 ×30 | 1 ×30 | 17.4 (7.6) | 5.7 (5.1–8.0) | attempt 2 after "activity Heartbeat timeout", 30/30 | 0 dup / +0 — **held 30/30** |
| EXTERNAL `after:tool_effect` (T2) | **2** / 2 ×30 | 3 ×30 | 1 ×30 | 17.7 (7.6) | 5.6 (4.9–6.3) | same, 30/30 | 1 / +0 — **held 30/30** (`dup_eff` 30) |
| EXTERNAL `after:tool_return` (T3) | **2** / 2 ×30 | 3 ×30 | 1 ×30 | 18.0 (7.6) | 5.7 (5.2–7.7) | same, 30/30 | 1 / +0 — **held** (H1: T2 ≡ T3, 30 = 30) |
| EXTERNAL `pause_past_ttl@before:tool_call` (T4), draws 4.04–8.00 s | **3 / 3 ×17, 2 / 2 ×13** — `dup_eff` **47** | 3 ×30 | **0** ×30 | 16.4 (7.6) | 5.6 (4.2–8.1) | the one `recoveries` entry is attempt **3** in 17 trials, 2 in 13, its `last_failure` a heartbeat timeout 30/30 | 1 dup — **held for every draw under 5.0 s; over 5.6 s it is 2** |
| IDEMPOTENT T1 | 1 / 1 ×30 | 3 ×30 | 1 ×30 | 19.2 (8.5) | 6.4 (5.3–9.6) | heartbeat timeout, 30/30 | — |
| IDEMPOTENT T2, T3 | **1 / 2** ×30 each | 3 ×30 | 1 ×30 | 17.6, 17.7 (8.5) | 5.9, 5.9 | heartbeat timeout, 60/60; both receipts carry the same `<run_id>:4` key | H3: one applied at F1 — **held 60/60** (`dup_rcpt` 30 each, `dup_eff` 0) |
| IDEMPOTENT T4, draws 4.31–7.98 s | **1 / 3 ×21, 1 / 2 ×9** — `dup_rcpt` **51**, `dup_eff` 0 | 3 ×30 | 0 ×30 | 16.4 (8.5) | 6.5 (4.4–8.1) | the one `recoveries` entry is attempt 3 in 21, attempt 2 in 9; one key on every receipt | H3 — **held 30/30** |
| `sigterm_grace_ok@after:tool_effect`, EXTERNAL / IDEMPOTENT | **2** / 2 ×30 · 1 / 2 ×30 | 3 ×30 | 1 ×30 | 17.8 (7.6), 17.3 (8.5) | 5.7 (5.1–8.3), 5.4 (5.1–6.4) | attempt 2 after a heartbeat timeout, 60/60; the latency is T2's — nothing of the 3 s grace shows in the rows | "not in the fact sheet ⇒ measured" (H8) — **measured: 1 dup at F0, `dup_rcpt` 1 and `dup_eff` 0 at F1, 30/30 each — T2 by another name** |
| `sigterm_grace_too_short@after:tool_effect`, EXTERNAL / IDEMPOTENT | **2** / 2 ×30 · 1 / 2 ×30 | 3 ×30 | 1 ×30 | 18.2 (7.6), 17.3 (8.5) | 5.9 (5.3–8.3), 5.4 (4.8–6.8) | heartbeat timeout, 60/60 | 1 dup — **held 30/30** (`dup_eff` 30 at F0; `dup_rcpt` 30, `dup_eff` 0 at F1) |
| `tool_500@after:tool_effect`, EXTERNAL / IDEMPOTENT | **2** / 2 ×30 · 1 / 2 ×30 | 3 ×30 | 0 ×30 | 10.3 (7.6), 10.4 (8.5) | 1.1 (1.1–1.2), 1.1 (1.1–1.6) | attempt 2 after `tool_500: HTTP 500`, 60/60 — the RetryPolicy's 1 s initial interval is the latency | "RetryPolicy per activity" (H9) — **retried 60/60**; the 500 answered an applied effect, so 1 dup at F0 and one applied under the key at F1 |
| `tool_timeout@before:tool_call`, EXTERNAL / IDEMPOTENT | **2** / 2 ×30 · 1 / 2 ×30 | 3 ×30 | 0 ×30 | 15.2 (7.6), 14.7 (8.5) | 0.03, 0.02 (the held request's own receipt is the first live one) | attempt 2 after `activity StartToClose timeout`, 60/60 — the one fault where the 5 s timeout, not the heartbeat, detects | "RetryPolicy per activity" (H9) — **retried 60/60**; the held request had reached the World, so 1 dup at F0, `dup_rcpt` 1 at F1 |
| `model_500@before:model_call`, EXTERNAL / IDEMPOTENT | 1 / 1 ×30 | **4** ×30 (**+1**) | 0 ×30 | 10.2 (7.6), 11.5 (8.5) | 1.7 (1.5–2.3), 1.7 (1.5–2.4) | attempt 2 after `model_500: HTTP 500`, 60/60 | "RetryPolicy" — **retried 60/60**, +1 call, 0 dup |
| W5 `approval_delay` (duplicate click) | deploy 1 ×30 | 3 ×30 | 0 ×30 | 6.9 (6.6) | 0.19 (0.17–0.30), grant → deploy | the second click is on every fault row (`duplicate: true`) and deployed nothing | H7: 1 — **held 30/30** |
| W5 `kill_while_waiting` | deploy 1 ×30 | 3 ×30 | 1 ×30 | 11.9 (6.6) | 5.0 (4.3–5.6), kill → deploy | no activity retried (`recoveries` empty 30/30): the grant's workflow task re-ran on the restarted worker | H7: 1 / +0 — **held 30/30** |
| W5 `approval_expiry` | deploy 0 ×30 | 2 ×30 | 0 ×30 | 10.8 (6.6) | — | the 5 s timer fired: `not done: approval expired`, 30/30 | nothing deployed, COMPLETED — **30/30** |
| W5 `kill@after:tool_effect` | deploy **2** ×30 | 3 ×30 | 1 ×30 | 13.3 (6.6) | 4.1 (3.9–4.9) | heartbeat timeout, 30/30 | T2 behind a gate: 1 dup — **30/30** |
| W5-pre `approval_delay`, `kill_while_waiting` | notify **1**, deploy 1 ×30 each | 3 ×30 | 0, 1 ×30 | 9.0, 11.5 (8.8) | 0.19, 4.6 | the continuation skips the `notify` that already ran, 60/60 | tier-2 H7 predicts 2 only for pre-interrupt re-run; Pydantic AI's deferred-tool continuation does not re-run — **1, like Keel, 60/60** |
| re-ask: `kill@after:tool_effect` + `model_reask_alternate@before:model_call` (`v1_reask`) | **2** / 2 ×30 — `dup_eff` 30 | 3 ×30 (**+0**) | 1 ×30 | 12.0 (6.0) | — (a composed cell's later trigger is the modifier's; not computed) | heartbeat timeout, 30/30; the modifier armed (`executed: true`) 30/30 and was never served: no model request was re-asked | H10: a memoizing arm is invisible to the alternate — **held 30/30**: the answer is the baseline's in 30/30, the duplicate is T2's |

Three things the rows say that the prediction table does not:

- **Detection is the heartbeat, every time** — `last_failure` is "activity Heartbeat timeout" on every
  recorded retry in the kill and freeze cells above, 300/300 — one `recoveries` entry per trial, and in
  the two `pause_past_ttl` cells that entry is attempt 3 in 38 of the 60, so the attempts it superseded
  carry no `last_failure` on any row — and in the four `sigterm_*` cells, 120/120; start-to-close fires only in
  `tool_timeout`. At 30 seeds `recovery_latency_ms` (fault → first live receipt) is
  5.6–5.7 s median for the EXTERNAL W1 kills and 5.9–6.4 s for the IDEMPOTENT ones (4.9–9.6 s over the
  180 trials), the supervisor respawns the worker 0.10–0.13 s after the kill (medians), and kill-cell wall
  medians are 17.4–19.2 s against 7.6 / 8.5 s baselines. The engine's own timers put a floor under a
  recovery — the 2 s heartbeat timeout plus the RetryPolicy's 1 s initial interval — but a soft one:
  the timeout runs from the last beat, and the SDK's `0.8 ×` throttle can have sent that up to 1.6 s
  before the fault. The fastest of these 180 is 4.9 s; W5's `kill@after:tool_effect` row above, the
  same trigger on another workload, reaches 3.9 s. Above that floor the rows measure only that respawn
  and the first live step (`time_to_first_live_step_ms`, 5.5–6.3 s median); nothing on a row measures
  the worker's start, and wall time is never scored.
- **The zombie count grows with the pause.** §13.7 predicts one duplicate: the timed-out attempt
  completes after the thaw and the retry fires too. That is what every draw under 5.0 s did (15 of the
  60 T4 trials: one extra attempt — `dup_eff` 1 in the 8 EXTERNAL, `dup_rcpt` 1 and `dup_eff` 0 in
  the 7 IDEMPOTENT). A draw over 5.6 s spans more than one heartbeat-plus-backoff cycle, and the
  attempt that completed is attempt 3: attempt 1 and attempt 2 both timed out while the worker was
  frozen, and after the thaw the worker sent three requests (33 of 60: two extra attempts — `dup_eff`
  2 in the 14 EXTERNAL, `dup_rcpt` 2 in the 19 IDEMPOTENT). The 12 draws between 5.0 and 5.6 s went
  either way (one extra attempt : two — EXTERNAL 5 : 3, IDEMPOTENT 2 : 2).
  History records only the attempt that closed, so which frozen attempts reached the worker is
  inferred from the receipts, not read from Temporal. Summed over the 30 seeds that is **47 duplicate
  effects** at F0 on `dedup: false`, within `at_least_once`; at F1 it is **51 duplicate receipts and 0
  duplicate effects**, because every receipt carries one key and the receiver applies once. The
  duplicate count at T4 is a function of `pause / (heartbeat + backoff)` — the reason §13.4 draws the
  pause rather than fixing it, and the reason the cell is a spread and not a number: one extra attempt
  in 13 of the 30 EXTERNAL trials and two in 17, one in 9 of the IDEMPOTENT and two in 21.
- **`kill_while_waiting` deploys 60/60, and in the smoke histories the grant was decided after its
  deadline fired on the server.** In the pinned smoke the grant signal arrived 0.65–0.77 s into the park.
  With the sticky queue at 2 s the grant's workflow task is available to any worker 2.7 s into the park,
  and the restarted worker reaches it later still: in both of the pinned smoke's `kill_while_waiting`
  histories, W5 and W5-pre, `TIMER_FIRED` lands 0.4–0.9 s before that worker's next workflow-task
  completion, so the 5 s expiry timer won. What the worker spends those seconds on is not measured
  here, and no published row times it. The one
  activation that sees both delivers the signal first,
  `wait_condition` is satisfied, and the deploy runs. At 30 seeds the deploy landed 4.3–5.6 s after the
  kill (W5) and 4.2–5.4 s (W5-pre), the worker respawned 0.48 s after it (median), nothing was retried
  (`recoveries` empty 60/60), and it deployed 60/60. Whether the timer fired before the grant was
  decided in those 60 is not on a row — a row carries no history — so the ordering above is the
  pinned smoke's two histories, not the release's. By arrival order the grant is right; Keel judges expiry
  by the store's clock at drain time. Whether an approval
  that arrived on time but was processed late resolves in the human's favour is a semantic the two arms
  differ on — printed, not scored.

The proxy-mode twin is `bench/results/v1_w1_proxy/` (this arm's 18 cells there, 540 trials, 0 void). `crashproof agree`
over the two sets (`bench/reports/agreement_v1.md`) pairs 14 of this arm's cells — the baseline, the
three kills, `pause_past_ttl`, `tool_500` and `tool_timeout`, each in both variants; `tool_dropped_response`
and `tool_malformed` have no shim twin, and `tool_delay`, the three model faults and the two `sigterm_*`
cells no proxy one — and 10 of the 14 agree. The 4 that do not are instrument findings, not runtime
ones. `kill@after:tool_return` ×2 (`dup_eff` 30 / 0 EXTERNAL, `dup_rcpt` 30 / 0 IDEMPOTENT): the
proxy's kill is a `taskkill` from outside the process and lands later than the shim's `os._exit`
inside the parse — in these rows late enough that nothing was retried: no tool-call activity was retried
in 60/60
(`recoveries` empty in 29/30 EXTERNAL and 30/30 IDEMPOTENT; the one retry was the next model-request
activity, after a heartbeat timeout), 12 of the 60 workers were never restarted at all (`restarts` 0 in
3 EXTERNAL and 9 IDEMPOTENT trials), the trial ended 0.6–1.7 s after the kill in 59/60 (8.3 s in the one
that retried), and wall is the baseline's (7.3 s against 7.0 s EXTERNAL, 7.0 against 6.9 IDEMPOTENT).
*Late enough that nothing was retried* is an inference from those times, not something a row records:
a workflow task stranded on the dead worker would have cost the 2 s sticky timeout plus a worker start,
and 59 of the 60 trials ended sooner than that.
That is the agreement page's own reading of the window: a kill from the edge lands "often after the
parse, sometimes after the run has finished, which is what a proxy cell with fewer restarts than its
shim twin shows". `pause_past_ttl` ×2 (`dup_eff` 47 / 50 EXTERNAL, `dup_rcpt` 51 / 50 IDEMPOTENT):
the proxy's draws sum to 50 duplicates at F0 and 50 duplicate receipts at F1 — one extra attempt in 10
of the 30 trials and two in 20, in each variant, against the shim's 13 and 17 (EXTERNAL) and 9 and 21
(IDEMPOTENT) above: the same spread from a different set of draws, not a different mechanism.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the framework does not do itself (the RetryPolicy is
Temporal's default), no dedup in the adapter, no key other than the documented one. The worker's argv
never changes and carries no id. The model is the workload script, selected by request content alone.
