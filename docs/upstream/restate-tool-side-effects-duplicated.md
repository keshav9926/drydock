# Restate: a `ctx.run` whose result was not journaled runs again, so a tool side effect lands twice

## Pre-filing notes (for the owner; delete this section before filing)

| | |
|---|---|
| Status | **draft, not filed** |
| Where | [restatedev/docs-restate](https://github.com/restatedev/docs-restate/issues), as a docs issue. The same sentence is also on pydantic.dev's Restate page (source in [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)). File once, at Restate, and name the second page in the issue. |
| Kind | *Contradicts* the sentence as written. The likely fix is a qualifier in the docs, not an engine change, so it is filed as a docs issue (the template's *sharpens* route). |
| Rows | `bench/results/week2_w1_shim`, `week2_w1_proxy`, `week2_w5` at `dcdd533`. The Restate shard ran under WSL2 from a Linux clone. |
| Quotes re-verified | 2026-09-18, every quoted doc sentence, verbatim, on the live pages. The pages carry no version. restate-sdk 1.0.5 is still the latest release on PyPI. |

Of the 13 Restate cells that fail S1 (5 shim, 7 proxy, W5), the body leans on 4 kill cells and the freeze. The retry cells are named in the body as *not* counted, with the reason. The proxy-mode `kill@after:tool_return` (5 of 30) is not cited: the agreement page treats that trigger from the proxy as an instrument difference (the kill lands after `taskkill`'s latency).

**Before filing, re-run the freeze cell.** The 4 of 60 `pause_past_ttl` trials that were still RUNNING at 60 s were the harness's own race (the worker stopped itself after the supervisor's resume), fixed in `8d90198`; the README now says so. The freeze counts quoted below come from the run that had it, so re-quote them from the re-run of `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` at the fixed commit, or drop the freeze paragraph and file on the kill windows alone.

Template checklist:

- [x] Doc quote in hand (re-fetched 2026-09-18; see the version note above).
- [x] Survives *"your adapter is wrong"*: see "Is the adapter missing something?" below.
- [x] Not the documented semantics restated: the arm is judged against `exactly_once` because that is what the page says.
- [ ] **Repro run from a clean clone: not done for this draft.** The arm is Linux-only, and a confirmation bench held the machine. Run the command below once on Linux before filing.
- [x] Specific counterexample: `(6b50e0ebfe17bcd187442adebe1a4814d214907c18390b074f011acef12d5b66, seed 7, t-7)`.
- [x] `verify --recheck` exit 0: the README records exit 0 over all 12,520 week-2 rows, on the machine that ran them. It was not re-run for this draft.
- [x] Not due a re-run: the week-2 rows are the re-run the post-phase-8 audit asked for.

---

## Issue body

**Title:** Durable agents: "Tool side effects are not duplicated", but a `ctx.run` action re-executes when the process dies after the action and before its result is journaled

**What the docs say.** From [docs.restate.dev/ai/patterns/durable-agents](https://docs.restate.dev/ai/patterns/durable-agents), "How durable execution works":

> Tool side effects are not duplicated (no double bookings, no duplicate emails)

> Side effects are executed exactly once. On recovery, the result is replayed.

From [pydantic.dev/docs/ai/integrations/durable_execution/restate](https://pydantic.dev/docs/ai/integrations/durable_execution/restate/):

> The result is persisted and retried until it succeeds.

> Side effects won't be duplicated on recovery.

Tested against restate-sdk 1.0.5, restate-server 1.7.10 (Linux binary) and pydantic-ai-slim 2.43.0 on Python 3.13, under Linux (WSL2).

**What happens.** A Pydantic AI agent wrapped in `RestateAgent` calls one tool. The tool does its work inside `restate_context().run_typed("create_issue", action)`, as both pages show. The action makes one HTTP request to a receiver that cannot deduplicate, like an email or a legacy API. The worker process is `SIGKILL`ed after the receiver applied the request and before the SDK sent the run's result to the server. It is then restarted on the same port. Restate re-invokes it and the action runs a second time. **The receiver applied the request twice in 30 of 30 trials.** Every invocation completed successfully.

Seed 7, trial `t-7`. Restate's own journal and the receiver's log show the window (UTC):

```
20:24:13.376  journal [7]  Command: Run  name=create_issue  completion_id=4      <- journaled before the action
20:24:13.390  receiver     issues.create  seq=2  applied                          <- the action's request
20:24:13.403  harness      SIGKILL worker (pid 89725)
20:24:13.425  journal event RT0010 "stream closed because of a broken pipe"
20:24:13.488  journal event RT0010 "h2 pool connection error: Connection refused"  (retries 60 ms, 114 ms, 254 ms ... until the worker is back)
20:24:18      worker restarted on the same port (pid 89754)
20:24:20.207  receiver     issues.create  seq=3  applied                          <- the action again
20:24:20.234  journal [8]  Notification: Run  completion_id=4  Success            <- the only completion ever journaled
20:24:20.570  invocation completed, completion_result=success
```

At the moment of the kill, the server's journal held the `Command: Run` for `create_issue` and no completion for it. That is correct for a run whose result had not arrived. The retry then re-executed the action, as it should for a run with no completion. The receiver's log, trimmed (`body` elided):

```
{"endpoint": "kv.search",     "logical_identity": "kv.search#1",     "seq": 1, "ts": 1789590253.247, "effect_key": null}
{"endpoint": "issues.create", "logical_identity": "issues.create#1", "seq": 2, "ts": 1789590253.390, "effect_key": null, "args": {"title": "CI flake: test_retry", ...}}
{"endpoint": "issues.create", "logical_identity": "issues.create#1", "seq": 3, "ts": 1789590260.207, "effect_key": null, "args": {"title": "CI flake: test_retry", ...}}
```

The same holds, 30 of 30 each, at every point we killed after the effect:

| window | cell | applied / received | trials |
|---|---|---|---|
| killed after the receiver applied, before the tool returned | `restate.pydantic_ai.EXTERNAL.after:tool_effect` | 2 / 2 | 30 of 30 |
| killed after the tool returned to the agent, before the result reached the server | `restate.pydantic_ai.EXTERNAL.after:tool_return` | 2 / 2 | 30 of 30 |
| as the first row, but the kill comes from a proxy between the worker and the receiver, after the receiver answered and before the answer is forwarded | `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` (proxy mode) | 2 / 2 | 30 of 30 |
| as the first row, behind a human approval (awakeable, already resolved) | `restate.pydantic_ai.GATED.kill@after:tool_effect` (`deploy_service`) | 2 / 2 | 30 of 30 |
| control: killed *before* the request was sent | `restate.pydantic_ai.EXTERNAL.before:tool_call` | 1 / 1 | 30 of 30 |
| control: no fault | `restate.pydantic_ai.EXTERNAL.baseline` | 1 / 1 | 30 of 30 |

The window is narrow. With no fault, the median time from the receiver applying the request to Restate journaling the run's completion was 23.4 ms. This was measured over the same workload, on the WSL clock the receiver shares.

**A second window: a frozen worker.** In this cell the worker is sent `SIGSTOP` just before the request, for longer than the inactivity and abort timeouts, then `SIGCONT`. `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` applied the request **twice in 15 trials and three times in 14**. The 30th trial hit a fault in our harness (since fixed) and is not counted. Seed 7 froze for 24.84 s from 20:52:21.760. The server aborted the attempt (RT0001, *"the invocation stream was closed after the 'abort timeout' (5s) fired"*) and retried twice, 54 ms and 107 ms after each abort, to the one registered endpoint: the frozen process. After the thaw, that process ran `create_issue` three times within 84 ms (receiver seq 2, 3, 4 at 20:52:46.652, .718, .736): once for the aborted attempt and once for each re-dispatched attempt. The journal holds one completion. This window depends on our pins: inactivity 2 s and abort 5 s, against documented defaults of 1 min and 10 min. With the defaults, the same freeze would not have been abandoned, and the request would have been applied once.

**Why this is not the documented behaviour.** The page says tool side effects are not duplicated, and names duplicate emails as the thing avoided. It does not qualify that for the interval between a `ctx.run` action finishing and its result reaching the server. In that interval, the only record of the action is the effect it had. A retry re-executes it, because the journal correctly shows the run as not completed. We think that behaviour is right, and the sentence is what should change.

**This may be intended. Here is what the docs say.** Several Restate pages point to at-least-once execution of the action, with journaled results never recomputed:

- [Durable steps](https://docs.restate.dev/develop/python/durable-steps): *"Failures in `ctx.run` are treated the same as any other handler error. Restate will retry it unless configured otherwise or unless a `TerminalError` is thrown."*
- The same page gives `ctx.uuid()`: *"To generate stable UUIDs for things like idempotency keys"*. The UUID comes from helpers *"seeded by the invocation ID — so they return the **same result on retries**"*.

We ran that recipe too. The tool drew `str(ctx.uuid())` before its `run_typed` and sent it as `Idempotency-Key` to a receiver that deduplicates on it. The receiver then **applied once in 30 of 30** at both kill windows (2 requests received, 1 applied). So the guarantee holds for journaled results, and for effects whose receiver takes an idempotency key. The case the sentence names, a duplicate email to a receiver that cannot deduplicate, is exactly the case it does not cover. A qualifier on the durable-agents page would make the page match the engine. For example: *"once its result is journaled, a `ctx.run` is never re-executed; if the process dies after the action and before its result is journaled, the action runs again, so pass an idempotency key from `ctx.uuid()`"*. The same applies to the pydantic.dev page.

**Is the adapter missing something?** We looked for a documented option that makes a run at-most-once across a crash and found none. `RunOptions.max_attempts` and `max_duration` bound retries of an action that *raises* (*"When giving up, `ctx.run` will throw a `TerminalError`"*, restate-sdk 1.0.5). Their docstrings say nothing about an attempt whose completion never reached the server, and we did not test them in this window. If such an option exists, this finding is about our adapter, and we would like to know. `RestateAgent(auto_wrap_tools=True)` would put the tool body in the same kind of `ctx.run`, with the same window. We wrap by hand only so the idempotency key can be drawn before the run.

**Reproduction.** Linux only, because restate-sdk ships no Windows wheel. Needs `restate-server` 1.7.10 on `PATH` (or `CRASHPROOF_RESTATE_BIN=/path/to/restate-server`); no Postgres needed for this arm:

```bash
git clone https://github.com/keshav9926/drydock && cd drydock && git checkout dcdd533
uv sync --extra dev --extra restate
uv run crashproof bench --matrix bench/specs/week2_w1_shim.yaml --cells 'restate.pydantic_ai.EXTERNAL.after:tool_effect' --seeds 1 --base-seed 7 --out out/repro
uv run crashproof verify out/repro/restate.pydantic_ai.EXTERNAL.after_tool_effect/t-7 --effects
```

The effect ledger should show `issues.create#1` with 2 received and 2 applied. The trial directory holds the receiver's log (`world/receipts.jsonl`), Restate's journal as read from `sys_journal` / `sys_journal_events` (`sut/journal.json`), the server log, and the fault row. Our own trial directories are not in the repository, because they are hundreds of MB per run; the command above regenerates one. Other windows use the same form:

- `--matrix bench/specs/week2_w1_shim.yaml --cells 'restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call'` for the freeze;
- `--matrix bench/specs/week2_w5.yaml --cells 'restate.pydantic_ai.GATED.kill@after:tool_effect'` for the approval-gated one.

At `HEAD`, each of these cell ids still resolves to the same spec hash as the published rows. `dcdd533` is the commit the rows ran at.

**What this is not a claim about.** The harness kills a process inside a ~20 ms window that a random production crash would rarely hit. The numbers are 30 seeds per cell on one host. Nothing here says Restate is unsafe or unsuitable for anything. This is one sentence on one page, compared with what the engine does. The harness's own reference runtime has the same exposure in the freeze window: it applies twice in 20 of 30 of the same `pause_past_ttl` trials.

Four more cells in the rows also apply twice, 30 of 30. In each, the receiver applied the request and then answered with an HTTP 500, held its answer past the client's 5 s timeout, dropped the connection, or sent a body that was not JSON. We do not count any of them here. In each, the action *raised*, and Restate's documented retry re-ran it (default `RunOptions`). That is "retried until it succeeds" doing what it says. `RunOptions.max_attempts` is the documented way to stop it.

**Everything needed to disagree.**

- Adapter: [`crashproof/adapters/restate.py`](https://github.com/keshav9926/drydock/blob/dcdd533/crashproof/adapters/restate.py) (~580 lines), with its write-up in [`docs/adapters/restate.md`](https://github.com/keshav9926/drydock/blob/dcdd533/docs/adapters/restate.md). The agent is shared with the DBOS and Temporal arms: [`pydantic_ai_agent.py`](https://github.com/keshav9926/drydock/blob/dcdd533/crashproof/adapters/pydantic_ai_agent.py).
- Spec files: `bench/specs/week2_w1_shim.yaml`, `week2_w1_proxy.yaml` and `week2_w5.yaml`. Every trial is seeded from 7 upward.
- Rows (committed): `bench/results/week2_w1_shim/results.jsonl`, `week2_w1_proxy/…` and `week2_w5/…`.
- Counterexample: `spec_hash 6b50e0eb…5b66`, seed 7, `t-7`.
- Claim judged against: `EXTERNAL: exactly_once`, taken from the sentence above. **S1 FAIL, 30 of 30.**
- Fairness level: **F0** (`key_source = none`). The receiver has `dedup: false`, and no key is sent. The keyed contrast above is **F1**: `key_source = framework`, the key is `str(ctx.uuid())` drawn before the run, and the receiver has `dedup: true`.
- `config_pin` on every row:
  - versions: restate-sdk 1.0.5, restate-server 1.7.10, pydantic-ai-slim 2.43.0, hypercorn 0.18.0, Python 3.13.15;
  - `InvocationRetryPolicy(initial_interval=50ms, exponentiation_factor=2.0, max_interval=60s, max_attempts=70, on_max_attempts=pause)`, which is the documented default spelled out;
  - `ctx.run` with default `RunOptions()`;
  - inactivity 2 s, abort 5 s;
  - one partition, `RESTATE_LISTEN_MODE=tcp`;
  - the worker served by `hypercorn.asyncio.serve(restate.app([workflow]))` over h2c;
  - platform `linux (WSL2)`.
- Pins that could change the number:
  - The inactivity and abort timeouts change the freeze cell only: its count is roughly the freeze length divided by 7 s.
  - The kill cells do not depend on any timeout. In seed 7 the kill landed 13 ms after the receiver applied, and `crashproof placement` puts 100 % of the shim-mode kills inside the intended window.
  - `RunOptions.max_attempts` was not set.
