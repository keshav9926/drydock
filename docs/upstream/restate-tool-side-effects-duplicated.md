# Restate: a `ctx.run` whose result was not journaled runs again, so a tool side effect lands twice

## Pre-filing notes (for the owner; delete this section before filing)

| | |
|---|---|
| Status | **filed** 2026-09-25 as [restatedev/docs-restate#410](https://github.com/restatedev/docs-restate/issues/410), after the checks below. The section under `## Issue body` is what was filed; this section was not. |
| Where | [restatedev/docs-restate](https://github.com/restatedev/docs-restate/issues), as a docs issue. The same sentence is also on pydantic.dev's Restate page (source in [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai)). File once, at Restate, and name the second page in the issue. |
| Kind | *Contradicts* the sentence as written. The likely fix is a qualifier in the docs, not an engine change, so it is filed as a docs issue (the template's *sharpens* route). |
| Rows | `bench/results/v1_w1_shim`, `v1_w1_proxy`, `v1_w5` at `251e52d` — the release re-run; every row carries that commit and no Restate trial is void. The Restate shard ran under WSL2 from a Linux clone. Two Restate cells — the proxy `kill@after:tool_return` cell and its baseline — also carry the confirmation tier's 300 seeds (§15.3, seeds ≥ 100 000), and the grid prints those two at n = 300 with their n = 30 reading in the page's appendix. Every Restate cell the body cites is a screening cell at n = 30. |
| Quotes re-verified | 2026-09-25, every quoted doc sentence, verbatim, string-matched against the live pages (HTML and the `.md` renderings). The pages carry no version. restate-sdk 1.0.5 is still the latest release on PyPI; restate-server's latest is 1.7.12 (2026-09-22), which the clean-clone repro below also ran. |

Of the 13 Restate cells that fail S1 in the three row sets above (5 shim, 7 proxy, 1 W5; a 14th, `kill@after:tool_effect+model_reask_alternate@before:model_call` in `bench/results/v1_reask`, is the `after:tool_effect` kill with `model_reask_alternate` added and fails the same way, 30 of 30), the body leans on 4 kill cells and the freeze. The six retry cells are named in the body as *not* counted, with the reason. Two are not cited. The proxy-mode `kill@after:tool_return` is one of the confirmed cells: it applied twice in 97 of 300 and once in 203, with one restart in every trial (`bench/reports/v1_w1_proxy.md`; its screening appendix reads 12 of 30, and the 330 rows hold both tiers). The agreement page (`bench/reports/agreement_v1.md`, shim 30 / proxy 12 over the 30 seeds both instruments ran, marked as not agreeing) reads a kill from outside the process as arriving with latency, often after the parse and sometimes after the run has finished. Its wording names `taskkill`, which is generic prose written for the Windows shards: this arm ran under WSL2, where `crashproof/faults/process.py` sends `SIGKILL` instead, so the latency reading transfers and the utility's name does not. That the 203 are the trials whose completion reached the server before the kill is our inference from the count: no row records where those kills landed, and we have no measurement of the latency on this platform. The proxy-mode `pause_past_ttl@before:tool_call` applied three times in 20 and twice in 10; in proxy mode the worker is frozen *and* its request is parked at the proxy until the thaw (`docs/adapters/keel.md`, "Proxy mode"), so the body quotes the shim cell, where nothing but the worker is stopped.

**The freeze paragraph's counts are quoted from a clean run; its mechanism is still read from `dcdd533`.** At `dcdd533`, 4 of 60 `pause_past_ttl` trials were still RUNNING at 60 s; that was the harness's own race (the POSIX worker stopped itself after the supervisor's resume), fixed in `8d90198` before the release re-run. At `251e52d` both Restate `pause_past_ttl` shim cells complete 30 of 30 with L1 30 of 30, and the counts, freeze lengths, statuses, restarts and the one RT0001 per row below are theirs. The re-dispatch timings in the same paragraph are not: no release artefact in the repository carries them, because the trial directories are not committed. They are still the `dcdd533` copy of the same seed, and the paragraph says so.

Template checklist:

- [x] Doc quote in hand (re-fetched 2026-09-18; see the version note above).
- [x] Survives *"your adapter is wrong"*: see "Is the adapter missing something?" below.
- [x] Not the documented semantics restated: the arm is judged against `exactly_once` because that is what the page says.
- [x] Repro run from a clean clone, 2026-09-25, WSL2 Ubuntu: `git clone` + `git checkout 251e52d` + `uv sync --extra dev --extra restate` (restate-sdk 1.0.5, pydantic-ai-slim 2.43.0, hypercorn 0.18.0). The command below on restate-server 1.7.10: seed 7 → `issues.create#1` 2 received, 2 applied, S1 FAIL, `bench` and `verify` exit 7. The same cell on restate-server **1.7.12** (the latest release, sha256 checked) with `--seeds 3`: seeds 7, 8, 9 → 2 received, 2 applied each; every row's `config_pin` records 1.7.12. The trial directory holds `world/receipts.jsonl`, `sut/journal.json`, `sut/restate-server.log` and `faults.jsonl`, as the body says.
- [x] Specific counterexample: `(6b50e0ebfe17bcd187442adebe1a4814d214907c18390b074f011acef12d5b66, seed 7, t-7)` — the same `(spec_hash, seed, trial_id)` at `251e52d`.
- [x] `verify --recheck`: the release commit (`1199992`) records each of the seven `v1_*` row sets rechecked green from its trial directories, and the confirmation commit (`119d605`) records every confirmation trial re-verifying from its own. Neither was re-run for this draft.
- [x] Not due a re-run: the `251e52d` rows are the re-run the week-2 status asked for.

---

## Issue body

**Title:** Durable agents: "Tool side effects are not duplicated", but a `ctx.run` action re-executes when the process dies after the action and before its result is journaled

**What the docs say.** From [docs.restate.dev/ai/patterns/durable-agents](https://docs.restate.dev/ai/patterns/durable-agents), "How durable execution works":

> Tool side effects are not duplicated (no double bookings, no duplicate emails)

> Side effects are executed exactly once. On recovery, the result is replayed.

From [pydantic.dev/docs/ai/integrations/durable_execution/restate](https://pydantic.dev/docs/ai/integrations/durable_execution/restate/):

> The result is persisted and retried until it succeeds.

> Side effects won't be duplicated on recovery.

Tested against restate-sdk 1.0.5, restate-server 1.7.10 (Linux binary) and pydantic-ai-slim 2.43.0 on Python 3.13, under Linux (WSL2). The one-trial reproduction below, run from a clean clone, gives the same result on restate-server 1.7.12, the latest release: 2 applied in 3 of 3 seeds.

**What happens.** A Pydantic AI agent wrapped in `RestateAgent` calls one tool. The tool does its work inside `restate_context().run_typed("create_issue", action)`, as both pages show. The action makes one HTTP request to a receiver that cannot deduplicate, like an email or a legacy API. The worker process is `SIGKILL`ed after the receiver applied the request and before the SDK sent the run's result to the server. It is then restarted on the same port. Restate re-invokes it and the action runs a second time. **The receiver applied the request twice in 30 of 30 trials.** Every invocation completed successfully.

Seed 7, trial `t-7`. Restate's own journal and the receiver's log show the window (UTC). The transcript is the `dcdd533` run's, from the trial directory of the same seed; the release row for `t-7` at `251e52d` (same spec hash) carries the same two RT0010 events, 15 ms and 74 ms after the kill, and the same count:

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

The window is narrow. `crashproof placement --window` over the release trials puts the median time from the receiver applying the request to Restate journaling the run's completion at 16.1 ms (IQR 15.0–17.4 ms) over the 60 W1 shim baseline trials, on the WSL clock restate-server and the receiver share. The width is read from the trial directories rather than from the rows, and those are not in the repository.

**A second window: a frozen worker.** In this cell the worker is sent `SIGSTOP` just before the request, for longer than the inactivity and abort timeouts, then `SIGCONT`. `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` applied the request **twice in 15 trials and three times in 15**; all 30 completed (L1 30 of 30), none restarted. The freezes drawn ran 14.1–28.0 s: twice at 14.1–19.0 s, three times at 19.4–28.0 s. Seed 7 froze for 24.84 s from 19:13:52.030; the receiver holds three `issues.create` receipts, three applied, and the journal one completion. The journal keeps one RT0001 event per freeze (*"the invocation stream was closed after the 'abort timeout' (5s) fired"*), stamped 12.0 s after the fault fired in every one of the 30 rows whether the request was applied twice or three times, so it is neither the moment of the first abort nor a count of the attempts sent. What follows is the mechanism, and it is not from the release run — the release trial directories are not in the repository. It is read from the `dcdd533` run's copy of the same seed (the same 24.84 s draw), whose server log showed the server abandoning the attempt and re-dispatching twice, 54 ms and 107 ms after each abort, to the one registered endpoint: the frozen process. After the thaw, that process ran `create_issue` three times, once for the aborted attempt and once for each re-dispatched attempt; the three requests spanned 84 ms and landed 52–136 ms after the thaw. This window depends on our pins: inactivity 2 s and abort 5 s, against documented defaults of 1 min and 10 min. With the defaults, the same freeze would not have been abandoned, and the request would have been applied once.

**Why this is not the documented behaviour.** The page says tool side effects are not duplicated, and names duplicate emails as the thing avoided. It does not qualify that for the interval between a `ctx.run` action finishing and its result reaching the server. In that interval, the only record of the action is the effect it had. A retry re-executes it, because the journal correctly shows the run as not completed. We think that behaviour is right, and the sentence is what should change.

**This may be intended. Here is what the docs say.** Several Restate pages point to at-least-once execution of the action, with journaled results never recomputed:

- [Durable steps](https://docs.restate.dev/develop/python/durable-steps): *"Failures in `ctx.run` are treated the same as any other handler error. Restate will retry it unless configured otherwise or unless a `TerminalError` is thrown."*
- The same page gives `ctx.uuid()`: *"To generate stable UUIDs for things like idempotency keys"*. The UUID comes from helpers *"seeded by the invocation ID — so they return the **same result on retries**"*.

We ran that recipe too. The tool drew `str(ctx.uuid())` before its `run_typed` and sent it as `Idempotency-Key` to a receiver that deduplicates on it. The receiver then **applied once in 30 of 30** at both kill windows (2 requests received, 1 applied). So the guarantee holds for journaled results, and for effects whose receiver takes an idempotency key. The case the sentence names, a duplicate email to a receiver that cannot deduplicate, is exactly the case it does not cover. A qualifier on the durable-agents page would make the page match the engine. For example: *"once its result is journaled, a `ctx.run` is never re-executed; if the process dies after the action and before its result is journaled, the action runs again, so pass an idempotency key from `ctx.uuid()`"*. The same applies to the pydantic.dev page.

**Is the adapter missing something?** We looked for a documented option that makes a run at-most-once across a crash and found none. `RunOptions.max_attempts` and `max_duration` bound retries of an action that *raises* (*"When giving up, `ctx.run` will throw a `TerminalError`"*, restate-sdk 1.0.5). Their docstrings say nothing about an attempt whose completion never reached the server, and we did not test them in this window. If such an option exists, this finding is about our adapter, and we would like to know. `RestateAgent(auto_wrap_tools=True)` puts the tool body inside a `ctx.run` with no handler code before it, which is why we wrap by hand — the idempotency key has to be drawn before the run. We did not run that setting: every cell cited here has `auto_wrap_tools=False` in its `config_pin`, so we do not claim its window from these rows.

**Reproduction.** Linux only, because restate-sdk ships no Windows wheel. Needs `restate-server` 1.7.10 on `PATH` (or `CRASHPROOF_RESTATE_BIN=/path/to/restate-server`); no Postgres needed for this arm:

```bash
git clone https://github.com/keshav9926/drydock && cd drydock && git checkout 251e52d
uv sync --extra dev --extra restate
uv run crashproof bench --matrix bench/specs/week2_w1_shim.yaml --cells 'restate.pydantic_ai.EXTERNAL.after:tool_effect' --seeds 1 --base-seed 7 --out out/repro
uv run crashproof verify out/repro/restate.pydantic_ai.EXTERNAL.after_tool_effect/t-7 --effects
```

The effect ledger should show `issues.create#1` with 2 received and 2 applied; both commands exit 7, which is the harness's code for a failed invariant (here S1). The trial directory holds the receiver's log (`world/receipts.jsonl`), Restate's journal as read from `sys_journal` / `sys_journal_events` (`sut/journal.json`), the server log, and the fault row. Our own trial directories are not in the repository, because they are hundreds of MB per run; the command above regenerates one. Other windows use the same form:

- `--matrix bench/specs/week2_w1_shim.yaml --cells 'restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call'` for the freeze;
- `--matrix bench/specs/week2_w5.yaml --cells 'restate.pydantic_ai.GATED.kill@after:tool_effect'` for the approval-gated one.

These are the spec files the release rows ran: every row carries its `spec_hash`, and the hash on each cell's rows is the one the named file declares for that cell id — `6b50e0eb…` for `after:tool_effect`, `88d3c984…` for the freeze, `58533035…` for the gated kill. `251e52d` is the commit the rows ran at; at `HEAD` each still resolves to the same hash, since neither `bench/specs/` nor the harness's spec code has changed since.

**What this is not a claim about.** The harness kills a process inside a ~16 ms window that a random production crash would rarely hit. The numbers are 30 seeds per cell on one host, except where the confirmation tier re-ran a cell at 300. Nothing here says Restate is unsafe or unsuitable for anything. This is one sentence on one page, compared with what the engine does. The harness's own reference runtime has the same exposure in the freeze window: it applies twice in 97 of 300 of the same `pause_past_ttl` trials — its confirmed reading, where the screening tier read 4 of 30 — and in 30 of 30 in proxy mode, where the freeze parks the request at the proxy.

Four more faults in the rows (six cells across the two modes) also apply twice, 30 of 30. In each, the receiver applied the request and then answered with an HTTP 500, held its answer past the client's 5 s timeout, dropped the connection, or sent a body that was not JSON. We do not count any of them here. In each, the action *raised*, and Restate's documented retry re-ran it (default `RunOptions`). That is "retried until it succeeds" doing what it says. `RunOptions.max_attempts` is the documented way to stop it.

**Everything needed to disagree.**

- Repository: [keshav9926/drydock](https://github.com/keshav9926/drydock), commit `251e52d` for the runs; the rows are committed at the tag `v1`.
- Adapter: [`crashproof/adapters/restate.py`](https://github.com/keshav9926/drydock/blob/251e52d/crashproof/adapters/restate.py) (~580 lines), with its write-up in [`docs/adapters/restate.md`](https://github.com/keshav9926/drydock/blob/251e52d/docs/adapters/restate.md). The agent is shared with the DBOS and Temporal arms: [`pydantic_ai_agent.py`](https://github.com/keshav9926/drydock/blob/251e52d/crashproof/adapters/pydantic_ai_agent.py).
- Spec files: `bench/specs/week2_w1_shim.yaml`, `week2_w1_proxy.yaml` and `week2_w5.yaml`. Every trial cited here is seeded from 7 upward; the confirmation tier's seeds start at 100 000.
- Rows: `bench/results/v1_w1_shim/results.jsonl`, `v1_w1_proxy/…` and `v1_w5/…`, the release row sets.
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
  - The inactivity and abort timeouts change the freeze cell only, and not by a clean multiple: over its 30 rows the request was applied twice for freezes of 14.1–19.0 s and three times for 19.4–28.0 s, so the step sits between 19.0 s and 19.4 s and the longest freeze drawn produced three applications, not four. What the timeouts decide is whether a freeze is abandoned at all; with the documented defaults, none of these would have been.
  - The kill cells do not depend on any timeout. In the `dcdd533` transcript above the kill landed 13 ms after the receiver applied; `crashproof placement` over the release trials puts every shim-mode kill this arm fired inside the intended window — 30 of 30 in each of its `after:tool_effect`, `after:tool_return` and `before:tool_call` cells, 100 %. That output reads the W1 shim trials only: it covers neither the proxy `kill@after:tool_effect` cell nor the gated one, and nothing joins a trial's kill placement to the duplicate it produced. For those two we have the count and no placement behind it — at `251e52d` all four kill-after-effect cells applied twice, 30 of 30 each.
  - `RunOptions.max_attempts` was not set.
