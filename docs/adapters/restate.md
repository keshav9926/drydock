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
| S4 | N/A | The verifier reads a Keel-shaped journal (`STEP_ATTEMPT_STARTED` per attempt, with timestamps). Restate does journal a run's `Command: Run` before its action executes — in the one-seed smoke's journals at `d73a171` the tool's command is appended before its first World receipt, which is the journal-before-effect §2 credits Restate with, and no release row or page scores that ordering — but once per run, not once per attempt: the re-execution after a kill appends no new command. Exporting that command as Keel's `STEP_ATTEMPT_STARTED` would be the adapter authoring a Keel journal, so the ordering is reported here and not scored |
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

## The release cells — 30 seeds each, 300 in the two confirmed ones, against §13.7's predictions

`bench/reports/v1_w1_shim.md`, `v1_w1_proxy.md`, `v1_w5.md`, `v1_w5_pre.md` and `v1_reask.md`, rows in
`bench/results/v1_*/results.jsonl`: 54 Restate cells, 2 220 trials — seeds 7–36 in every cell, and seeds
100 000–100 299 again in the two proxy cells the confirmation tier selected (below) — run under WSL2
from the Linux clone at `251e52d` (every row's `keel_commit`; every row `platform: linux (WSL2)`), with `--out`
on the Linux filesystem. **Every trial valid and COMPLETED, 0 void; L2/S2/S3 PASS in every cell, L1 30/30 in
every screening cell and 300/300 in the two confirmed ones**;
no extra model call in any cell that did not fault the model. S1 is judged against the `exactly_once` claim,
so every cell below that **applies** an effect twice is also an S1 FAIL — and only those: a duplicate
*receipt* the receiver dedups is not one, which is why the F1 cells below are S1 PASS at 30 and 51
duplicate receipts (`v1_w1_shim.md`). Seed 7 reproduces the one-seed smoke at `d73a171` that this
section used to print, count for count and pause draw included (24.84 s).

**Earlier runs.** No count in this section's tables comes from one. Four preceded it: that smoke, two
discarded passes (one over WSL's 9P mount, both under a drifting VM clock, since fixed), and week 2's
30-seed run at `dcdd533`, whose two `pause_past_ttl` shim cells had 4 of 60 trials still RUNNING at 60 s
(the harness's POSIX self-`SIGSTOP` race, fixed in `8d90198` before this run — the end of this section).
Where a paragraph below reads a *journal* rather than a row it says which run's: the release trials'
journals are on the WSL filesystem and not in this repo, so a mechanism first read in the smoke is cited
as the smoke's and carries no count.

| cell (shim; W5 rows from their own pages) | applied / receipts, of 30 | restarts | wall s, median (baseline 3.0 / 3.0) | recovery s, median | what re-drove it (journal events, on every row) | §13.7 predicted |
|---|---|---|---|---|---|---|
| EXTERNAL `before:tool_call` (T1) | 1 / 1 ×30 | 1 | 6.6 | 3.7 | `stream closed because of a broken pipe` (RT0010) at the kill, then `Connection refused` until the worker was back | 0 / +0 — **held 30/30** |
| EXTERNAL `after:tool_effect` (T2) | **2 / 2 ×30** | 1 | 6.7 | 3.7 | same; the run's command was journaled and its result was not, so it re-executed | 1 / +0 — **held 30/30** |
| EXTERNAL `after:tool_return` (T3) | **2 / 2 ×30** | 1 | 6.9 | 3.8 | same | 1 / +0 — **held 30/30** (H1: T2 ≡ T3) |
| EXTERNAL `pause_past_ttl@before:tool_call` (T4), pauses drawn 14.1–28.0 s | **2 / 2 in 15 seeds (pauses 14.1–19.0 s), 3 / 3 in 15 (19.4–28.0 s)** | 0 | 22.4 (17.3–31.2) | 19.3 | `the invocation stream was closed after the 'abort timeout' (5s) fired` (RT0001), once per trial | 1 dup after inactivity + abort — **missed: 1 or 2 dups, by the pause** (below) |
| EXTERNAL `tool_500@after:tool_effect` | **2 / 2 ×30** | 0 | 3.3 | 0.1 | `FaultResponse('tool_500: HTTP 500')` recorded as a transient error (RT0007); the run re-executed in the same worker 0.1 s later | "documented exponential backoff, pinned so it does not pause" — **held** (H9) |
| EXTERNAL `tool_timeout@before:tool_call` | **2 / 2 ×30** | 0 | 8.5 | 0.0 | `TimeoutError('timed out')` (RT0007) once the World had held the response past the client's 5 s; the held request had applied, and the re-execution applied again | the same entry as `tool_500` — the fault is aimed at the write tool (`landmark: tool:create_issue`) — **held** (H9) |
| IDEMPOTENT T1 | 1 / 1 ×30 | 1 | 6.9 | 3.7 | as EXTERNAL | — |
| IDEMPOTENT T2, T3 | **1 / 2 ×30** each | 1, 1 | 7.0, 7.0 | 3.7, 3.7 | as EXTERNAL; one applied | H3: one applied at F1 — **held 30/30** |
| IDEMPOTENT T4, pauses 15.1–27.9 s | **1 / 2 in 9 seeds (15.1–18.5 s), 1 / 3 in 21 (19.2–27.9 s)** | 0 | 25.4 | 22.3 | RT0001, once per trial; 2 or 3 receipts by the pause, as EXTERNAL, and one applied | H3 — **held 30/30** |
| IDEMPOTENT `tool_500`, `tool_timeout` | 1 / 2 ×30 each | 0, 0 | 3.3, 8.3 | 0.1, 0.0 | as EXTERNAL; one applied | — |
| `sigterm_grace_ok`, `sigterm_grace_too_short` @ `after:tool_effect`, both variants | 1 / 1 ×30, in each of the four cells | 0, except 1 in 2 of the 30 IDEMPOTENT `too_short` trials | 3.2 | — | nothing re-drove the tool: no trial in the four made a request to the World after the fault, so none has a recovery latency | `grace_ok` not in the fact sheet ⇒ measured, no prediction; `too_short` 1 dup — **missed: 0 dup in 60 trials** (below) |
| W5 `approval_delay` (duplicate click) | deploy 1 ×30 | 0 | 6.0 (baseline 5.3) | 0.0 | the second resolve reaches nothing (above) | H7: 1 — **held 30/30** |
| W5 `approval_expiry` | deploy 0 ×30, 2 model calls (+calls −1) | 0 | 8.0 | — | the 5 s `ctx.sleep` won the select: `not done: approval expired`, 30/30 | nothing deployed, COMPLETED — **held 30/30** |
| W5 `kill_while_waiting` | deploy 1 ×30 | 1 | 9.7 (8.7–15.2) | 3.8 (25 trials at 3.4–4.1 s, 5 at 7.1–8.0 s) | `Connection refused` (RT0010) only — a suspended handler has no stream to break — until the worker was back; the replay took the grant (below) | H7: 1 / +0 — **held 30/30** |
| W5 `kill@after:tool_effect` | deploy **2** ×30 | 1 | 9.2 | 3.8 (max 4.0) | RT0010 + `Connection refused`; the approval was already journaled, so it was not asked again | T2 behind a gate: 1 dup — **held 30/30** |
| W5-pre `approval_delay`, `kill_while_waiting` | notify **1**, deploy 1 ×30 each | 0, 1 | 6.8, 14.8 (baseline 6.1) | 0.1, 7.5 (28 of 30 at 7.1–8.2 s, the other two at 3.8 and 4.0 s) | `notify`'s run is journaled before the park and the continuation skips it | tier-2 H7 predicts 2 only for a pre-interrupt re-run — **1, 30/30**, like Keel, Temporal and DBOS |

What the rows say that the prediction table does not:

- **The freeze's successor is the frozen process, and the duplicate count is the pause.** §13.7 predicts
  one duplicate at T4. Every retry goes to the one endpoint Restate has registered — the process that is
  frozen — and every attempt dispatched to it while it was stopped ran its tool after the thaw: the zombie
  plus one retry, or plus two. Thirty drawn pauses put the boundary in one place in all four freeze cells:
  2 requests for every pause up to 19.0 s and 3 for every pause from 19.1 s, EXTERNAL and IDEMPOTENT, shim
  and proxy, with one exception (a 27.4 s proxy trial at 2); none reached 4 by 28.0 s. That is why §13.4
  draws the pause. The journal cannot say how many attempts were sent — it keeps one RT0001 event per
  freeze, in every trial — so the count is read from the World. **Detection is 7 s** by the two pinned
  timeouts (Pins, above), a documented figure and not one the release rows measure: nothing in them times
  the abandonment, only the effects it costs. Temporal's arm grows the same way — its own page reads the draw against the duplicate count cell by cell, without a single boundary between one duplicate and two.04–8.00 s, one duplicate for
  every draw under 5.0 s and two over 5.6 s (`v1_w1_shim.md`, `docs/adapters/temporal.md`).
- **The SIGTERM prediction is missed too, and in the other direction.** §13.7's second table predicts **1 dup** for
  Restate at `sigterm_grace_too_short@after:tool_effect` — a hard kill 150 ms after the SIGTERM
  (`crashproof/faults/injectors/base.py`), which for Keel is T2 again. The rows are `dup_eff 0 · dup_rcpt 0 ·
  lost 0`, L1 30/30, in EXTERNAL and IDEMPOTENT alike (`v1_w1_shim.md`): one applied and one receipt in all
  60 trials, with two of the IDEMPOTENT trials restarting once and still applying once. The rows say that
  much and no more — where inside the tool's boundary the 150 ms landed is in the trial's journal (WSL), not
  on the page, and `sigterm_grace_ok` is a cell §13.7 leaves unpredicted for every arm but Keel.
- **Recovery after a kill is neither detection nor the harness's respawn.** Where the handler is *running*,
  detection is immediate: the broken-pipe RT0010 event lands at the kill, in every running-handler row above.
  Where it is suspended there is no stream to break — the `kill_while_waiting` row above records
  `Connection refused` only, which is the *next dispatch* failing, not the kill being noticed. That contrast is
  read from the trials' journals — which the rows of the table above quote — and not from the published
  results: `recovery_detect_ms` is null in all 2 220 release rows of this arm, kill cells and wait cells
  alike, and no page prints the field. The harness's respawn is small either
  way — `restart_latency_ms` is the interval from the fault to the supervisor *deciding* to spawn the next
  incarnation (`crashproof/faults/supervisor.py` appends the timestamp immediately before the spawn;
  `crashproof/verifier/metrics.py` subtracts the fault's), so it measures the harness, not the new process
  starting. Across the fifteen W1, W5 and W5-pre kill cells at the screening tier its per-cell median is
  33.3–74.6 ms, and per trial those 450 measurements run 13.9–205.3 ms, 94 of them above 70 ms (the maximum
  is in W5 `kill_while_waiting@supervisor`, whose own per-trial range is 56.0–205.3 ms; the confirmed proxy
  cell's own 300 are a median 69.3 ms; the re-ask cell's figure is negative because the metric counts
  from the later of a trial's faults, and that cell's modifier fires on the successor). Recovery itself is
  3.3–4.4 s in all 320 W1 kill trials of the screening tier that measured one, median 3.7 s, shim and proxy
  alike. Everything between that respawn and the re-attempt is recorded whole, as
  `time_to_first_live_step_ms` — a median 3 671.9 ms in the shim's EXTERNAL `after:tool_effect` cell, 30/30
  rows, and 3.55–3.79 s in every other kill cell of W1 and W5 at the screening tier. One cell is twice
  that, W5-pre's `kill_while_waiting@supervisor` at 7.5 s, and it is the parked-handler case this bullet
  comes back to below. No page prints either field; both are read from
  `bench/results/v1_{w1_shim,w1_proxy,w5,w5_pre}`. What is inside it — the new
  process importing Pydantic AI and the Restate SDK, and which interval of Restate's pinned backoff
  (50 ms × 2ⁿ, capped at 60 s) found it — is not in the rows, which carry no attempt timestamps. It is not one
  number either: the confirmed proxy cell's 97 measured recoveries are 74 at 3.4–4.1 s and 23 at 6.8–8.2 s
  (median 3.8 s), and `kill_while_waiting` has the same two modes —
  W5-pre's recovered in 7.1–8.2 s in 28 of 30 trials (median 7.5 s) and in 3.8 and 4.0 s in the other two;
  W5's in 3.4–4.1 s in 25 and 7.1–8.0 s in 5 (median 3.8 s). The slow mode is not the wait: 23 of the
  confirmed proxy cell's 97 recoveries fall in it, and that cell's workload has no approval in it at all.
  Which retry interval or timeout it
  is — and why the same fault falls in it 28 of 30 times in W5-pre and 5 of 30 in W5 — is a journal question,
  not answered here. The fast mode is not a
  pinned timeout (H6 for kills): 3.3–4.4 s against inactivity 2 s, abort 5 s and detection 7 s. The slow
  mode's 6.8–8.2 s brackets the 7 s detection figure, and the rows cannot say whether that is what it is.
- **`kill_while_waiting` decides a grant after its deadline fired, and grants.** In the smoke's journal
  the handler was suspended 2.0 s after the park (the inactivity timeout), the harness killed the worker
  and granted: the resolution was journaled 2.1 s into the park, the 5 s timer's completion at 5.0 s, and
  the deploy ran 0.65 s after that, on the restarted worker. On replay `restate.select` returned the
  awakeable, which is first in the journal. At n = 30 every trial deployed — 30/30 in W5 and in W5-pre,
  none answered `not done: approval expired`. By arrival order the grant is right, as it was in Temporal's
  arm; Keel judges expiry by the store's clock at drain time. Printed, not scored.
- **The duplicate click is accepted.** `202 Accepted` for both, and a second `Notification: Signal` in the
  journal (the smoke's `clicks.jsonl` and journal; the rows hold the count). One-shot semantics keep it
  from granting anything — deploy 1 in 30/30, W5 and W5-pre — but a human who clicks twice is not told
  the second click was redundant.

**Proxy mode** (`v1_w1_proxy.md`, 18 cells, 1 140 trials — 540 at 30 seeds, 600 at the confirmation tier)
agrees with the shim on 10 of its 14 twins (`bench/reports/agreement_v1.md`, which pairs every twin at the
screening tier both sides ran). The four it does not are the two `kill@after:tool_return` twins and the two
`pause_past_ttl@before:tool_call` twins. The kills differ by the instrument: the proxy's fires from the edge
and applied once in 203 of its 300 confirmation seeds, twice in 97
(`logical_correctness` 203/300, `replay_divergence` 97/300; at screening, 18 and 12 of 30, which is the
reading the agreement page compares), where the shim's T3 inside
the process applied twice in all 30. Its F1 twin splits the same way: two
receipts in 8 of 30 at the proxy against all 30 at the shim (`duplicate_receipts` 30/8 on the agreement
page), one applied on both sides — the rows hold the counts, and whether a trial's result had reached the
server before the kill is in that trial's journal (WSL), not on the page. The `pause_past_ttl` twins differ
by their drawn pauses: a pause at or past 19.1 s cost 2 duplicates and a shorter one 1, so the split of the
thirty draws is the cell's count. At F0 the shim drew 15 long and 15 short — 30 + 15 = 45 duplicates — and the
proxy 21 long and 9 short — 41 + 9 = 50, the 41 being 20 trials at 3 applied plus seed 27's 27.4 s trial at 2
(the one exception above). At F1 the shim drew 21 long and 9 short (42 + 9 = 51 duplicate receipts) and the
proxy 20 and 10 (40 + 10 = 50). The proxy-only faults,
`tool_dropped_response` and `tool_malformed` at `after:tool_effect`, applied twice in all 30 each:
`RemoteDisconnected` and `JSONDecodeError` recorded as transient errors (RT0007), the run re-executed 0.1 s
later; F1 turned both into one applied, in all 30.

**S1, from the rows.** 14 cells fail the `exactly_once` claim, with 499 counterexample rows between them
(§15.4: a safety cell is PASS with no violation in n, or FAIL with the list — never a rate, and a FAIL at
either tier is a FAIL): shim EXTERNAL
`after:tool_effect`, `after:tool_return`, `pause_past_ttl@before:tool_call`, `tool_500@after:tool_effect`
and `tool_timeout@before:tool_call` (30 counterexamples each, one per seed); proxy EXTERNAL `kill@after:tool_effect`,
`pause_past_ttl@before:tool_call`, `tool_500@after:tool_effect`, `tool_dropped_response@after:tool_effect`,
`tool_malformed@after:tool_effect` and `tool_timeout@before:tool_call` (30 each) and
`kill@after:tool_return` (109 — 12 of the screening seeds and 97 of the 300 confirmation seeds); W5
`kill@after:tool_effect` (30); the re-ask cell (30). No IDEMPOTENT
cell, no `before:tool_call` kill, no model-side fault and neither SIGTERM cell fails it: the claim fails
exactly where a run's action executed and its result was not journaled, and the receiver's key is what
turns the same window into a pass at F1.

**The re-ask cell** (`v1_reask.md`, spec `bench/specs/release_reask.yaml`):
`kill@after:tool_effect+model_reask_alternate@before:model_call`. The modifier arms the script's alternate
for the second decision — `create_issue` titled `CI flake (rephrased)` — for any arm that asks that question
again after the kill. Restate never did: `Model call` is a `ctx.run`, so the successor replayed the journaled
decision and filed `CI flake: test_retry` twice, 30/30, with 3 model calls and 1 317 tokens, its baseline's
exactly (+calls 0). The cell's `diverged 30/30` and its S1 FAIL are T2's duplicate, the same as the plain
cell's; the arms that filed the rephrased issue were `langgraph.async` and `langgraph.exit`, 30/30 each.

**Confirmation** (§15.3, `bench/confirm/v1.yaml`). One Restate fault cell is selected — the proxy
`kill@after:tool_return`, whose `logical_correctness` 18/30 and `replay_divergence` 12/30 at screening are
not unanimous — with its baseline beside it as τ₀: two cells, `host: wsl`, 300 fresh seeds
(100 000–100 299), 600 trials, and Keel's cell at the same (variant, location, fault) on the Windows half.
Both ran at `251e52d`, every trial valid and COMPLETED, and the rows are folded into
`bench/results/v1_w1_proxy/results.jsonl`: `v1_w1_proxy.md` now prints both cells at n = 300, with their
n = 30 reading in its screening appendix. The baseline applied once in all 300 (S1 PASS, `duplicate_effects`
0); the kill cell applied once in 203 and twice in 97 — `logical_correctness` 203/300,
`replay_divergence` 97/300, L1 300/300, S1 FAIL with 97 counterexamples, and of the 97 recoveries measured
74 at 3.4–4.1 s and 23 at 6.8–8.2 s (median 3.8 s). Ten times the seeds moved neither verdict: they
sharpened the divergence estimate that 30 seeds had read as 12, and they turned up the slow recovery mode
the screening tier had not shown in this cell at all.

**Two harness bugs this arm found**, both in the POSIX freeze. In a discarded pass the IDEMPOTENT T4 cell's
frozen attempt reached the World 17 ms after its fault row, before the freeze took hold: on POSIX
`freeze_self` raised `SIGSTOP` on its own process and returned, but a process-directed stop is taken by
whichever thread the kernel wakes, and the shim thread that raised it ran on long enough to send. Windows
never had the race (the thread parks on the thaw marker); the fix parked the thread on POSIX too. Week 2's
run at `dcdd533` found the second: the worker still stopped itself before parking, and when the supervisor
froze it between the fault row's write and that self-stop, the self-stop landed after the supervisor's
resume and nothing resumed it again — 4 of 60 `pause_past_ttl` shim trials sat stopped until the 60 s
timeout and scored L1 against Restate, the trial directories showing Restate retrying and the worker silent.
Fixed in `8d90198` (`crashproof/faults/process.py`: the supervisor alone stops the worker, on both platforms,
and `PARK_S` is 120 s, past the longest drawn pause), pinned by `tests/unit/test_process.py` with a real
child, and every row above ran on it: the four freeze cells COMPLETED 120/120, L1 120/120.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the engine does not do itself (the retry policy is Restate's
documented default), no dedup in the adapter, no key other than the documented one. The worker's argv
never changes and carries no id; the engine is never killed. The model is the workload script, selected
by request content alone.
