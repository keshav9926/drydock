# drydock

[![ci](https://github.com/keshav9926/drydock/actions/workflows/ci.yml/badge.svg)](https://github.com/keshav9926/drydock/actions/workflows/ci.yml)

Two things live here, and the second is the point of the first.

**`keel/`** — a single-node, event-sourced, agent-native durable execution runtime (Python, Postgres).
**`crashproof/`** — the fault-injection and conformance harness that runs Keel *and other runtimes*
through the same workloads under the same faults, and publishes a matrix.

> Framework checkpoints are snapshots; durable execution means someone notices the crash, resumes, and
> neither double-fires nor loses an effect. An agent that cannot survive `kill -9` is a demo.

The specification is [`docs/KEEL-ARCHITECTURE.md`](docs/KEEL-ARCHITECTURE.md). Its **Appendix A (design
constitution)** binds every decision here; where a section and the constitution disagree, the constitution
wins.

## One command

```bash
uv sync --extra dev --extra langgraph && docker compose up -d postgres
uv run crashproof demo
```

A real worker, a real Postgres, a real HTTP receiver that fsyncs its receipt **before** it computes a
response. The worker is killed at the one instant where the receiver has the effect and the journal
does not. Every line below is read back from the trial's own artefacts — journal, receipt log, fault
log, verdicts — not narrated by the code that ran it:

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

Now the same command, same fault, same landmark, same World, same seed, against another runtime:

```bash
uv run crashproof demo --adapter langgraph --config sync
```

```
[4]–[7] no journal exposed. This runtime keeps a checkpoint, not an event log …
[13] resume re-runs the interrupted node; whether that re-fires the effect is what the
     World's receipt count below answers
[18] World: receipts(issues.create#1)=2  applied=2   ·  duplicate_effects=1
```

Neither arm failed an invariant. LangGraph declares `at_least_once` for EXTERNAL and is held to what
it claims — **the duplicate is the cost, printed**. That rule, and not a leaderboard, is what the
whole matrix is built on.

## The matrix

**[`bench/reports/matrix_v0.md`](bench/reports/matrix_v0.md)** — 40 cells × 30 seeds, **1 200
trials**, four runtime configs, two bands, every arm running the same spec file. Duplicate *applied*
effects in the `EXTERNAL` band (`issues.create`, `dedup: false`, no key), out of 30 seeds:

| (location, fault) | keel | langgraph sync | async | exit |
|---|---|---|---|---|
| `before:tool_call` | 0 | 0 | 0 | 0 |
| `after:tool_effect` | **0** | **30** | **30** | **30** |
| `after:tool_return` | **0** | **30** | **30** | **30** |
| `pause_past_ttl` | **11** | 0 | 0 | 0 |

The middle two rows are the thesis; the last row is the honest cost, and it is Keel's. A fence
protects the journal and cannot reach a third party, so a worker frozen past its lease duplicated in
11 of 30 trials — the residual the constitution names and refuses to claim away. In the `IDEMPOTENT`
band the same freeze produced 10 re-sends and **0** duplicates: the key travels and the receiver does
the rest. LangGraph's zombie column is 0 for a different reason — with no successor, nothing takes
over while it is frozen, so nothing races it.

Beside it, and never unioned with it:
**[`bench/keel_conformance/table.md`](bench/keel_conformance/table.md)** — 66 white-box cells (54 run,
12 N/A with the reason) firing faults *inside* Keel's own write path, its inbox drain, its approval
park and its spawn, where no shim can reach. A boundary only one runtime exposes is not a fair column.

How each arm is built, and the key formula behind its fairness level:
[`docs/adapters/keel.md`](docs/adapters/keel.md) ·
[`docs/adapters/langgraph.md`](docs/adapters/langgraph.md) ·
[`docs/adapters/dbos.md`](docs/adapters/dbos.md) ·
[`docs/adapters/temporal.md`](docs/adapters/temporal.md) ·
[`docs/adapters/restate.md`](docs/adapters/restate.md). What a finding has to clear before it
goes to someone else's issue tracker: [`docs/upstream-report-template.md`](docs/upstream-report-template.md).

## Status — phase 8 of 8: outside the holder

Week 2 of §29.1. Everyone who is *not* the lease holder — a human with a decision, a child with a
result, a network with an opinion — now influences a run through one table, applied by the holder
at a step boundary inside its own fenced transaction, without ever becoming a second writer.

- **The inbox** (§4.10). `keel cancel|pause|resume|approve|reject|signal|rebind`, and
  `Keel.pause|cancel|approve|reject|rebind` in the Python client (§24.1), are each one row in `signals`
  and nothing else; the holder drains at every step boundary, `SIGNAL_RECEIVED` ‖ what was done ‖
  `consumed_seq` in one transaction. The MVP's direct `runnable_at` path is deleted. A park — on an
  approval, on children, a suspended re-park, a retry backoff — releases its lease as the last
  statement of its own `RUN_WAITING` transaction, guarded by `runnable_at IS NULL`, so a signal that
  landed since the last drain rolls the park back instead of being erased by it; the claim also takes
  a run with an unconsumed signal. A pause sets `paused_at` and holds until a resume or a cancel, and
  the resume appends `RUN_PAUSE_LIFTED`. A SUSPENDED run can be cancelled, and one woken without a
  resume drains and parks again without re-executing. A `rebind` is journaled as
  `MODEL_BINDING_CHANGED` and reaches live MODEL steps only (§16.7).
- **Approvals** (§7.5). `ctx.approve(gates=(tool, args))` parks with no lease **and** no `runnable_at`
  — zero compute, zero ticks — and binds the effect key it authorises before anyone decides. The step
  after it must be that bound call, or it fails with `ApprovalBindingError` before an attempt starts;
  a refused call costs no attempt (`attempt_no=0`, `DENIED`). A decision from `keel approve|reject` or
  the Python client names its `approval_id` — the CLI resolves the open one and writes it into the
  row — so a stale or repeated click is `SIGNAL_IGNORED{approval_terminal}`, never a decision for
  whichever gate is open by then. Expiry is judged by the store's clock and outranks arrival order.
- **Children** (§17). `ctx.delegate_many` commits the spawn as one fact (INTENT + STARTED +
  N×`CHILD_SPAWNED` + each child's row, `RUN_CREATED` and contract + the park); a child's terminal
  event co-commits its parent's `child_result` row; the parent grades the result against the contract
  at the drain; cancel is asked first and forced by lease takeover after `cancel_grace` — the fifth
  control-plane statement, pinned epoch, grace by the store's clock, open non-PURE attempts honoured,
  depth-first, so a child is taken over only once its own children are terminal. The reaper collects
  strays of a terminal parent the same way (S8). A child's `run_root_id` is its own; a cancelled child
  stays charged at its full slice; a retry is admitted against the slices already promised to
  ordinals still waiting for a slot; `fail_parent` cancels the open siblings in the same transaction.
  `deadline_s` is journaled, not yet enforced.
- **Retries and outages** (§8, §11.5). A retry the policy will make is journaled with the failure,
  `STEP_FAILED{next_attempt_at}`, so a successor that finds it retries instead of failing the run.
  `keel/runtime/breaker.py` is the per-provider circuit breaker. A retry wait of a second or more
  parks as `RUN_WAITING{retry_backoff}` at zero compute instead of being slept under the lease; the
  Keel arm's pinned policy (three attempts from a 0.1 s base) never waits that long on its own, and an
  open breaker's cooldown does. `provider_outage` is built in shim mode; no published cell runs it.
- **The verifier.** S7 is judged against the World through the effect ledger and can now fail: two
  applications under one approval, an application under an approval rejected, expired or never
  decided, or a gated tool applied with nothing granted. S6 (cancel honoured, judged by journal order)
  is a grid column on every page and N/A in every published cell, because no tier-1 cell cancels.
  `approval_binding_violations`, `wait_durability` and `cancel_latency_ms` are computed on every new
  row; the published rows predate them and no page prints them yet.
- **Fifteen of seventeen hook boundaries**, with cells: [`bench/keel_conformance/table.md`](bench/keel_conformance/table.md)
  is 66 cells, 54 run and 12 N/A, S7 and S8 judged from the whole tree of journals.
  `during:approval_wait` and `during:child_wait` fire with the lease already released.
- **Proxy mode** (§11.2). The black-box injector at the network edge: the proxy is the only firing
  site, and the shim inside the SUT rides along observe-only to count calls at the wire.
  [`bench/reports/tier1p.md`](bench/reports/tier1p.md): 36 cells × 30 seeds, **1 080 trials**, every
  safety invariant PASS; Keel applies once under kill-after-effect, 5xx, dropped, malformed and timeout
  (the probe finds COMMITTED), LangGraph sync twice in each (PASS against at-least-once, printed raw).
  Two of its triggers need a re-run. Keel's `pause_past_ttl` froze the process named by `sut/pid-0`,
  which the successor wrote too, and in 41 of its 60 trials that was the idle successor: the worker
  holding the run was never frozen, timed out on its own parked request, re-attempted, and the parked
  request applied again at the thaw. The duplicates are on the page either way; the mechanism the cell
  exists to show ran in 19 of the 60. And 34 of the 120 `kill@after:tool_return` trials record no
  restart — the run finished before the kill landed — which current scoring makes a void trial.
  [`bench/reports/agreement_tier1p.md`](bench/reports/agreement_tier1p.md) pairs the same cells with
  their shim twins and counts **0 comparable**: all 28 twins pair rows from different commits, and
  most Keel twins different retry, claim-poll and reaper pins, so no difference on the page can be put
  down to the instrument. (It read 23 of 28 agree before twins were checked for matching commits and
  pins.)
- **W5 at thirty seeds** ([`bench/reports/w5.md`](bench/reports/w5.md), 450 trials;
  [`w5_pre.md`](bench/reports/w5_pre.md), 270), the harness as the human, against Keel and LangGraph's
  `interrupt()` in its `sync` and `async` configs. The clauses of §13.7's H7 that ran held 30/30 on
  every arm: killed while waiting and then granted, the gated deploy fires once. LangGraph re-runs the
  interrupting node on every re-entry — 4 model calls to Keel's 3 on resume, 5 when killed while
  parked — and in the tier-2 form an ungated `notify` before the gate fires 2× on resume and 3× when
  killed while parked: 240 extra effects in LangGraph's 180 trials (120 per config), PASS against
  at-least-once and printed. `interrupt()` has no deadline, so under `approval_expiry` LangGraph is
  still WAITING at 60 s in 60 of 60 trials (L1 FAIL by design) where Keel expires by the store's
  clock and completes with nothing deployed, 30/30. The wait is not the only difference: under
  `kill@after:tool_effect` LangGraph applies the gated deploy twice in 30 of 30 trials per config,
  Keel once.
  What did not run: the `langgraph.exit` arm; `kill @ landmark:approval_decided`, where H7 predicts a
  duplicate for every at-least-once arm; and the rest of §14.2's 21 tier-1 W5 pairs — the day-4
  faults, the reask arm, `pause_past_ttl` and the other kill locations. H7 calls the tier-2 re-fire
  an S7 counterexample at F0; the verifier scores S7 N/A for LangGraph, which has no journal to bind
  an effect to, so that clause is a printed count and not a verdict. W5-pre is tier-2 (V2) in §14.2,
  built ahead of its stage because it is the only cell that reaches H7's pre-interrupt clause, and it
  stays in its own band. **Both pages need a re-run:** `approval_delay` now sends §11.4-C's duplicate
  click and `approval_expiry` forbids the deploy by name — new `spec_hash`es for both cells — and the
  Keel arm's approve now names the approval it decides.
- **Engine arms.** DBOS (`native`, and Pydantic AI under `DBOSDurability`; `recovery_mechanism = self`,
  F1 `workflow_id:step_id`), Temporal (Pydantic AI under `TemporalDurability`; `engine`, F1
  `workflow_run_id:activity_id`) and Restate (Pydantic AI through `RestateAgent` — a wrapper in
  Restate's SDK, not a pydantic-ai capability, and every Restate cell carries that caveat; `engine`, F1
  `ctx.uuid()` drawn before each tool's `ctx.run`) are merged, each with a one-seed smoke of W1, W5 and
  W5-pre in its adapter page — smokes, not results. `restate-sdk` has no Windows wheel and
  `restate-server` is a Linux binary, so the Restate arm's rows come from the harness under WSL2, and
  its `config_pin` says `platform: linux (WSL2)` where every other arm's rows are Windows.

### Post-phase-8 audit

After `2313613`, ten auditors each took one area of the repository — the inbox, fencing, delegation,
the proxy, the verifier, the reports, the kill criteria, scope against §29.1, the docs, hygiene — and
every finding was re-checked adversarially before it counted. **103 were confirmed** (12 blocker, 39
major, 43 minor, 9 nit) and 2 rejected. By kind: 48 code bugs, 22 stale documents, 13 report
mismatches, 11 scope gaps, 4 CI, 3 hygiene, 2 kill criteria.

- **Keel's wake path could lose a signal.** A park released its lease in a second, unguarded update
  that erased an approve, a child's result or a resume landing in between; any signal lifted a pause;
  a SUSPENDED run could not be cancelled; an approve naming one approval decided whichever was open;
  `ApprovalBindingError` was declared and never raised. Delegation gave children their parent's
  `run_root_id`, so a retried child died on `DuplicateEffectKey`, settled a cancelled child at zero,
  and forced cancels out of depth order.
- **The harness and its pages claimed more than they measured.** The proxy froze the wrong process in
  41 of 60 `pause_past_ttl` trials; a kill that never landed scored as executed; S7's applied check
  could never match, so a gated effect applied twice under one approval passed; LangGraph's IDEMPOTENT
  rows said `key_source=framework` though it sends no key (960 rows relabelled `none`, no other field
  changed); `keel_commit` was read from `HEAD` once per bench, so some rows name a commit that is not
  the code that ran; `verify --recheck` exited 0 having re-verified nothing; every page claimed an
  n = 300 confirmation tier nobody had run; the agreement page paired twins across commits; the
  placement view compared two clocks.
- **Week-2 scope was missing and unnamed:** `provider_outage`, the circuit breaker, S6 and three
  metrics, the §24.1 control calls and `keel rebind`, §11.4-C's duplicate click, the §19.5 placement
  histogram, `tool_duplicate_response`, `partition_worker_world`, and the K1/K3/K5 checkpoint. All but
  the two proxy faults are now built or recorded; those two are named [below](#not-yet-built-and-when).
- **Published cells it invalidated**, kept and marked rather than deleted: tier1p's Keel
  `pause_past_ttl` and its `kill@after:tool_return` cells; all of W5 and W5-pre; the agreement page.
  matrix v0, tier1a and reask_alternate have no `facts.json`, so `verify --recheck` exits 9 on them and
  K3 cannot be computed from them. A full re-run at one commit, with the engine arms added, is the
  week-2 matrix.

Fixes: the Keel runtime in `41f6ca0` and `652d8e6`; the harness, verifier, reports and CI in
`22f53d9`..`cd8665e`; the week-2 gaps in `3e70a9f`, `9a6e1ae` and `182994a`; the documents in the
commit that added this section.

### Week 2: eight arms, one commit

§29.1's artifact: Keel, LangGraph ×3, DBOS `native` and `pydantic_ai`, Temporal and Restate (both
Pydantic AI), over W1 in `shim` and `proxy` mode, W5 and W5-pre — **12 480 trials, every row at
`dcdd533`**, one void left after two re-take passes (LangGraph `exit`, proxy `kill@after:tool_return`,
seed 32). Restate's shard ran the same specs under WSL. Pages:
[`week2_w1_shim`](bench/reports/week2_w1_shim.md) (208 cells) ·
[`week2_w1_proxy`](bench/reports/week2_w1_proxy.md) (144) · [`week2_w5`](bench/reports/week2_w5.md)
(40) · [`week2_w5_pre`](bench/reports/week2_w5_pre.md) (24) ·
[`agreement_week2`](bench/reports/agreement_week2.md).
`crashproof verify --recheck` over the trial directories re-verifies all 12 520 rows (re-takes
included) with no drift, exit 0 — §29.3's publication gate; the directories stay on the machine
that ran them, as every published run's do.

- **Keel fails no safety invariant in any cell of the four.** Its one duplicate source is the named
  zombie residual: `EXTERNAL` `pause_past_ttl` applies twice in 20 of 30 shim trials (30 of 30 in proxy
  mode, where the parked request lands after the successor's re-attempt).
- **The window every other arm leaves open.** At `kill@after:tool_effect` on `EXTERNAL`, all seven
  other configs apply the issue twice, 30 of 30; Keel's probe finds the applied effect, 0. The same
  holds behind the approval gate: W5's `kill@after:tool_effect` deploys twice in 30 of 30 trials on
  every arm but Keel. At `after:tool_return` LangGraph ×3, Temporal and Restate duplicate 30 of 30 and
  DBOS 18 (`native`) and 24 (`pydantic_ai`) — a race against DBOS's step checkpoint written off the
  event loop ([dbos](docs/adapters/dbos.md)).
- **Faults that do not kill.** Keel ends 30/30 logically correct under `tool_500`, `tool_timeout`,
  `model_500`, `model_timeout` and `provider_outage`. DBOS runs with step retries off (its default), so
  a 5xx, a tool timeout or the outage ends the workflow in ERROR — 0/30 correct, recovered, printed not
  judged. Temporal and Restate retry the `EXTERNAL` call under `tool_500` and `tool_timeout` and create
  the issue twice, 30 of 30.
- **Restate is judged against its own claim** ("Tool side effects are not duplicated", so
  `exactly_once`): S1 FAIL in 5 shim cells, 7 proxy cells and W5's `kill@after:tool_effect`. Its
  `pause_past_ttl` cells also scored L1 in 4 of 60 shim trials — still RUNNING at 60 s — and that was
  **the harness, not Restate**: on POSIX the worker also stopped itself, and when the supervisor froze
  it before that self-stop ran, the self-stop landed after the supervisor's resume and nothing resumed
  it again (the trial directories show Restate retrying and the worker silent). Fixed after the run —
  the worker only parks now, as on Windows — so Restate's two `pause_past_ttl` shim cells are pending a
  re-run; its other cells never froze. Only the Restate shard ran on POSIX.
- **W5-pre** reproduces H7's pre-interrupt clause on every LangGraph config — `notify` twice in the
  fault-free baseline (one `sync` trial three times) and under `approval_delay`, three times under `kill_while_waiting` — and on no
  other arm. LangGraph's `approval_expiry` is L1 FAIL by design on all three configs (no deadline
  primitive); every other arm completes "not done".

### Kill criteria at the end of week 2

§29.1 checks K1, K3 and K5 here (§30).

- **K1 (everyone passes) has not fired.** It needs zero S1–S5 FAILs and zero raw duplicates at T2/T3
  in every F0 cell; in the week-2 matrix every arm but Keel duplicates the `EXTERNAL` issue at
  `after:tool_effect` 30 of 30, and Restate fails S1.
- **K3 (unfair triggers) fired for one trigger on one runtime: DBOS at `after:tool_return`.**
  `crashproof placement` reads each runtime's own commit record (Keel's journal on the host clock,
  LangGraph's checkpoints, DBOS's `completed_at_epoch_ms`, Temporal's `ActivityTaskCompleted`, Restate's
  `Notification: Run`) and puts 100 % of fired faults inside the intended window in every tool-boundary
  shim cell of Keel, LangGraph ×3, Temporal and Restate. DBOS lands 60 % / 53 % (`native`, EXTERNAL /
  IDEMPOTENT) and 80 % / 57 % (`pydantic_ai`) there, 40 and 47 points from the other arms: its step
  checkpoint is written off the event loop and often commits before the shim's kill. Joined per trial,
  every in-window kill duplicated and every out-of-window kill did not (12/12, 14/14, 6/6, 13/13) — so
  those four cells measure the kill's timing, not DBOS, and per §30 they are **exploratory**, not
  headline; DBOS at `after:tool_effect` (100 % in window) is its T2 result. Model-boundary faults have no
  K3 window. The proxy/shim agreement column is the cross-check: 87 of 112 comparable twins agree, and
  the 25 that differ are the instrument — `kill@after:tool_return` from outside lands after `taskkill`'s
  latency (15), `pause_past_ttl` parks the request at the proxy instead of freezing before the send
  (6), and LangGraph `async`'s shim kill lands before its checkpoint flush (4, receipt counts only).
- **K4 (window too narrow) is week 3's; its instrument exists.** `crashproof placement DIR --window`
  measures `ambiguity_window_width` on baseline trials — World receipt to the SUT's own commit record —
  median over W1 shim: DBOS 7.8 / 8.5 ms, Keel 9.1, LangGraph 12.3 (`async`) / 12.8 (`sync`) / 20.5
  (`exit`), Temporal 18.7, Restate 23.4 (on the WSL clock its World shares). K4 also needs a realistic kill rate
  to turn a width into an exposure, which the benchmark does not measure and does not invent.
- **K5 (adapter infeasible) has not fired** for any merged arm. DBOS ×2, Temporal and Restate express
  W1, W5 and W5-pre in cited primitives with no counter, pre-send lookup, retry or dedup of the
  adapter's own, and all three F1 formulas carry a doc citation ([dbos](docs/adapters/dbos.md),
  [temporal](docs/adapters/temporal.md), [restate](docs/adapters/restate.md)). Restate's is `ctx.uuid()`
  ("stable UUIDs for things like idempotency keys"), and its SDK source says what that is stable over:
  an invocation-seeded generator rebuilt per attempt, so the key is drawn in the tool before its
  `ctx.run`, where replay repeats the draw — inside the run it would shift. Restate's W5 wait is an
  awakeable raced against a durable timer, resolved over the documented HTTP API. What the arms cannot
  express is N/A with the reason: S7 (no approval id binds a decision to an effect), S4/S5 (no
  per-attempt write-ahead record — Restate journals a run's command before its action, but once per run),
  C1 for DBOS and Restate (no documented replay of a recorded run), W6 (no cited child mechanism).
  Restate is also the one arm whose documentation claims more than at-least-once for tool side effects
  ("Tool side effects are not duplicated"), so its rows are judged against `exactly_once`. The LangGraph
  W5 binding is `interrupt()` + `Command(resume=)`, cited from the version under test.

- **K6 (Keel fails itself) is week 3's, but its first case came early**, from the property suite rather
  than a hook cell: an IDEMPOTENT attempt whose outcome is unknown (timeout, 5xx, dropped answer) with no
  retry left ended the run FAILED with the effects row `ABSENT` — while the World held the effect. §7.4
  and §8.5 prescribed exactly that, so it was a decision, not a slip. The document is amended to extend
  §9.1's own rule ("a clean failure would hide an applied one"): the row reads `AMBIGUOUS` while a retry
  is pending, and with none left the step is `RESOLVED_UNKNOWN{key_window_expired}` and the run
  SUSPENDED for a human. The week-2 matrix never reaches the path — every fault there fires once and the
  next attempt resolves it — so no published row changes.

### Phase 7: the artifact other people see

`crashproof demo` above, read off the artefacts rather than scripted, with CI diffing its printed
lines on every commit. `keel events --follow` — an MVP flag of §25.2's that phase 7 built, where
`keel effects --class` is still not — in place of the `keel watch` TUI, which is cut: what the TUI
was for is the BEFORE CRASH / AFTER RESTART split, and that split already lives in the event stream. Every rendered report now carries the MDD tables and
the "you only ran this thirty times" FAQ, because an answer that needs a second command to produce
is an answer a reader will not find.

### Phase 6: white box

The windows that decide whether Keel's journal protocol is correct are all inside a single
transaction, where no shim can reach. So Keel grew ten named boundaries in its own write path, and
pointing the first one at the journal found a real bug: a store error raised from inside a step
arrived at the worker's `except Exception` — right about a program bug, wrong about an outage — and
the worker wrote `RUN_FAILED` and released the lease, turning a two-second blink into permanent
unrecoverable loss with the issue already filed. `StoreUnavailable` now takes the `Abandon` path:
**a worker that cannot write must not write a verdict.**

The conformance table's payoff is one window with three disposals. Crash at `after:effect_exec`,
World has the effect, journal does not:

| class | disposal | receipts | applied |
|---|---|---|---|
| PURE | `COMPLETED` (re-read) | 2 | 0 |
| IDEMPOTENT | `COMPLETED` (re-fired under the same key) | 2 | **1** |
| EXTERNAL | `RESOLVED_COMPLETED` (probed) | **1** | 1 |

Also phase 6: `crashproof/stats/ci.py` (Wilson · exact binomial · paired bootstrap · Holm · MDD),
comparisons made per `(location, fault)` cell instead of averaged across triggers — which made Holm
mean something and exposed a verdict that had been printing the *diverging* arm as the better one —
`crashproof verify --recheck/--placement/--effects` over a `facts.json` every trial now writes, and
`KeelMachine`, a Hypothesis state machine that fires those faults in sequences nobody wrote down.

### Phase 5: replay as a first-class mode

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

### Phase 4: ambiguity

A crash is the easy fault. Phase 4 is the one where the process stays alive and the *answer* goes
missing — the request left, the receiver applied it, and nothing came back. Retrying is how correct
systems duplicate effects; failing is how they abandon work that already happened.

```bash
uv run crashproof bench --matrix bench/specs/tier1a.yaml --out bench/results/tier1a
uv run crashproof report  bench/results/tier1a --out bench/reports/tier1a.md
uv run crashproof compare bench/results/tier1a --a 'keel.*' --b 'langgraph.sync.*'
```

**[`bench/reports/tier1a.md`](bench/reports/tier1a.md)** — 32 cells, 30 seeds, **960 trials**, none
void: five faults that never touch the process, and two that SIGTERM it and end it when the grace
runs out. Duplicate *applied* effects, `EXTERNAL` band
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

None of the other five kills anything. In the first two the request left the process, the World applied
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
— 480 paired trials, one comparison per `(location, fault)` cell: `duplicate_effects` 0 vs 120, and
`logical_correctness` A better in four `EXTERNAL` cells — `tool_timeout`, `tool_500` and both
`sigterm_grace_*` — each 30 discordant pairs to 0, Holm p < 0.0001. Every recovery-latency row declines
to claim anything, including the ones that would have flattered Keel — `tool_500@after:tool_effect`
at a median 37.5 ms against 2 722.2 ms is tagged *not claimable*, because the arm it beats has a
supervisor re-invoking it and therefore no detection time to spend.

Tokens are counted by the harness at `before:model_call`, in every arm, by one function — charged when
the request is sent, not when it returns, because an attempt that never came back was still billed.
Keel's clean run costs 280 tokens of prompt to LangGraph's 163: a real cost of carrying a full message
history where the other carries a state dict. After a fault that does not touch the model both are
**+0**, because a synchronous checkpoint restores the state without re-deciding — LangGraph duplicates
the effect without paying for a second decision.

The pieces: a **retry policy** with full jitter, off by default (phase 4 clamped it inside the lease; week 2's park lifted that);
**reserve-then-settle budgets** where an attempt nobody heard back from stays charged forever, which
is what makes the journaled spend an upper bound on the bill; `UnknownOutcome` and `Rejected`, so the
step engine routes on the *effect class* rather than the status code; a `tool_timeout` armed **at the
receiver**, so the effect really lands and the answer really never comes; and `crashproof compare`,
which counts safety, estimates liveness, and says *too noisy to claim* out loud.

### Phase 3: the matrix

Phase 1 built the spine, phase 2 built the referee. Phase 3 points a saboteur at the runtime and
publishes what the referee saw.

```bash
uv run crashproof bench --matrix bench/specs/matrix_v0.yaml --cells 'keel.*'
uv run crashproof report bench/results/latest --out bench/reports/matrix_v0.md
```

**[`bench/reports/matrix_v0.md`](bench/reports/matrix_v0.md)** — 40 cells, 30 seeds, **1 200 trials**,
four runtime configs, two bands, every arm running the same spec. Every safety invariant held in every
scored trial; no counterexamples. The headline table is [at the top](#the-matrix); what follows is how
it was taken.

A kill between the effect landing and the outcome being recorded duplicates the issue in every
LangGraph trial and in none of Keel's — the journal remembers that the attempt started, so the
successor asks the receiver instead of guessing. S1 is PASS for all four columns, because LangGraph
claims `at_least_once` and is held to that; the duplicate is printed anyway.

Model calls are counted at the wire, identically for every arm, so the economy column exists for
runtimes that keep no tally of their own. After a kill at `after:tool_effect`: `+0` for Keel and
LangGraph `sync`, **`+2`** for `async` and `exit`, which re-run model calls the checkpoint did not save.

The pieces: a **fault spec** addressed by workload landmarks rather than ordinals in any one
runtime's traffic; a pure **seeded expansion** where all of a trial's randomness lives; a **trial
directory** that is firing state outliving the process it belongs to; a **shim** that fires the same
three instants inside every runtime; a **supervisor** that restarts with identical argv and env and
never says what to resume; a **verifier** that is a pure function from four logs to a verdict; and a
**report** that prints safety and estimates differently because they are different kinds of claim.

### Phase 2: effects, ambiguity and ground truth

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

## Running it yourself

```bash
uv sync --extra dev --extra langgraph                    # the LangGraph arm; a sync without the extra uninstalls it
docker compose up -d postgres                            # Docker Desktop first, on Windows
uv run keel db migrate --app keel.agents.demo:app

uv run crashproof demo                                   # the one command, in under a minute
uv run python scripts/day2_demo.py                       # the same window, narrated step by step
uv run crashproof bench --matrix bench/specs/matrix_v0.yaml --out out/mine   # ~2 h, serial
uv run crashproof bench --matrix bench/specs/tier1p.yaml   --out out/proxy  # the same windows, from the network edge
uv run crashproof verify out/mine/results.jsonl --recheck                    # the publication gate
uv run crashproof placement out/mine                                         # §19.5's histogram and K3's two numbers
```

**The rows behind every published report are in this repository**, one JSON object per trial, each
carrying its own `(spec_hash, seed, keel_commit, config_pin)`, the framework versions inside the pin:
[`matrix_v0`](bench/results/matrix_v0/results.jsonl), [`tier1a`](bench/results/tier1a/results.jsonl),
[`reask_alternate`](bench/results/reask_alternate/results.jsonl),
[`tier1p`](bench/results/tier1p/results.jsonl), [`w5`](bench/results/w5/results.jsonl),
[`w5_pre`](bench/results/w5_pre/results.jsonl). `report`, `compare` and `agree` are pure functions
over them, and every page names the results directory, the row count and each `keel_commit` it was
rendered from, and the last trial's end rather than the time it was rendered, so a re-render is
byte-identical. [`scripts/render_reports.py`](scripts/render_reports.py) is the one list of which rows
back which of the twelve pages, as the exact commands; CI runs it and fails on any diff under
`bench/reports`:

```bash
uv run python scripts/render_reports.py && git diff --exit-code -- bench/reports
uv run crashproof report bench/results/matrix_v0 --out /tmp/check.md   # byte-identical to the published one
```

**The commit on a row is approximate in three places**, all from before `keel_commit` was read at
the start of each trial and marked `-dirty` on an edited tree. Matrix v0's 360 LangGraph rows stamped
`7c4c2be` started before the LangGraph adapter was committed (`b46547d`). Its 60 Keel `pause_past_ttl`
rows stamped `cefd652` — the rows behind the `11` in the headline table — finished a minute before
`490807e` committed changes to the Keel adapter and the injector, and that commit's message credits
one of those changes with moving the zombie rate to 11 of 30 from 3. tier1p's 78 rows stamped
`426b7df` are a resumed run that started seven seconds before `ac9a849` was committed and kept the
stamp past `8ee372d`; its Keel `EXTERNAL` `kill@after:tool_return` and `pause_past_ttl` cells each mix
those rows with another commit's.

The per-trial directories — journals, receipt logs, fault logs, one `facts.json` each — are hundreds
of megabytes and are *not* committed. That is the one thing a clone cannot re-check: `--recheck`
re-runs the verifier over each trial's own recorded facts and fails (exit 7) if a verdict moved or
the results file has drifted from the directories it summarises, so it runs against a directory you
generated. A row with no `facts.json` behind it exits 9 — a clone's rows, and matrix v0, tier1a and
reask_alternate even on the machine that ran them, because those trials predate the file. An
invariant added after a row was written and N/A for it is not drift (the row could not carry it), so
the tier1p, W5 and W5-pre directories recheck with exit 0 on that machine: 1080, 450 and 270 rows,
the FAILs it prints being the 60 designed LangGraph `approval_expiry` L1s in W5.

**`bench` is serial on purpose, and parallelism is sharding.** One run owns one `results.jsonl` and
one `cursor.json`, which is what makes `--resume` safe and a re-taken void trial unambiguous; two
processes pointed at the same `--out` corrupt both. To use more cores, give each shard its own cell
glob and its own directory, then concatenate — the row carries its own `cell_id`, `seed` and
`spec_hash`, so a merged file is exactly the file a single run would have written:

```bash
uv run crashproof bench --matrix bench/specs/matrix_v0.yaml --cells 'keel.*'      --out out/keel &
uv run crashproof bench --matrix bench/specs/matrix_v0.yaml --cells 'langgraph.*' --out out/lg &
wait && mkdir -p out/all && cat out/*/results.jsonl > out/all/results.jsonl
uv run crashproof report out/all --out bench/reports/matrix_v0.md
```

A long run gets killed for memory on some machines roughly every few hundred trials — each
LangGraph SUT imports the whole langgraph stack. That is what `--resume` is for: re-issue the same
command and it continues from the store, re-taking void trials and costing nothing for the rows that
already exist.

### What phase 2 proves

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

### The World

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
uv run pytest tests/unit tests/property tests/conformance -q  # no database; rewrites bench/keel_conformance/table.md
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
| `tests/unit/test_compare.py` | pairing, one comparison per `(location, fault)` cell, Holm within a metric family, and the detection-bound tag |
| `tests/unit/test_stats.py` | the exact test on the hand-checkable splits; Holm monotone; the MDD refusing where nothing is detectable |
| `tests/unit/test_views.py` | facts survive the trip to a file; placement names the open attempt; the ledger judges each effect by its own class |
| `tests/unit/test_verify.py` | VERIFY writes nothing; a recovered run hashes like a clean one; a reordered program fails with the step named |
| `tests/unit/test_journal_fixtures.py` | every recorded journal in `tests/journals/` still agrees with the program |
| `tests/unit/test_reask_alternate.py` | the modifier is refused alone; the provider has no ask counter; identities separate "twice" from "something else" |
| `tests/unit/test_matrix_spec.py` | matrix v0's arithmetic, which is a published claim |
| `tests/unit/test_layering.py` | the architecture, as an assertion |
| `tests/property/test_fold_props.py` | determinism, incremental == batch, prefix monotonicity, blobs |
| `tests/property/test_key_props.py` | the effect key: stable, unique, fork-distinct, credential-blind |
| `tests/property/test_step_machine_props.py` | the recovery table, per class, against the World |
| `tests/property/test_runtime_machine.py` | `KeelMachine`: §12.3's rules for every mechanism built — kills at every hook boundary and mid-effect, timeouts, lease expiry and zombie resume, late responses, drain, journal faults, retry backoff, signals and duplicates, approvals (decide, expire, stale and duplicate clicks), delegation with forced takeover and a stray child — with S1–S8, J1–J2 and C1 after every rule and L1–L3, C3 at teardown; `sim.to_fault_spec` turns a shrunk sequence into a spec, `tests/property/regressions/` pins each one |
| `tests/conformance/test_hook_cells.py` | the crash-window enumeration: 66 `(boundary, fault, class)` cells — the write path per effect class, the inbox drain and the approval park on a gated run, the spawn transaction and the park on children of a delegating run — 44 run and 12 N/A with reasons; S8 judged from the whole tree of journals |
| `tests/unit/test_delegation.py` | children under contracts: the spawn as one transaction, results that wake the parent, the parent grading the result, cancel asked then forced by takeover, the reaper collecting a stray, fan-out bounded by slots |
| `tests/unit/test_proxy.py` | the black-box injector: the shim's three instants one process out, what the World did versus what the SUT was told under a dropped, 5xx, malformed or never-sent answer, real kills aimed at the pid the SUT wrote, a freeze that forwards nothing until the thaw |
| `tests/integration/` | the same claims against a real database, and per-trial template clones |

The property files drive the *real* runtime over `MemoryJournal` + `FakeClock` and take its journal — random
event lists would be rejected by the fold and would prove nothing. The crash is a `CancelledError` raised
inside the tool after the effect has landed, which is the exact shape of the window and needs no sleeps.

`tests/conformance/` is the white-box half: faults fired at named boundaries *inside* Keel's write path,
which the shim cannot reach because those windows are inside a single transaction. Each cell checks the
window the fault left before checking the recovery, and the table it writes to `bench/keel_conformance/`
is published beside the matrix and never unioned with it — a boundary only one runtime exposes is not a
fair column. A fault this mode cannot deliver is `N/A` with the reason named, never skipped.

## Layout, and where it departs from §23.1

`keel/` never imports `crashproof/`; `keel/runtime` imports no sibling package (executors register
themselves through `core/protocols.py`); `keel/state` has no I/O imports. `tests/unit/test_layering.py`
enforces all of that, including that `crashproof` touches `keel` in two modules only.

Deliberate departures from the file list in §23.1, each with its reason. Several are merges, because
the split would be boilerplate before it is structure and a file that only re-exports is worse than a
documented merge. Three of the four phase 8 added keep APPROVAL, DELEGATE and the inbox drain inside
the step engine, because each is a transaction the engine owns; the fourth gives the forced cancel a
module of its own:

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
| `verifier/{invariants,metrics}.py` | plus `verifier/views.py` | §19.5's placement view and effect ledger are *views* over the same `TrialFacts` the verdicts are computed from, not verdicts. Putting them in `invariants.py` would mix "what is true" with "how to read it", and `crashproof verify --placement` needs them without needing a verdict |
| `approvals/approvals.py`, registering `StepExecutor(APPROVAL)` | `runtime/ctx.py` (`ctx.approve`) + `runtime/steps.py` (`_park_for_approval`, the binding check, the decision at the drain) | a `StepExecutor` runs one attempt to one outcome (`execute(intent, sctx) -> StepOutcome`). An APPROVAL step has no outcome in its attempt: it commits INTENT, STARTED, `APPROVAL_REQUESTED`, `RUN_WAITING` and the lease release in one fenced transaction and is completed by a later drain — the engine's transaction, fence and drain. An executor registered from outside would need that protocol widened into a second copy of the park, so the engine dispatches the kind itself and `StepExecutor` is unchanged |
| `orchestration/{contracts,children}.py`, registering `StepExecutor(DELEGATE)` | `runtime/delegation.py` (the contract, its validation and schema grading, the `child_result` and `cancel` rows) + `runtime/steps.py` (`_spawn_children`, the drain's child results, fan-out slots) | the same reason as APPROVAL: the spawn is one fenced transaction ending in a park, and a child's result is applied at the parent's drain |
| `runtime/signals.py` | `runtime/steps.py` (`StepEngine._drain_inbox`) | the drain runs at every step boundary inside the engine's own append transaction and acts on the engine's fold — a cancel acknowledged at step *i*, the decision for the approval that parked — so everything it reads and writes is the engine's |
| `runtime/reaper.py`'s force-cancel takeover | `runtime/takeover.py` | two callers — the parent's step engine after `cancel_grace`, and the reaper for a stray whose parent is terminal — share one depth-first path, and neither owns it |
| §25.2 / §25.3 command trees | seven commands differ | declared and not built: `crashproof export`, `keel watch` (cut), `keel fork` (cut from phase 5). Built and in neither tree: `crashproof workloads`, `crashproof agree`, `crashproof placement`, `keel reap`. Those, and every flag-level difference in both directions, are in [`docs/cli-ledger.md`](docs/cli-ledger.md) — a command tree is a contract, and an undocumented gap in one is the same defect as an `N/A` printed as `PASS` |
| §25.2 exit codes | same, now wired, plus one | `chaos`, `inject` and `bench` exit **7** on an invariant FAIL in any scored trial, and `compare --strict` exits **8** when nothing could be claimed. `verify` exits **9** when a row cannot be re-verified, a code §25.1 does not name ([ledger](docs/cli-ledger.md)). A harness whose failure mode is red text in a log nobody reads is not a CI gate |

One platform note: psycopg's async mode cannot run on Windows' default ProactorEventLoop, so every entry
point that opens a connection selects a compatible loop in `keel/core/aio.py`.

## Not yet built (and when)

**Week 3 (§29.2) is depth, and most of it has landed:** `KeelMachine` over every mechanism with
`sim.to_fault_spec` (r001–r005 fixed, K6's first case amended); `ctx.sleep`, the durable plan
(`ctx.plan`), `ctx.compact()` and continuation segments (`Continue(state)`, `SEGMENT_STARTED`, the
forced boundary, C2, `before:segment_write`) with W3 `long_horizon_50` on
the Keel arm; `crashproof confirm` and the two-tier report, and the week-2 confirmation plan (25
cells, 7 500 trials) running at `dcdd533`; `ambiguity_window_width` and K3 for every arm; streaming (`STEP_CHUNK`, `partial_ok`, `during:stream(chunk=k)` — **all seventeen hook boundaries
now exist**, with 54 conformance cells run and 12 N/A — `model_stream_truncate`, W7 `streaming_answer` on
the Keel arm); the static HTML matrix pages (`report --fmt html`, `bench/reports/html/`) and the static
timeline page (`crashproof demo --html`). **In progress:** human resolution (`keel signal --resolve`),
the `Policy` implementation, the §18.6 drift detectors, the `Sandbox` per-epoch workspace and §20.7's
audit queries. **Not started:** FORK, cut from phase 5 by §28.5's own cut
line and last in week 3's cut order. **Cut:** FastAPI + SSE (second in §29.2's cut order — the static
page alone gives outreach a link) and `keel watch` (`keel events --follow` shows the same BEFORE CRASH /
AFTER RESTART split, in the event stream where it already lives).

**Named, not built:**

- `max_usd` and `max_wall_clock` (phase 4): they need a pinned price table and a deadline every
  waiting kind respects.
- A delegation's `deadline_s` is journaled in the contract and not enforced by the parent: a child
  that never reaches terminal leaves its parent in `WAITING_CHILDREN`, charged at the child's full
  slice, until someone cancels it. The timer → cancel → takeover path that closes it is the one
  parent-cancel already uses, and arrives with the first cell that measures it.
- `keel signal --resolve STEP=… [--evidence S]` and `--compensate STEP` (§25.2, v1), and
  `Keel.compensate`. A run SUSPENDED on a `RESOLVED_UNKNOWN` step — EXTERNAL's `escalate`, and now an
  IDEMPOTENT outcome nobody knows (`key_window_expired`) — has no way out today but `keel cancel`:
  `keel resume` replays to that step and suspends again.
- The crash-open half of `key_window_expired` (§9.1): an attempt still open at recovery is re-run
  under the same key without counting against the retry policy, because recovery is not retry (§8.3);
  bounding it needs its own count, and nothing measures it yet.
- `tool_duplicate_response` (§27.7: week 2, proxy only). The proxy speaks HTTP/1.1 with `Connection:
  close`, one response per request, and §11.5's own caveat is that the late bytes reach the SUT only
  when the transport outlives the app-level timeout — a cell for a sync-tool variant that does not
  exist yet.
- `partition_worker_world`: V2 in §27.7, and fourth in §29.1's cut order.
- W4 `side_effecting_order` is **cut**, third in §29.1's cut order: it needs TRANSACTIONAL, the
  effect-table bridge and a DBOS arm to be a comparison.

§27 is the binding staging table. One published page is ahead of it: W5-pre, a tier-2 cell built in
week 2 for the reason given above.
