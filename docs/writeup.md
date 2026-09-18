# Crashproof: the write-up

The essay §29.3 says the benchmark exists for. Every number below is from the week-2 matrix at
`dcdd533` — [`week2_w1_shim`](../bench/reports/week2_w1_shim.md) (208 cells),
[`week2_w1_proxy`](../bench/reports/week2_w1_proxy.md) (144), [`week2_w5`](../bench/reports/week2_w5.md)
(40), [`week2_w5_pre`](../bench/reports/week2_w5_pre.md) (24),
[`agreement_week2`](../bench/reports/agreement_week2.md) — **12 480 trials, 12 520 rows with re-takes,
one void**, the rows committed under `bench/results/week2_*/results.jsonl`. The release re-run (week 4)
re-quotes every number at the release commit. The confirmation tier
([`bench/confirm/week2.yaml`](../bench/confirm/week2.yaml): 25 cells, 7 500 trials, seeds ≥ 100 000) is
running and its rows land in the same pages at n = 300. An older page is named where it is cited.

## 1. The thesis

Framework checkpoints are snapshots; durable execution means someone notices the crash, resumes, and
neither double-fires nor loses an effect. An agent that cannot survive `kill -9` is a demo (§1.1).

**Keel** is a single-node, event-sourced, agent-native durable execution runtime (Python, Postgres).
**Crashproof** is the harness that runs Keel *and seven other runtime configurations* through the same
workloads under the same faults, judges each against what it claims, and prints the raw counts beside
every verdict. Keel is the reference implementation that has to pass its own harness, with no path
through it the other arms do not get.

The altitude is below Temporal, DBOS and Restate: those are general workflow engines; Keel is the
agent-native journal, where model calls are the decisions and tool effects are the risk. §2.2 gives four
reasons they were not adopted as the implementation: none has effect classes, so "was it applied?" is
the developer's problem; none distinguishes a model call from a tool call; none exposes
`before:outcome_commit` as a boundary a white-box property suite can fire at; and the objective was to
build the lease, the fence, the journal and the recovery table, not to configure them. Keel claims
exactly-once for nothing but the TRANSACTIONAL class, which is in no published cell.

## 2. The mechanism

Every durable execution engine reduces to three lines (§8.2), and so does Keel:

```python
await journal.append(STEP_ATTEMPT_STARTED(step_index, attempt_no, attempt_deadline))  # barrier
result = await tool.execute(args, effect_key=effect_key)                              # effect
await journal.append(STEP_COMPLETED(step_index, attempt_no, result))                  # outcome
```

**Journal before effect.** Nothing leaves the process before line 1 is durable, and the first statement
of every append is the lease fence — `UPDATE runs SET lease_expires_at = now() + $ttl WHERE run_id = $1
AND lease_epoch = $2` — so a worker that has lost its lease cannot commit another event. Losing line 3 is
the ambiguity; losing line 1 would be an unjournaled effect, which is why S4 and S10 are invariants.

**Effect classes decide what a crash means.** A tool declares exactly one of PURE, IDEMPOTENT, EXTERNAL,
TRANSACTIONAL, and the class alone decides retry, replay and recovery. `STARTED` without an outcome
re-runs a PURE step, re-fires an IDEMPOTENT one under the same `effect_key`, provably never applied a
TRANSACTIONAL one, and makes an EXTERNAL one `AMBIGUOUS` — resolved by the tool's declared `probe`,
`assume_failed`, `assume_succeeded` or `escalate`, never guessed. A timeout on an EXTERNAL tool is the
same state (§8.5): the request left, the receiver's state is unknown, and retrying is how correct
systems duplicate.

**Recovery is not a special path.** On every lease acquisition the worker re-executes the program from
the latest continuation segment; every `ctx.*` call with a journaled outcome returns it at no tokens and
no effect, and the first step without one becomes live. The successor decides from journal state alone
(§8.3) and never consults the dead worker; model outputs are recorded decisions, so control flow is
deterministic under replay by construction, and `VERIFY` is the same loop with `allow_live=False`. All
visible state is a pure fold over the journal.

What Keel does not guarantee is stated once (§8.8): no exactly-once beyond TRANSACTIONAL; no fencing of
third-party APIs; no elimination of the zombie window for EXTERNAL; no detection of a mis-declared class;
no compensation; no protection against a receiver that drops keys; no survival of the single Postgres
node's disk. Each is a named fault or a reported invariant.

## 3. The harness

**The World is ground truth outside every runtime.** A deterministic HTTP receiver whose receipt is
written and `fsync`ed *before* the effect is applied or a response computed
(`tests/unit/test_world.py::test_receipt_is_durable_before_the_response_is_computed`), with per-endpoint
`dedup` and `natural`, `hold(endpoint, ms)` to aim a kill into the effect → acknowledgement window, and
an oracle answering `applied`, `receipts` and `probe`. `duplicate_receipts` counts how often the receiver
was asked; `duplicate_effects` how often the world changed. The gap is what the receiver's idempotency
bought, and the runtime gets no credit for it.

**One spec, one schedule per seed, every arm.** A fault is addressed by workload landmark
(`after:tool_effect` at `tool:create_issue`), never by an ordinal in one runtime's traffic; all of a
trial's randomness lives in a seeded expansion, so `(spec_hash, seed)` is one schedule every arm sees.
The supervisor restarts with identical argv and env and never says which run to resume.

**Verdicts are judged against claims** (§13.6). Each adapter declares `recovery_mechanism` (`self`,
`engine`, `harness`), `claims` per class, `config_pin`, and the `key_source` formula behind its fairness
level: F0 sends no key; F1 sends a key that is a pure function of identifiers the framework persists
*and restores* (Keel's `effect_key`, DBOS's `workflow_id:step_id`, Temporal's
`workflow_run_id:activity_id`, Restate's `ctx.uuid()` drawn before its `ctx.run`); F-exp is an
adapter-synthesised key and never enters the headline band. LangGraph has no F1 key — `thread_id` is
restored by the harness, the same fact as `recovery_mechanism = harness` — so its IDEMPOTENT rows say
`key_source=none` and meet the `natural: true` endpoint ([langgraph](adapters/langgraph.md)).

**Safety cells are never proportions** (§15.4). S1–S10 print `PASS (0 violations in n)` or `FAIL` with
every `(spec_hash, seed, trial_id)` that refutes them; one violation is a FAIL and no number of trials
averages it away. Liveness and economy print as estimates with Wilson intervals, and `too noisy to claim`
replaces any verb of comparison §15.8 forbids. An invariant whose inputs a runtime cannot supply is N/A
with the input named, never PASS.

**Three injection modes.** `shim` fires inside the SUT's client at three instants every runtime has;
`proxy` fires at the network edge with the shim riding along observe-only; `hook` fires inside Keel's own
write path at seventeen boundaries no shim can reach, and its 66 cells (54 run, 12 N/A with the reason)
print in [their own table](../bench/keel_conformance/table.md), never unioned with a cross-runtime row.

## 4. The matrix

Eight configurations — `keel.default`, `langgraph.{sync,async,exit}`, `dbos.{native,pydantic_ai}`,
`temporal.pydantic_ai`, `restate.pydantic_ai`, the last three sharing one Pydantic AI agent so "different
agent code" is not a confound between engines — over W1 `tool_chain_1_effect` in two bands (EXTERNAL:
`issues.create`, `dedup: false`, no key; IDEMPOTENT: `issues.upsert`, `dedup: true, natural: true`), in
shim and proxy mode, and W5 `approval_gated_deploy` with its tier-2 form W5-pre. Thirty seeds per cell.
Restate's shard ran under WSL2; its rows say `platform: linux (WSL2)`, every other arm's Windows.

Duplicate *applied* effects, EXTERNAL band, shim mode, out of 30 seeds
([week2_w1_shim](../bench/reports/week2_w1_shim.md)):

| (location, fault) | keel | lg sync | lg async | lg exit | dbos native | dbos pyd | temporal | restate |
|---|---|---|---|---|---|---|---|---|
| `kill@before:tool_call` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `kill@after:tool_effect` | **0** | 30 | 30 | 30 | 30 | 30 | 30 | 30 ✗ |
| `kill@after:tool_return` | **0** | 30 | 30 | 30 | 18 † | 24 † | 30 | 30 ✗ |
| `pause_past_ttl@before:tool_call` | **20** | 0 | 0 | 0 | 0 | 0 | 51 ‡ | 43 ‡ ✗ |
| `tool_500@after:tool_effect` | 0 | 30 | 30 | 30 | 0 § | 0 § | 30 | 30 ✗ |
| `tool_timeout@before:tool_call` | 0 | 30 | 30 | 30 | 0 § | 0 § | 30 | 30 ✗ |
| `sigterm_grace_ok` / `too_short` | 0 / 0 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 |

✗ S1 FAIL against Restate's declared `exactly_once`. † exploratory under K3 (§7). ‡ summed over 30
trials; the count per trial grows with the seeded pause. § the workflow ended in ERROR (DBOS step
retries are off by default): applied once, run not correct. Every other cell has L1 30/30. In the
IDEMPOTENT band `duplicate_effects` is 0 in every cell of every arm; the receipts say what the receiver
absorbed — 30 at `after:tool_effect` for Keel, DBOS, Temporal, Restate and `sync`, 60 for `async` and
`exit`, 18 for Keel under the freeze, 46 and 49 for Restate and Temporal.

**Arm by arm.** *Keel* (`self`): no S1–S5 FAIL in any of its 52 cells across the four pages, C1 PASS in
every one; its only duplicate source is the zombie residual, 20 of 30 shim and 30 of 30 proxy trials
under the freeze; kills cost +0 model calls, `model_500`/`model_timeout` +1, `provider_outage` +3 in every
arm that survives it; median recovery 2.3 s against a 2 s lease. *LangGraph ×3* (`harness`): nothing
notices the crash, the supervisor re-invokes by `thread_id` and the interrupted node re-runs from its
first line; two applied 30 of 30 at T2, T3, `tool_500`, `tool_timeout`, both SIGTERM cells and, in proxy
mode, under dropped and malformed responses — PASS against `at_least_once`, printed; `sync` +0 calls,
`async` and `exit` +2; the SIGTERM cells score identically because there is no drain path to give grace
to. *DBOS ×2* (`self`): the restarted process's PENDING scan resumes the run; 30 of 30 at T2, 18 and 24
at T3 — a race between the shim's kill and a step checkpoint written off the event loop
([dbos](adapters/dbos.md)); with retries off, a 5xx, a tool timeout or the outage ends the workflow in
ERROR, 0 of 30 correct, printed not judged; `pydantic_ai` recovers 1.3 s slower than `native`, the cost of
importing Pydantic AI. *Temporal* (`engine`): the server times the dead or frozen worker's activity out on
its 2 s heartbeat and retries; 30 of 30 at T2, T3, `tool_500`, `tool_timeout`; 51 duplicates over 30
frozen trials, the count being `pause / (heartbeat + backoff)` with the pause drawn in [2×, 4×] of the
heartbeat ([temporal](adapters/temporal.md)); C1 through `temporalio.worker.Replayer`, PASS. *Restate*
(`engine`), judged against its own documentation — "Tool side effects are not duplicated", so
`exactly_once`: **S1 FAIL** in 5 shim cells, 7 proxy cells and W5's `kill@after:tool_effect` — two
applied 30 of 30 at T2 in both modes, behind the gate, and under `tool_500`, `tool_timeout`, dropped and
malformed responses; 5 of 30 at the proxy's T3, where a kill from outside usually lands after the
journal write. Its `pause_past_ttl` cells also scored L1 in 4 of 60 shim trials, and that was the
harness: on POSIX the worker stopped itself too, and when the supervisor's freeze landed first the
self-stop landed after the resume. Fixed after the run; those two cells are pending a re-run.

**Three findings that matter.**

1. **The window every other arm leaves open.** At `kill@after:tool_effect` on EXTERNAL — the World has
   the effect, the framework has not recorded it — all seven other configurations apply the issue twice,
   30 of 30, in shim and in proxy mode. Keel's probe finds the applied effect and re-fires nothing: 0. The
   same holds behind the approval gate: W5's `kill@after:tool_effect` deploys twice 30 of 30 on every arm
   but Keel ([week2_w5](../bench/reports/week2_w5.md)). Six of the seven claim at-least-once and are held
   to it; this is the cost of a journal written after the effect, printed.
2. **Restate against its own claim.** The one arm whose documentation claims more than at-least-once for
   tool side effects fails S1 in 13 cells, every seed listed. The draft upstream report
   ([docs/upstream](upstream/README.md)) frames it as a docs qualifier — probably intended
   at-least-once — and nothing has been filed.
3. **W5 behind the gate.** Killed while parked on an approval and then granted, every arm deploys exactly
   once, 30 of 30 (H7). LangGraph pays +1 model call because `interrupt()` re-runs the interrupting node,
   and in the tier-2 form ([week2_w5_pre](../bench/reports/week2_w5_pre.md)) an ungated `notify` before
   the gate fires twice in the fault-free baseline on all three configs (one `sync` trial three times) and
   three times under `kill_while_waiting` — 60 extra effects per config in that cell — and on no other
   arm. `interrupt()` has no deadline, so under `approval_expiry` LangGraph is still WAITING at 60 s, 0 of
   30 on every config, L1 FAIL by design; every other arm completes "not done" with nothing deployed.

## 5. Hypotheses (§13.7)

| H | Prediction | Verdict |
|---|---|---|
| **H1** T2 ≡ T3 | a journal written after the effect re-fires at both | **held** for LangGraph ×3, Temporal, Restate (30/30 at both); **refuted by the instrument** for DBOS — 18/30 and 24/30 at T3 against 30/30 at T2, the shim's kill landing after DBOS's off-loop checkpoint in 40–47 % of trials (K3). In proxy mode T3 lands after the parse for most arms (0 for `sync`, `exit`, DBOS, Temporal; 22 `async`; 5 Restate) — the instrument again |
| **H2** Keel is the only zero-duplicate arm at T2/F0 | every other arm exactly one duplicate, within its claim | **held** for the `probe` route: 0 against 30/30 ×7 (shim and proxy). The `escalate` route runs in no published cell — **untested** |
| **H3** keys equalise T2 at F1 | every F1 arm applies once | **held**: 0 applied, 30 receipts for Keel, DBOS ×2, Temporal, Restate. The "knows it re-fired" clause (`ambiguity_surfacing_rate`) is not printed — **untested** |
| **H4** +calls is a durability-mode property | 0 or 1 for memoizing arms; `async` a lost-checkpoint term; `exit` all prior | **held** in shape: kills +0 for Keel, DBOS, Temporal, Restate, `sync`; `exit` +2 (all prior); `async` +2 rather than the predicted +0/+1 — both prior calls, not one |
| **H5** the zombie is the price of a successor | duplicates only with a second claimant; IDEMPOTENT zombie-safe | **held**: Keel 20/30 (two workers), Temporal 51, Restate 43; DBOS ×2 and LangGraph ×3 0 with a 3.1 s gap equal to the pause; Keel IDEMPOTENT 0 applied / 18 receipts |
| **H6** detection latency is the pinned timeout | engines: pinned timeouts; Keel: reaper; DBOS: restart | **held** for Keel (2.3 s), Temporal (4.0 s ≈ heartbeat + retry + start), DBOS (restart + imports); **refuted** for Restate kills — detection is immediate at connection loss and the 7.3 s median is worker start against a doubling backoff ([restate](adapters/restate.md)); its freezes are the timeouts (19.5 s; Temporal 5.5 s). Not compared across arms: no week-2 compare page, and Restate ran on another host |
| **H7** approval durability | one gated effect after a kill while parked; LangGraph +1; tier-2 gives two | **held** 30/30 on all eight arms; LangGraph +1; W5-pre `notify` 2× baseline, 3× killed. `kill @ landmark:approval_decided` **untested**; the "S7 counterexample" clause is a count, not a verdict — S7 is N/A for LangGraph |
| **H8** drain | Keel 0 at `grace_ok`, as T2 at `too_short`; others measured | **held** for Keel (0 / 0, as its T2 is 0). Measured: LangGraph ×3, DBOS ×2, Temporal duplicate 30/30 in both cells identically; Restate applies once in both and the page records no recovery for either — whether it drained or ignored the signal is not on the page |
| **H9** retry cells | documented per-step retry separates the arms; Keel's difference is classification | **held in part**: Temporal and Restate retry and apply twice 30/30; DBOS's documented retries are off by default, so it fails the run instead; LangGraph, predicted to fail, re-fires 30/30 through the harness restart; Keel's timeout is AMBIGUOUS → probe, 0 duplicates, 30/30 correct |
| **H10** `alternate` discriminates only non-memoizing arms | `async`/`exit` diverge, memoizing arms never | **held** for Keel (0/30, +0) and `async` (30/30 — a *different* issue filed, `duplicate_effects` 0); `sync` re-asked nothing (+0) yet scores `diverged` 30/30 on the re-fired tool, so the column does not separate re-fire from re-decision. `exit`, the engines and the M1 positive control **untested** in any published matrix ([reask_alternate](../bench/reports/reask_alternate.md), 180 trials, an older commit) |

## 6. The residual windows

**The zombie.** A worker paused past its lease can still complete the HTTP call whose `STARTED` it
committed; its outcome append is fenced, so the journal never records an effect the receiver has.
Fencing protects journal appends and TRANSACTIONAL effects and nothing else (§8.4). Keel bounds the
window three ways — a pre-dispatch check that `lease_valid_until − now ≥ tool.timeout`, an
`attempt_deadline` committed in `STARTED`, and a reaper that orphans a run with an open non-PURE attempt
only when `now() > max(lease_expires_at, attempt_deadline)` — and eliminates it with none. A `probe` is
point-in-time: a request received before the deadline and applied after the probe is a duplicate it
could not see, a TOCTOU window that closes only with receiver cooperation, i.e. an IDEMPOTENT key.
Measured: 20 of 30 shim trials, where the pause lands between the last `await` and the socket write
(§4.7); 30 of 30 in proxy mode, where the request is parked at the proxy and forwarded at the thaw,
after the successor's re-attempt; under the same freeze the IDEMPOTENT band shows 18 receipts, 0 applied.
The constitution names this window and refuses to claim it away; every runtime with a successor shows it.

**LOCAL_FS reordering.** An IDEMPOTENT-by-content write is at-least-once-with-reordering under a zombie:
a stale write of step *i* can land after the successor's write to the same target at step *i+k*, so the
world ends at the older value while the journal says the newer (§8.7, §9). The v1 `Sandbox` per-epoch
workspace checkout has landed (`78e1312`): a stale worker's write lands in the dead epoch's directory,
the one place Keel makes an EXTERNAL-shaped hazard zombie-safe by construction. The git snapshot/restore
behind `Sandbox.snapshot/restore` is cut, first in §29.2's cut order. No published cell measures this
window — W2, which names it, is not in the matrix.

**The EXTERNAL timeout.** A timeout or transport error on an EXTERNAL tool is crash window W3 with the
worker alive; Keel makes it `STEP_AMBIGUOUS`, never `STEP_FAILED`, and the declared resolution probes.
Measured under `tool_timeout`, `tool_500`, `tool_delay` and, in proxy mode, `tool_dropped_response` and
`tool_malformed`: 0 duplicates for Keel, 30/30 for every arm that retries or re-runs. The IDEMPOTENT half
of the window is the K6 case (§7): with no retry left, an IDEMPOTENT attempt whose outcome was never
known ended the run FAILED with the effects row ABSENT while the World held the effect — §7.4 and §8.5
prescribed exactly that, so it was a design decision. The document is amended: the row reads AMBIGUOUS
while a retry is pending, and with none left the step is `RESOLVED_UNKNOWN{key_window_expired}` and the
run SUSPENDED. No published row reaches that path.

**How wide the window is.** `crashproof placement DIR --window` measures `ambiguity_window_width` on
baseline trials, World receipt to the runtime's own commit record — median over W1 shim: DBOS 7.8 ms
(`native`) / 8.5 (`pydantic_ai`), Keel 9.1, LangGraph 12.3 (`async`) / 12.8 (`sync`) / 20.5 (`exit`),
Temporal 18.7, Restate 23.4 (on the WSL clock its World shares). K4 turns a width into an exposure only
with a realistic kill rate, which the benchmark does not measure and does not invent.

## 7. The instrument

A benchmark that reports its own instrument faults is the point.

**K3 fired for one trigger on one runtime.** `crashproof placement` reads each runtime's own commit
record — Keel's journal on the host clock, LangGraph's checkpoints, DBOS's `completed_at_epoch_ms`,
Temporal's `ActivityTaskCompleted`, Restate's `Notification: Run` — and puts 100 % of fired faults inside
the intended window in every tool-boundary shim cell of Keel, LangGraph ×3, Temporal and Restate. DBOS
at `after:tool_return` lands 60 % / 53 % (`native`, EXTERNAL / IDEMPOTENT) and 80 % / 57 %
(`pydantic_ai`). Joined per trial, every in-window kill duplicated and every out-of-window kill did not
(12/12, 14/14, 6/6, 13/13): those four cells measure the kill's timing, not DBOS, and per §30 they are
exploratory.

**The agreement column.** Proxy and shim twins paired on `(cell, seed)`: 87 of 112 comparable cells agree
on every verdict and every raw count. The 25 that differ are the instrument, each printed with both
numbers: 15 are `kill@after:tool_return`, which from outside the process lands after `taskkill`'s
latency, often after the parse and sometimes after the run has finished; 6 are `pause_past_ttl`, where
the proxy parks the request instead of freezing before the send (Keel 20 → 30, Restate 43 → 50, Temporal
51 → 52); 4 are LangGraph `async`'s receipt counts, whose shim kill lands before its checkpoint flush. The
`after:tool_effect` window is the same in both.

**The audit.** After the phase-8 commit ten reviewers each took one area, every finding re-checked
adversarially before it counted: 103 confirmed (12 blocker, 39 major, 43 minor, 9 nit). On the harness
side, among others: the proxy froze the wrong process in 41 of 60 `pause_past_ttl` trials (`tier1p`); a
kill that never landed scored as executed; S7's applied check could never match, so a gated effect
applied twice under one approval passed; 960 LangGraph rows said `key_source=framework` though the
adapter sends no key; `verify --recheck` exited 0 having re-verified nothing; every page claimed an
n = 300 tier nobody had run. On the runtime side: a park released its lease in a second, unguarded update
that could erase an approve landing in between. Every published cell the audit invalidated was kept and
marked; the week-2 matrix is the re-run at one commit with every arm.

**What the property suite found in Keel.** `KeelMachine` drives the real runtime over `MemoryJournal`
and `FakeClock`; each shrunk failure is pinned as a regression and a fault spec
(`tests/property/regressions/`): a store outage at `before:lease_release` escaped the worker (r001);
VERIFY failed a force-cancelled child whose program raises past its last step (r002); a worker spun for
ever on `WakeRaced` after the reaper marked its lapsed lease (r003); VERIFY failed a run paused between a
decided failure and its `RUN_FAILED` (r004); a forced cut pending when the program returned `Continue`
wrote a stale boundary (r005); and the K6 case above.

**What the adapters found in the harness.** On POSIX `freeze_self` raised `SIGSTOP` on its own process
and returned, and the shim thread ran on long enough to send the request 17 ms after the fault row
([restate](adapters/restate.md)); the fix parks the thread on both platforms. A process mid-`taskkill` is
alive to `poll()` and refuses `NtResume` with `0xC000010A` (`crashproof/faults/process.py`); until that
status was treated as gone the end-of-trial resume took a run down. Temporal's kill cells carried ~8 s of
the SDK's 10 s sticky-queue default hiding behind the pinned 2 s heartbeat — a documented worker option,
now pinned. The WSL VM's clock drifted ±7 % in 0.8 s steps and failed a Keel baseline on S4; a trial
whose store-clock offset moves past `STORE_CLOCK_TOLERANCE_S` (50 ms) is now void.

**Upstream.** Two draft reports, neither filed ([docs/upstream](upstream/README.md)): Restate's
side-effect claim, framed as a docs qualifier; and `restate-sdk[pydantic-ai]` failing to import
`restate.ext.pydantic`. Four candidates considered and not drafted, each failing the
[template](upstream-report-template.md): LangGraph's pre-interrupt re-run is documented and prominent;
its `approval_expiry` is an absent feature, not a contradiction; DBOS's T3 is within its documented
at-least-once and exploratory under K3; Restate's 4 of 60 was the harness.

## 8. What this does not show

- **Thirty seeds.** At n = 30 a recovery-rate gap under ~30 percentage points is invisible and `0/30`
  carries a Wilson upper bound of 11.4 % (§15.7); every page prints the MDD tables and the FAQ.
  `PASS (0/30)` means thirty aimed kills found no duplicate, not that the runtime cannot duplicate. The
  confirmation tier — 25 cells selected by non-unanimous estimates, no claimed difference among them
  (`claims: []`) — is running; nothing on these pages is confirmed.
- **One host, and one and a half.** Every arm but Restate ran on one Windows machine; Restate ran under
  WSL2 on it. A latency difference involving Restate is two hosts as well as two runtimes, which is why
  no latency is compared here.
- **A scripted model.** The provider answers by request content, so every arm sees the same decisions and
  `model_reask_alternate` is possible. It is a fixture; K11(b)'s real-model subset has not been run.
- **Workloads and faults.** W1, W5 and W5-pre only. W4 is cut (it needs TRANSACTIONAL, the effect-table
  bridge and a DBOS arm); W3 and W7 exist on the Keel arm as one-seed smokes ([keel](adapters/keel.md)),
  not matrix rows; W6 has no cited child mechanism in any engine. `partition_worker_world` and
  `tool_duplicate_response` are not built; `provider_outage` ran in shim mode only;
  `kill @ landmark:approval_decided` and the `exit` config's W5 did not run.
- **Pending.** Restate's two `pause_past_ttl` shim cells; the release re-run at the release commit.
- **Not compared.** There is no week-2 compare page; McNemar, paired bootstrap and Holm have run only on
  the older Keel-vs-LangGraph pages
  ([compare_tier1a](../bench/reports/compare_tier1a_keel_vs_langgraph_sync.md): `logical_correctness` A
  better in four EXTERNAL cells, 30 discordant pairs to 0, Holm p < 0.0001; every latency row declined
  to claim). A delegation `deadline_s` is journaled and not enforced.

## 9. Kill criteria (§30), current verdicts

| Id | Verdict at week 2 |
|---|---|
| K1 everyone passes | not fired: every arm but Keel duplicates at T2 30/30, and Restate fails S1 |
| K2 engine parity | week 3's, after confirmation; not decided. Screening: Temporal and DBOS match Keel on every *judged* safety verdict (they claim at-least-once and are held to it) and differ on raw `duplicate_effects` 30 vs 0 at T2, which is not a verdict; Restate does not match |
| K3 unfair triggers | fired for one trigger on one runtime, DBOS at `after:tool_return`; those cells are exploratory and its T2 (100 % in window) is its result |
| K4 window too narrow | week 3's; the widths are in §6; the kill rate it also needs is not measured |
| K5 adapter infeasible | not fired: DBOS ×2, Temporal and Restate express W1, W5, W5-pre in cited primitives with no counter, lookup, retry or dedup of the adapter's own; what they cannot express is N/A with the reason (S7; S4/S5; C1 for DBOS and Restate; W6) |
| K6 Keel fails itself | first case came early, from the property suite: the IDEMPOTENT unknown outcome; amended, no published row changes |
| K7 not reproducible | `verify --recheck` re-verifies all 12 520 rows with no drift, exit 0; void 1 of 12 480. The no-op-commit flip clause has not been run |
| K8 no power | week 3's; the confirmation tier is running |
| K9 prior-art collision | jepsen.io/analyses re-checked 2026-09-18: no analysis of Temporal, Cadence, DBOS, Restate, Hatchet, Inngest or LangGraph is listed. arXiv was not re-searched for this draft, so this page does not use the word "first" |
| K10 schedule | did not fire: matrix v0 (40 cells × 30 seeds) was delivered on day 3 |
| K11 instrument invalid | (a) receipt-before-response is asserted by a unit test on every commit; the 300-seed audit that kills the World between receipt and response is on no page. (b) not run |

## 10. Positioning

The contribution claimed is the combination and the measurement, not the ideas (§2.5). Each work below
was checked to exist at the spec's URL on 2026-09-18; nothing is said about any of them beyond what the
spec says.

| Prior work | What it has | What Crashproof/Keel adds |
|---|---|---|
| **ActiveGraph** — "The Log is the Agent" (Nakajima, [arXiv 2605.21997](https://arxiv.org/abs/2605.21997)) | the same spine: append-only log as truth, projections, byte-reproducible replay, fork at any event; Keel's FORK is essentially its fork (§2.2) | everything that happens when the process dies: leases and fencing, the write-ahead effect barrier, effect classes, ambiguity resolution, approvals that release compute, a reaper — and a benchmark. "An event log without a write-ahead effect barrier records what the agent decided but cannot say whether the world was changed" (§31.3) |
| **The DBOS chaos suite** — "How to Test the Reliability of Durable Execution" (Jul 2025), as described in §2.5 and §11; the spec's URL, [dbos.dev/blog/how-to-test-durable-execution](https://www.dbos.dev/blog/how-to-test-durable-execution), resolved at check time to a page titled "Lessons from Testing Distributed Systems", dated 3 Jul 2025 | the closest published method: random process crashes, database disconnects, rolling deploys, six checked properties — one system, self-run | differential across eight configurations with a World oracle outside every SUT, per-effect duplicate accounting, and the decisions-vs-effects distinction a general engine has no reason to make |
| **Crab** — "A Semantics-Aware Checkpoint/Restore Runtime for Agent Sandboxes" ([arXiv 2604.28138](https://arxiv.org/abs/2604.28138)) | crash-recovery correctness for agents at the OS/sandbox layer, on Terminal-Bench (§2.2, §20.5) | the durable-execution layer above it: which effects left the process and whether the receiver saw them. Crab is a candidate implementation behind Keel's `Sandbox` protocol, not a competitor; `LOCAL_FS` is where they meet |
| **Applied Technology Index 2026** — [Comparative Analysis: Durable Execution Infrastructure for Long-Running AI Agents](https://appliedtechnologyindex.com/research/2026-comparative-analysis-durable-execution-infrastructure-ai-agents/) | an architecture comparison from public docs; the page states "This is an architecture comparison, not a reliability or performance benchmark." and "No common agent workload was executed across the systems." (both present at check time) | exactly that: one canonical workload, one World, one fault schedule, across runtimes, verdicts judged against each runtime's own claims |

Cited as prior art in §2.5 and not re-checked here: Atomix, agrepl, Causal Agent Replay,
langchain-replay, AgentChaosBench, Resonate's DST and temporalio/features. This page adds no
characterisation of its own.

## 11. How to reproduce

```bash
uv sync --extra dev --extra langgraph && docker compose up -d postgres
uv run crashproof demo                                   # the one command: the T2 window, Keel
uv run crashproof demo --adapter langgraph --config sync # the same seed, the other answer

uv run crashproof bench --matrix bench/specs/week2_w1_shim.yaml  --out out/shim   # serial; shard with --cells
uv run crashproof bench --matrix bench/specs/week2_w1_proxy.yaml --out out/proxy
uv run crashproof bench --matrix bench/specs/week2_w5.yaml       --out out/w5
uv run crashproof bench --matrix bench/specs/week2_w5_pre.yaml   --out out/w5_pre
uv run crashproof verify out/shim/results.jsonl --recheck        # the gate: exit 0; 7 on drift; 9 if a row cannot be re-verified
uv run crashproof placement out/shim                             # K3's two numbers; --window for the widths
uv run python scripts/render_reports.py && git diff --exit-code -- bench/reports   # every page is a pure function of its rows
```

The Restate arm runs the same specs from a Linux clone under WSL2 (`restate-sdk` has no Windows wheel).
Every row carries `(spec_hash, seed, keel_commit, config_pin)` with the framework versions inside the
pin; the rows behind every page are at `bench/results/<page>/results.jsonl`, and `keel_commit` on every
week-2 row is `dcdd533`. The per-trial directories stay on the machine that ran them, so `--recheck`
works on a directory you generated. Disagreement is settled by running it.
