# Adapter: DBOS

The same workload, the same World, the same shim, the same spec file — expressed in DBOS's
documented primitives and nothing else, twice: once as DBOS code written directly, once as a
Pydantic AI agent under Pydantic AI's DBOS integration.

Source: [`crashproof/adapters/dbos.py`](../../crashproof/adapters/dbos.py). Versions under test:
`dbos 2.31.1`, `pydantic-ai-slim 2.43.0` (both pinned in every row's `config_pin`). Quotes below are
from the pages named, fetched against those versions, or from the installed package where it says so.

## Declarations

| | |
|---|---|
| `recovery_mechanism` | **`self`** — the restarted process runs `DBOS.launch()` and DBOS's own PENDING scan resumes the run |
| `key_sources` | `none` (F0) and `framework` (F1), per variant |
| `claims` | PURE `at_least_once` · IDEMPOTENT `effectively_once` · EXTERNAL `at_least_once` |
| Per-trial dependency | a DBOS system database on the harness Postgres, cloned from a template migrated by `dbos migrate`'s own code (`dbos.cli.migration.run_dbos_database_migrations`), dropped at the end of the trial |
| Durable unit | one `@DBOS.step` per model call and per tool call |
| `worker_count` | 1 — no Conductor, so no successor (§13.4) |
| Configs | `agent_code ∈ {native, pydantic_ai}` (§13.5) |

**Cell naming.** The config id *is* the `agent_code`, the way LangGraph's is its `durability`:
`dbos.native.<variant>.<trigger>` and `dbos.pydantic_ai.<variant>.<trigger>`. The matrix entry is
`{id: native, agent_code: native}` / `{id: pydantic_ai, agent_code: pydantic_ai}`, and the adapter
takes `agent_code` as its one argument. DBOS is the one runtime with two rows because a native adapter
is cheap and the pair isolates the integration layer from the engine: **a difference between the
two rows is a finding about Pydantic AI, not about DBOS** (§13.5).

**Claims.** From [the workflow tutorial](https://docs.dbos.dev/python/tutorials/workflow-tutorial):

> Steps are tried *at least once* but are never re-executed after they complete.

That is the PURE and EXTERNAL claim as written. IDEMPOTENT claims `effectively_once` on the F1
argument of §13.6 — a key DBOS itself persists and restores, presented to a receiver that dedups on
it — and nothing more: the receiver does the deduplicating, not DBOS. `exactly_once` is DBOS's claim
for `@DBOS.transaction` ("Transactions commit *exactly once*"), which only W4's TRANSACTIONAL class
could exercise; W4 is cut (§29.1), so the adapter declares nothing for that class.

## `key_source` formula

```
effect_key = f"{DBOS.workflow_id}:{DBOS.step_id}"      read inside the step that sends the effect
```

From [the contexts reference](https://docs.dbos.dev/python/reference/contexts):

> `step_id`: Return the step ID for the currently executing step. This is a unique identifier of the
> current step within the workflow.

and from [the workflow tutorial](https://docs.dbos.dev/python/tutorials/workflow-tutorial), the
determinism rule that makes it stable across a recovery — a workflow must "invoke the same steps with
the same inputs in the same order". The workflow id is chosen once, as a pure function of the trial
directory (`crashproof-<trial dir name>`), and persisted by DBOS with the run; the step id is assigned
by DBOS in program order. Both are persisted **and restored by DBOS's own recovery**, which is what
F1 requires and what LangGraph's `thread_id` lacks. It is sent only when the variant asks for
`framework` and the class is IDEMPOTENT (W1's IDEMPOTENT band); the EXTERNAL band and both W5 forms
send none, and their rows say `none`.

**The Pydantic AI row is F1 too, and for a documented reason.** Pydantic AI's DBOS integration does
not wrap function tools
([pydantic.dev, DBOS integration](https://pydantic.dev/docs/ai/integrations/durable_execution/dbos/)):

> Custom tool functions and event stream handlers registered on the agent directly or through another
> capability are **not automatically wrapped** by DBOS.
>
> Decorate with `@DBOS.step` if the function involves non-determinism or I/O.

(the installed package says the same in `pydantic_ai/durable_exec/_spec.py`: "DBOS omits
`'function'` (function tools run inline via `@DBOS.step`)"). So each workload tool is a function tool
whose body is a `@DBOS.step`, exactly as documented — and inside a DBOS step `DBOS.step_id` is the same
documented identity as in the native row. Model requests are the capability's own steps: "the
capability routes model requests and MCP communication through DBOS steps."

## What a restart does

The first incarnation (`recovery_index == 0`) calls `DBOS.launch()` and starts the workflow under
`SetWorkflowID(crashproof-<trial>)`. Every later incarnation calls `DBOS.launch()` and nothing else —
no start, no nudge, no id on the command line; `worker_argv` is `python -m crashproof.adapters.dbos`
every time. From [workflow recovery](https://docs.dbos.dev/production/workflow-recovery):

> each time you restart your application's process, DBOS recovers all workflows that were executing
> before the restart (all `PENDING` workflows).

The recovered workflow function re-executes from the top; every completed step returns its
checkpointed output without running, and the step in flight at the kill — which had no checkpoint —
runs again. Nobody notices while the process is down: detection *is* the restart, so the recovery
latency column is process start + imports + launch + DBOS's internal-queue dequeue.

`on_worker_restart` is a no-op. DBOS documents that a workflow id started twice "executes only
once", so re-starting the run on every incarnation would have been harmless to the World — and it
would have been the adapter telling the runtime which run to resume, which is `harness`, not `self`.

## Pins

`retries_allowed=False` on every step, stated explicitly (it is also DBOS's default): the adapter
adds no retry (§13.3 rule 1) and DBOS is not asked for one. `max_recovery_attempts = 100` on the
workflow, DBOS's default passed explicitly; [the decorators reference](https://docs.dbos.dev/python/reference/decorators)
says a workflow over it "is set to `MAX_RECOVERY_ATTEMPTS_EXCEEDED` and it may no longer be executed",
so it must be ≥ `max_recoveries` (§22.3) or DBOS would dead-letter a run the supervisor is still
restarting; `worker_count` refuses a spec above it. No step timeout (a hung call ends at the World
client's 5 s socket timeout, as in LangGraph); executor id `local`, no Conductor; application
version = DBOS's default hash of the workflow source. For `pydantic_ai`: the capability's defaults,
`parallel_execution_mode='parallel_ordered_events'` and an empty `model_step_config`.

## W5 — the human in the loop

**The wait is `DBOS.recv`**, not `set_event`/`get_event`: `recv` is the primitive that consumes a
message sent *to* the workflow, which is what a decision is. From
[workflow communication](https://docs.dbos.dev/python/tutorials/workflow-communication):

> Each call to `recv()` waits for and consumes the next message to arrive in the queue for the
> specified topic, returning `None` if the wait times out.
>
> All messages are persisted to the database, so if `send` completes successfully, the destination
> workflow is guaranteed to be able to `recv` it.

The timeout is the run input's `expires_in` (5 s), so `approval_expiry` resolves the way Keel's does:
`recv` returns `None` and the run completes `not done: approval expired` with nothing deployed. The
deadline survives a kill: at 2.31.1 `recv` checkpoints its timeout as a `DBOS.sleep` step when the
wait begins (visible in every W5 trial's `sut/steps.json`). While it waits, the workflow stays live
in the worker process — the fact sheet's "holds a worker thread", §13.7 H7 — rather than being
released and re-driven.

**The human is `DBOSClient.send`** ("You can also call `send` from outside of your DBOS application
with the DBOS Client") on topic `approval`, from the harness process. **§11.4 C's duplicate click is
the same `send` again, with no idempotency key.** DBOS persists a second message; the workflow
`recv`s once and never asks again, so the second message is never consumed and grants nothing.

**Native:** the model step returns the node's decision; `before_approval` calls (W5-pre) run as
their own tool steps; then `recv`; then the gated tool step.

**Pydantic AI:** approval is a property of a *tool* there, so the workload's gated tool is registered
`requires_approval=True` ("Whether this tool requires human-in-the-loop approval"). The scripted model
answers the gated node with one response holding the pre-approval calls and the gated call; the
framework runs the ungated ones and ends the run with `DeferredToolRequests` ("Tool calls that require
approval or external execution … Results can be passed to the next agent run using a
`DeferredToolResults` object with the same tool call IDs"). The workflow then `recv`s, and a granted
decision resumes with `agent.run(message_history=…, deferred_tool_results=DeferredToolResults(approvals=…))`
— the documented deferred-tools loop, with DBOS's wait in the middle. Pydantic AI skips a call whose
return is already in the history, so `notify` is not re-run by the resume.

**Status.** DBOS's own workflow status (`DBOSClient.list_workflows`) decides every terminal state:
`SUCCESS → COMPLETED`, `ERROR → FAILED`, `CANCELLED → CANCELLED`, `MAX_RECOVERY_ATTEMPTS_EXCEEDED →
FAILED`. There is no documented query for "this PENDING workflow is parked in `recv`", so `WAITING`
comes from a marker the workflow writes to `sut/status` immediately before and after the wait — the
same channel the LangGraph worker uses. It is a file write in workflow code, so recovery repeats it;
it adds no durable operation to the run.

## N/A, named

| Invariant | Why |
|---|---|
| **S2** | *Measured.* `committed_effects` is read from `list_workflow_steps`: a step DBOS checkpointed as complete has the World's response as its recorded output, and that response names its own label (`external_ref`). Read, never counted. |
| **S4** | N/A — DBOS writes a step's record only when it completes (`started_at_epoch_ms` arrives with the output), so there is no per-attempt STARTED before the effect to order against a receipt. |
| **S5**, **S7** | N/A — no journal of step-state transitions or of APPROVAL_REQUESTED/DECIDED to bind an effect to. The W5 rows still print the gated `deploy.service` count raw, which is what H7 is about. |
| **C1** | N/A — `replay_check` is not implemented: DBOS documents no replay that re-checks a recorded run without re-executing it (`fork_workflow` re-runs steps from a point; it is not a verifier). |
| **W4** | not declared — TRANSACTIONAL (`@DBOS.transaction`) is expressible, but W4 is cut (§29.1). |
| **W6** | not declared — a DBOS child-workflow citation is not in the fact sheet (§14.1). |

## Places a documented primitive forced a choice

1. **Who starts the run.** The worker's first incarnation, not the harness: `DBOSClient.enqueue` could
   start it from outside, but only through a queue the worker listens on, which would add a queue's
   dequeue semantics to every trial. The id is a pure function of the trial directory either way.
2. **`WAITING`** is a marker file, for want of a documented "parked in `recv`" query (above).
3. **The Pydantic AI gate is per tool**, derived from the workload's gated tools, because
   `requires_approval` is a tool property while the script puts `approval:` on a node. The two are the
   same set in W5 and W5-pre: the gated tool is only ever called from the gated node.
4. **A rejected or expired approval ends the run without resuming the agent** in the Pydantic AI row,
   as it does in every other arm. The documented alternative — `ToolDenied` — would hand the model a
   denial the script has no node for.
5. **Pydantic AI tools are `Tool.from_schema` with an open object schema**, so the script's arguments
   reach the step exactly as the other arms send them; the scripted model's `tool_call_id` is
   `<node>:<index>`, a pure function of the node (§13.2), never a counter. None of it is DBOS code: the
   agent is `crashproof/adapters/pydantic_ai_agent.py`, shared with the Temporal arm, and this row
   supplies only the `{workflow_id}:{step_id}` key, `@DBOS.step` around each tool, and `DBOSDurability`
   (`tests/unit/test_pydantic_ai_agent.py` pins that both arms answer a history identically).
6. **The template is migrated by `dbos migrate`'s implementation**, called in-process, rather than by
   launching a DBOS app in the harness: `DBOS` is a process-wide singleton, and the harness must not
   register the workload's workflows.

## 1-seed smoke (not a published matrix)

`bench/specs/smoke_dbos.yaml`, `smoke_dbos_w5.yaml`, `smoke_dbos_w5_pre.yaml`, seed 7, both rows. Every
trial valid, COMPLETED, restarts as scheduled, every judged verdict PASS, `+calls` 0 everywhere.

| cell | native | pydantic_ai | §13.7 |
|---|---|---|---|
| W1 EXTERNAL T1 `before:tool_call` | 1 applied, 0 dup | 1 applied, 0 dup | 0 / +0 — held |
| W1 EXTERNAL T2 `after:tool_effect` | **2 applied, 1 dup** | **2 applied, 1 dup** | 1 / +0 — held |
| W1 EXTERNAL T3 `after:tool_return` | 2 applied, 1 dup | **1 applied, 0 dup** | 1 / +0 — held native, **not** pydantic_ai (see below) |
| W1 IDEMPOTENT (F1) T1 / T2 / T3 | applied 1; receipts 1 / 2 / 2 | applied 1; receipts 1 / 2 / 2 | H3: applied 1 at F1 — held |
| W5 `approval_delay` + duplicate click | deploy 1 | deploy 1 | H7 — held; the second message grants nothing |
| W5 `kill_while_waiting` | deploy 1, 3 model calls | deploy 1, 3 model calls | H7: one for DBOS — held, and no re-ask |
| W5 `approval_expiry` | `not done: approval expired`, nothing deployed | same | expires by `recv` timeout |
| W5 `kill@after:tool_effect` | deploy 2 | deploy 2 | at-least-once past the gate |
| W5-pre `approval_delay` / `kill_while_waiting` | notify 1, deploy 1 | notify 1, deploy 1 | memoized pre-wait step: no re-fire |

**T3 is a race in this arm, not a window.** The shim's `after:tool_return` kill is `call_soon`'d; DBOS
records an async step's output with `await asyncio.to_thread(...)`, which starts the checkpoint write
on an executor thread *before* the loop runs the kill. So the kill's fsync-then-exit on the loop
thread races DBOS's commit on another thread. In the pydantic_ai EXTERNAL trial the commit won
(`completed_at_epoch_ms` …529458 against the fault row's …529.4617) and nothing re-fired; in the other
three T3 trials the kill won. H1 (T2 ≡ T3) therefore holds only as often as the kill wins, and 30
seeds are what will say how often; one seed says it is not always.

Recovery latency (kill → first live step): ≈3.5–4.1 s native, ≈5.2–6.3 s pydantic_ai. The difference
is importing Pydantic AI in the restarted process — a finding about the integration layer, as §13.5
says the pair exists to show.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry (DBOS's are off), no dedup in the adapter, no key the
framework does not hand over. The worker is restarted verbatim and never told which run to resume.
Both rows share one World client, one shim and one script; they differ only in whether the loop is
written against DBOS or against Pydantic AI.
