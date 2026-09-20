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

**[`bench/reports/v1_w1_shim.md`](bench/reports/v1_w1_shim.md)** — 208 cells, eight runtime
configurations, two bands, every arm running the same spec file at one commit. Duplicate *applied*
effects in the `EXTERNAL` band (`issues.create`, `dedup: false`, no key), per cell:

| (location, fault) | keel | dbos ×2 | langgraph ×3 | restate | temporal |
|---|---|---|---|---|---|
| `before:tool_call` | 0 of 30 | 0 of 30 | 0 of 30 | 0 of 30 | 0 of 30 |
| `after:tool_effect` | **0 of 30** | **30 of 30** | **30 of 30** | **30 of 30** | **30 of 30** |
| `after:tool_return` | **0 of 300** | **239 · 204 of 300** | **30 of 30** | **30 of 30** | **30 of 30** |
| `pause_past_ttl` | **97 of 300** | 0 of 30 | 0 of 30 | **45 of 30** | **47 of 30** |

The middle two rows are the thesis: a journal written before the effect leaves the process, and a
fence that makes the write mean something. The last row is the honest cost, and the first share of it
is Keel's. A fence protects the journal and cannot reach a third party, so a worker frozen past its
lease duplicates in 97 of its 300 trials — 0.32 extra applications a trial, the residual the
constitution names and refuses to claim away. Restate and Temporal duplicate *more* at that trigger,
45 and 47 applications over thirty trials apiece, which is 1.5 and 1.57 each; LangGraph and DBOS read 0 for a different reason — with no successor taking over
while the holder is frozen, nothing races it. In the `IDEMPOTENT` band the same freeze produced 18
re-sends and **0** duplicates for Keel: the key travels and the receiver does the rest.

The day-3 run this page used to front, [`matrix_v0`](bench/reports/matrix_v0.md) (40 cells × 30
seeds, four configs), is still published and is what K10 was checked against.

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

## Status — phase 10 of 10: publication

Week 4 of §29.3, and the last one. The runtime is complete to its v1 scope, the harness can say what
its own instrument is doing, and every cell the release publishes as its matrix has been re-run at
one commit with a confirmation tier on the cells a claim depends on (the earlier runs — `matrix_v0`,
`tier1a`, `tier1p`, `reask_alternate`, the four `week2_*` pages — stay published as what they were)
([below](#the-release-matrix-eight-arms-at-251e52d)). The [write-up](docs/writeup.md) is current; the
[upstream reports](docs/upstream/README.md) are drafts and are not filed — that is the owner's call,
not the harness's. All eleven kill criteria are read at the release and
[three fired](#kill-criteria-at-the-release).

- **Property depth** (§12). `KeelMachine` drives the real worker, engine, inbox, approvals,
  delegation, takeover, reaper, retry policies, breaker, segments and streams over `MemoryJournal` and a
  `SimClock`, checks S1–S9, C1–C3, J1–J2 after every rule and L1–L3 at teardown, and turns a shrunk
  failure into a fault spec (`sim.to_fault_spec`, `bench/specs/regressions/`). Five Keel bugs pinned
  as r001–r005, and one design gap — an IDEMPOTENT outcome nobody knows hid an applied effect behind a
  clean FAILED — amended in the document rather than patched (K6's first case).
- **Long horizon** (§18). `ctx.sleep` parked on the store's clock; the durable plan as `PLAN_UPDATED`;
  `ctx.compact()` as a MODEL step that resets the context projection; continuation segments —
  `Continue(state)` with a program-declared model, `SEGMENT_STARTED`, the forced boundary, recovery
  and VERIFY from the latest boundary, `state_schema_mismatch` → SUSPENDED, C2, `before:segment_write`
  — and W3 `long_horizon_50` on the Keel arm at 30 seeds: fifty rounds, a compaction and a plan item
  every ten, a two-second sleep after the twenty-fifth and a continuation boundary every twenty, ending
  `counter=49` ([the script](crashproof/workloads/scripts/long_horizon_50.yaml)); three cells, every
  invariant held and L1 30/30 ([`v1_w3`](bench/reports/v1_w3.md)).
- **Streaming** (§10.7). `STEP_CHUNK` batched every 256 tokens / 500 ms under the fence, `partial_ok`
  for PURE, a mid-stream failure disposed by the class, the budget charged from `usage_cum`,
  `during:stream(chunk=k)` — **all seventeen boundaries**, 66 conformance cells (54 run, 12 N/A) —
  `model_stream_truncate`, and W7 `streaming_answer` on the Keel arm at 30 seeds
  ([`v1_w7`](bench/reports/v1_w7.md)); which arms can stream is on each adapter page.
- **The human's last moves** (§7, §20). `keel signal --resolve STEP=completed|failed|cancelled` and
  `Keel.resolve_step` settle a `RESOLVED_UNKNOWN` step (a resolve implies the resume); `StaticPolicy`
  with `allowed_tools` and `require_approval` as a pre-step verdict that takes two indices; the
  §18.6 drift detectors on `keel show`; the `Sandbox` per-epoch checkout for `LOCAL_FS`; §20.7's
  audit queries. Cut, in §29.2's own order: the Sandbox git snapshot, FastAPI + SSE; FORK stays cut.
- **Honest numbers** (§15, §19.5). `crashproof confirm` writes the n = 300 plan from the rows (the
  release's: 17 cells, 5 100 trials at `251e52d`, run and folded into the pages); `report` and `compare`
  tell the tiers apart by seed and print screening in an appendix; `crashproof placement` reads every arm's own commit record
  — K3 fired for DBOS at `after:tool_return` over the release's shim trials, those cells exploratory —
  and `--window` measures `ambiguity_window_width` (medians 8.2–26.6 ms over the release's shim
  baselines, [below](#kill-criteria-at-the-release)); `report --fmt html` and the static timeline page.
- **What the instrument got wrong, found and fixed this phase**: the POSIX self-`SIGSTOP` racing the
  supervisor (four Restate freeze trials scored against Restate; the release re-run completes both
  cells 30/30), a stale forced segment cut (r005), VERIFY on a run paused after a decided failure
  (r004), the sticky-queue default hiding behind Temporal's pinned heartbeat, and a VM clock that failed
  a Keel baseline on S4.

461 unit + property + conformance tests and 31 against Postgres at the phase commit. The write-up is
`notes/Phase-9-Depth.{html,pdf}`; the confirmation rows are folded into the three release pages whose
cells the tier selected — [`v1_w1_shim`](bench/reports/v1_w1_shim.md) (7 cells),
[`v1_w1_proxy`](bench/reports/v1_w1_proxy.md) (6) and [`v1_w5_pre`](bench/reports/v1_w5_pre.md) (4) —
each of which prints those cells at n = 300 and keeps their thirty-seed reading in an appendix. The
other four pages selected no cell and are thirty seeds throughout.

### Phase 8: outside the holder

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
  open breaker's cooldown does. `provider_outage` is built in shim mode; the release matrix runs it at
  `before:model_call` on every arm ([`v1_w1_shim`](bench/reports/v1_w1_shim.md)).
- **The verifier.** S7 is judged against the World through the effect ledger and can now fail: two
  applications under one approval, an application under an approval rejected, expired or never
  decided, or a gated tool applied with nothing granted. S6 (cancel honoured, judged by journal order)
  is a grid column on every page and N/A in every published cell, because no tier-1 cell cancels.
  `approval_binding_violations` is measured on the 840 release rows whose workload gates something
  and `wait_durability` on the 480 that park; `cancel_latency_ms` is defined and null on all 18 843,
  because no published cell cancels. No page prints any of the three yet.
- **Fifteen of seventeen hook boundaries** at the end of this phase; the last two landed in phase 9,
  and [`bench/keel_conformance/table.md`](bench/keel_conformance/table.md) is now
  66 cells, 54 run and 12 N/A, S7 and S8 judged from the whole tree of journals.
  `during:approval_wait` and `during:child_wait` fire with the lease already released.
- **Proxy mode** (§11.2). The black-box injector at the network edge: the proxy is the only firing
  site, and the shim inside the SUT rides along observe-only to count calls at the wire. Both append
  to the trial's log, and on Windows that append was not atomic until `7a22596`, after the release
  commit: about one proxy trial in six lost a tool-boundary observation line, and one torn line took a
  bench run down, which `--resume` re-took. No published metric reads those lines, and the model-call
  lines the economy columns count were not lost in any baseline trial checked.
  [`bench/reports/tier1p.md`](bench/reports/tier1p.md): 36 cells × 30 seeds, **1 080 trials**, every
  safety invariant PASS; Keel applies once under kill-after-effect, 5xx, dropped, malformed and timeout
  (the probe finds COMMITTED), LangGraph sync twice in each (PASS against at-least-once, printed raw).
  Two of its triggers were unsound, and both have been re-run. Keel's `pause_past_ttl` froze the
  process named by `sut/pid-0`, which the successor wrote too, and in 41 of its 60 trials that was the
  idle successor: the worker holding the run was never frozen, timed out on its own parked request,
  re-attempted, and the parked request applied again at the thaw. The duplicates are on the page
  either way; the mechanism the cell exists to show ran in 19 of the 60. And 34 of the 120
  `kill@after:tool_return` trials record no restart — the run finished before the kill landed — which
  current scoring makes a void trial. Their latest re-run is the release matrix at `251e52d`
  ([`v1_w1_proxy`](bench/reports/v1_w1_proxy.md)), after `22f53d9` gave the successor a pid file of its
  own and made a kill that never landed void: all 60 of Keel's `pause_past_ttl` trials there record the
  successor's `ORPHANED` takeover, the `EXTERNAL` cell applies twice in 30 of 30 and the `IDEMPOTENT`
  one re-sends 30 times and applies 0, L1 30/30 in both; and the four `kill@after:tool_return` cells of
  Keel and LangGraph `sync` have no void trial, every kill in them executed.
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
  stays in its own band. **Both pages are superseded:** `approval_delay` now sends §11.4-C's duplicate
  click and `approval_expiry` forbids the deploy by name — new `spec_hash`es for both cells — and the
  Keel arm's approve now names the approval it decides. [`v1_w5`](bench/reports/v1_w5.md) and
  [`v1_w5_pre`](bench/reports/v1_w5_pre.md) are the latest re-run, at `251e52d` and on all eight
  configurations, `exit` included ([below](#the-release-matrix-eight-arms-at-251e52d)); the rest of
  what did not run still has not.
- **Engine arms.** DBOS (`native`, and Pydantic AI under `DBOSDurability`; `recovery_mechanism = self`,
  F1 `workflow_id:step_id`), Temporal (Pydantic AI under `TemporalDurability`; `engine`, F1
  `workflow_run_id:activity_id`) and Restate (Pydantic AI through `RestateAgent` — a wrapper in
  Restate's SDK, not a pydantic-ai capability, and every Restate cell carries that caveat; `engine`, F1
  `ctx.uuid()` drawn before each tool's `ctx.run`) are merged, each smoked at one seed over W1, W5 and
  W5-pre when it merged — smokes, not results; the release matrix
  ([below](#the-release-matrix-eight-arms-at-251e52d)) runs their cells at 30 seeds, and six of them at
  300 in its confirmation tier: DBOS's shim `EXTERNAL` `after:tool_return` and its baseline in both
  configs, and Restate's proxy `kill@after:tool_return` and its baseline. `restate-sdk` has
  no Windows wheel and `restate-server` is a Linux binary, so the Restate arm's rows come from the
  harness under WSL2, and its `config_pin` says `platform: linux (WSL2)` where every other arm's rows
  are Windows.

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
  K3 cannot be computed from them. The first full re-run at one commit, with the engine arms added, was
  the week-2 matrix at `dcdd533` ([`week2_w1_shim`](bench/reports/week2_w1_shim.md),
  [`week2_w1_proxy`](bench/reports/week2_w1_proxy.md), [`week2_w5`](bench/reports/week2_w5.md),
  [`week2_w5_pre`](bench/reports/week2_w5_pre.md)); the release matrix
  ([below](#the-release-matrix-eight-arms-at-251e52d)) is the one that supersedes it.

Fixes: the Keel runtime in `41f6ca0` and `652d8e6`; the harness, verifier, reports and CI in
`22f53d9`..`cd8665e`; the week-2 gaps in `3e70a9f`, `9a6e1ae` and `182994a`; the documents in the
commit that added this section.

### The release matrix: eight arms at `251e52d`

§29.3's artifact: Keel, LangGraph ×3, DBOS `native` and `pydantic_ai`, Temporal and Restate (both
Pydantic AI), over W1 in `shim` and `proxy` mode, W5, W5-pre and the re-ask cell, with Keel alone on
W3 and W7 — **448 cells × 30 seeds, 13 440 screening trials, plus the 17 cells the confirmation tier
selected re-run at n = 300, 5 100 more; every row at `251e52d`** (18 843 rows across the seven sets,
re-takes included). 46 trials are void, all of them in LangGraph `exit`'s two proxy
`kill@after:tool_return` cells (21 and 25 of 30 — the proxy's kill from outside races `exit`-mode's
own process exit). A void rate of 70 % and 83 % is §30's K7, so those two cells are **withdrawn** on
[`v1_w1_proxy`](bench/reports/v1_w1_proxy.md): the grid prints their void and raw counts and no
verdict, because what their trials measured is the harness. Every other set is void-free, the
confirmation tier included. Restate's shard ran the
same specs under WSL. Pages:
[`v1_w1_shim`](bench/reports/v1_w1_shim.md) (208 cells) ·
[`v1_w1_proxy`](bench/reports/v1_w1_proxy.md) (144) · [`v1_w5`](bench/reports/v1_w5.md) (40) ·
[`v1_w5_pre`](bench/reports/v1_w5_pre.md) (24) · [`v1_reask`](bench/reports/v1_reask.md) (16) ·
[`v1_w3`](bench/reports/v1_w3.md) (3) · [`v1_w7`](bench/reports/v1_w7.md) (13) ·
[`agreement_v1`](bench/reports/agreement_v1.md) · 21 `compare_v1_*` pages, Keel against each of the
seven other configurations on `v1_w1_shim`, `v1_w1_proxy` and `v1_w5` (for one,
[`compare_v1_w1_shim_keel_vs_langgraph_sync`](bench/reports/compare_v1_w1_shim_keel_vs_langgraph_sync.md)).
The write-up marks every §13.7 hypothesis and is re-quoted at the release commit
([`docs/writeup.md`](docs/writeup.md)); the upstream reports are the §29.3 deliverable still in draft,
and filing them is the owner's call.
`crashproof verify --recheck` over the trial directories is §29.3's publication gate; the
directories stay on the machine that ran them, as every published run's do.

**The confirmation tier** ([`bench/confirm/v1.yaml`](bench/confirm/v1.yaml), §15.3) is those 17 cells
— every cell whose binary estimate was not unanimous at screening, Keel's arm at the same trigger,
and each one's baseline — re-run at n = 300 on fresh seeds (100 000–100 299), 5 100 trials, none
void, each re-verified from its own trial directory. Nine of the seventeen are fault cells; the other
eight are the baselines their deltas are paired against.

*Two verdicts moved, both DBOS's.* `after:tool_return` fails L1 in both configs — 2 of 300 in
`native` (seeds 100251 and 100272) and 1 of 300 in `pydantic_ai` (seed 100142), no terminal state
inside the trial timeout, each after one restart — where screening read 30/30 in both.

*Six raw counts moved, read per trial.* Keel's zombie residual under `pause_past_ttl` goes 0.13 → 0.32
duplicate applications a trial (4 of 30 → 97 of 300); DBOS's two `after:tool_return` cells 0.70 → 0.80
and 0.47 → 0.68 (21 and 14 of 30 → 239 and 204 of 300); LangGraph `async`'s proxy kill holds on effects
at 0.97 → 0.98 (29 of 30 → 294 of 300) and *does not* on receipts, 1.0 → 1.43 (30 of 30 → 428 of 300);
Restate's proxy kill falls, 0.40 → 0.32 (12 of 30 → 97 of 300); and two divergence rates fall for
arithmetic rather than behaviour — W5-pre's `langgraph.sync` `approval_delay` 1 of 30 → 1 of 300, and
Keel's proxy kill 0 of 30 → 1 of 300, that one trial being the artefact described below. No safety
verdict moves in any of them: an arm that declares at-least-once is judged against that, at either n.
W5-pre's `approval_delay` keeps its duplicate shape exactly — the ungated `notify` applied twice in
every one of the 300 `langgraph.sync` trials and three times in one, so `dup_eff` counts 301 extra
against 31 over 30 — and Keel's two W5-pre cells and its shim `after:tool_return` stay clean at
300/300.

*Two things only the larger n could show, and both are ours.* One of Keel's 300 frozen trials ended
FAILED (seed 100067): a step that went ambiguous, was probed `ABSENT`, re-attempted and went
ambiguous again could not be probed a second time, because the `events_resolved_once` index keyed the
resolution method rather than the attempt. Every invariant on that row passes — it is visible as
`logical_correctness` 0, not as an L1 or C1 FAIL — which is why no verdict caught it. Fixed after the
release commit in `2ffbe91`, with §6.2 amended and `MemoryJournal` mirroring the index; the published
rows are at `251e52d` and none of them changes. And one of Keel's 300 proxy baselines ended FAILED
(seed 100099) for a reason that is not Keel's: `kv.search` timed out three times against a World
taking 1.2 s to answer on a machine running two other jobs, and the three-attempt policy gave up. Its three receipts are those attempts — two of them counted duplicates — and with
one more from seed 100100 they are the whole of the 26th disagreement in the agreement column, the
only one of the 26 that is not the instrument. The same seed's kill trial is the single `replay_divergence` in that cell — it applied the
effect once and completed, and is scored divergent only because the metric compares a trial to its
own twin, and that twin applied nothing.

Against the week-2 matrix at `dcdd533` (12 480 trials, the four `week2_*` pages) — reading the
release's confirmed cells at their screening tier, which is the tier `dcdd533` has — every safety
verdict is the same in all 416 cells the two runs share; two L1 verdicts go from FAIL to PASS —
Restate's shim `pause_past_ttl`, 29/30 → 30/30 in `EXTERNAL` and 27/30 → 30/30 in `IDEMPOTENT`
(below) — and 21 cells print a different count, latency medians aside. The largest: Keel's shim
`pause_past_ttl` residual, 20 → 4 of 30; DBOS's `EXTERNAL` `after:tool_return` duplicates, 18 / 24 →
21 / 14 (`native` / `pydantic_ai`); LangGraph `async`'s proxy `kill@after:tool_return`, 22 → 29
duplicates (re-sends 23 → 30, and 18 → 34 in the `IDEMPOTENT` band; +2 model calls where it was +1);
Restate's in that cell, 5 → 12; and LangGraph `exit`'s two proxy cells, void 1 → 46. Ten more are
shifts of one to five in the `pause_past_ttl` and `after:tool_return` duplicate and re-send counts of
Temporal, Restate and DBOS — in one of them, Restate's `IDEMPOTENT` shim `pause_past_ttl`, `diverged`
also goes 3/30 → 0/30. The last three are W5-pre's `sync` column: `kill_while_waiting` `diverged`
29/30 → 30/30, and `notify` duplicates 31 → 30 in the fault-free baseline and 30 → 31 under
`approval_delay`.

- **Keel fails no safety invariant in any cell of the seven.** Its one duplicate source is the named
  zombie residual: `EXTERNAL` `pause_past_ttl` applies twice in 97 of the 300 confirmed shim trials
  and 4 of the 30 that screened it (30 of 30 in proxy mode, at thirty seeds, where the parked request
  lands after the successor's re-attempt); in the `IDEMPOTENT` band the same freeze re-sends 18 times
  in shim mode and 30 in proxy, and applies 0 in both.
- **The window every other arm leaves open.** At `kill@after:tool_effect` on `EXTERNAL`, all seven
  other configs apply the issue twice, 30 of 30, in shim and proxy mode alike; Keel's probe finds the
  applied effect, 0. The same holds behind the approval gate: W5's `kill@after:tool_effect` deploys
  twice in 30 of 30 trials on every arm but Keel. At `after:tool_return` LangGraph ×3, Temporal and
  Restate duplicate 30 of 30, against Keel's 0 of 300 at the same trigger. DBOS duplicates there too —
  confirmed at n = 300, 239 of 300 (`native`) and 204 of 300 (`pydantic_ai`) — but its four cells at
  that trigger are **exploratory, not headline**: they are the four the release's placement check
  fails on, 47–70 % of their kills landing inside the intended window against 100 % on every other arm,
  because DBOS writes its step checkpoint on an executor thread that races the shim's kill
  ([dbos](docs/adapters/dbos.md), [K3 below](#kill-criteria-at-the-release)).
- **Faults that do not kill.** Keel ends 30/30 logically correct under `tool_500`, `tool_timeout`,
  `model_500`, `model_timeout` and `provider_outage`. DBOS runs with step retries off (its default), so
  a 5xx, a tool timeout or the outage ends the workflow in ERROR — 0/30 correct, recovered, printed not
  judged. Temporal and Restate retry the `EXTERNAL` call under `tool_500` and `tool_timeout` and create
  the issue twice, 30 of 30.
- **Restate is judged against its own claim** ("Tool side effects are not duplicated", so
  `exactly_once`): S1 FAIL in 5 shim cells, 7 proxy cells, W5's `kill@after:tool_effect` and the re-ask
  cell. Its two `pause_past_ttl` shim cells, stuck in 4 of 60 trials at `dcdd533` by a harness race
  (the POSIX self-`SIGSTOP` landing after the supervisor's resume — fixed in `8d90198`, the worker only
  parks now, as on Windows), complete 30/30 with L1 30/30 in both. Only the Restate shard runs on POSIX.
- **The re-ask cell on every arm** (`kill@after:tool_effect` + `model_reask_alternate`, H10). LangGraph
  `async` and `exit` re-ask the model after the restart (+2 calls) and file a second, different issue
  beside the first, 30 of 30 — `duplicate_effects` 0; the one request re-sent (`dup_rcpt` 30) is the
  search. Every step-memoizing arm re-asks nothing (+0): Keel 0 duplicates, and DBOS ×2, Temporal,
  Restate and LangGraph `sync` re-fire the same tool 30 of 30.
  By H10's own discriminator, `replay_divergence`, it held for Keel (`diverged` 0/30), `async` and
  `exit` (30/30) and **failed** for DBOS ×2, Temporal, Restate and LangGraph `sync`, which score 30/30
  on the re-fired tool with no re-decision (+0): the column does not tell a re-fire from a re-decision.
  By `+calls`, which the hypothesis does not name, all eight separate as predicted.
- **W5-pre** reproduces H7's pre-interrupt clause on every LangGraph config — `notify` twice in the
  fault-free baseline and under `approval_delay`, three times under `kill_while_waiting` — and on no
  other arm. The `sync` column's first two cells are confirmed: 300 extra `notify` effects over 300
  baseline trials and 301 over 300 under `approval_delay`, where one trial sent it three times. W5's
  `approval_expiry` is L1 FAIL by design on all three LangGraph configs (no deadline primitive);
  every other arm completes "not done".
- **W3 and W7 are 30-seed rows, Keel only.** W3 `long_horizon_50`: baseline, `kill@after:tool_effect`
  and `pause_past_ttl` — every invariant held, L1 30/30, 30 re-sends and 0 duplicates under the kill and
  the freeze alike. W7 `streaming_answer`: 13 cells — the baseline, kills before and after the model call
  and the tool call, `kill@during:model_stream(chunk=7)`, `model_stream_truncate`, `model_500`, a freeze
  before the model call, and the four re-ask twins — every invariant held, L1 30/30, 0 duplicates, one
  extra model call on each model-side fault and none on the tool-side kills.

### Kill criteria at the release

§29.3 asks for K7, K9 and K11 at the end of week 4; this release reads all eleven (§30), each against
that section's own wording. **Two fired — K3 and K7** — and a third, K9, has its remedy applied
although its measurement is not met. Each carries §30's own decision with what was done beside it. K3's and K4's
numbers come from `crashproof placement` over the release trials, which reads the trial directories
rather than the rows, so no page under `bench/reports` carries them and CI cannot re-render them.

| | at the release | in one line |
|---|---|---|
| **K1** everyone passes | not fired | Restate FAILs S1 in 14 cells against its own claim, and every non-Keel arm duplicates an EXTERNAL effect at T2 |
| **K2** engine parity | not fired | DBOS and Temporal match Keel on every *judged* safety verdict and Restate does not; none of the three matches on economy |
| **K3** unfair triggers | **FIRED** | DBOS at `after:tool_return`, 47–80 % of kills in window against a 90 % floor |
| **K4** window too narrow | not decidable | the widths are measured; the kill rate they must be multiplied by is not |
| **K5** adapter infeasible | not fired | every arm expresses W1, W5 and W5-pre in cited primitives; what it cannot is N/A with the reason |
| **K6** Keel fails itself | not fired on its measurement | no `hook` cell FAILs; two design defects found by other instruments, both fixed, both sections amended |
| **K7** not reproducible | **FIRED** | two cells 70 % and 83 % void — withdrawn from the grid, counts kept |
| **K8** no power | not fired | at n = 300 the compare pages claim differences rather than reading them all too noisy |
| **K9** prior art collision | not fired on its text · remedy applied | two public artifacts hold a clause each and neither holds both; cite, do not compete |
| **K10** schedule | not fired | matrix v0 landed on day 3 |
| **K11** instrument invalid | (a) not fired, audited · (b) not run | 400 audited kills, none answered without its receipt; the real-model subset was cut |

- **K1 (everyone passes) has not fired.** It needs zero S1–S5 FAILs and zero raw duplicates at T2/T3
  in every F0 cell; in the release matrix every arm but Keel duplicates the `EXTERNAL` issue at
  `after:tool_effect` 30 of 30, and Restate fails S1.
- **K3 (unfair triggers) fired at one trigger, on both clauses.** DBOS at `after:tool_return`, and
  the ten-point clause fires between the two DBOS adapters as well as between runtimes.
  `crashproof placement` reads each runtime's own commit record (Keel's journal on the host clock,
  LangGraph's checkpoints, DBOS's `completed_at_epoch_ms`, Temporal's `ActivityTaskCompleted`, Restate's
  `Notification: Run`). Over the release's W1 shim trials (6 241 rows, every one at `251e52d`) it puts
  100 % of fired faults inside the intended window in every tool-boundary cell of every arm but four,
  all DBOS at `after:tool_return`: 70 % (21/30) and 63 % (19/30) for `native` EXTERNAL / IDEMPOTENT, and
  47 % (14/30) and 53 % (16/30) for `pydantic_ai`, whose EXTERNAL cell it also flags mis-aimed (its
  commonest landing, 16 of 30, is after commit step 4). Between arms that trigger is 53 points apart in
  EXTERNAL and 47 in IDEMPOTENT; every other tool-boundary trigger, 0. DBOS writes its step checkpoint on
  an executor thread, which races the shim's kill ([dbos](docs/adapters/dbos.md)). The same join over
  the confirmation trials (2 119 rows), which is the tier the grid publishes the two `EXTERNAL` cells
  at, reads 80 % (239/300) for `native` and 68 % (205/300) for `pydantic_ai` — still under the 90 %
  floor, and Keel's two confirmed cells are 300/300. In aggregate the in-window counts track those
  cells' duplicate counts (239 against `dup_eff` 239 at n = 300, 205 against 204; 21 / 19 / 14 / 16
  against the same four at thirty seeds), but no output joins the two per trial, so the correspondence
  is a total and not a per-trial claim. §30's decision for a K3 failure is that shim cross-runtime
  cells are not publishable, with the fallback that claims move to `proxy` mode and shim cells demote
  to **exploratory**. Applied here: every W1 cell has a proxy twin and the cross-runtime reading at
  that trigger rests there, and those four DBOS cells are exploratory rather than headline — DBOS at
  `after:tool_effect` (100 % in window) is its T2 result. The rest of the shim set is still published,
  which is a departure from §30's blanket wording and is stated as one: placement is 100 % for every
  other tool-boundary trigger of every arm, at both tiers. Model-boundary faults have no
  K3 window, so their cells are not computable. The proxy/shim agreement column is the cross-check
  ([`agreement_v1`](bench/reports/agreement_v1.md)): 86 of 112 comparable twins agree, and 25 of the 26
  that differ are the instrument — `kill@after:tool_return` from outside lands after `taskkill`'s
  latency (15), `pause_past_ttl` parks the request at the proxy instead of freezing before the send
  (6), and LangGraph `async`'s shim kill lands before its checkpoint flush (4, receipt counts only).
  The twenty-sixth is not: Keel's `EXTERNAL` baseline, twinned over the 330 seeds both sides ran,
  carries three duplicate receipts on the proxy side and none on the shim's — two of those trials
  re-sent a call the World had already received, and one of the two ended FAILED.
  [`agreement_week2`](bench/reports/agreement_week2.md) counts 87 of 112 at `dcdd533`: the same 25
  cells, without that last one.
- **K4 (window too narrow) is week 3's; its instrument exists.** `crashproof placement DIR --window`
  measures `ambiguity_window_width` on baseline trials — World receipt to the SUT's own commit record.
  Over the release's W1 shim baselines, 60 per arm, the medians are DBOS 8.2 (`native`) / 9.8
  (`pydantic_ai`) ms, Keel 9.0, LangGraph 12.9 (`async`) / 13.4 (`sync`) / 21.1 (`exit`), Restate 16.1
  (on the WSL clock its World shares) and Temporal 26.6 (IQR 21.1–34.8). K4 also needs a realistic kill
  rate to turn a width into an exposure, which the benchmark does not measure and does not invent.
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
  SUSPENDED for a human. The release matrix never reaches the path — its aimed faults fire once, and
  the single confirmed trial whose re-attempt went ambiguous a second time ended on the
  `events_resolved_once` index instead ([above](#the-release-matrix-eight-arms-at-251e52d)) — so no
  published row changes. On §30's own text K6 has not fired at the release: its measurement is a
  `hook`-mode conformance cell failing S1–S10 or C1–C3, and none does
  ([`table.md`](bench/keel_conformance/table.md), 54 run, 12 N/A, 0 failed). Both defects were found by
  other instruments — the property suite and the confirmation tier. §30's K6 fallback is four things:
  stop adding adapters, fix the design, amend the sections, then re-run the matrix at the same
  `(spec_hash, seed)` and publish the diff. The first three were done for both defects; the re-run was
  not, and no adapter was added after either fix. The published rows are the ones `251e52d` produced —
  no published row reaches the IDEMPOTENT path, and exactly one reaches the resolution-key path, the
  FAILED trial named above.

- **K7 (not reproducible) fired, on the `void_rate` clause.** `langgraph.exit`'s two proxy
  `kill@after:tool_return` cells are 21 and 25 of 30 void, 70 % and 83 % against §30's 5 %; every other
  cell of all seven sets is 0 void, and the confirmation tier — which those two were never part of — is
  void-free after one `--resume` re-take. §30's fallback reads "Move the affected fault types to `hook` mode
  (deterministic with `MemoryJournal` + `FakeClock`) or to proxy cells; publish nothing from them until
  the recheck is byte-identical" — and these already *are* the proxy cells, with a byte-identical
  recheck, so as written it asks for nothing more. The release withholds them anyway, which is stricter
  than the fallback and follows §30's own decision column, *the harness, not the runtimes, is being
  measured*: the grid withdraws any cell over the threshold, printing its void and raw counts and no
  verdict. The
  shim twins are not offered as a substitute — [`agreement_v1`](bench/reports/agreement_v1.md) records
  that they disagree (`duplicate_effects` 9/0 on the nine surviving proxy trials), which is itself the
  instrument finding. `crashproof verify --recheck` is green on every published row of every set, with
  one caveat: since `ef203c4` it skips a row a re-take superseded, which is weaker than §30's "differs
  on any published row". The no-op-commit clause has not been run.
- **K8 (no power) has not fired.** After the confirmation tier the `compare_v1_*` pages claim
  differences rather than reporting them all too noisy: Keel against `dbos.native`,
  `logical_correctness` 300/300 versus 59/300 and `replay_divergence` 0/300 versus 239/300 (p = 0.0000,
  Holm-corrected); Keel against `langgraph.async`, `extra_model_calls` 0.0 versus 2.0 at n = 300. Every
  page keeps its MDD table for the cells that are still too noisy.
- **K9 (prior-art collision) has not fired on §30's text, and its remedy is applied anyway.** The
  measurement is one conjunction: a published artifact that runs *a common agent workload*, under
  process kills, across ≥ 2 durable-execution runtimes, *with an external oracle*, before v1. Two
  artifacts hold a clause each. [`mstevens843/crashpoint`](https://github.com/mstevens843/crashpoint)
  (created 2026-08-27, last commit 2026-09-15; checked 2026-09-20) crashes five engines — LangGraph,
  Temporal, DBOS, Restate, Vercel Workflow — at three barriers named around the effect and the
  runtime's persist write, counts side effects in a hash-chained ledger a daemon holds behind two
  sockets and the subject "cannot read, reset, or seal", proves that oracle discriminates with six
  control subjects over 1 800 trials, and publishes a per-cell pass-rate matrix with error bars over 18
  evidence files. Its workload is one external effect in one step, not an agent. (Its CrewAI finding is
  a same-process tool retry, explicitly not a crash.)
  [`paolo-perrone/agent-crash-recovery`](https://github.com/paolo-perrone/agent-crash-recovery) (public
  2026-08-19) implements one agent on LangGraph, Inngest, DBOS and Temporal and SIGKILLs it mid-run,
  counting the steps paid for twice — with measured tables published for three of the four, the model
  stubbed, and its own banner saying no run against live services is published. Its counter is a
  `@probe` ledger *inside the agent*, and its tools are local sleeps, so nothing outside the system
  under test says what a receiver saw. Neither meets every clause, so the threshold is not met — and a
  novelty claim resting on that gap is not worth making, so §30's remedy is applied as if it had:
  **complement, do not compete.** Nothing had to be retracted, because this page has never used the
  word "first". The headline is what neither checks: effect classes as *declarations* with
  per-endpoint receiver semantics — crashpoint varies the caller's key strategy, never the receiver's
  — ambiguity surfaced and resolved rather than only counted, token accounting, approval and delegation
  invariants, and the two-tier protocol. Three claims came off that list after reading crashpoint
  properly: it scores replay determinism as its own outcome, its controls pin its oracle, and it ran a
  real model in six cells, which this release did not run at all.
- **K10 (schedule) did not fire.** [`matrix_v0`](bench/reports/matrix_v0.md) — 40 cells × 30 seeds,
  1 200 trials — landed on day 3.
- **K11 (instrument invalid): (a) audited and not fired; (b) not run.** (a) The World writes a receipt
  and fsyncs it before it computes the response, and every `after:tool_effect` cell rests on that
  ordering. `scripts/k11_oracle_audit.py` kills the World process around a request and convicts on one
  outcome — a client answered for a request with no receipt in the log. **0 of 400** audited trials
  (300 at a delay drawn from the round trip, 100 aimed inside a withheld response, every one of which
  found its receipt on disk). It is narrower than §30's words: no audited trial landed *between* the
  receipt's fsync and the response's computation, because that interval is microseconds wide and a kill
  from outside takes 0.5–1.1 s to arrive. The audit is calibrated rather than asserted: a third band
  runs a World that defers the receipt past the answer, and it convicts that one 100 times out of 100.
  The reach is bounded by the kill itself, 0.5–1.1 s on this platform, so a mis-ordering of that order
  or wider is visible and one of microseconds is not; `tests/unit/test_k11_audit.py` keeps the
  calibration honest in CI. (b) The `real-model` validation subset is a §29.3 reach item and was cut, so
  no cell's verdict has been compared against a real provider — the matrix pages and the 21 compare
  pages say so beside the model-boundary cells they read, and the agreement pages list those cells as
  unpaired, because model traffic does not cross the proxy.

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
[`w5_pre`](bench/results/w5_pre/results.jsonl), the four `week2_*` sets and the seven `v1_*` sets
([`v1_w1_shim`](bench/results/v1_w1_shim/results.jsonl) … [`v1_w7`](bench/results/v1_w7/results.jsonl)).
`report`, `compare` and `agree` are pure functions over them, and every page names the results
directory, the row count and each `keel_commit` it was rendered from, and the last trial's end rather
than the time it was rendered, so a re-render is byte-identical.
[`scripts/render_reports.py`](scripts/render_reports.py) is the one list of which rows back which
page, as the exact commands; CI runs it and fails on any diff under `bench/reports`:

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
| `tests/conformance/test_hook_cells.py` | the crash-window enumeration: 66 `(boundary, fault, class)` cells — the write path per effect class, the inbox drain and the approval park on a gated run, the spawn transaction and the park on children of a delegating run — 54 run and 12 N/A with reasons; S8 judged from the whole tree of journals |
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
the Keel arm at 30 seeds; `crashproof confirm` and the two-tier report; the release re-run at `251e52d`
([above](#the-release-matrix-eight-arms-at-251e52d)) and its confirmation tier
([`bench/confirm/v1.yaml`](bench/confirm/v1.yaml): 17 cells, 5 100 trials at n = 300, Restate's two
under WSL), run and folded into the pages; `ambiguity_window_width` and K3
for every arm; streaming (`STEP_CHUNK`, `partial_ok`, `during:stream(chunk=k)` — **all seventeen hook boundaries
now exist**, with 54 conformance cells run and 12 N/A — `model_stream_truncate`, W7 `streaming_answer` on
the Keel arm at 30 seeds); the static HTML matrix pages (`report --fmt html`, `bench/reports/html/`) and the static
timeline page (`crashproof demo --html`). Human resolution (`keel signal --resolve STEP=completed|failed|cancelled`, `Keel.resolve_step`;
a resolve implies the resume, §7.2.1), `StaticPolicy` (`allowed_tools`, `require_approval` as a
pre-step verdict that takes two indices, the child's contract held to the parent's capability set), the
§18.6 drift detectors (`steps_since_plan_update`, `items_completed_without_effects`, shown by `keel
show`, the first one gating through `StaticPolicy(stale_plan_after=)`), the `Sandbox` per-epoch
checkout for `LOCAL_FS` tools, and §20.7's audit queries (`keel/journal/audit.py`). **Not started:** FORK, cut from phase 5 by §28.5's own cut
line and last in week 3's cut order. **Cut:** FastAPI + SSE (second in §29.2's cut order — the static
page alone gives outreach a link), the `Sandbox` git snapshot/restore (first in that order; the
per-epoch checkout stays) and `keel watch` (`keel events --follow` shows the same BEFORE CRASH /
AFTER RESTART split, in the event stream where it already lives).

**Named, not built:**

- `max_usd` and `max_wall_clock` (phase 4): they need a pinned price table and a deadline every
  waiting kind respects.
- A delegation's `deadline_s` is journaled in the contract and not enforced by the parent: a child
  that never reaches terminal leaves its parent in `WAITING_CHILDREN`, charged at the child's full
  slice, until someone cancels it. The timer → cancel → takeover path that closes it is the one
  parent-cancel already uses, and arrives with the first cell that measures it.
- `keel signal --compensate STEP` and `Keel.compensate` (§25.2, v1): `--resolve` is built, and a
  compensating action is a second effect with its own class, which nothing here declares yet.
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

§27 is the binding staging table. One published workload is ahead of it: W5-pre, a tier-2 cell built
in week 2 for the reason given above, on three pages since (`w5_pre`, `week2_w5_pre`, `v1_w5_pre`).
