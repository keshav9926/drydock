# Adapter: Restate (`agent_code = pydantic_ai`)

The same workload, the same World, the same shim, the same spec file — written once as a Pydantic AI
`Agent` and made durable by **`RestateAgent`, which is a wrapper in Restate's SDK
(`restate.ext.pydantic`), not a pydantic-ai capability**. That is the caveat §13.5 attaches to every
Restate cell, and it is printed here first because it is the one way this arm is not built like the
Temporal and DBOS `pydantic_ai` rows: those attach a capability to the agent; this one wraps the
finished agent (`class RestateAgent(WrapperAgent)`, restate-sdk 1.0.5) and the tools do their own
`ctx.run`.

Source: [`crashproof/adapters/restate.py`](../../crashproof/adapters/restate.py).

Versions under test: `restate-sdk 1.0.5`, `restate-server 1.7.10` (the Linux binary, not the docker
image), `pydantic-ai-slim 2.43.0`, `hypercorn 0.18.0`, Python 3.13. Every one of them is in `config_pin`
on every row, beside `platform`.

**Platform.** `restate-sdk` ships no Windows wheel and `restate-server` is a Linux binary, so this arm
runs the whole harness under WSL2 (Ubuntu 24.04), with trial directories on the Linux filesystem. Every
other arm's published rows come from Windows; this arm's rows say `platform: linux (WSL2)`. A matrix
that puts them side by side is comparing two hosts as well as two runtimes, and a latency difference
between them is not a runtime finding until both are measured on one host.

**Packaging.** `restate.ext.pydantic` imports `pydantic_ai.mcp` unconditionally, which raises without
the MCP client, and `pydantic_ai.mcp` 2.43 imports `httpx`, which `pydantic-ai-slim[mcp]` no longer
brings. Neither `restate-sdk[pydantic-ai]` nor `pydantic-ai-slim[mcp]` asks for what the import needs, so
the `restate` extra names `pydantic-ai-slim[mcp]` and `httpx` itself.

## Cell naming

The adapter is `restate`; its one config is `pydantic_ai`. Cells read
`restate.pydantic_ai.<variant>.<trigger>` — the same `runtime.config` shape as `temporal.pydantic_ai`.
`agent_code: native` is refused at construction: §22.3 and §27 stage Restate only as
`pydantic_ai/restate`.

## Declarations

| | |
|---|---|
| `recovery_mechanism` | **`engine`** — restate-server re-invokes the endpoint it registered; the restarted worker is told nothing |
| `key_sources` | `none` (F0) and `framework` (F1) |
| `claims` | PURE `exactly_once` · IDEMPOTENT `exactly_once` · EXTERNAL `exactly_once` — Restate's documentation, as written (below) |
| Per-trial dependency | `restate-server` with `RESTATE_BASE_DIR=<trial>/sut/restate-data` on free loopback ports, never killed during the trial, data dir wiped at teardown (§22.3) |
| SUT process | the ASGI app, `hypercorn.asyncio.serve(restate.app([workflow]), config)` on `127.0.0.1:<port fixed for the trial>` — the form pydantic.dev's Restate page serves it in |
| Durable unit | one `ctx.run` per model request (`RestateAgent`'s, named `Model call`) and per tool call (the tool's own `restate_context().run_typed`, named after the tool) |
| Workflow | `restate.Workflow("crashproof")`, key `crashproof-<trial dir name>`, one `run` handler |
| `worker_count` | 1 — the server is the successor |

**Claims.** Restate's AI documentation does not qualify its side-effect guarantee, so the adapter
declares it as written and the harness judges it (§8: Restate's "exactly-once semantics without
requiring idempotency keys" holds for journaled results, not for the effect-vs-journal crash window, and
"Crashproof reports the raw `world_applied` counts and judges the claim"):

> Tool side effects are not duplicated (no double bookings, no duplicate emails)
> — [docs.restate.dev/ai/patterns/durable-agents](https://docs.restate.dev/ai/patterns/durable-agents), "How durable execution works"

> Use `restate_context()` actions inside tools to make their execution durable. The result is persisted
> and retried until it succeeds. Side effects won't be duplicated on recovery.
> — [pydantic.dev/docs/ai/integrations/durable_execution/restate](https://pydantic.dev/docs/ai/integrations/durable_execution/restate/)

> Tool executions in `ctx.run()`: Side effects are executed exactly once. On recovery, the result is replayed.
> — [docs.restate.dev/ai/patterns/durable-agents](https://docs.restate.dev/ai/patterns/durable-agents) (the Restate-SDK tabs)

The fact sheet's reading (Appendix B, Restate) is the one the matrix tests: "The docs do not state
what happens if the process dies after the ctx.run action executed but before the result was journaled;
by the architecture the action re-runs (at-least-once)". So `exactly_once` is not a concession to Restate
and not a trap for it: it is the sentence on the page, and every S1 verdict below is that sentence
checked against the World. The raw `duplicate_effects` is printed either way.

**The agent** is not written here. It is
[`crashproof/adapters/pydantic_ai_agent.py`](../../crashproof/adapters/pydantic_ai_agent.py), the one
Pydantic AI agent every engine arm runs, built with no capability (`durability=None` — the seam's
engine-neutral way of saying "this integration wraps") and then wrapped:
`RestateAgent(pydantic_ai_agent.build_agent(..., wrap=_durable_tool, key=..., durability=None))`.
Restate supplies its key, its tool wrapping and the wrapper; nothing else differs.
`tests/unit/test_pydantic_ai_agent.py` pins that the Restate agent's model answers every checked history
exactly as the bare shared agent does (the wrapper's `Model call` run records what that model returns),
and `tests/unit/test_restate_adapter.py` runs every declared workload through the wrapped agent
in-process as its script.

**Tools** are wrapped the way both documentation pages write them — the work inside
`restate_context().run_typed(name, action)` — rather than with `RestateAgent(auto_wrap_tools=True)`,
because the F1 key has to be drawn in handler code before the run (next section) and `auto_wrap_tools`
leaves no handler code between the tool call and its run.

## `key_source` formula

```
key = str(restate_context().uuid())         drawn in the tool, immediately before its run
await restate_context().run_typed(tool_name, action)     action sends Idempotency-Key: key
```

[Durable steps](https://docs.restate.dev/develop/python/journaling-results): *"to generate stable UUIDs
for things like idempotency keys: `my_uuid = ctx.uuid()`"*, and the helpers are *"seeded by the
invocation ID — so they return the **same result on retries**"*;
[actions](https://docs.restate.dev/foundations/actions): `# Idempotency key generation` / `id = ctx.uuid()`.

The SDK source says what "stable" is a function of. `ServerInvocationContext.uuid()` is
`UUID(int=self.random_instance.getrandbits(128), version=4)` over `Random(invocation.random_seed)`
(restate-sdk 1.0.5, `server_context.py`), and a new context — a new `Random` — is built for every attempt.
So the key is the *n*-th draw of an invocation-seeded generator, and it is the same on the next attempt
only if the handler makes the same draws in the same order before it. Handler code between runs is
re-executed on every attempt, and run bodies are not ("inside `ctx.run`, you cannot use the Restate
context"): a draw inside a run would be skipped when that run is replayed and every later key would
shift. That is why the draw is in the tool, before the run — the documented placement, and the one
where replay repeats it. `tests/unit/test_restate_adapter.py` checks no draw ever happens inside a run.
The §13.4 phrase "deterministic per journal position" is this, read from the source.

| Variant | Endpoint | `dedup` | Key sent | Level |
|---|---|---|---|---|
| EXTERNAL | `issues.create` | `false` | none | **F0** |
| IDEMPOTENT | `issues.upsert` | `true, natural: true` | `Idempotency-Key: <ctx.uuid()>` | **F1** |

## What a restart does

Nothing, from the worker's side, and that is the point of `engine`.

1. **The invocation starts once, from the adapter.** `submit` waits for the worker's port, registers
   it (`POST /deployments {"uri": "http://127.0.0.1:<port>"}` on the admin API — the SDK's own test
   harness does the same), and sends the run (`POST /crashproof/<key>/run/send` on the ingress). The
   worker never starts, names or nudges anything, and `worker_argv` is
   `python -m crashproof.adapters.restate` every time (§13.3 rules 2, 3). `on_worker_restart` is a no-op.
2. **A kill is connection loss.** Restate records it in the invocation's journal events —
   `stream closed because of a broken pipe` (RT0010) — and retries per the pinned policy against the
   same endpoint: `h2 pool connection error: Connection refused` while the worker restarts, then a new
   attempt with the journal attached. Completed runs replay; the run in flight at the kill re-executes.
   The restarted worker comes back on the same registered port because the port is in its env, which
   is identical on every spawn.
3. **A freeze is noticed only by the two timeouts.** The fact sheet: *"Worker death is observed as
   connection loss (immediate) or, for a stalled handler, by the inactivity timeout ... followed by the
   abort timeout"*. [Error handling](https://docs.restate.dev/guides/error-handling): *"When the Restate
   Server does not receive a next journal entry from a running handler within the inactivity timeout, it
   will ask the handler to suspend"*, and the abort timeout *"is started after the 'inactivity timeout'
   has expired ... Once the timer expires, it will abort the service/handler invocation."* A
   `SIGSTOP`ped process cannot suspend, so it is abandoned at inactivity + abort — journal event
   `the invocation stream was closed after the 'abort timeout' (5s) fired` (RT0001) — and the retry
   goes to the one registered endpoint, which is the frozen process itself.

## Pins

| Pin | Value | Why |
|---|---|---|
| `inactivity_timeout` | 2 s (default 1 min) | §13.4. On the `Workflow`, so it travels in the discovery manifest |
| `abort_timeout` | 5 s (default 10 min) | §13.4 |
| **Detection timeout** (`detection_timeout_s`) | **7 s = inactivity + abort** | the time after which a frozen handler is abandoned and its invocation retried, from the two sentences quoted above. Not the inactivity timeout alone: that only *asks* a handler to suspend, which a frozen one cannot do |
| `pause_past_ttl` pause | seeded `pause_factor ∈ [2, 4]` × 7 s = 14–28 s (§13.4) | the supervisor's draw; the applied pause is on the fault row (`pause_ms`) |
| `InvocationRetryPolicy` | `initial_interval=50ms, exponentiation_factor=2.0, max_interval=60s, max_attempts=70, on_max_attempts=pause` | Restate's documented default ([service configuration](https://docs.restate.dev/services/configuration), "Default"), spelled out. 70 attempts at a 60 s cap cannot be spent inside a 60 s trial, so the invocation cannot pause before `max_recoveries` (§13.4). A `paused` invocation would read FAILED |
| `ctx.run` retries | `RunOptions()` default — the invocation policy | "If any of the other retry related fields is specified, the default for this field is 50 milliseconds, otherwise restate will fallback to the overall invocation retry policy" (`RunOptions.initial_retry_interval`, 1.0.5); none is specified, by `RestateAgent` or by the tools |
| Journal retention | 1 day (the documented default, spelled out) | collection reads the journal after completion |
| Server env | `RESTATE_LISTEN_MODE=tcp`, `RESTATE_DISABLE_TELEMETRY=true`, `RESTATE_{BOOTSTRAP,DEFAULT}_NUM_PARTITIONS=1`, `RESTATE_ROCKSDB_TOTAL_MEMORY_SIZE=32 MB` | no semantics; partitions and RocksDB memory are the values `restate.harness.RestateContainer` (1.0.5) runs the server with |
| Protocol | the SDK's default, deduced at discovery (h2c to hypercorn) | an idle handler stayed open until the inactivity timeout asked it to suspend — streaming behaviour, and why a park shows 2 s late (W5 below) |
| Client-side retries | none | the provider is a `FunctionModel` with no HTTP client, and the World client never retries |

## W5 — the human in the loop

**The gate** is Pydantic AI's, as in every `pydantic_ai` row: a gated tool is `requires_approval=True`,
the run ends in `DeferredToolRequests`, and the continuation is `agent.run(message_history=...,
deferred_tool_results=DeferredToolResults(approvals={id: True}))`, which skips any call that already has
a return in the history (W5-pre's `notify`).

**The wait** is Restate's documented external-event pattern, from
[signals and external events](https://docs.restate.dev/develop/python/external-events) and
[durable timers](https://docs.restate.dev/develop/python/durable-timers):

```python
awakeable_id, decision = ctx.awakeable(type_hint=dict)
await ctx.run_typed("request approval", hand_to_reviewer, sut_dir=..., awakeable_id=awakeable_id)
match await restate.select(decision=decision, expired=ctx.sleep(timedelta(seconds=expires_in))):
```

— `id, promise = ctx.awakeable(...)`, `await ctx.run_typed("trigger task", request_human_review, ...)`,
`review = await promise` in the docs; the timeout because "For long waits, combine the primitive with a
durable timer to implement a timeout", with `restate.select` against `ctx.sleep` as the durable-timers
page writes it. `hand_to_reviewer` writes the id to `<trial>/sut/awakeable`: the reviewer is the harness,
and a run is where the docs hand the id over. **Expiry is a durable timer** from the run input's
`expires_in` (5 s): when it wins, the run returns `not done: approval expired` and nothing is deployed.

**Status.** `status()` is `sys_invocation.status` through the admin SQL API (`POST /query`), with no
worker involved: `completed` → COMPLETED/FAILED by `completion_result`, `suspended` → WAITING,
`paused` → FAILED, anything else RUNNING. `suspended` is *"waiting on some external input (e.g.
request-response call, awakeable, sleep, ...)"* ([introspection](https://docs.restate.dev/operate/introspection)),
and the only thing this workflow waits on is the approval. Over a bidirectional stream the server asks an
idle handler to suspend when the inactivity timeout runs out, so the park is visible — and
`kill_while_waiting` fires — 2 s after the handler starts waiting, not at once.

**The human, and the duplicate click.** `approve()` sends `POST /restate/awakeables/{id}/resolve` with
`{"decision": "granted", "by": "harness"}` on the ingress — the documented HTTP resolution — and writes
every response to `sut/clicks.jsonl`. §11.4 C's second, unkeyed click is the same request again.
**What Restate does with it:** both requests are answered `202 Accepted`, and the journal gets **two**
`Notification: Signal` entries for the same awakeable (`{"Index": 17}`) with the same payload. An
awakeable is "resolved or rejected once" — the handler's future takes the first and the second reaches
nothing: one deploy. Nothing in the HTTP answer tells the second clicker the approval was already
decided.

## What is N/A, and why

| Invariant | Verdict | Reason |
|---|---|---|
| S2 | **judged** | `committed_effects` is read from Restate's own journal (`sys_journal` through the admin SQL API): every `Notification: Run` whose `Command: Run` — joined on `completion_id` — is named after a non-PURE tool, and whose `Success` value names a World label (`external_ref`). A run's completion notification is the engine's record that its result was journaled. No counter is added. (`entry_json` is "The entry serialized as a JSON string. Filled only if journal version is 2"; 1.7.10 enables journal v2) |
| S4 | N/A | The verifier reads a Keel-shaped journal (`STEP_ATTEMPT_STARTED` per attempt, with timestamps). Restate does journal a run's `Command: Run` before its action executes — in every smoke journal the tool's command is appended before its first World receipt, which is the journal-before-effect §2 credits Restate with — but once per run, not once per attempt: the re-execution after a kill appends no new command. Exporting that command as Keel's `STEP_ATTEMPT_STARTED` would be the adapter authoring a Keel journal, so the ordering is reported here and not scored |
| S5 | N/A | same: no Keel step lifecycle is exported |
| S7 | N/A | S7 is judged from `APPROVAL_REQUESTED/DECIDED`. Restate's journal has the approval run, the timer and the awakeable's completions, but nothing binds the decision to the gated run; the per-effect count (`deploy.service#1`) is on the page |
| C1 | N/A | Restate documents no replay of a recorded journal against the code. The SDK's test harness has `always_replay` ("this forces restate-server to always replay on a suspension point. This is useful to hunt non-deterministic bugs that might prevent your code to replay correctly", `restate.harness.create_test_harness`, 1.0.5), but that replays live invocations, executing their runs — not a verifier of a finished one. `replay_check` is not implemented |
| W6 | not declared | a Restate child-invocation citation is not in the fact sheet (§14.1) |
| W7, `model_stream_truncate` | N/A | no streamed model call is cited: `RestateAgent` makes each model request a `ctx.run` whose whole response is journaled ("every LLM response is saved in the Restate Server and replayed during recovery"), and nothing in the adapter's citations covers a stream inside one. Unverified rather than refuted — restate-sdk has no Windows wheel, so its `restate.ext.pydantic` source is checked only in the WSL clone — so N/A until an adapter README cites a streaming primitive |

## Places a documented primitive forced a choice

1. **Where the key is drawn.** Before the run, not in it — the section above. `auto_wrap_tools=True`
   would have put the tool body inside the run with no handler code before it.
2. **How the reviewer learns the awakeable id.** A file, written inside a run. The docs hand the id to
   the reviewer's system from a run (`request_human_review(..., id=id)`); the harness is that system,
   and a file in the trial directory is how it is reached. The id is deterministic, so a re-executed
   run writes the same one.
3. **WAITING is `suspended`**, which appears only when the server has asked the idle handler to suspend
   (the inactivity timeout, 2 s). A marker file would show the park at once, and would be the adapter
   reporting a state the engine has not reached.
4. **The workflow is a `restate.Workflow`**, not a `restate.Service`, so its key is the trial and its
   invocation and journal outlive completion for collection without an idempotency key on the send.

## Smoke — one seed per cell, against §13.7's predictions

`bench/specs/smoke_restate.yaml`, `smoke_restate_w5.yaml`, `smoke_restate_w5_pre.yaml`, seed 7, 20 trials,
run under WSL2 from a Linux clone of this branch at `d73a171` (every row's `keel_commit`), with `--out` on
the Linux filesystem. **Every trial valid, COMPLETED, L1/L2/S2/S3 PASS**, no extra model calls anywhere. S1
is judged against the `exactly_once` claim, so every duplicate below is also an S1 FAIL. One seed is a check
that each cell runs and lands where it was aimed, not a rate.

Two earlier passes are not on this page: one ran from the Windows worktree over WSL's 9P mount (worker start
4–7 s, and Linux git cannot follow a worktree's Windows `.git` path, so `keel_commit` was empty), and both
ran while the WSL VM's clock was drifting (±7 %, 0.8 s steps, since fixed). Their applied counts were the
same as these in every cell; their timings are not evidence of anything, and one of them found the harness
bug at the end of this section.

| cell | applied / receipts | restarts | wall s (baseline 4.0 / 3.7) | recovery s | what re-drove it (journal events) | §13.7 predicted |
|---|---|---|---|---|---|---|
| EXTERNAL `before:tool_call` (T1) | 1 / 1 | 1 | 7.4 | 3.6 | `stream closed because of a broken pipe` (RT0010) at the kill, then `Connection refused` until the worker was back | 0 / +0 — **held** |
| EXTERNAL `after:tool_effect` (T2) | **2 / 2** | 1 | 7.2 | 3.4 | same; the run's command was journaled and its result was not, so it re-executed | 1 / +0 — **held** |
| EXTERNAL `after:tool_return` (T3) | **2 / 2** | 1 | 7.0 | 3.5 | same | 1 / +0 — **held** (H1: T2 ≡ T3) |
| EXTERNAL `pause_past_ttl@before:tool_call` (T4), pause **24.84 s** (factor 3.55 × 7 s) | **3 / 3** | 0 | 29.0 | 24.9 | `the invocation stream was closed after the 'abort timeout' (5s) fired` (RT0001); all three requests reached the World within 60 ms of the thaw | 1 dup after inactivity + abort — **missed: 2 dups** (below) |
| EXTERNAL `tool_500@after:tool_effect` | **2 / 2** | 0 | 4.3 | 0.1 | `FaultResponse('tool_500: HTTP 500')` recorded as a transient error; the run re-executed in the same worker 0.1 s later | "documented exponential backoff, pinned so it does not pause" — **held** (H9) |
| IDEMPOTENT T1 | 1 / 1 | 1 | 7.5 | 3.7 | as EXTERNAL | — |
| IDEMPOTENT T2, T3 | **1 / 2** each | 1, 1 | 7.6, 7.3 | 3.9, 3.6 | as EXTERNAL; both receipts carry one key (`1f87013f-…`) | H3: one applied at F1 — **held** |
| IDEMPOTENT T4, pause 24.77 s | **1 / 3** | 0 | 28.8 | 24.8 | RT0001; three receipts after the thaw, one key | H3 — **held** |
| IDEMPOTENT `tool_500@after:tool_effect` | 1 / 2 | 0 | 3.9 | 0.1 | as EXTERNAL; one key | — |
| W5 `approval_delay` (duplicate click) | deploy 1 | 0 | 6.3 (baseline 5.9) | — | both resolves answered `202`; two `Notification: Signal` for one awakeable; the second reached nothing | H7: 1 — **held** |
| W5 `approval_expiry` | deploy 0, 2 model calls | 0 | 8.8 | — | `Notification: Sleep` 5.0 s after the park: `not done: approval expired` | nothing deployed, COMPLETED — **held** |
| W5 `kill_while_waiting` | deploy 1 | 1 | 9.4 | 3.6 | the grant was journaled 2.1 s into the park and the timer's completion at 5.0 s, before the worker was back; the replay took the grant (below) | H7: 1 / +0 — **held** |
| W5 `kill@after:tool_effect` | deploy **2** | 1 | 12.9 | 7.3 | RT0010 + `Connection refused`; the approval was already journaled, so it was not asked again | T2 behind a gate: 1 dup — **held** |
| W5-pre `approval_delay`, `kill_while_waiting` | notify **1**, deploy 1 | 0, 1 | 6.9, 9.6 (baseline 5.8) | —, 3.8 | `notify`'s run is journaled before the park and the continuation skips it | tier-2 H7 predicts 2 only for a pre-interrupt re-run — **1**, like Keel, Temporal and DBOS |

What the rows say that the prediction table does not:

- **The freeze's successor is the frozen process.** §13.7 predicts one duplicate at T4: the timed-out
  attempt completes after the thaw and the retry fires too. A 24.8 s freeze is 3.5 detection periods,
  and every retry goes to the one endpoint Restate has registered — the process that is frozen. Every
  attempt dispatched to it while it was stopped ran its tool after the thaw: the zombie plus two retries,
  three requests inside 60 ms. The duplicate count at T4 is a function of `pause / (inactivity + abort)` —
  which is why §13.4 draws the pause, and why 30 seeds of this cell will show a spread — and the journal
  cannot say how many attempts were sent: it keeps one RT0001 event per freeze (appended 12.0 s after the
  run's command in both cells), and that is not the moment of the first abort. **Detection is 7 s,
  bracketed by two probe trials** outside the smoke (EXTERNAL, the same cell with `pause_ms` pinned, same
  commit): 5 s → 1 applied, no retry; 9 s → 2 applied. Temporal's arm shows the same growth (3 applied at
  7.1 s).
- **Recovery after a kill is worker start plus the retry schedule, not detection.** Detection is
  immediate — the RT0010 event lands at the kill — and the restarted hypercorn process logs `Running on`
  about 3 s later (Python importing Pydantic AI and the Restate SDK). Restate's documented backoff
  (50 ms × 2ⁿ, capped at 60 s) finds it on the next attempt after that: 3.4–3.9 s in eight of the nine
  kill cells, and 7.3 s in W5's `kill@after:tool_effect`, where the worker came up just after an attempt
  and waited out the next, doubled interval. The number is the doubling schedule against start time, not
  a pinned timeout (H6 for kills).
- **`kill_while_waiting` decides a grant after its deadline fired, and grants.** The handler was
  suspended 2.0 s after the park (the inactivity timeout), the harness killed the worker and granted: the
  resolution was journaled 2.1 s into the park, the 5 s timer's completion at 5.0 s, and the deploy ran
  0.65 s after that, on the restarted worker. On replay `restate.select` returned the awakeable, which is
  first in the journal. By arrival order the grant is right, as it was in Temporal's arm; Keel judges
  expiry by the store's clock at drain time. Printed, not scored.
- **The duplicate click is accepted.** `202 Accepted` for both, and a second `Notification: Signal` in the
  journal. One-shot semantics keep it from granting anything, but a human who clicks twice is not told
  the second click was redundant.

**A harness bug this arm found.** In a discarded pass the IDEMPOTENT T4 cell's frozen attempt reached the
World 17 ms after its fault row, before the freeze took hold: on POSIX `freeze_self` raised `SIGSTOP` on its
own process and returned, but a process-directed stop is taken by whichever thread the kernel wakes, and
the shim thread that raised it ran on long enough to send. Windows never had the race (the thread parks on
the thaw marker). The fix parks on POSIX too (`crashproof/faults/process.py`), `tests/unit/test_process.py`
pins it, and every row above ran on it.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the engine does not do itself (the retry policy is Restate's
documented default), no dedup in the adapter, no key other than the documented one. The worker's argv
never changes and carries no id; the engine is never killed. The model is the workload script, selected
by request content alone.
