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

## Status — phase 2 of 8: effects, ambiguity and ground truth

Phase 1 built the spine: the journal, lease = fence = heartbeat, pure-fold projections, memoized
re-execution, the per-class recovery table, the reaper predicate, the scripted provider and the MVP CLI.

Phase 2 builds the **referee**. Until now the runtime's own journal was the only witness to what happened
in the outside world, which is precisely the thing that cannot be trusted: a system that appears to recover
while quietly re-firing a side effect looks identical, from the inside, to one that recovers correctly.

- **The World** — deterministic mock services (`issues`, `kv`) behind one HTTP surface, with a receipt log
  that is **fsynced before the response is computed**, per-endpoint `dedup` / `natural`, `hold(endpoint, ms)`
  to aim a kill into the effect → acknowledgement window, and an **oracle** answering `applied`, `receipts`
  and `probe`. It is ground truth outside every runtime under test.
- **Both published bands of matrix v0**, measured end to end. `create_issue` is registered twice under one
  name, and the program cannot tell which it is calling.
- **The recovery table, completed.** A crash that abandons a `PURE` or `IDEMPOTENT` attempt now re-runs it
  under the same `effect_key` instead of failing the run — recovery is not retry.
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

One platform note: psycopg's async mode cannot run on Windows' default ProactorEventLoop, so every entry
point that opens a connection selects a compatible loop in `keel/core/aio.py`.

## Not yet built (and when)

Phase 3 is the make-or-break one: the `shim` injector, the supervisor and its trial-owned fault log, the
LangGraph adapter, the verifier (S1–S5, L1–L2) and **matrix v0** — the same faults, the same workload, the
same World, two runtimes, published. Phase 4 adds retries, timeouts→ambiguity and budgets; phase 5 VERIFY,
FORK and `model_reask_alternate`; phases 6–8 the hook boundaries, the Hypothesis state machine, statistics
and the published artifact. §27 is the binding staging table; nothing here is ahead of it.
