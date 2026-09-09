# drydock

Two things live here, and the second is the point of the first.

**`keel/`** — a single-node, event-sourced, agent-native durable execution runtime (Python, Postgres).
**`crashproof/`** — the fault-injection and conformance harness that runs Keel *and other runtimes*
through the same workloads under the same faults, and publishes a matrix. Built from phase 2.

> Framework checkpoints are snapshots; durable execution means someone notices the crash, resumes, and
> neither double-fires nor loses an effect. An agent that cannot survive `kill -9` is a demo.

The specification is [`docs/KEEL-ARCHITECTURE.md`](docs/KEEL-ARCHITECTURE.md). Its **Appendix A (design
constitution)** binds every decision here; where a section and the constitution disagree, the constitution
wins.

## Status — day 1 of 7: the spine

Journal, lease = fence = heartbeat, projections, memoized re-execution, the per-class recovery table,
the reaper predicate, the scripted provider, the effect registry, and the MVP CLI.

## Quickstart

```bash
uv sync --extra dev
docker compose up -d postgres
uv run keel db migrate --app keel.agents.demo:app
uv run python scripts/day1_demo.py       # start, kill -9, orphan, recover, resolve, complete
```

## What day 1 proves

`scripts/day1_demo.py` starts a real `keel worker`, kills it (`SIGKILL`) at the instant the effect has
landed at the receiver but its outcome has not been journaled, waits for `max(lease_expires_at,
attempt_deadline)`, and starts a second worker:

```
 seq  ep  event                 step  detail                          origin
   1   0  RUN_CREATED              -  tool_chain 1.0+73aaa3
   2   1  RECOVERY_STARTED         -  cause=START from_seq=1
   3   1  RECOVERY_COMPLETED       -  live_from_step=0 replayed_steps=0
   4   1  STEP_INTENDED            0  MODEL decide                     memo
   6   1  STEP_COMPLETED           0  {"text": "searching", ...}       memo
   7   1  STEP_INTENDED            1  TOOL search [PURE]               memo
   9   1  STEP_COMPLETED           1  {"hits": [...]}                  memo
  10   1  STEP_INTENDED            2  MODEL decide                     memo
  12   1  STEP_COMPLETED           2  {"text": "filing", ...}          memo
  13   1  STEP_INTENDED            3  TOOL create_issue [EXTERNAL]     recovered
  14   1  STEP_ATTEMPT_STARTED     3  attempt=1 deadline=+1s           recovered   <- kill -9 here
  15   2  RECOVERY_STARTED         -  cause=ORPHANED from_seq=14
  16   2  STEP_AMBIGUOUS           3  cause=crash                      recovered
  17   2  STEP_RESOLVED            3  RESOLVED_COMPLETED via probe     recovered
  18   2  RECOVERY_COMPLETED       -  live_from_step=4 replayed_steps=4
  19   2  STEP_INTENDED            4  MODEL decide                     live
  22   2  RUN_COMPLETED            -  {"answer": "filed the issue"}

receiver saw 1 receipt(s) - no duplicate effect
```

Two work sessions; three steps returned from the journal without a model call or a tool execution; the
one step whose outcome the crash destroyed is marked **ambiguous** and *resolved against the receiver*
rather than guessed; the live step is the only one that costs anything.

## Tests

```bash
uv run pytest tests/unit -q                                   # no database needed
KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel \
  uv run pytest tests/integration -q                          # the four control-plane statements
```

`tests/unit/test_fence.py` is the day-1 risk test: two workers, one run, exactly one appends. It was
written before the worker loop, because a missing conjunct in the fence or the acquire predicate produces
a system that looks correct until day 3 and then fails `pause_past_ttl` in a way that is indistinguishable
from a real finding.

## Layout, and where it departs from §23.1

`keel/` never imports `crashproof/`; `keel/runtime` imports no sibling package (executors register
themselves through `core/protocols.py`); `keel/state` has no I/O imports. `tests/unit/test_layering.py`
enforces all of that.

Three deliberate departures from the file list in §23.1, each because the split would be boilerplate
before it is structure:

| §23.1 says | Here | Why |
|---|---|---|
| `state/{fold,run,steps,effects,context,views}.py` | `state/{fold,views}.py` | the MVP fold is one flat dispatch; it splits when a projection earns its own module |
| `runtime/{lease,scheduler,drain}.py` | folded into `runtime/worker.py` | the claim loop, the heartbeat and the SIGTERM handler are twenty lines each and share all their state |
| `cli/{run,runs,show,...}.py` (11 files) | `cli/main.py` | one Typer app; eleven files of command wiring is scaffolding |

`effects/keys.py` does not exist either: `effect_key()` lives in `core/hashing.py`, which is where `ctx`
computes it.

One platform note: psycopg's async mode cannot run on Windows' default ProactorEventLoop, so every entry
point that opens a connection selects a compatible loop in `keel/core/aio.py`.

## Not yet built (and when)

Day 2: the World + oracle, the effects table's resolution paths, property tests. Day 3: the shim
injector, the LangGraph adapter, matrix v0. Days 4–7: retries and budgets, VERIFY/FORK, the hook
boundaries and the Hypothesis suite, the demo and the published matrix. §27 is the binding staging
table; nothing here is ahead of it.
