# drydock

[![ci](https://github.com/keshav9926/drydock/actions/workflows/ci.yml/badge.svg)](https://github.com/keshav9926/drydock/actions/workflows/ci.yml)

**Keel** is a durable execution runtime for AI agents: single-node, event-sourced, on Postgres. It
journals every model decision and every tool effect before it matters, so a worker can be killed at any
instant and a different process finishes the run — without re-deciding what was decided, and without
silently re-doing an effect that already happened.

**Crashproof** is the harness that tests that claim, and the same claim for other runtimes. It runs
identical agent workloads under identical faults against a receiver that keeps its own ledger of every
request, and judges each runtime against what that runtime *declares* it guarantees.

Keel is the reference implementation that has to pass its own harness. Both are built from one
specification, [`docs/KEEL-ARCHITECTURE.md`](docs/KEEL-ARCHITECTURE.md), whose Appendix A is the design
constitution.

> A framework checkpoint is a snapshot. Durable execution means someone notices the crash, resumes, and
> neither double-fires nor loses an effect. An agent that cannot survive `kill -9` is a demo.

## The problem, in one command

```bash
uv sync --extra dev --extra langgraph && docker compose up -d postgres
uv run crashproof demo
```

A real worker, a real Postgres and a real HTTP receiver that fsyncs its receipt **before** it computes a
response. The worker is killed at the one instant where the receiver has the effect and the journal does
not. Every line is read back from the trial's own artefacts — journal, receipt log, fault log, verdicts —
not narrated by the code that ran it:

```
──────────────────────────────────── BEFORE CRASH ────────────────────────────────────
[7]  STEP_ATTEMPT_STARTED #3 attempt 1 seq 14   — the write-ahead barrier: no receipt may precede this seq
[8]  World receipt issues.create#1  ·  1 request(s) received before the cut
[9]  fault kill @ after:tool_effect  landmark tool:create_issue  → fault-log row fsync → process gone
     at the cut: last committed seq 14 · open step 3.1 · no outcome · World's last receipt issues.create#1
─────────────────────────────────── AFTER RESTART ────────────────────────────────────
[12] RECOVERY_STARTED{cause=ORPHANED, from_seq=14} seq 15   — a different process, told nothing
[13] re-execution: 4 steps returned from the journal  — 0 model calls, 0 World calls, 0 tokens
[14] #3 STARTED without an outcome, class EXTERNAL  → STEP_AMBIGUOUS seq 16   — the runtime does not guess
[15] probe → the receiver is asked, not assumed: probe says COMMITTED
     STEP_RESOLVED{RESOLVED_COMPLETED} seq 17   — resolved, never re-fired
[17] World after the restart: 0 further receipt(s) for issues.create#1   — the effect was never re-sent
```

The same command, fault, landmark, receiver and seed, against another runtime
(`uv run crashproof demo --adapter langgraph --config sync`):

```
[4]–[7] no journal exposed. This runtime keeps a checkpoint, not an event log …
[13] resume re-runs the interrupted node; whether that re-fires the effect is what the
     World's receipt count below answers
[18] World: receipts(issues.create#1)=2  applied=2   ·  duplicate_effects=1
```

Neither arm failed an invariant: LangGraph declares at-least-once for this kind of effect and is judged
against that. The duplicate is its documented cost, and it is printed. That rule — every runtime judged
against its own declared guarantee, every raw count published regardless — is what the whole matrix is
built on. CI diffs the demo's printed lines on every commit.

## What it measured

The release matrix is **18 540 trials at one commit** (`251e52d`): 448 cells × 30 seeds (13 440
screening trials), plus 17 cells re-run at n = 300 on fresh seeds (5 100 confirmation trials) — the six
whose screening result was not unanimous, Keel's cell at the same trigger, and each one's baseline. It
covers eight configurations of five runtimes, each pinned in every row:

| runtime | configurations | version |
|---|---|---|
| Keel | journal on Postgres | 0.1.0 (this repository) |
| LangGraph | `sync`, `async`, `exit` durability, `AsyncPostgresSaver` | langgraph 1.2.11 |
| DBOS | native steps, and Pydantic AI under `DBOSDurability` | dbos 2.31.1 |
| Temporal | Pydantic AI under `TemporalDurability` | temporalio 1.33.0, server 1.32.0 |
| Restate | Pydantic AI through `RestateAgent` (Linux, under WSL2) | restate-sdk 1.0.5, server 1.7.10 |

Every row is one JSON object carrying its own `(spec_hash, seed, keel_commit, config_pin)`, committed
under [`bench/results/`](bench/results); every published page is a pure function of those rows and is
re-rendered byte-for-byte by CI. Before publication all 18 540 rows were re-verified from their own trial
directories. The pages: [`v1_w1_shim`](bench/reports/v1_w1_shim.md) ·
[`v1_w1_proxy`](bench/reports/v1_w1_proxy.md) · [`v1_w5`](bench/reports/v1_w5.md) ·
[`v1_w5_pre`](bench/reports/v1_w5_pre.md) · [`v1_reask`](bench/reports/v1_reask.md) ·
[`v1_w3`](bench/reports/v1_w3.md) · [`v1_w7`](bench/reports/v1_w7.md), plus 21 pairwise
`compare_v1_*` pages and the [proxy/shim agreement](bench/reports/agreement_v1.md) page.

A row marked `valid: false` is void — its fault never fired, it recorded a fault that did not happen, or
the store's clock moved more than 50 ms against the host's during the trial — and no verdict counts it.
349 of the 18 843 committed rows are void: 303 are attempts that a re-take at the same seed superseded,
and 46 are the last word on their trial, all in `langgraph.exit`'s two proxy `kill@after:tool_return`
cells, where the outside kill races the process's own exit ([K7](#kill-criteria)). Eight void rows carry a
FAIL their artefacts produced — five S4s in Keel rows whose store clock moved, three L1s whose fault never
fired — and all eight were re-taken and pass.

### The window a journal written after the effect leaves open

The `EXTERNAL` band: `issues.create`, a receiver that cannot deduplicate and is sent no key — an email, a
legacy API. Extra applications of the one effect the run makes (Σ `duplicate_effects`), over the trials of
each cell, in shim mode:

| fault | Keel | DBOS native · Pydantic AI | LangGraph ×3 | Temporal | Restate |
|---|---|---|---|---|---|
| kill before the request is sent | 0 / 30 | 0 / 30 · 0 / 30 | 0 / 30 each | 0 / 30 | 0 / 30 |
| kill after the receiver applied it | **0 / 30** | **30 / 30 · 30 / 30** | **30 / 30 each** | **30 / 30** | **30 / 30** |
| kill after the tool returned | **0 / 300** | 239 / 300 · 204 / 300 † | **30 / 30 each** | **30 / 30** | **30 / 30** |
| worker frozen past its lease | **97 / 300** | 0 / 30 · 0 / 30 | 0 / 30 each | **47 / 30** | **45 / 30** |

The middle rows are the thesis. A runtime that commits its record of a step *after* the effect has left the
process has a window in which the effect exists and the record does not; killed there, it runs the step
again. Keel commits a write-ahead record (`STEP_ATTEMPT_STARTED`) before the effect and, finding it open
with no outcome, does not re-send blindly — it asks the receiver (a probe) and records what it learns.

The last row is the cost, and Keel's share of it is named rather than hidden. A lease fence protects the
journal; it cannot reach a third party. A worker frozen past its lease — after its write-ahead record,
before its request is sent — is replaced; the successor finds the attempt open and resolves it; and when
the frozen process thaws, its request still goes out: 97 of 300 trials, 0.32 extra applications a trial.
In proxy mode, where the request is also held at the proxy and released at the thaw, after the
successor's re-attempt, it is 30 of 30, and the proxy compare pages print that cell as a difference
*against* Keel: logically correct in 0 of 30 trials, against 30 of 30 for DBOS ×2 and LangGraph ×3.
Keel therefore declares `EXTERNAL` effects **at-least-once** and is judged against that. The fix is the one this design exists to
enable: send a key. In the `IDEMPOTENT` band — the same freeze, a receiver that deduplicates on
`effect_key` — Keel's frozen trials re-send 18 times and apply **0** extra. LangGraph and DBOS read 0 in the
last row for a different reason: nothing replaces a frozen holder, so nothing races it.

† DBOS writes its step checkpoint on an executor thread that races an in-process kill: at that trigger only
47–70 % of kills land inside the intended window at screening and 68–80 % at n = 300, where every other
arm's tool-boundary kills land 100 % inside
([placement](bench/instrument/placement_v1_w1_shim.md), [n = 300](bench/instrument/placement_v1_w1_shim_confirm.md)).
Those DBOS cells measure the kill's timing as much as DBOS, so they are exploratory and not bolded
([K3](#kill-criteria)).

### Everything else the matrix found

- **Keel fails no safety invariant in any of the 448 cells.** The only configuration with safety failures
  is Restate: S1 in 14 cells (5 shim, 7 proxy, 1 approval, 1 re-ask), judged against its own documented
  claim that "tool side effects are not duplicated". The finding is filed upstream as
  [restatedev/docs-restate#410](https://github.com/restatedev/docs-restate/issues/410), with a clean-clone
  reproduction on restate-server 1.7.10 and 1.7.12.
- **Behind a human approval (W5).** Killed while parked on an approval and then granted, every one of the
  eight configurations deploys exactly once, 30 of 30. Killed after the gated deploy has landed, every
  configuration but Keel deploys twice, 30 of 30. Under an approval that expires, Keel, both DBOS
  configurations, Temporal and Restate complete with nothing deployed, 30 of 30; LangGraph's `interrupt()` has no deadline, so all three LangGraph
  configurations are still waiting at the 60 s trial timeout.
- **Effects before an interrupt (W5-pre).** LangGraph re-runs the interrupting node on resume, so an ungated
  notification before the approval fires again: twice in every baseline trial (330 of 330 for `sync`
  across both tiers), three times when killed while parked, and three times in 2 of 330 `sync` trials
  under a delayed approval with no kill at all. No other configuration re-sends it.
- **Faults that do not kill.** Keel ends logically correct in 30 of 30 under a 5xx from the tool, a tool
  timeout, a 5xx from the model, a model timeout and a sustained provider outage. Under the tool's 5xx and
  timeout, LangGraph ×3, Temporal and Restate re-send the `EXTERNAL` call and create the issue twice, 30 of
  30. DBOS runs with step retries off (its default), so it ends FAILED under the tool's 5xx, the tool
  timeout, the model's 5xx and the outage.
- **Re-asking the model after a crash (the re-ask cell).** When a crashed runtime re-asks the model and the
  model answers differently: LangGraph `async` and `exit` re-ask (about two extra model calls a trial) and file
  a second, different issue beside the first, 30 of 30. DBOS ×2, Temporal, Restate and LangGraph `sync`
  re-ask nothing but re-fire the same tool, 30 of 30. Keel re-asks nothing and re-fires nothing: the journal
  is the memo.
- **Long horizon and streaming, Keel only (W3, W7).** Fifty rounds with compactions, plan updates, a durable
  sleep and continuation boundaries; and streamed model answers under kills mid-stream, truncated streams
  and re-asks. 16 cells, 480 trials: every invariant held, all 480 completed, 0 duplicate effects.
- **What n = 300 showed that n = 30 did not.** DBOS at `after:tool_return` fails liveness in 2 of 300
  (`native`) and 1 of 300 (Pydantic AI) trials, where screening read 30 of 30. Keel's frozen-worker
  residual is 97 of 300, where screening read 4 of 30. And two Keel trials ended FAILED. Seed 100067: a
  step probed `ABSENT`, re-attempted, and gone ambiguous again could not be probed a second time, because
  a unique index keyed the resolution per step rather than per attempt — fixed, with the specification
  amended; re-run at the fix, that trial completes. Seed 100099, a proxy-mode baseline: the read-only
  `kv.search` timed out three times under host load and the retry policy gave up, as it is built to;
  nothing was applied twice, and re-run, that trial completes.

### Keel against its own write path

The matrix measures what every runtime exposes. Keel's own journal protocol is also tested where no
outside instrument can reach — inside single transactions:

- **66 white-box cells** at **17 named hook boundaries** inside the write path, the inbox drain, the
  approval park and the delegation spawn, per effect class: **54 run, 12 N/A with the reason, 0 failed**
  ([`bench/keel_conformance/table.md`](bench/keel_conformance/table.md)). Published beside the matrix and
  never unioned with it — a boundary only one runtime exposes is not a fair column. Each cell prints what
  the journal and the receiver held at the instant of the fault and how the successor closed the step.
  The table judges three verdicts the matrix cannot: S8 over the whole tree of journals (the matrix
  collects one per trial), S9 — a run is never charged less than the provider billed — and S10, no
  receipt for a write-ahead record the journal refused.
- **A property-based state machine** (`KeelMachine`) drives the real worker, engine, inbox, approvals,
  delegation, takeover, reaper, retries, circuit breaker, segments, streams, deadlines and key windows over
  an in-memory journal and a simulated clock, with kills at every boundary, zombie resumes, late responses,
  duplicate signals and journal faults, and checks the safety invariants after every rule and liveness,
  replay and journal–receiver agreement (L1–L3, C1, C3) at the end of every example. The deep profile is
  2 000 examples of 60 steps. It found five runtime bugs, each pinned as a regression test, and one design
  gap the specification was amended for.
- **Reproducibility.** All 4 200 of Keel's published trials were run again at the release tag, at the same
  `(spec_hash, seed)`: 4 199 pairs, **0 verdicts changed** (two statuses moved, both FAILED → COMPLETED —
  seed 100067, and a baseline whose host-load timeouts did not recur). Separately, 300 trials re-run after a
  no-op commit changed 0 verdicts; raw counts moved only in the timing races. Rows:
  `bench/results/k6_*`, `bench/results/k7_noop`.
- **The receiver is audited, not assumed.** Every "kill after the effect" cell rests on the receiver
  writing its receipt before it answers. An audit killed the receiver around 400 requests and found none
  answered without its receipt on disk — and the audit is calibrated: against a receiver built to receipt
  *after* answering, it convicts 100 times out of 100 ([the audit](bench/instrument/k11_audit.md)). Its
  reach is stated with it: a kill from outside takes 0.5–1.1 s to land here, so it catches a mis-ordering
  that wide or wider; the microsecond ordering itself is asserted by a unit test on the write order.

### Kill criteria

The specification names eleven results that would mean the project's claims are wrong or unfair (§30).
Each is read against that section's own wording; two fired, and their remedies are applied — K3's with one
departure, named in its row.

| | verdict | in one line |
|---|---|---|
| **K1** everyone passes | not fired | every configuration but Keel duplicates an `EXTERNAL` effect after the receiver applied it, and Restate fails S1 against its own claim |
| **K2** engine parity | not fired | DBOS and Temporal match Keel on every judged safety verdict and Restate does not; none matches on economy |
| **K3** unfair triggers | **fired** | DBOS at `after:tool_return`: 47–80 % of kills in window against a 90 % floor ([placement](bench/instrument/placement_v1_w1_shim.md)). Those cells are exploratory, and the cross-runtime reading at that trigger rests on its proxy-mode twin. The departure: §30 would stop publishing *every* shim cross-runtime cell, and the rest of the shim set — each trigger 100 % in window on every arm — stays published |
| **K4** window too narrow | not decidable | the window is measured (median 8.2–26.6 ms from receipt to the runtime's own commit record, per arm — [widths](bench/instrument/window_v1_w1_shim.md)); the kill rate it must be multiplied by is not |
| **K5** adapter infeasible | not fired | every configuration expresses W1, W5 and W5-pre in cited primitives; what one cannot express is N/A with the reason |
| **K6** Keel fails itself | not fired | no white-box cell fails; two design defects found by other instruments were fixed, the sections amended, and the re-run changed 0 verdicts |
| **K7** not reproducible | **fired** | two LangGraph `exit` proxy cells are 70 % and 83 % void (the outside kill races the process's own exit): withdrawn from the grid, counts kept. Everything else re-verifies, and a no-op commit flips 0 of 300 verdicts |
| **K8** no power | not fired | at n = 300 the compare pages claim differences (e.g. Keel vs DBOS `native`: logically correct 300/300 vs 59/300, Holm-corrected p < 0.0001) |
| **K9** prior art | not fired on its text; remedy applied | two public artifacts each hold part of this design — [crashpoint](https://github.com/mstevens843/crashpoint) and [agent-crash-recovery](https://github.com/paolo-perrone/agent-crash-recovery) — cited, not competed with |
| **K10** schedule | not fired | the first matrix (40 cells × 30 seeds) landed on day 3 |
| **K11** instrument invalid | (a) not fired · (b) not run | (a) 0 of 400 audited kills answered without a receipt, calibration 100/100 — narrower than §30's words, which name a microsecond interval no outside kill can aim at; (b) the real-model subset was not run — see below |

The full reasoning for each, with the measurements, is §9 of the [write-up](docs/writeup.md).

## How Keel works

A Keel program is ordinary async Python. Everything nondeterministic goes through `ctx`: `ctx.model(...)`,
`ctx.tool(name, **args)`, `ctx.now()`, `ctx.approve(...)`, `ctx.delegate(...)`, `ctx.sleep(...)`. Each call
is a **step** with an identity `(kind, name, hash of args)`, recorded in an append-only journal.

```mermaid
sequenceDiagram
    participant P as program (ctx.tool)
    participant K as Keel step engine
    participant J as journal (Postgres)
    participant R as receiver
    P->>K: ctx.tool("create_issue", args) — step i
    K->>J: TX: fence · STEP_INTENDED{effect_key} · effects row · STEP_ATTEMPT_STARTED
    Note over K,J: the write-ahead barrier: nothing leaves the process before this commits
    K->>R: the request (with Idempotency-Key = effect_key, if the tool presents it)
    R-->>K: the response
    K->>J: TX: fence · STEP_COMPLETED{result} · effects row COMMITTED
    K-->>P: result
    Note over K,R: killed between the two transactions: STARTED with no outcome.<br/>The successor decides by the tool's effect class.
```

**The journal is the state.** `events(run_id, seq)` is append-only; every projection — run phase, steps,
budget, plan, context, children — is a pure fold over it. Nothing is ever rewritten: a schema change is an
upcaster applied at load (STEP_COMPLETED is at v2), and C4 checks that every projection folds equal over
old events and their upcast.

**One writer, fenced.** A worker claims a run (`SELECT … FOR UPDATE SKIP LOCKED`) and holds a lease whose
epoch increments on every acquisition. Every append transaction starts with the fence —
`UPDATE runs … WHERE lease_epoch = $mine` — so a zombie's writes are rejected by the database, not by
politeness. The heartbeat extends the lease; the reaper marks a run orphaned only once its lease has lapsed
*and* its open attempt's deadline has passed, and a tool whose timeout exceeds the lease is refused at start.

**Recovery is re-execution, not resumption.** A successor re-runs the program from the top (or from the
latest continuation boundary). Every journaled step returns its recorded value — no model call, no tool
call, no tokens — until the first step with no outcome, which the successor disposes of **by the tool's
declared effect class**:

| class | an attempt found open (STARTED, no outcome) | guarantee |
|---|---|---|
| `PURE` | closed as abandoned; re-run | effectively-once to the program |
| `IDEMPOTENT` | re-sent under the **same key**, `effect_key = sha256(run_root ‖ step ‖ tool ‖ canonical args)`, bounded by the key window its retry policy declares (`max_elapsed_s`) and by three abandoned attempts; past either, it goes to a human | effectively-once, if the receiver honours the key |
| `EXTERNAL` | **never re-sent blindly**: `STEP_AMBIGUOUS`, then the tool's declared resolution — a probe, `assume_failed`, `assume_succeeded`, or escalate to a human (`keel signal --resolve`) | at-least-once, or at-most-once, or a human's decision |

A program that issues a different step than the journal recorded at that index is not guessed at: the run
is SUSPENDED with `NondeterminismDetected`, naming the step. `keel replay --verify` re-executes a run
against its journal, appending nothing to it (the check is recorded as a `replays` row), and compares the
logical projection hash (C1).

**Everything else a production agent needs, as journal events:**

- **Retries, budgets and deadlines.** A retry the policy will make is journaled with the failure
  (`next_attempt_at`), so a successor honours it; a wait of a second or more parks with the lease released,
  and a per-provider circuit breaker holds off an outage. Budgets are reserve-then-settle — tokens, model
  calls, tool calls, and dollars from a price table pinned when the run is created — and a crashed attempt
  stays charged at its reservation, so the journal's charge is an upper bound on what the provider billed —
  in dollars too, wherever the model binding is priced (an unpriced one makes the dollar figure a floor,
  and `keel show` says so).
  `deadline_at` and `max_wall_clock` are enforced inside the transaction that would start an attempt, and
  a wait woken past its deadline fails the run, its children cancelled first.
- **The inbox.** Cancel, pause, resume, rebind, approve, reject and a human's resolution are rows in a
  `signals` table, applied by the lease holder at a step boundary inside its own fenced transaction — never
  by a second writer.
- **Approvals** park with no lease held and nothing polling them (zero compute while a human thinks), bind the
  effect key of the one call they authorise, and expire by the store's clock.
- **Delegation.** `ctx.delegate` spawns child runs under a contract — result schema, budget slice, allowed
  tools, deadline, failure policy — in one transaction; a child's terminal event commits its parent's
  result row with it; cancel is asked first and forced by lease takeover after a grace period, and a child
  never outlives its parent (S8).
- **Long horizon.** Durable sleep, a journaled plan, compaction of the model context, and continuation
  segments, so a thousand-step run replays from its latest boundary rather than from step zero.
- **Streaming**, **tool policy** (`allowed_tools`, `require_approval`), a **manual compensate hook** — an
  undo is a new step with its own key, never automatic — and a **workspace per lease epoch** for
  file-writing tools.
- **Observability** is views over the journal: `keel show`, `keel events --follow`, `keel diff`, and
  `keel otel`, which exports a run as OpenTelemetry spans (OTLP/JSON) with ids derived from the journal, so
  a re-export is identical.

## How Crashproof works

```mermaid
flowchart LR
    SPEC[matrix spec + seed] --> SCH[fault schedule]
    SCH --> SUP[supervisor]
    SUP -->|start · kill · freeze · restart| SUT[runtime under test]
    SUT -->|tool calls| W[(World: receipt fsynced<br/>before the response)]
    SUT -. faults fired by shim · proxy · hook .-> LOG[fault log]
    W --> V[verifier]
    LOG --> V
    SUT -->|journal or checkpoints| V
    V --> ROW[one row per trial] --> PAGES[report · compare · agree]
```

- **The World** is the ground truth: a deterministic HTTP receiver that writes and fsyncs a receipt for
  every request *before* it computes the response, and applies each effect according to that endpoint's
  declared semantics (`dedup`, `natural`). Its two counts — how often it was *asked* and how often the world
  actually *changed* — are what `duplicate_receipts` and `duplicate_effects` read. The gap between them is
  what a receiver's idempotency bought, and the runtime gets no credit for it.
- **Faults**: process kills at named instants, a freeze past the lease (`SIGSTOP`-style), tool 5xx /
  timeout / delay / dropped / malformed / duplicated response, model 5xx / timeout / outage / truncated
  stream / a different answer when re-asked, SIGTERM with a grace too short, journal and blob-store
  failures, and the human's faults (a late approval, an expired one, a kill while waiting).
- **Three injection modes, never pooled into one verdict.** The **shim** fires inside the runtime's process at
  three instants of every tool call (`before:tool_call`, `after:tool_effect`, `after:tool_return`) — the same
  instants in every arm. The **proxy** fires from the network edge, needing nothing inside the runtime. The
  **hook** fires inside Keel's own write path, for the white-box table only.
- **The supervisor** restarts a killed runtime with identical arguments and environment, up to a bound,
  and plays the human for approval workloads. A trial's fault schedule is drawn from `(spec_hash, seed)`
  alone, so it re-runs exactly; the timing races it aims into do not, which is what the no-op re-run
  measures.
- **Adapters** build each workload from each runtime's documented primitives — no counter, pre-send lookup,
  retry or deduplication of the adapter's own — and every adapter page cites the documentation for the
  primitive it uses and for the key it sends ([`docs/adapters/`](docs/adapters)).
- **The verifier** judges each trial against the runtime's declared claims: S1 no duplicate beyond the
  claim · S2 no lost committed effect · S3 no phantom completion · S4 no effect without a prior write-ahead
  record · S5 no step state regresses · S7 one applied effect per approval · L1 recovery reaches a terminal
  or legitimate waiting state · L2 bounded restarts · C1 replay reproduces the run · C2 continuation
  segments fold equal. An input a runtime does not expose makes that verdict N/A, never a pass, and every
  page names what each N/A can lack. Three invariants the specification defines are not judged by the
  matrix: S6 (cancel honoured — no published workload cancels, so it is N/A in every row), S8 (no child
  outlives its parent — it needs every journal of a run tree, and the matrix collects one, so it is N/A
  too) and C3 (journal and receiver agree — the matrix computes no effects ledger to compare). The
  property machine checks S6 and C3, and the white-box table S8.
- **Statistics.** Safety is never a proportion: one violation in n is a FAIL with its counterexample seed.
  Liveness is a Wilson interval. Two runtimes are compared on the same `(cell, seed)` pairs — McNemar's
  exact test for binary outcomes, a paired bootstrap for continuous ones, Holm across a metric family — and
  "too noisy to claim" is a verdict, printed with the minimum detectable difference.
- **Two tiers.** Every cell runs at n = 30. A cell whose screening result is not unanimous is re-run at
  n = 300 on fresh seeds, with Keel's cell at the same trigger and each one's baseline, and its page
  prints both tiers.
- **The instrument checks itself**: where each fired fault actually landed against each runtime's own commit
  record (K3), the width of the window per runtime (K4), agreement between the shim and proxy readings of
  the same cell (86 of 112 twins agree; 25 of the 26 that differ are the instrument — where each mode's
  fault can land — named per cell), and `verify --recheck`, which re-derives every row from its trial
  directory. K3, K4 and the receiver audit read artefacts the rows do not carry, so they are published as
  measured in [`bench/instrument/`](bench/instrument/README.md).

## What it does not show

- **The model is a fixture.** Every trial runs a scripted provider that answers from request content alone,
  so a model-boundary cell says what a runtime did with a scripted answer. The real-model validation subset
  was not run, and no real model provider ships with Keel.
- **One machine.** Windows 11, one Postgres in Docker, Restate's arm under WSL2 (its rows say so). Cells
  that are races by construction — the frozen worker, a kill after the tool returned — move their raw
  counts from run to run; the no-op and K6 re-runs show the verdicts do not.
- **An outside kill takes 0.5–1.1 s to land** on this platform, so a window narrower than that is measured
  by the in-process shim and the white-box hooks, and the proxy's reading of it is labelled as the
  instrument.
- **Keel is single-node**, and `EXTERNAL` without a key is at-least-once by construction: the frozen-worker
  residual above is the price, and a key is the remedy. A file write that is idempotent by content could
  be reordered by a zombie; the per-epoch workspace closes that by construction for writes inside it (a
  stale worker writes into its dead epoch's directory), and no published cell measures it.
- **Not built:** the `TRANSACTIONAL` effect class and the workload that needs it (W4); counterfactual
  replay (FORK); a network partition between worker and receiver; a live UI (the pages are static);
  retention and archival of old runs; adapters for Hatchet, Inngest, native Temporal and Julep. The OTel
  export is checked against Langfuse's documented ingest, not against a live instance.
- **Each arm is one configuration** of its runtime, built from documented primitives. A runtime configured
  differently can behave differently; the configuration is pinned in every row and argued on each adapter
  page.

## Reproduce it

```bash
uv sync --extra dev --extra langgraph                  # add --extra dbos --extra temporal for those arms
docker compose up -d postgres
uv run keel db migrate --app keel.agents.demo:app

uv run crashproof demo                                 # the one command
uv run pytest tests/unit tests/property tests/conformance -q  # no database; 511 pass with the three arms' extras
KEEL_TEST_DSN=postgresql://keel:keel@localhost:5432/keel \
  uv run pytest tests/integration -q                                    # 39 pass against Postgres

uv run crashproof bench --matrix bench/specs/week2_w1_shim.yaml --cells 'keel.*' --out out/keel
uv run crashproof verify out/keel/results.jsonl --recheck               # re-derive every row from its trial
uv run crashproof report out/keel --out out/keel.md
uv run python scripts/render_reports.py && git diff --exit-code -- bench/reports   # every page, byte-identical
```

The Restate arm needs Linux (restate-sdk has no Windows wheel). A bench is serial by design — one run owns
one results file, and `--resume` continues it, re-taking void trials; parallelism is sharding by cell glob
into separate directories, whose results files concatenate into exactly what one run would have written.
Per-trial directories (journals, receipt logs, fault logs) are hundreds of megabytes and are not committed,
so `--recheck` runs on a directory you generated. Exit codes: `7` an invariant failed in a scored trial, `8`
a comparison could claim nothing (`--strict`), `9` a row could not be re-verified.

## Repository

```
keel/                  the runtime
  core/ events/          ids, clocks, hashing, errors · the event schema, envelope, upcasters
  journal/               append with the fence first · Postgres and in-memory backends · blobs · SQL
  state/                 pure folds: run, steps, budget, plan, context, children · views · OTel spans
  runtime/               ctx, the step engine and recovery table, worker, reaper, takeover, retry,
                         breaker, budget, delegation, policy, sandbox
  effects/ replay/       tool registry and executor · VERIFY and journal fixtures
  providers/ agents/     model protocol, scripted provider, pinned prices · reference programs
  cli/ client.py api/    `keel …` · the Python client · the static timeline page
crashproof/            the harness
  world/ faults/ proxy/  the receiver and oracle · specs, schedules, injectors, supervisor · the edge
  adapters/ workloads/   one module per runtime · W1, W3, W5, W5-pre, W7 as declarative scripts
  runner/ verifier/      bench, collection, trial databases · invariants, metrics, placement, ledger
  stats/ report/ cli/    Wilson, McNemar, bootstrap, Holm, MDD · pages, compare, agreement · `crashproof …`
bench/                 specs/ (the cells) · confirm/ (n = 300 plans) · results/ (committed rows)
                       reports/ (pages rendered from the rows) · keel_conformance/ (the white-box
                       table) · instrument/ (K3, K4 and the receiver audit, as measured)
tests/                 unit · property · conformance · integration · journals/ (fixtures) · golden/
docs/                  the specification, the write-up, per-adapter pages, and the ledgers below
```

The dependency direction is enforced by a test: `core ← events ← journal ← state ← runtime ← {effects,
replay} ← agents ← {cli, client}`, `keel` never imports `crashproof`, and `keel/state` has no I/O.

**Documents.** [The specification](docs/KEEL-ARCHITECTURE.md) (Appendix A is the constitution) ·
[the write-up](docs/writeup.md), the argument and every hypothesis's verdict ·
[`docs/adapters/`](docs/adapters) — how each arm is built, with citations ·
[`docs/cli-ledger.md`](docs/cli-ledger.md) — every difference between the specified CLI and the built one ·
[`docs/layout.md`](docs/layout.md) — where the code departs from the specified file list, and why ·
[`docs/upstream/`](docs/upstream/README.md) — reports to other projects ·
[`docs/build-log.md`](docs/build-log.md) — the record, phase by phase, of how it was built and what each
phase found and fixed.
