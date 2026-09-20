# Crashproof: the write-up

The essay §29.3 says the benchmark exists for. Every number below is from the release re-run at
`251e52d` — [`v1_w1_shim`](../bench/reports/v1_w1_shim.md) (208 cells),
[`v1_w1_proxy`](../bench/reports/v1_w1_proxy.md) (144), [`v1_w5`](../bench/reports/v1_w5.md) (40),
[`v1_w5_pre`](../bench/reports/v1_w5_pre.md) (24), [`v1_reask`](../bench/reports/v1_reask.md) (16),
[`v1_w3`](../bench/reports/v1_w3.md) (3), [`v1_w7`](../bench/reports/v1_w7.md) (13) — 448 cells × 30
seeds and, for the seventeen cells the confirmation tier selected, 300 more: **18 540 trials, of which
46 end void, and 18 843 rows with the re-takes**. Every trial that ends void is in `langgraph.exit`'s
two proxy `kill@after:tool_return` cells (9 and 5 of 30 seeds scored; each void row records its kill
`executed: false` and nothing about why); the other 303 void rows are the ones a `--resume` re-take of
the same seed superseded, and no cell counts them. The rows are under `bench/results/v1_*/results.jsonl`. The
agreement column (§7) is [`agreement_v1`](../bench/reports/agreement_v1.md), over the shim and proxy
rows; the compare pages (§8) are the 21 `compare_v1_*` pages, Keel against each of the seven other
configurations over `v1_w1_shim`, `v1_w1_proxy` and `v1_w5`. K3's placement and K4's window widths
(§6, §7) are `crashproof placement` over the release trials, which reads trial directories no published
page carries. The week-2 matrix at `dcdd533` is named wherever a number is still its. The confirmation
tier ([`bench/confirm/v1.yaml`](../bench/confirm/v1.yaml): 17 cells, 5 100 trials on seeds
100 000–100 299 at the same commit) has run and is folded into the same rows: those cells print at
n = 300 in the grids, their screening reading is each page's "screening tier of the confirmed cells"
appendix, and this page quotes the confirmed number wherever it has one.

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
shim and proxy mode, W5 `approval_gated_deploy` with its tier-2 form W5-pre, and the re-ask cell
(`kill@after:tool_effect` armed with `model_reask_alternate`); Keel alone over W3 `long_horizon_50` and
W7 `streaming_answer`. Thirty seeds per cell, three hundred where the confirmation tier took one.
Restate's shard ran under WSL2, and only its rows record that: `platform: linux (WSL2)` in the config
pin, where no other arm's pin carries the field at all.

Duplicate *applied* effects, EXTERNAL band, shim mode, out of 30 seeds — or out of 300 where the cell
says so, which is the confirmation tier ([v1_w1_shim](../bench/reports/v1_w1_shim.md)):

| (location, fault) | keel | lg sync | lg async | lg exit | dbos native | dbos pyd | temporal | restate |
|---|---|---|---|---|---|---|---|---|
| `kill@before:tool_call` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `kill@after:tool_effect` | **0** | 30 | 30 | 30 | 30 | 30 | 30 | 30 ✗ |
| `kill@after:tool_return` | **0** of 300 | 30 | 30 | 30 | 239 of 300 † | 204 of 300 † | 30 | 30 ✗ |
| `pause_past_ttl@before:tool_call` | **97** of 300 | 0 | 0 | 0 | 0 | 0 | 47 ‡ | 45 ‡ ✗ |
| `tool_500@after:tool_effect` | 0 | 30 | 30 | 30 | 0 § | 0 § | 30 | 30 ✗ |
| `tool_timeout@before:tool_call` | 0 | 30 | 30 | 30 | 0 § | 0 § | 30 | 30 ✗ |
| `sigterm_grace_ok` / `too_short` | 0 / 0 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 30 / 30 | 0 / 0 |

✗ S1 FAIL against Restate's declared `exactly_once`. † exploratory under K3 (§7), whose placement is
measured at the screening seeds. ‡ summed over 30
trials; the count per trial grows with the seeded pause. § the workflow ended in ERROR (DBOS step
retries are off by default): applied once, run not correct. The four cells printed at 300 read 0, 21, 14
and 4 of 30 at screening; the tier moved no safety verdict and two liveness ones. L1 is unanimous in
every cell of this table, § included — 30/30 where the cell ran at thirty seeds, 300/300 in five of the
seven the tier confirmed (the three baselines, Keel's `after:tool_return` and its freeze) — except
DBOS's two `after:tool_return` cells, the other two confirmed, 298/300 and 299/300, where three runs
reached no terminal state inside the trial timeout, each after one restart (seeds 100251, 100272 and
100142, named on the page). In the
IDEMPOTENT band `duplicate_effects` is 0 in every cell of every arm; the receipts say what the receiver
absorbed — 30 at `after:tool_effect` for Keel, DBOS, Temporal, Restate and `sync`, 60 for `async` and
`exit`, 18 for Keel under the freeze, 51 for Restate and Temporal alike.

**Arm by arm.** *Keel* (`self`): no S1–S5 FAIL in any of its 70 cells across the seven pages, C1 PASS in
every one; its only source of a duplicate *effect* is the zombie residual, 97 of 300 shim and 30 of 30
proxy trials under the freeze — its IDEMPOTENT cells take re-sent receipts like everyone else, 30 at
T2 and 18 under the freeze, and apply none of them twice; tool-boundary kills cost +0 model calls, `model_500`/`model_timeout` +1,
`provider_outage` +3 in every arm that survives it; median recovery 2.3 s against a 2 s lease.
*LangGraph ×3* (`harness`): nothing notices the crash, the supervisor re-invokes by `thread_id` and the
interrupted node re-runs from its first line; two applied 30 of 30 at T2, T3, `tool_500`,
`tool_timeout`, both SIGTERM cells and, in proxy mode, under dropped and malformed responses — PASS
against `at_least_once`, printed; at the shim's kills `sync` +0 calls, `async` and `exit` +2; the SIGTERM
cells score identically because there is no drain path to give grace to. *DBOS ×2* (`self`): the
restarted process's PENDING scan resumes the run; 30 of 30 at T2, 239 and 204 of 300 at T3 — a race
between the shim's kill and a step checkpoint written off the event loop ([dbos](adapters/dbos.md));
with retries off, a 5xx, a tool timeout or the outage ends the workflow in ERROR, 0 of 30 correct,
printed not judged; median recovery at T2 3.1 s (`native`) and 4.4 s (`pydantic_ai`), two medians with
no paired test between them. Those two T3 cells are also the only place three hundred trials moved a
verdict: each config left runs with no terminal state inside the trial timeout, 2 of 300 (`native`) and
1 of 300 (`pydantic_ai`), each after one restart — an L1 FAIL thirty seeds did not reach.
*Temporal* (`engine`): the server times the dead or frozen worker's activity out on
its 2 s heartbeat and retries; 30 of 30 at T2, T3, `tool_500`, `tool_timeout`; 47 duplicates over 30
frozen trials, the count being `pause / (heartbeat + backoff)` with the pause drawn in [2×, 4×] of the
heartbeat ([temporal](adapters/temporal.md)); C1 through `temporalio.worker.Replayer`, PASS. *Restate*
(`engine`), judged against its own documentation — "Tool side effects are not duplicated", so
`exactly_once`: **S1 FAIL** in 5 shim cells, 7 proxy cells, W5's `kill@after:tool_effect` and the re-ask
cell — two applied 30 of 30 at T2 in both modes, behind the gate, under the re-ask, and under `tool_500`,
`tool_timeout`, dropped and malformed responses; 97 of 300 at the proxy's T3, a twin the agreement page
reads as the instrument (§7). Its `pause_past_ttl` cells complete 30 of 30 with L1 30/30 in
both bands; at `dcdd533` they were stuck in 4 of 60 shim trials, and that was the harness: on POSIX the
worker stopped itself too, and when the supervisor's freeze landed first the self-stop landed after the
resume — fixed (`8d90198`) before the release run.

**Three findings that matter.**

1. **The window every other arm leaves open.** At `kill@after:tool_effect` on EXTERNAL — the World has
   the effect, the framework has not recorded it — all seven other configurations apply the issue twice,
   30 of 30, in shim and in proxy mode. Keel's probe finds the applied effect and re-fires nothing: 0. The
   same holds behind the approval gate: W5's `kill@after:tool_effect` deploys twice 30 of 30 on every arm
   but Keel ([v1_w5](../bench/reports/v1_w5.md)). Six of the seven claim at-least-once and are held
   to it; this is the cost of a journal written after the effect, printed.
2. **Restate against its own claim.** The one arm whose documentation claims more than at-least-once for
   tool side effects fails S1 in 14 cells, every seed listed. The draft upstream report
   ([docs/upstream](upstream/README.md)) frames it as a docs qualifier — probably intended
   at-least-once — and nothing has been filed.
3. **W5 behind the gate.** Killed while parked on an approval and then granted, every arm deploys exactly
   once, 30 of 30 (H7). LangGraph pays +1 model call because `interrupt()` re-runs the interrupting node,
   and in the tier-2 form ([v1_w5_pre](../bench/reports/v1_w5_pre.md)) an ungated `notify` before the
   gate fires twice in the fault-free baseline and under `approval_delay` on all three configs — `sync`
   ran both of those cells at three hundred seeds, 300 duplicate effects over 300 baseline trials and
   301 over 300 delayed ones, the one extra a trial that fired it three times — and three times under
   `kill_while_waiting`, 60 extra effects per config in that cell, and on no other arm. `interrupt()`
   has no deadline, so under `approval_expiry`
   LangGraph is still WAITING at 60 s, 0 of 30 on every config, L1 FAIL by design; every other arm
   completes "not done" with nothing deployed.

## 5. Hypotheses (§13.7)

| H | Prediction | Verdict |
|---|---|---|
| **H1** T2 ≡ T3 | a journal written after the effect re-fires at both | **held** for LangGraph ×3, Temporal, Restate (30/30 at both); **refuted by the instrument** for DBOS — 239 and 204 of 300 at T3 against 30/30 at T2, the shim's kill landing after DBOS's off-loop checkpoint (K3 fails for that trigger at `251e52d`, §7; the fraction that misses is the screening tier's 9 and 16 of 30). In proxy mode T3 lands after the parse for most arms (0 of 30 for `sync`, DBOS ×2, Temporal; 0 of the 9 `exit` trials that scored, 21 void; 294 of 300 `async`; 97 of 300 Restate) — the instrument again |
| **H2** Keel is the only zero-duplicate arm at T2/F0 | every other arm exactly one duplicate, within its claim | **held** for the `probe` route: 0 against 30/30 ×7 (shim and proxy). The `escalate` route runs in no published cell — **untested** |
| **H3** keys equalise T2 at F1 | every F1 arm applies once | **held**: 0 applied, 30 receipts for Keel, DBOS ×2, Temporal, Restate. The "knows it re-fired" clause (`ambiguity_surfacing_rate`) is not printed — **untested** |
| **H4** +calls is a durability-mode property | 0 or 1 for memoizing arms; `async` a lost-checkpoint term; `exit` all prior | **held** in shape at the shim's kills: +0 for Keel, DBOS, Temporal, Restate, `sync`; `exit` +2 (all prior); `async` +2 rather than the predicted +0/+1 — both prior calls, not one. From the proxy `async` is +0 at T1 and T2 (§7) |
| **H5** the zombie is the price of a successor | duplicates only with a second claimant; IDEMPOTENT zombie-safe | **held**: Keel 97 of 300 (two workers; 4 of 30 at screening), Temporal 47, Restate 45; DBOS ×2 and LangGraph ×3 0 with a 3.1 s gap equal to the pause; Keel IDEMPOTENT 0 applied / 18 receipts |
| **H6** detection latency is the pinned timeout | engines: pinned timeouts; Keel: reaper; DBOS: restart | **held** for Keel (2.3 s), Temporal (5.6 s ≈ heartbeat + retry + start), DBOS (3.1 s / 4.4 s: restart); **refuted** for Restate kills — the 3.7 s median is under its pinned 7 s detection timeout, which the adapter doc reads from its smoke journals as detection at connection loss plus worker start against a doubling backoff ([restate](adapters/restate.md)); its freezes are the timeouts (19.3 s; Temporal 5.6 s). Across arms only Keel is compared (§8): `recovery_latency_ms` is B higher, Keel the lower, in every W1 kill cell where both arms record a recovery, against DBOS ×2, Temporal and Restate (Restate's rows two hosts as well as two runtimes), and `not claimable` against LangGraph ×3 |
| **H7** approval durability | one gated effect after a kill while parked; LangGraph +1; tier-2 gives two | **held** 30/30 on all eight arms; LangGraph +1; W5-pre `notify` 2× baseline, 3× killed. `kill @ landmark:approval_decided` **untested**; the "S7 counterexample" clause is a count, not a verdict — S7 is N/A for LangGraph |
| **H8** drain | Keel 0 at `grace_ok`, as T2 at `too_short`; others measured | **held** for Keel (0 / 0, as its T2 is 0). Measured: LangGraph ×3, DBOS ×2, Temporal duplicate 30/30 in both cells identically; Restate applies once in both and the page records no recovery for either — whether it drained or ignored the signal is not on the page |
| **H9** retry cells | documented per-step retry separates the arms; Keel's difference is classification | **held in part**: Temporal and Restate retry and apply twice 30/30; DBOS's documented retries are off by default, so it fails the run instead; LangGraph, predicted to fail, re-fires 30/30 through the harness restart; Keel's timeout is AMBIGUOUS → probe, 0 duplicates, 30/30 correct |
| **H10** `alternate` discriminates only non-memoizing arms | `async`/`exit` diverge, memoizing arms never | **held** for Keel (`diverged` 0/30, +0 calls) and for `async` and `exit` (30/30 at +2 calls, a *different* issue filed: `duplicate_effects` 0, 30 receipts) ([v1_reask](../bench/reports/v1_reask.md)); **not scorable** for the five other memoizing arms — `sync`, DBOS ×2, Temporal, Restate re-ask nothing (+0) yet print `diverged` 30/30 on the re-fired tool (30 applied twice each; Restate S1 FAIL), so the column the hypothesis names cannot separate re-fire from re-decision, and "memoizing arms never" is neither held nor refuted for them. The M1 positive control **untested** |

## 6. The residual windows

**The zombie.** A worker paused past its lease can still complete the HTTP call whose `STARTED` it
committed; its outcome append is fenced, so the journal never records an effect the receiver has.
Fencing protects journal appends and TRANSACTIONAL effects and nothing else (§8.4). Keel bounds the
window three ways — a pre-dispatch check that `lease_valid_until − now ≥ tool.timeout`, an
`attempt_deadline` committed in `STARTED`, and a reaper that orphans a run with an open non-PURE attempt
only when `now() > max(lease_expires_at, attempt_deadline)` — and eliminates it with none. A `probe` is
point-in-time: a request received before the deadline and applied after the probe is a duplicate it
could not see, a TOCTOU window that closes only with receiver cooperation, i.e. an IDEMPOTENT key.
Measured: 97 of 300 shim trials — the cell the confirmation tier took to three hundred, where screening
read 4 of 30 — with the pause landing between the last `await` and the socket write
(§4.7); 30 of 30 in proxy mode, where the request is parked at the proxy and forwarded at the thaw,
after the successor's re-attempt; under the same freeze the IDEMPOTENT band shows 18 receipts from the
shim and 30 from the proxy, 0 applied in both. S1–S5 hold at both tiers: EXTERNAL without a receiver
key is at-least-once by declaration, and the residual is inside it.
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
run SUSPENDED. No published row reaches that path. Three hundred frozen trials then found the
neighbouring case in the same resolution path: in one of them the successor's probe answered ABSENT,
the re-attempt timed out under host load and went ambiguous in its turn, and `events_resolved_once`,
keyed `(run_id, step_index, method)`, refused the second probe row — so the run FAILED where it should
have resolved. Nothing failed a verdict: safety held, and so did L1 — the run reached a terminal state,
just the wrong one. It is visible in the rows as `logical_correctness` 0 and in no verdict at all, which
is why the cell still folds to zero FAILs at n = 330 and why a tier of thirty seeds would have had to be
lucky to see it. The index now keys on `attempt_no`, §6.2 is amended
and the `MemoryJournal` mirrors it — fixed after the release commit (`2ffbe91`), and every published row
is still the one `251e52d` produced.

**How wide the window is.** `crashproof placement DIR --window` measures `ambiguity_window_width` on
baseline trials, World receipt to the runtime's own commit record. It needs the trial directories, which
the published rows do not carry, so no page prints it; run over the release shim trials' directories
(6 241 rows at the screening seeds, every one at `251e52d`; 60 baselines per arm, none unplaced),
the medians are DBOS 8.2 ms (`native`) / 9.8
(`pydantic_ai`), Keel 9.0, LangGraph 12.9 (`async`) / 13.4 (`sync`) / 21.1 (`exit`), Restate 16.1 (on the
WSL clock its World shares), Temporal 26.6. K4 turns a width into an exposure only with a realistic kill
rate, which the benchmark does not measure and does not invent.

## 7. The instrument

A benchmark that reports its own instrument faults is the point.

**K3 fired for one trigger on one runtime.** `crashproof placement` reads each runtime's own commit
record — Keel's journal on the host clock, LangGraph's checkpoints, DBOS's `completed_at_epoch_ms`,
Temporal's `ActivityTaskCompleted`, Restate's `Notification: Run` — and, over the release shim trials
(6 241 rows at the screening seeds, every one at `251e52d`), puts 100 % of fired faults inside the
intended window in every
tool-boundary cell of every arm except DBOS's `after:tool_return`, which lands 70 % / 63 % (`native`,
EXTERNAL / IDEMPOTENT: 21 and 19 of 30) and 47 % / 53 % (`pydantic_ai`: 14 and 16 of 30; the EXTERNAL
cell is flagged mis-aimed, its commonest landing — 16 of the 30 kills — after commit step 4, outside the
window). Between arms that trigger fails K3 by 53 points (EXTERNAL) and 47 (IDEMPOTENT); every other
tool-boundary trigger passes at 0. A fault at `before:model_call` has no K3 window, so the model-fault
triggers are not computable. At those same thirty seeds the in-window counts equal the cells' screening
duplicate counts — 21 and 14 are the two EXTERNAL cells' `dup_eff` in the shim page's screening
appendix, 19 and 16 the `dup_rcpt` of the two IDEMPOTENT cells, which ran at thirty seeds only and so
print in the grid itself — but no output joins the two per trial. The adapter doc names the race — the
shim's `call_soon`'d kill against the checkpoint DBOS writes from an executor thread
([dbos](adapters/dbos.md)) — and per §30 the four cells are exploratory.

**The agreement column.** Proxy and shim twins paired on `(cell, seed)`
([agreement_v1](../bench/reports/agreement_v1.md), `crashproof agree` over `v1_w1_shim` and
`v1_w1_proxy`, folded over the seeds both sides ran): 86 of 112 comparable twinned cells agree on every
safety verdict and every raw count.
The 26 that differ are the instrument, each printed with both numbers: 15 are `kill@after:tool_return`,
which from outside the process lands after `taskkill`'s latency, often after the parse and sometimes
after the run has finished; 6 are `pause_past_ttl`, where the proxy parks the request and forwards it at
the thaw instead of freezing before the send (EXTERNAL duplicates Keel 4 → 30 over the thirty seeds the
proxy also ran, Restate 45 → 50, Temporal
47 → 50); 4 are LangGraph `async`'s receipt counts at `before:tool_call` and `after:tool_effect` (30 → 0
and 60 → 30 in each band), where the shim's kill re-runs both prior model calls (+2) and the proxy's
re-runs none; the twenty-sixth is Keel's EXTERNAL baseline, paired over the 330 seeds both sides ran
(the thirty screening and the three hundred of the tier), 0 receipts against 3,
which two of the three hundred trials contribute: seed 100099, the one FAILED run, whose PURE `kv.search`
timed out three times under host load until the retry policy gave up — three receipts for the attempts,
two of them counted duplicates, nothing applied — and seed 100100, which completed correctly and applied
`issues.create` once but took a second `kv.search` receipt. Nothing was applied twice in either, and that
one FAILED run is why the cell's `logical_correctness` reads 299/300 on the compare pages.
The `after:tool_effect` window — applied, receipted, nobody told — is the same in both.

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
([restate](adapters/restate.md)); the first fix parked the thread on the thaw marker as well, and the second (`8d90198`, after the week-2 run) stopped sending `SIGSTOP` at all, because a self-stop that landed after the supervisor's resume left the worker stopped for good — the 4 of 60 Restate freeze trials at `dcdd533`, 0 of 60 in the release rows. A process mid-`taskkill` is
alive to `poll()` and refuses `NtResume` with `0xC000010A` (`crashproof/faults/process.py`); until that
status was treated as gone the end-of-trial resume took a run down. Temporal's kill cells carried ~8 s of
the SDK's 10 s sticky-queue default hiding behind the pinned 2 s heartbeat — a documented worker option,
now pinned. The WSL VM's clock drifted ±7 % in 0.8 s steps and failed a Keel baseline on S4; a trial
whose store-clock offset moves past `STORE_CLOCK_TOLERANCE_S` (50 ms) is now void. And the confirmation
run's proxy shard died at its second trial on a torn log line: in proxy mode the proxy and the SUT's
observe-only shim append to the same `observations.jsonl`, and on Windows `open(..., "a")` is a
seek-to-end followed by a write that another process can land between — a probe of three writers lost
522 lines of 4 500 and tore 221. About one proxy trial in six had lost a tool-boundary observation line
that way; no published metric reads those lines, and the model-call lines the economy columns do count
were intact in every baseline trial checked. The append is now one `FILE_APPEND_DATA` write the file
system places at the end, `O_APPEND` on POSIX (`7a22596`, after the release commit); `--resume` re-took
the dead trial, and no row changes.

**Upstream.** Two draft reports, neither filed ([docs/upstream](upstream/README.md)): Restate's
side-effect claim, framed as a docs qualifier; and `restate-sdk[pydantic-ai]` failing to import
`restate.ext.pydantic`. Four candidates considered and not drafted, each failing the
[template](upstream-report-template.md): LangGraph's pre-interrupt re-run is documented and prominent;
its `approval_expiry` is an absent feature, not a contradiction; DBOS's T3 is within its documented
at-least-once and exploratory under K3; Restate's 4 of 60 was the harness.

## 8. What this does not show

- **Thirty seeds, except where they were three hundred.** At n = 30 a recovery-rate gap under ~30
  percentage points is invisible and `0/30` carries a Wilson upper bound of 11.4 % (§15.7); every page
  prints the MDD tables and the FAQ. `PASS (0/30)` means thirty aimed kills found no duplicate, not that
  the runtime cannot duplicate. The confirmation tier took exactly the cells that admitted it — 17: the
  six whose screening estimate was not unanimous, Keel's cell at the same location, and each one's
  baseline, with no claimed difference to confirm (`claims: []`) — to 300 fresh seeds, and it earned its
  keep: two cells that fail L1 where thirty seeds read 30/30 (DBOS's two `after:tool_return` cells, 2 of
  300 and 1 of 300 with no terminal state in the trial timeout), Keel's zombie residual at 97 of 300
  where screening read 4 of 30, and one FAILED run in Keel's 300 proxy baselines. Every other confirmed
  cell repeated its screening verdicts; four did not repeat a raw count. Three are at the proxy's
  `kill@after:tool_return`: LangGraph `async` reads `dup_eff` 294 · `dup_rcpt` 428 of 300 against the
  appendix's 29 · 30 of 30, so the effects rate holds (0.97 → 0.98 a trial) and the receipts rate does
  not (1.0 → 1.43); Restate reads `dup_eff` 97 of 300 against 12 of 30; and Keel reads `diverged` 1 of
  300 where screening read 0 of 30 — that one trial applied its effect once and completed, and counts as
  divergent only because `replay_divergence` compares a trial to its own fault-free twin at the same
  seed, and that twin is the baseline which failed under host load and applied nothing. The fourth is on
  W5-pre, where `langgraph.sync`'s `approval_delay` keeps its duplicate shape exactly (301 extra over 300
  trials against 31 over 30) and its divergence does not (1 of 30 → 1 of 300). The other 431 cells are still thirty seeds, and
  nothing on this page says otherwise.
- **One host, and one and a half.** Every arm but Restate ran on one Windows machine; Restate ran under
  WSL2 on it. A latency difference involving Restate is two hosts as well as two runtimes: its compare
  pages print latency verdicts against Keel, and this page reads none of them as a finding about either
  runtime.
- **A scripted model.** The provider answers by request content, so every arm sees the same decisions and
  `model_reask_alternate` is possible. It is a fixture; K11(b)'s real-model subset has not been run.
- **Workloads and faults.** W1, W5, W5-pre and the re-ask cell on every arm; W3 and W7 on the Keel arm
  only ([v1_w3](../bench/reports/v1_w3.md), [v1_w7](../bench/reports/v1_w7.md): 3 and 13 cells, every
  safety row PASS, L1 30/30, W3's kill and freeze at the 23rd put applied once and receipted twice), the
  spec files naming why each other arm is N/A or not yet bound. W4 is cut (it needs TRANSACTIONAL, the
  effect-table bridge and a DBOS arm); W6 has no cited child mechanism in any engine.
  `partition_worker_world` and `tool_duplicate_response` are not built; `provider_outage` ran in shim
  mode only; `kill @ landmark:approval_decided` did not run.
- **Nothing pending.** The release re-run is done and folded, the confirmation tier with it, and this
  page quotes both; Restate's two `pause_past_ttl` shim cells, stuck in 4 of 60 trials at `dcdd533`,
  complete 30 of 30 with L1 30/30 here.
- **Compared only against Keel.** The 21 `compare_v1_*` pages pair Keel (A) with each other
  configuration (B) on `(workload, variant, trigger, spec_hash, seed)` over `v1_w1_shim`, `v1_w1_proxy`
  and `v1_w5` — McNemar's exact test on binary estimates, a paired bootstrap on continuous ones, Holm
  across the cells of one metric table (e.g.
  [against DBOS `native`, shim](../bench/reports/compare_v1_w1_shim_keel_vs_dbos_native.md)). Safety is
  counted there, never tested: `duplicate_effects` Keel 4 / 30 / 0 (shim / proxy / W5) against 165–350 /
  30–473 / 30. The commonest verdict is `too noisy to claim`: `recovery_rate` gets it in every W1 cell of
  every page, on 0 discordant pairs everywhere but DBOS's two confirmed `after:tool_return` cells, where
  Keel recovers 300 of 300 against 298 and 299 — two discordant pairs and one, still too few to claim
  anything. `logical_correctness` is A
  better wherever the other arm applied twice, ended its run in ERROR or — LangGraph under W5's
  `approval_expiry` — never ended it, and Keel did none of these (at T2, 30 discordant pairs to 0, Holm p
  printed 0.0000), and B better in one cell: the proxy's EXTERNAL `pause_past_ttl`, where Keel is
  correct in 0 of 30 trials against 30 of 30 for DBOS ×2 and LangGraph ×3 — §6's zombie residual; the
  shim twin, 26 against 30, is `too noisy to claim (4 discordant pairs)`, the pages pairing on the seeds
  both arms ran, so Keel's three hundred there meet the other arm's thirty. Four of the
  `logical_correctness` comparisons at the confirmation n are the confirmed fault cells, and all four are
  A better at Holm p 0.0000: 300/300 against 59/300 and 95/300
  (DBOS ×2 at the shim's T3) and against 6/300 and 203/300 (LangGraph `async` and Restate at the proxy's).
  The other four rows at that n are the confirmed baselines — 300/300 against 300/300 on the two DBOS shim
  pages, 299/300 against 300/300 on the LangGraph `async` and Restate proxy pages — and all four read
  `too noisy to claim`.
  `recovery_rate` at that same n claims nothing, DBOS's 300/300 against 298/300 and 299/300 included.
  Latency is H6's row. No page pairs two of the other arms. A delegation `deadline_s` is journaled and
  not enforced.

## 9. Kill criteria (§30), current verdicts

| Id | Verdict at the release re-run (`251e52d`) |
|---|---|
| K1 everyone passes | not fired: every arm but Keel duplicates at T2 30/30, and Restate fails S1 |
| K2 engine parity | not fired, and now decidable because confirmation has run. Temporal and DBOS match Keel on every *judged* safety verdict (they claim at-least-once and are held to it) and differ on raw `duplicate_effects` 30 vs 0 at T2, which is not a verdict; but the paired differences do not favour the engine — `logical_correctness` is A better at n = 300 in both DBOS `after:tool_return` cells, and `recovery_latency_ms` is B higher against DBOS ×2 and Temporal in every W1 kill cell where both arms record a recovery — the proxy's `kill@after:tool_return` has 0 paired observations on either side and claims nothing, and Restate's latency verdicts are two hosts as well as two runtimes, so this page does not put them to work (§8). Restate does not match at all: S1 FAIL in 14 cells |
| K3 unfair triggers | **fired**, at `after:tool_return`, on both of §30's clauses. Over the shim screening trials `crashproof placement` reads 70 % / 63 % in window (`native`, EXTERNAL / IDEMPOTENT) and 47 % / 53 % (`pydantic_ai`); over the confirmation trials, which is the tier the grid publishes the two EXTERNAL cells at, 80 % and 68 %, against Keel's 300/300. The between-arms clause fires at 53 and 47 points across runtimes and at 23 points between DBOS's own two adapters. Every other tool-boundary trigger is 100 % on every arm at both tiers. §30's decision is that shim cross-runtime cells are not publishable, with the fallback that claims move to `proxy` mode and shim cells demote to exploratory: every W1 cell has a proxy twin and the cross-runtime reading at that trigger rests there, those four DBOS cells are exploratory, and the rest of the shim set is still published — a departure stated as one |
| K4 window too narrow | week 3's; the widths in §6 are `crashproof placement --window` over the release baselines, medians 8.2–26.6 ms; the kill rate it also needs is not measured |
| K5 adapter infeasible | not fired: DBOS ×2, Temporal and Restate express W1, W5, W5-pre in cited primitives with no counter, lookup, retry or dedup of the adapter's own; what they cannot express is N/A with the reason (S7; S4/S5; C1 for DBOS and Restate; W6) |
| K6 Keel fails itself | not fired on §30's own measurement, which is a `hook`-mode conformance cell failing S1–S10 or C1–C3: none does (54 run, 12 N/A, 0 failed). Two design defects were found by other instruments and both got K6's remedy — the IDEMPOTENT unknown outcome, from the property suite (`c509409`, §7.4 / §9.1 / §8.7 amended in `794161f`), and `events_resolved_once` keyed per step rather than per attempt, from the confirmation tier (`2ffbe91`, §6.2 amended). No published row changes for either |
| K7 not reproducible | **fired**, on the `void_rate` clause: `langgraph.exit`'s two proxy `kill@after:tool_return` cells are 21 and 25 of 30 void — 70 % and 83 % against §30's threshold of 5 % — because the kill from outside the process races exit mode's own process exit; §30's remedy is "publish nothing from them", so the grid **withdraws** them: it prints their void and raw counts and no verdict (`d65fa33`, a rule over the rows themselves — any cell over the 5 % threshold). The shim twins are not a substitute: §7's agreement column records that they disagree with these cells (`duplicate_effects` 9/0 on the nine proxy trials that scored), which is the instrument finding rather than a reading to inherit. No other cell of any set leaves a trial void: 46 of 18 540, all in those two, the void rows elsewhere being ones a re-take superseded. 18 843 rows, `keel_commit` `251e52d` on every row. The confirmation tier's 5 100 trials each re-verified from their own trial directory (`119d605`). Over the release rows `verify --recheck`'s first pass reported one drift that was the gate's own: a void shim row had been re-taken, and recheck compared the superseded row with the re-take's trial directory. `ef203c4`, a child of `251e52d` that changes only `verify --recheck` (`crashproof/cli/main.py` and its unit test), makes it skip a superseded row; no page records a recheck result after that fix, so the screening rows' gate has no stated result here. The no-op-commit flip clause has not been run |
| K8 no power | not fired: after confirmation ([v1.yaml](../bench/confirm/v1.yaml), 17 cells at n = 300) the non-safety comparisons are not all `too noisy to claim` — `logical_correctness` is A better at that n in all four confirmed fault cells (300/300 against 59/300 and 95/300 at the shim's T3, 6/300 and 203/300 at the proxy's), Holm p 0.0000. `recovery_rate` is still `too noisy to claim` in every W1 cell, the same reading at ten times the seeds; the one cell where it claims anything is W5's `approval_expiry`, A better against each of LangGraph ×3 at thirty seeds, 30/30 against 0/30 |
| K9 prior-art collision | **fired in substance**, and §10 carries the citations. §30's text asks for a common agent workload under process kills across ≥ 2 durable-execution runtimes with an external oracle: [crashpoint](https://github.com/mstevens843/crashpoint) has the kills, six runtimes and the oracle but a single-effect workload; [agent-crash-recovery](https://github.com/paolo-perrone/agent-crash-recovery) has the agent, four runtimes and the kills but reads each runtime's own logs. Neither satisfies every clause alone, and leaning on that gap is not a defence, so §30's remedy applies: complement, do not compete. Nothing is retracted — this page has never used the word "first" — and the headline moves to what neither checks. jepsen.io/analyses, re-checked 2026-09-18, still lists no analysis of these engines |
| K10 schedule | did not fire: matrix v0 (40 cells × 30 seeds) was delivered on day 3 |
| K11 instrument invalid | (a) **audited, not fired.** `scripts/k11_oracle_audit.py` kills the World process mid-request over 300 seeds and convicts on one outcome — a client answered for a request whose receipt is not in the log: 0 of 400 audited trials (300 at a delay drawn from the round trip, 100 aimed inside a withheld response, every one of which found its receipt on disk). It is calibrated, not asserted: a third band runs a World that defers the receipt past the answer, and the audit convicts it 100 times in 100. The reach is the kill's own latency, 0.5–1.1 s here, so a mis-ordering of that order or wider is visible and one of microseconds is not; `tests/unit/test_k11_audit.py` pins the calibration in CI, which is where §30 asks for this check. (b) not run: the `real-model` subset was cut, and every report page now says so beside the model-boundary cells |

## 10. Positioning

The contribution claimed is the combination and the measurement, not the ideas (§2.5) — and after K9
fired at the release, less than that: two public artifacts already crash durable-execution runtimes
under kills, one of them with an oracle outside the system under test. Each work below was checked to
exist at the spec's URL on 2026-09-18, and the two new rows on 2026-09-20; nothing is said about any of
them beyond what their own pages say.

| Prior work | What it has | What Crashproof/Keel adds |
|---|---|---|
| **ActiveGraph** — "The Log is the Agent" (Nakajima, [arXiv 2605.21997](https://arxiv.org/abs/2605.21997)) | the same spine: append-only log as truth, projections, byte-reproducible replay, fork at any event; Keel's FORK is essentially its fork (§2.2) | everything that happens when the process dies: leases and fencing, the write-ahead effect barrier, effect classes, ambiguity resolution, approvals that release compute, a reaper — and a benchmark. "An event log without a write-ahead effect barrier records what the agent decided but cannot say whether the world was changed" (§31.3) |
| **The DBOS chaos suite** — "How to Test the Reliability of Durable Execution" (Jul 2025), as described in §2.5 and §11; the spec's URL, [dbos.dev/blog/how-to-test-durable-execution](https://www.dbos.dev/blog/how-to-test-durable-execution), resolved at check time to a page titled "Lessons from Testing Distributed Systems", dated 3 Jul 2025 | the closest published method: random process crashes, database disconnects, rolling deploys, six checked properties — one system, self-run | differential across eight configurations with a World oracle outside every SUT, per-effect duplicate accounting, and the decisions-vs-effects distinction a general engine has no reason to make |
| **Crab** — "A Semantics-Aware Checkpoint/Restore Runtime for Agent Sandboxes" ([arXiv 2604.28138](https://arxiv.org/abs/2604.28138)) | crash-recovery correctness for agents at the OS/sandbox layer, on Terminal-Bench (§2.2, §20.5) | the durable-execution layer above it: which effects left the process and whether the receiver saw them. Crab is a candidate implementation behind Keel's `Sandbox` protocol, not a competitor; `LOCAL_FS` is where they meet |
| **Applied Technology Index 2026** — [Comparative Analysis: Durable Execution Infrastructure for Long-Running AI Agents](https://appliedtechnologyindex.com/research/2026-comparative-analysis-durable-execution-infrastructure-ai-agents/) | an architecture comparison from public docs; the page states "This is an architecture comparison, not a reliability or performance benchmark." and "No common agent workload was executed across the systems." (both present at check time) | exactly that: one canonical workload, one World, one fault schedule, across runtimes, verdicts judged against each runtime's own claims |

| **crashpoint** — [mstevens843/crashpoint](https://github.com/mstevens843/crashpoint), created 27 Aug 2026, last commit 15 Sep, checked 20 Sep 2026 | the neighbouring experiment, one layer down: LangGraph, Temporal, DBOS, Restate, Vercel Workflow and CrewAI crashed at barriers named around the effect and the runtime's persist write (b0, b1, b2); side effects counted in an out-of-process hash-chained ledger the subject "cannot read, reset, or seal"; a per-cell pass-rate matrix with error bars over 18 evidence files; six control oracles pinned through the same harness; replay determinism scored as its own outcome; one LangGraph cell against a real model | the agent layer above the barrier: effect classes as *declarations* with per-endpoint receiver semantics — it varies the caller's key strategy, never the receiver's — ambiguity surfaced and resolved rather than only counted, token accounting, approval and delegation invariants, and a two-tier protocol with a confirmation tier. Its workload is one external effect in one step. K9 fires on it in substance, and §30's answer is to cite it, not to compete |
| **agent-crash-recovery** — [paolo-perrone/agent-crash-recovery](https://github.com/paolo-perrone/agent-crash-recovery), public 19 Aug 2026, checked 20 Sep 2026 | the other half of K9's clause: one common agent across LangGraph, Inngest, DBOS and Temporal, SIGKILLed mid-run, counting the steps you "pay for twice" | the oracle. It reads each runtime's own logs and checkpoints, so nothing outside the system under test says what the receiver saw — which is the clause K9 turns on, and the reason this project's World exists at all |

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
uv run crashproof bench --matrix bench/specs/release_reask.yaml  --out out/reask
uv run crashproof bench --matrix bench/specs/w3.yaml             --out out/w3      # Keel only
uv run crashproof bench --matrix bench/specs/w7.yaml             --out out/w7      # Keel only
uv run crashproof confirm out/*/results.jsonl --out bench/confirm/v1.yaml  # which cells earn 300 seeds, and the bench commands for them
uv run crashproof verify out/shim/results.jsonl --recheck        # the gate: exit 0; 7 on drift; 9 if a row cannot be re-verified
uv run crashproof placement out/shim                             # K3's two numbers; --window for the widths
uv run crashproof agree --shim out/shim --proxy out/proxy        # the agreement column
uv run python scripts/render_reports.py && git diff --exit-code -- bench/reports   # every page is a pure function of its rows
```

The Restate arm runs the same specs from a Linux clone under WSL2 (`restate-sdk` has no Windows wheel).
Every row carries `(spec_hash, seed, keel_commit, config_pin)` with the framework versions inside the
pin; the rows behind every page are at `bench/results/<page>/results.jsonl`, and `keel_commit` on
every release row is `251e52d`. A confirmation run's rows are `cat`ed into the directory of the
screening rows they confirm — the tier is the seed range and not a flag, so `report` and `compare` pick
it up on their own. The per-trial directories stay on the machine that ran them, so
`--recheck` and `placement` work on a directory you generated. Disagreement is settled by running it.
