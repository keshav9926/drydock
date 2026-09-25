# Layout, and where it departs from §23.1

The package layout and its dependency rules, and every place the code departs from the file list in
[§23.1 of the specification](KEEL-ARCHITECTURE.md), each with its reason.

## The dependency rules

`keel/` never imports `crashproof/`. Inside `keel/` the direction is
`core ← events ← journal ← state ← runtime ← {effects, replay} ← agents ← {cli, client}`, with
`providers` beside `journal` (it imports `core` only): `runtime` imports only the layers below it —
`core`, `events`, `journal`, `state` and `providers` — and never `effects` or `replay`, so the step
engine decides recovery by effect class through `core/protocols.py`, with the TOOL executor registering
itself into `runtime.steps.EXECUTORS`. `state` has no I/O imports. `crashproof` touches `keel` in two
modules only: `adapters/keel.py` and `faults/injectors/hook.py`. `tests/unit/test_layering.py` enforces
all of it with an `ast` walk over every import.

## Departures from §23.1's file list

Most are merges: a split made before there is anything to split is boilerplate, and a file that only
re-exports is worse than a documented merge. The rest are modules §23.1 does not list, and pieces that
are not built.

### `keel/`

| §23.1 says | Here | Why |
|---|---|---|
| `state/{run,steps,effects,budget,approvals,children}.py` | `state/fold.py` | one flat dispatch over event types builds every projection; a projection splits out when it earns a module, as `plan` and `context` did |
| `state/checkpoints.py` (Future) | not built | projections fold from the journal, or from the latest continuation segment, in milliseconds at this scale |
| — | `state/{drift,spans}.py` | §18.6's drift detectors, and the OTel export's fold of a journal into spans (§19.7, V2) — both pure folds, so both belong in `state` |
| `runtime/{lease,scheduler,drain}.py` | `runtime/worker.py` | the claim loop, the heartbeat and the SIGTERM handler are twenty lines each and share all their state |
| `runtime/signals.py` | `runtime/steps.py` (`StepEngine._drain_inbox`) | the drain runs at every step boundary inside the engine's own append transaction and acts on the engine's fold — a cancel acknowledged at step *i*, the decision for the approval that parked — so everything it reads and writes is the engine's |
| `runtime/reaper.py`'s force-cancel takeover | `runtime/takeover.py` | two callers — the parent's step engine after `cancel_grace`, and the reaper for a stray whose parent is terminal — share one depth-first path, and neither owns it |
| `runtime/credentials.py` (v2) | not built | V2; tools read their declared secrets from the environment (`ToolCtx.credentials`) |
| — | `runtime/human.py` | a human's decision on a RESOLVED_UNKNOWN step (`keel signal --resolve`), applied at the drain |
| `effects/classes.py` | `effects/registry.py` (`ToolSpec._validate`) | the composition rules are five checks at registration, on the tool being registered |
| `effects/keys.py` | `core/hashing.py` | the key function lives beside the two other hashes, which is where `ctx` calls it |
| `effects/{table,resolution}.py` | `journal/protocol.py` + `runtime/steps.py` | the effects row is written inside the fenced append transaction, so it belongs to the journal; the resolution *policy* travels on the `ToolSpec` (`resolution`, `probe`) because `runtime` may not import `effects` |
| `effects/compensate.py` | `effects/registry.py` (`compensate_hook`, `compensation_spec`), `runtime/ctx.py` (`ctx.compensate`), `client.py` (`Keel.compensate`) | the undo is an ordinary TOOL step of its own tool, `<tool>.compensate`: a registration, one `ctx` call and one client call, with nothing new for the engine to execute |
| `effects/transactional.py` | not built | TRANSACTIONAL is cut with W4 (§29.1), and a tool that declares it is refused at registration |
| `replay/recover.py` | `runtime/steps.py` | the recovery table is consulted *by* the step engine, and §23.2's own dependency direction is `runtime ← replay`; moving it would invert the graph the layering test enforces |
| `replay/diff.py` | `replay/verify.py` | the step-sequence diff `keel diff` prints is the one VERIFY computes, beside it |
| `replay/fork.py` | not built | FORK is cut (§28.5's cut line) |
| — | `replay/fixtures.py` | recorded journals replayed as millisecond regression tests (`tests/journals/`) |
| `orchestration/{contracts,children}.py`, registering `StepExecutor(DELEGATE)` | `runtime/delegation.py` (the contract, its validation and schema grading, the `child_result` and `cancel` rows) + `runtime/steps.py` (`_spawn_children`, the drain's child results, fan-out slots) | the spawn is one fenced transaction ending in a park, and a child's result is applied at the parent's drain — the engine's transaction, fence and drain |
| `approvals/approvals.py`, registering `StepExecutor(APPROVAL)` | `runtime/ctx.py` (`ctx.approve`) + `runtime/steps.py` (`_park_for_approval`, the binding check, the decision at the drain) | a `StepExecutor` runs one attempt to one outcome. An APPROVAL step has no outcome in its attempt: it commits INTENT, STARTED, `APPROVAL_REQUESTED`, `RUN_WAITING` and the lease release in one fenced transaction and is completed by a later drain, so the engine dispatches the kind itself and `StepExecutor` is unchanged |
| `agents/{react,plan,compaction}.py` | `agents/demo.py` (the reference programs), `runtime/ctx.py` (`ctx.plan`, `ctx.compact`), `state/plan.py` | the plan and compaction are step kinds the engine executes and the fold projects, not programs; the programs the harness runs are one module |
| `providers/anthropic.py` | not built | no real provider ships; the `anthropic` extra in `pyproject.toml` is reserved for it and nothing imports it |
| `providers/replay_cache.py` | not built | it serves the real-model subset and FORK, neither built |
| — | `providers/pricing.py` | the pinned price table `max_usd` reserves against (§16.4) |
| `api/{app,routes,sse}.py` (FastAPI, SSE) | not built; `api/static/timeline.html` is | cut, second in §29.2's cut order — the static page alone gives a link |
| `cli/{run,runs,show,…,render}.py` (16 files) | `cli/main.py` | one Typer app; sixteen files of command wiring is scaffolding |
| — | `core/aio.py`, `journal/audit.py`, `journal/sql/0003–0005` | the Windows event-loop policy psycopg needs; §20.7's audit queries; the migrations that came with delegation, human resolution and per-attempt resolution |

### `crashproof/`

| §23.1 says | Here | Why |
|---|---|---|
| `world/services/{issues,email,payments,kv,fs}.py` | `world/services.py` | §11.1's own component table says `services.py`; the services are one endpoint table. `email`, `payments` and `fs` are not built: no workload uses them |
| `proxy/server.py` — a model-side, Anthropic-compatible front | `proxy/server.py` — the tool edge between the SUT and the World | §11.2's proxy mode is the black-box injector at the network edge. Model traffic never crosses it, so `mode: proxy` refuses model faults with that reason |
| `workloads/canonical_result.py` | `runner/trial.py` (collection) | the result is canonicalised where the trial collects it |
| `adapters/pydantic_ai/agent.py` | `adapters/pydantic_ai_agent.py` | one module: the shared agent all three engine arms run |
| `adapters/pydantic_ai/{temporal,dbos,prefect,restate}.py` | `adapters/{temporal,dbos,restate}.py` | one module per engine; `dbos.py` holds both its configurations (`native` and `pydantic_ai`). Prefect is not built |
| `adapters/{hatchet,inngest,julep}.py` (V2) | not built | V2, not started |
| `runner/collect.py` | `runner/trial.py` | collection is one step of a trial's lifecycle and shares its state |
| — | `runner/{bench,database,aio}.py`, `faults/process.py`, `demo.py` | the matrix runner; per-trial databases cloned from a template; the harness's event-loop policy; kill, freeze and resume on both platforms; the narrated demo |
| `verifier/{invariants,metrics}.py` | plus `verifier/views.py` | §19.5's placement view and effect ledger are *views* over the same `TrialFacts` the verdicts are computed from, not verdicts; `crashproof verify --placement` needs them without needing a verdict |
| `report/{matrix,markdown,html}.py` | plus `report/{compare,agreement,confirm,placement}.py` | a page per question: the pairwise comparison, the proxy/shim agreement, the confirmation plan, K3's placement |

### The command trees and exit codes

| §23.1 / §25 says | Here | Why |
|---|---|---|
| `crashproof compare a.jsonl b.jsonl --paired` (§25.3) | `crashproof compare <results-dir> --a <cell glob> --b <cell glob>` | a store is one append-only `results.jsonl`, not one file per cell, so a shell glob over filenames has nothing to match. The globs select cells instead. `--paired` is not a flag because pairing is the only mode: an unpaired comparison of two runtimes is not a weaker claim, it is a different one |
| §25.2 / §25.3 command trees | nine commands differ | declared and not built: `crashproof export`, `keel watch` (cut), `keel fork` (cut). Built and in neither tree: `crashproof workloads`, `crashproof agree`, `crashproof placement`, `crashproof confirm`, `keel reap`, `keel otel` (V2, after the tag). Those, and every flag-level difference in both directions, are in [`docs/cli-ledger.md`](cli-ledger.md) — a command tree is a contract, and an undocumented gap in one is the same defect as an `N/A` printed as `PASS` |
| §25.1 exit codes | wired, less one, plus one | `chaos`, `inject` and `bench` exit **7** on an invariant FAIL in any scored trial, and `compare --strict` exits **8** when nothing could be claimed. `verify` exits **9** when a row cannot be re-verified, a code §25.1 does not name. **5** (fenced) is never returned: every command that changes a run writes an inbox row, which nothing can fence, and a worker that loses its lease abandons that run and keeps running ([ledger](cli-ledger.md)) |

One platform note: psycopg's async mode cannot run on Windows' default ProactorEventLoop, so every entry
point that opens a connection selects a compatible loop in `keel/core/aio.py`.
