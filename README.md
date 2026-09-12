# drydock

Two things live here, and the second is the point of the first.

**`keel/`** — a single-node, event-sourced, agent-native durable execution runtime (Python, Postgres).
**`crashproof/`** — the fault-injection and conformance harness that runs Keel *and other runtimes*
through the same workloads under the same faults, and publishes a matrix.

> Framework checkpoints are snapshots; durable execution means someone notices the crash, resumes, and
> neither double-fires nor loses an effect. An agent that cannot survive `kill -9` is a demo.

The specification is [`docs/KEEL-ARCHITECTURE.md`](docs/KEEL-ARCHITECTURE.md). Its **Appendix A (design
constitution)** binds every decision here; where a section and the constitution disagree, the constitution
wins.

## Status — phase 5 of 8: replay as a first-class mode

Every phase so far asked whether a runtime reached the right answer. This one asks whether it got
there the way its own history says it did — and builds the fault that makes the difference visible
from outside the runtime.

```bash
uv run keel replay $RUN --verify              # no lease, no tokens, no effects
uv run keel diff $RUN_A $RUN_B                # where two runs stop agreeing, step by step
uv run keel events $RUN --json > tests/journals/name.jsonl   # capture a regression test
uv run crashproof bench --matrix bench/specs/reask_alternate.yaml
```

**[`bench/reports/reask_alternate.md`](bench/reports/reask_alternate.md)** — 6 cells, 30 seeds,
**180 trials**, none void. One fault: `kill @ after:tool_effect` composed with
`model_reask_alternate @ before:model_call`.

| arm | diverged | dup_eff | +calls | C1 |
|---|---|---|---|---|
| `keel.default` | **0/30** | 0 | 0 | PASS |
| `langgraph.async` | **30/30** | **0** | 2 | N/A |
| `langgraph.sync` | **30/30** | 30 | 0 | N/A |

Read the middle row slowly. `langgraph.async` has **zero duplicate effects** and zero missing
required effects — every safety invariant published in matrix v0 and tier1a scores it clean. It also
filed a *different issue*, in all thirty trials: the checkpoint did not survive the kill, the model
nodes re-ran, the re-asked question returned the node's declared `alternate`, and the runtime created
"CI flake (rephrased)" alongside the issue its first incarnation had already created. Two issues,
neither applied twice, so nothing that counts duplicates can see it.

`duplicate_effects` answers "did this effect happen more than once". It cannot answer "did a
different effect happen instead", and after a crash those are both ways of being wrong.

Keel diverged in none of the thirty — not because the fault was weaker against it, but because it
never re-asked a question it had already answered, so the armed alternate was never served at a node
that declares one. **A runtime that memoizes is invisible to this fault by being correct.**

The pieces: **VERIFY** as the memoization loop with `allow_live=False` — the same loop, one flag, not
a second replayer that would drift from it silently; the **logical projection hash** of §10.5, which
normalises `RESOLVED_COMPLETED` to `COMPLETED` so a run that crashed four times and probed its way to
the answer hashes equal to one that never crashed; the **`replays` row**, because VERIFY appends
nothing and without it a pass is a log line; **journal fixtures** that replay a recorded run against
current code in under 5 ms with no database and no provider key; and **C1**, which is N/A rather than
PASS for a runtime with no journal — a framework with nothing to reproduce must not score the
cleanest column.

FORK is cut, by §28.5's own cut line rather than by choice.

## Phase 4: ambiguity

A crash is the easy fault. Phase 4 is the one where the process stays alive and the *answer* goes
missing — the request left, the receiver applied it, and nothing came back. Retrying is how correct
systems duplicate effects; failing is how they abandon work that already happened.

```bash
uv run crashproof bench --matrix bench/specs/tier1a.yaml --out bench/results/tier1a
uv run crashproof report  bench/results/tier1a --out bench/reports/tier1a.md
uv run crashproof compare bench/results/tier1a --a 'keel.*' --b 'langgraph.sync.*'
```

**[`bench/reports/tier1a.md`](bench/reports/tier1a.md)** — 32 cells, 30 seeds, **960 trials**, none
void, seven faults that never touch the process. Duplicate *applied* effects, `EXTERNAL` band
(`issues.create`, `dedup: false`, no key), out of 30 seeds:

| (fault, boundary) | keel | langgraph sync |
|---|---|---|
| `tool_timeout@before:tool_call` | **0** | **30** |
| `tool_500@after:tool_effect` | **0** | **30** |
| `sigterm_grace_ok@after:tool_effect` | **0** | **30** |
| `sigterm_grace_too_short@after:tool_effect` | **0** | **30** |
| `tool_delay@after:tool_effect` | 0 | 0 |
| `model_timeout@before:model_call` | 0 | 0 |
| `model_500@before:model_call` | 0 | 0 |

None of these faults kills anything. In the first two the request left the process, the World applied
it, and the answer never came — and LangGraph's tool task re-runs on resume and files the issue again,
every trial. Keel's step is `RUNNING` with an EXTERNAL effect and no outcome, which the recovery table
calls `STEP_AMBIGUOUS` rather than a retry; the declared resolution asks the receiver what happened
instead of guessing.

The two `sigterm_grace_*` rows are the same fault at two grace periods — 3 s, longer than any arm's
step timeout, and 150 ms, shorter than the shortest step. A runtime with a drain path should behave
differently in the two cells. LangGraph scores them **identically**, because there is no drain path to
give grace to: a polite shutdown and a kill are the same event. That is §27's line about deploys
arriving as a measurement rather than an assertion.

`tool_delay` is the cell where the pin is the whole story. Keel's one-second tool timeout fires inside
the two-second delay, so the step is ambiguous in both bands — and the *declared resolution* decides
what happens next: EXTERNAL probes the receiver and re-sends nothing (0 duplicate receipts),
IDEMPOTENT re-issues under the same key (30). Two different correct answers to one fault, chosen by
the effect class. LangGraph does not appear in the row at all: it declares no step timeout and waits
the delay out.

In the `IDEMPOTENT` band both arms duplicate **0** effects. Keel gets no credit for that zero —
re-issuing under the same key is the correct response to an ambiguity, and it is the receiver that
made it safe. Both columns are printed so the distinction cannot be blurred.

**[`bench/reports/compare_tier1a_keel_vs_langgraph_sync.md`](bench/reports/compare_tier1a_keel_vs_langgraph_sync.md)**
— 480 paired trials: `duplicate_effects` 0 vs 120, `logical_correctness` A better at p < 0.0001 over
120 discordant pairs. Four of nine rows decline to claim anything, including one that would have
flattered Keel — median recovery latency 143 ms against 2 326 ms is tagged *not claimable*, because
the arm it beats has a supervisor re-invoking it and therefore no detection time to spend.

Tokens are counted by the harness at `before:model_call`, in every arm, by one function — charged when
the request is sent, not when it returns, because an attempt that never came back was still billed.
Keel's clean run costs 280 tokens of prompt to LangGraph's 163: a real cost of carrying a full message
history where the other carries a state dict. After a fault that does not touch the model both are
**+0**, because a synchronous checkpoint restores the state without re-deciding — LangGraph duplicates
the effect without paying for a second decision.

The pieces: a **retry policy** with full jitter, clamped inside the lease and off by default;
**reserve-then-settle budgets** where an attempt nobody heard back from stays charged forever, which
is what makes the journaled spend an upper bound on the bill; `UnknownOutcome` and `Rejected`, so the
step engine routes on the *effect class* rather than the status code; a `tool_timeout` armed **at the
receiver**, so the effect really lands and the answer really never comes; and `crashproof compare`,
which counts safety, estimates liveness, and says *too noisy to claim* out loud.

## Phase 3: the matrix

Phase 1 built the spine, phase 2 built the referee. Phase 3 points a saboteur at the runtime and
publishes what the referee saw.

```bash
uv run crashproof bench --matrix bench/specs/matrix_v0.yaml --cells 'keel.*'
uv run crashproof report bench/results/latest --out bench/reports/matrix_v0.md
```

**[`bench/reports/matrix_v0.md`](bench/reports/matrix_v0.md)** — 40 cells, 30 seeds, **1 200 trials**,
four runtime configs, two bands, every arm running the same spec. Every safety invariant held in every
scored trial; no counterexamples.

Duplicate *applied* effects, `EXTERNAL` band (`issues.create`, `dedup: false`, no key), out of 30 seeds:

| (location, fault) | keel | langgraph sync | async | exit |
|---|---|---|---|---|
| `before:tool_call` | 0 | 0 | 0 | 0 |
| `after:tool_effect` | **0** | **30** | **30** | **30** |
| `after:tool_return` | **0** | **30** | **30** | **30** |
| `pause_past_ttl` | **11** | 0 | 0 | 0 |

The middle two rows are the thesis. A kill between the effect landing and the outcome being recorded
duplicates the issue in every LangGraph trial and in none of Keel's — the journal remembers that the
attempt started, so the successor asks the receiver instead of guessing. S1 is PASS for all four
columns, because LangGraph claims `at_least_once` and is held to that; the duplicate is printed anyway.

The last row is the honest cost. Under a worker frozen past its lease, Keel duplicated in **11 of 30**
trials — the residual window the constitution names and refuses to claim away, since a fence protects
the journal and cannot reach a third party. In the `IDEMPOTENT` band the same freeze produced 10
re-sends and **0** duplicate effects: the key travels, and the receiver does the rest. LangGraph's
zombie column is 0 for a different reason — with no successor, nothing takes over while it is frozen,
so nothing races it.

Model calls are counted at the wire, identically for every arm, so the economy column exists for
runtimes that keep no tally of their own. After a kill at `after:tool_effect`: `+0` for Keel and
LangGraph `sync`, **`+2`** for `async` and `exit`, which re-run model calls the checkpoint did not save.

The pieces: a **fault spec** addressed by workload landmarks rather than ordinals in any one
runtime's traffic; a pure **seeded expansion** where all of a trial's randomness lives; a **trial
directory** that is firing state outliving the process it belongs to; a **shim** that fires the same
three instants inside every runtime; a **supervisor** that restarts with identical argv and env and
never says what to resume; a **verifier** that is a pure function from four logs to a verdict; and a
**report** that prints safety and estimates differently because they are different kinds of claim.

## Phase 2: effects, ambiguity and ground truth

Phase 2 built the **referee**. Until now the runtime's own journal was the only witness to what happened
in the outside world, which is precisely the thing that cannot be trusted: a system that appears to recover
while quietly re-firing a side effect looks identical, from the inside, to one that recovers correctly.

- **The World** — deterministic mock services (`issues`, `kv`) behind one HTTP surface, with a receipt log
  that is **fsynced before the response is computed**, per-endpoint `dedup` / `natural`, `hold(endpoint, ms)`
  to aim a kill into the effect → acknowledgement window, and an **oracle** answering `applied`, `receipts`
  and `probe`. It is ground truth outside every runtime under test.
- **Both published bands of matrix v0**, measured end to end. `create_issue` is registered twice under one
  name, and the program cannot tell which it is calling.
- **The recovery table, completed.** A crash that abandons a `PURE` or `IDEMPOTENT` attempt re-runs it
  under the same `effect_key` instead of failing the run, and a `probe` that comes back `ABSENT` takes the
  same edge: the receiver has said the effect never landed, so there is nothing to guess about. Recovery
  is not retry.
- **Drain on SIGTERM** hands the run back at a step boundary rather than holding it until the lease lapses.
- **Property tests** — the fold, the effect key and the step machine, on `MemoryJournal` + `FakeClock`.

## Quickstart

```bash
uv sync --extra dev
docker compose up -d postgres
uv run keel db migrate --app keel.agents.demo:app
uv run python scripts/day2_demo.py       # the World, a kill inside the window, and both bands
```

## What phase 2 proves

`scripts/day2_demo.py` starts a real World and a real `keel worker`, and kills the worker (`SIGKILL`) at the
instant the World has durably receipted the effect and the journal has no outcome for it. Then it runs the
identical program against a receiver that deduplicates.

**Band 1 — `EXTERNAL` against `issues.create` (`dedup: false`).** Nobody honours a key, so the runtime may
not re-fire on a guess:

```
   9   1  STEP_COMPLETED           1  {"hits": ["flaky test in ci #1", …]}             memo
  12   1  STEP_COMPLETED           2  {"text": "filing", …}                            memo
  13   1  STEP_INTENDED            3  TOOL create_issue [EXTERNAL]                     recovered
  14   1  STEP_ATTEMPT_STARTED     3  attempt=1 deadline=11:27:16                      recovered  <- kill -9
  15   2  RECOVERY_STARTED         -  cause=ORPHANED from_seq=14
  16   2  STEP_AMBIGUOUS           3  cause=crash                                      recovered
  17   2  STEP_RESOLVED            3  RESOLVED_COMPLETED via probe                     recovered
  18   2  RECOVERY_COMPLETED       -  live_from_step=4 replayed_steps=4
  22   2  RUN_COMPLETED            -  {"answer": "filed the issue"}

step  tool          class     status              resolution  external_ref
 3     create_issue  EXTERNAL  RESOLVED_COMMITTED  probe       issues.create#1

World  issues.create#1  receipts=1  applied=1        no duplicate effect
```

**Band 2 — `IDEMPOTENT` against `issues.upsert` (`dedup: true, natural: true`).** The same program, the
same crash, the same instant — disposed differently. The effect *is* re-sent, under the same key, and the
receiver applies it once:

```
  13   1  STEP_INTENDED            3  TOOL create_issue [IDEMPOTENT]                   recovered
  14   1  STEP_ATTEMPT_STARTED     3  attempt=1 deadline=11:27:28                      recovered  <- kill -9
  15   2  RECOVERY_STARTED         -  cause=ORPHANED from_seq=14
  16   2  STEP_FAILED              3  attempt_abandoned retryable=True                 recovered
  17   2  STEP_ATTEMPT_STARTED     3  attempt=2 deadline=11:27:35                      recovered
  18   2  STEP_COMPLETED           3  {"id": "40dca813715d", "url": "world://issues…"} recovered

step  tool          class       status     resolution  external_ref
 3     create_issue  IDEMPOTENT  COMMITTED  -           issues.upsert#1

World  issues.upsert#1  receipts=2  applied=1        no duplicate effect
```

Two receipts and one application is the whole argument for effect classes: **idempotency is a property of
the receiver, not of the caller.** The runtime's job is to keep the key stable across the crash and to be
honest when there is no key to keep.

## The World

```bash
uv run crashproof world --port 8600 --dedup issues.create=false --hold issues.create=150
curl :8600/oracle/applied      # {"issues.create#1": 1}
```

| Accounting | Question it answers | Metric |
|---|---|---|
| `receipts` | how many times was the receiver *asked*? | `duplicate_receipts` |
| `applied` | how many times did the world actually *change*? | `duplicate_effects`, which S1 reads |

The gap between the two is exactly what a receiver's idempotency buys, and it is why `dedup` and `natural`
are declared per endpoint: one workload measures "honours keys", "naturally idempotent" and "neither".

The ordering inside `World.receive` is the instrument and is tested first
(`tests/unit/test_world.py::test_receipt_is_durable_before_the_response_is_computed`): the receipt is
written and `fsync`ed **before** the effect is applied or a response computed. If it were not,
`after:tool_effect` would be a guess and every cell built on it would inherit the ambiguity.

## Tests

```bash
uv run pytest tests/unit tests/property -q                    # no database needed
KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel \
  uv run pytest tests/integration -q                          # the control-plane statements, trial clones
```

| File | What breaks if it fails |
|---|---|
| `tests/unit/test_fence.py` | two workers, one run, exactly one appends |
| `tests/unit/test_recovery.py` | both bands end to end, plus drain at a step boundary |
| `tests/unit/test_world.py` | the receipt ordering, dedup semantics, the oracle |
| `tests/unit/test_faults.py` | one (spec_hash, seed) is one schedule; firing state survives a kill |
| `tests/unit/test_verifier.py` | judged against claims, N/A where an input is missing, never a proportion |
| `tests/unit/test_shim.py` | the shim fires the same three instants, in order, in every arm |
| `tests/unit/test_retry_budget.py` | a retryable failure is retried and an ambiguity is not; the reservation of an attempt with no outcome is never released |
| `tests/unit/test_compare.py` | pairing, McNemar over discordant pairs only, and the detection-bound tag |
| `tests/unit/test_verify.py` | VERIFY writes nothing; a recovered run hashes like a clean one; a reordered program fails with the step named |
| `tests/unit/test_journal_fixtures.py` | every recorded journal in `tests/journals/` still agrees with the program |
| `tests/unit/test_reask_alternate.py` | the modifier is refused alone; the provider has no ask counter; identities separate "twice" from "something else" |
| `tests/unit/test_matrix_spec.py` | matrix v0's arithmetic, which is a published claim |
| `tests/unit/test_layering.py` | the architecture, as an assertion |
| `tests/property/test_fold_props.py` | determinism, incremental == batch, prefix monotonicity, blobs |
| `tests/property/test_key_props.py` | the effect key: stable, unique, fork-distinct, credential-blind |
| `tests/property/test_step_machine_props.py` | the recovery table, per class, against the World |
| `tests/integration/` | the same claims against a real database, and per-trial template clones |

The property files drive the *real* runtime over `MemoryJournal` + `FakeClock` and take its journal — random
event lists would be rejected by the fold and would prove nothing. The crash is a `CancelledError` raised
inside the tool after the effect has landed, which is the exact shape of the window and needs no sleeps.

## Layout, and where it departs from §23.1

`keel/` never imports `crashproof/`; `keel/runtime` imports no sibling package (executors register
themselves through `core/protocols.py`); `keel/state` has no I/O imports. `tests/unit/test_layering.py`
enforces all of that, including that `crashproof` touches `keel` in two modules only.

Deliberate departures from the file list in §23.1, each because the split would be boilerplate before it is
structure. Adding a file that only re-exports is worse than a documented merge:

| §23.1 says | Here | Why |
|---|---|---|
| `state/{fold,run,steps,effects,context,views}.py` | `state/{fold,views}.py` | the MVP fold is one flat dispatch; it splits when a projection earns its own module |
| `runtime/{lease,scheduler,drain}.py` | folded into `runtime/worker.py` | the claim loop, the heartbeat and the SIGTERM handler are twenty lines each and share all their state |
| `cli/{run,runs,show,...}.py` (11 files) | `cli/main.py` | one Typer app; eleven files of command wiring is scaffolding |
| `effects/keys.py` | `core/hashing.py` | the key function lives beside the two other hashes, which is where `ctx` calls it |
| `replay/recover.py` | `runtime/steps.py` | the recovery table is consulted *by* the step engine, and §23.2's own dependency direction is `runtime ← replay`. Moving it would invert the graph the layering test enforces |
| `effects/{table,resolution}.py` | `journal/protocol.py` + `runtime/steps.py` | the effects row is written inside the fenced append transaction, so it belongs to the journal; the resolution *policy* travels on the `ToolSpec` (`resolution`, `probe`) because `runtime` may not import `effects` |
| `world/services/{issues,kv}.py` | `world/services.py` | §11.1's own component table says `services.py`; the two services are one endpoint table and forty lines of semantics |
| `crashproof compare a.jsonl b.jsonl --paired` (§25.2) | `crashproof compare <results-dir> --a <cell glob> --b <cell glob>` | a store is one append-only `results.jsonl`, not one file per cell, so a shell glob over filenames has nothing to match. The globs select cells instead, which is the same selection expressed against the thing that exists. `--paired` is not a flag because pairing is the only mode: an unpaired comparison of two runtimes is not a weaker claim, it is a different one |
| §25.2 exit codes | same, now wired | `chaos`, `inject` and `bench` exit **7** on an invariant FAIL in any scored trial, and `compare --strict` exits **8** when nothing could be claimed. A harness whose failure mode is red text in a log nobody reads is not a CI gate |

One platform note: psycopg's async mode cannot run on Windows' default ProactorEventLoop, so every entry
point that opens a connection selects a compatible loop in `keel/core/aio.py`.

## Not yet built (and when)

Phases 6–8 the hook boundaries, the Hypothesis
state machine, statistics and the published artifact. Inside phase 4 itself, three things are named
rather than stubbed: `max_usd` and `max_wall_clock` (they need a pinned price table and a deadline
every waiting kind respects); backoff longer than the lease (it needs `RUN_WAITING` and the signals
inbox, both v1); and Holm–Bonferroni across families, which arrives with the rest of the statistics
module. §27 is the binding staging table; nothing here is ahead of it.
