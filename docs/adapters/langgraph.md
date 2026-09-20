# Adapter: LangGraph

The same workload, the same World, the same shim, the same spec file — expressed in LangGraph's
documented primitives and nothing else.

Source: [`crashproof/adapters/langgraph.py`](../../crashproof/adapters/langgraph.py).

## Declarations

| | |
|---|---|
| `recovery_mechanism` | **`harness`** |
| `key_sources` | `none` (F0) only |
| `claims` | PURE `at_least_once` · IDEMPOTENT `at_least_once` · EXTERNAL `at_least_once` |
| Per-trial dependency | a Postgres database cloned from a template, via `AsyncPostgresSaver` |
| Durable unit | one superstep; tool calls wrapped in `@task` |
| Configs | `durability ∈ {sync, async, exit}` — one documented setting, the only axis between the three columns |

`recovery_mechanism = harness` **is the finding, not a slight.** Nothing in LangGraph notices that a
worker died. The `thread_id` is persisted by the checkpointer but *restored by the harness*, which
reads it back out of the trial directory and calls `ainvoke(None, {"thread_id": …})`. The adapter
says so in the column header rather than quietly looking like an engine that resumed itself.

The `at_least_once` claim across all three classes is the honest reading of the documented
semantics: the fact sheet establishes no exactly-once primitive and no idempotency-key primitive
anywhere. Under the Jepsen rule that means **LangGraph cannot fail S1** — and its raw
`duplicate_effects` count is on the page regardless. A runtime is held to what it claims; the
observation is published either way.

## `key_source` formula — there isn't one, and that is the formula

**F1 requires a key that is a pure function of identifiers the framework itself persists *and
restores* across a restart** (§13.6). LangGraph's candidates and why each fails:

| Candidate | Why it is not an F1 key |
|---|---|
| `thread_id` | Persisted, but **restored by the harness**, not by the framework. It is one identifier for the whole run, not per effect. |
| `checkpoint_id` | Changes with every superstep, so it is not stable across the re-run of the interrupted node — which is precisely the moment a key has to be stable. |
| a loop counter in graph state | A counter **the adapter added**. §13.3 forbids exactly this: counters, pre-send lookups, retries and dedup in the adapter are the cheap route, and an adapter that quietly helps its framework destroys the result more thoroughly than one that hurts it. |

So the headline cells run `key_source=none` and send no `Idempotency-Key` header at all. A
synthesised key would be `key_source=adapter` (F-exp), which may claim only *"an adapter author can
make this framework look like F1 in n lines"* — never anything about the framework — and never
enters the headline matrix.

The IDEMPOTENT band is still measured honestly at F0, because the `issues.upsert` endpoint is
`natural: true`: it deduplicates on `logical_identity` rather than on a presented key. Natural
idempotency is a property of the **receiver**, and the caller gets no credit for it. That is why the
matrix prints `duplicate_receipts` beside `duplicate_effects`: the gap between them is exactly what
the receiver bought. A row records the key source in effect, so LangGraph's IDEMPOTENT rows say
`key_source=none`; the 960 published before that rule (matrix v0, tier1a, tier1p) said `framework`,
copied from the variant, and were relabelled with no other field changed (`deab7e9`), which is why
those pages head the band `key_source=framework, none`.

## What a restart does

Nothing, until the harness acts.

- **`sync` / `async`** — `on_worker_restart` calls `ainvoke(None, config={thread_id})` and the
  in-flight node re-runs **from its first line**. With `async`, the last checkpoint may not have
  been written at all.
- **`exit`** — there is no checkpoint to resume from, so `ainvoke(None, …)` has nothing to do. The
  adapter re-submits the original workload input on the same thread. That is **re-submission, not
  resumption**, and the asymmetry is itself the `exit` finding — it is stated here rather than
  smoothed over, because a column that silently means something different from its neighbours is
  the worst kind of benchmark row.

## Two results worth reading with the docs open

Both are printed, neither is a bug report. See
[the upstream-report template](../upstream-report-template.md) for the bar a finding has to clear
before it goes to a maintainer.

**`kill@after:tool_effect`, `sync`, EXTERNAL: two receipts, two applied.** The node re-runs from its
first line, the tool call goes out again, and the `dedup: false` receiver applies it twice. This is
the documented behaviour of checkpoint-and-replay, and the documented guidance is that side effects
should be idempotent. The adapter follows that guidance — the tool call *is* `@task`-wrapped — and
the duplicate happens anyway, because the crash landed after the effect and before the checkpoint.
At the release commit it is 30 of 30 in every config, at T2 and again at T3 `after:tool_return` —
H1 (T2 ≡ T3) held. `async` and `exit` come back from further up the graph, so each adds two receipts
per trial (the PURE search goes out again) and two model calls — `+calls 2` on the page, unanimous
in the rows but for one `async` T3 seed at `+1` — where `sync` adds one receipt and none
([`bench/reports/v1_w1_shim.md`](../../bench/reports/v1_w1_shim.md)).

**`kill@after:tool_effect` + `model_reask_alternate`, `async` and `exit`: `replay_divergence` 30/30
with `duplicate_effects` 0.** The interrupted step is not re-*done*, it is re-*decided*: the model is
re-invoked, returns a different tool call, and the recovered run follows a different branch and
files a different issue — `issues.create#1` and `#2`, one each, 30 of 30 in both configs, at
`+calls 2` (30 of 30 in `exit`; 28 of 30 in `async`, two seeds at `+1`). `sync` re-*does* it
instead: `duplicate_effects` 30, `+calls 0`, and `diverged 30/30` there as well, since the column
compares the applied order and counts against the baseline's and a second `issues.create#1` is a
difference. Its `model_reask_alternate` row is recorded in the successor (`recovery_index 1`) in
all 30, and the World applied `issues.create#1` twice and `#2` never; that the checkpointed tool
call is what `sync` replayed is the reading of `+calls 0`, not a field in the row. No *effect* was
duplicated in `async` or `exit` — their `dup_rcpt 30` is the PURE `kv.search` received twice in
every trial — so their `dup_eff` is 0, and a page that reported duplicates alone would print those
two cells as clean recoveries. S1 is PASS in all three configs, `sync`'s `dup_eff 30` included,
because an `at_least_once` claim cannot fail it; what separates the three is `replay_divergence`,
which is the whole reason it exists as a column
([`bench/reports/v1_reask.md`](../../bench/reports/v1_reask.md)).

## W5 — the human in the loop, measured (§13.7 H7)

The wait primitive is `interrupt()`; resumption is a fresh `ainvoke(Command(resume=...))` on the
same thread, made by the worker on the harness's instruction (a file in the trial directory — the
human's decision, written once and never deleted). Thirty seeds per cell, all three configs, at the
release commit ([`bench/reports/v1_w5.md`](../../bench/reports/v1_w5.md),
[`v1_w5_pre.md`](../../bench/reports/v1_w5_pre.md)) — except W5-pre's `sync` baseline and
`approval_delay`, which the confirmation tier re-ran at 300 seeds and which the grid therefore
prints at n = 300, with their n = 30 reading in that page's screening appendix. Every row below held
in every trial of every config — 30 of 30, or 300 of 300 where the confirmation tier ran — in the
0/n-or-n/n estimates the verifier turns into verdicts. Raw counts split within a cell: the
`kill@after:tool_effect` row below is a 14/15/1 split in `async`'s model calls. One LangGraph cell on
either page is not unanimous in such an estimate — W5-pre `approval_delay`, `diverged 1/30` at
screening, which is the rule `crashproof confirm` selects on
([`bench/confirm/v1.yaml`](../../bench/confirm/v1.yaml)); it has no row of its own, and its `sync`
outlier is named under the tier-2 `kill_while_waiting` row. Each count is a raw number beside
a declared `at_least_once` — none of them fails S1 — and the one verdict that fails is named in its row:

| cell | LangGraph sync | Keel | what it says |
|---|---|---|---|
| `approval_delay` (headline) | deploy **1**, 4 model calls | deploy **1**, 3 model calls | The gated effect after `interrupt()` fires once. No difference in effects, and that is the honest result; the resume re-runs the interrupting node, one model call. |
| `kill_while_waiting` (headline) | deploy **1**, 5 model calls | deploy **1**, 3 model calls | H7 held: `interrupt()` is checkpointed, so the successor is granted once. The interrupting node re-ran on the restart as well as on the resume — `+calls 1` over the arm's own baseline, in every config. |
| `kill@after:tool_effect` | deploy **2** | deploy **1** | The day-3 window behind the gate: after the decision and the deploy, before the checkpoint. The node re-runs and deploys again, in 30 of 30 trials in every config — the at-least-once cost, printed. What the re-run costs in model calls differs by config: `+0` sync and `+2` exit, unanimous; `async` splits — `+0` in 14 of 30, `+1` in 15, `+2` in seed 18, the one trial with two restarts — and the page prints its median, `+calls 1`. Seed 18's one executed kill is recorded at `recovery_index 1`, the incarnation the first restart produced, where the other 29 carry it at 0: only the second restart is the kill's and the row gives the first no reason, the same shape as the tier-2 outlier below. |
| `approval_expiry` | **still WAITING at 60 s**, **L1 0/30** (by design), nothing deployed | expired at 5 s, COMPLETED `not done`, nothing deployed | There is no deadline on `interrupt()`. A human who never answers is a run that never ends — 90 L1 counterexamples over the three configs, every one `status=WAITING` at the trial timeout. S3 passes on all 90, but vacuously: it is the no-phantom-completion check (`crashproof/verifier/invariants.py::_s3_no_phantom_completion`), and a run still WAITING claimed nothing. The effect the spec forbids under expiry, `deploy.service#1`, is declared as `expected_world_state` and scored by `logical_correctness`, which no matrix page prints. The grid's `diverged 30/30` in this row is `replay_divergence`, a different metric and the World half of the question: nothing was applied where the fault-free baseline deployed once, which is why every arm's cell reads it, `keel.default` included. The World applied the forbidden effect in none of the 90 — `world_applied {}` in every one of those rows. S7 is N/A for LangGraph: it has no journal to bind an applied effect to an approval. |
| **tier-2** baseline (`notify` before the gate) | notify **2**, deploy 1 | notify **1**, deploy 1 | H7 held: pre-interrupt code re-runs on resume. |
| **tier-2** `kill_while_waiting` | notify **3**, deploy 1 | notify **1**, deploy 1 | Every re-entry of the interrupting node re-runs what came before the interrupt: original, restart, resume. Across W5-pre's 870 published LangGraph trials that is 962 extra `notify` effects — one per trial from every baseline and `approval_delay` cell, two from every `kill_while_waiting` cell, plus two: the `sync` `approval_delay` cell carries, in each tier, a single trial that records a restart no fault asked for — the cell's only fault is the delayed, duplicated click, `executed: true`, and the row gives the restart no reason — beside a third `notify` and a fifth model call. That the re-entry is what cost them is the reading. The confirmation tier ran that cell at 300 seeds and reproduced the shape once: the grid reads `dup_eff 301` and `diverged 1/300` where the screening appendix reads `dup_eff 31` and `diverged 1/30` ([`bench/confirm/v1.yaml`](../../bench/confirm/v1.yaml) is the plan that selected it). Every one of the 870 trials deployed exactly once; none of the 962 is a deploy. |

What these rows do not cover. `kill @ landmark:approval_decided`, the clause of H7 that predicts a
duplicate gated effect for every at-least-once arm, did not run, nor did the rest of §14.2's tier-1
W5 pairs (the day-4 faults, the reask arm, `pause_past_ttl`, the other kill locations). H7 also
calls the tier-2 re-fire an S7 counterexample at F0; with S7 N/A for this arm the verifier cannot
score it, so here it is a count and not a verdict. `approval_delay` sends §11.4 spec C's duplicate
click: a second, unkeyed approve right after the first (`approval_duplicate_gap_ms: 0`). The second
click rewrites the same decision to the same `sut/resume` file — LangGraph's resume primitive carries
no approval id, so it reaches the framework only if the graph interrupts again. Nothing in the
headline rows says it did: `+calls 0` against the baseline, no restart and one deploy, 30 of 30 in
every config of W5. W5-pre's `sync` `approval_delay` cell has one trial per tier whose row reads as
a second interrupt — screening seed 17 and confirmation seed 100141, each with the restart, the
third `notify` and the fifth model call — and each of them deployed once. The
`approval_expiry` spec names `deploy.service#1` as forbidden. Both are in the release rows'
`spec_hash`; the re-run the earlier pages were due is these pages.

The tier-2 rows are in their own band because the workload was *constructed* to exercise a
documented caveat — §13.4: "pre-interrupt code re-runs" — and the adapter honours that on purpose:
the pre-gate call is deliberately not `@task`-wrapped, because wrapping it would measure the
adapter's care rather than the framework's resume semantics. It is a tier-2 (V2) cell in §14.2, built
in week 2 because it is the only cell that reaches H7's pre-interrupt clause. The citation the upstream
template requires — the sentence from the version under test, not from memory — is the framework's
own docstring, `langgraph.types.interrupt.__doc__` at `langgraph 1.2.11`, verbatim, its own emphasis:

> A client resuming the graph must use the [`Command`][langgraph.types.Command]
> primitive to specify a value for the interrupt and continue execution.
> The graph resumes from the start of the node, **re-executing** all logic.

So the tier-2 rows *sharpen* rather than contradict: the docs say the node re-executes, and the
rows say what that costs when the re-executed logic has a side effect — one extra `notify` per
re-entry, and three re-entries when the process holding the wait is killed. That is a docs-grade
finding by the template's own distinction (a documented behaviour with an undocumented consequence
a user would act on), not a bug report. `crashproof demo` cannot reproduce it — the demo runs
`tool_chain_1_effect` only — so its repro is the W5-pre form in
[the template](../upstream-report-template.md#the-report).

## W7 — streaming: N/A, with the citation

LangGraph 1.2.11 can *emit* a streamed model call: `Pregel.stream` documents `stream_mode="messages"`
("Emit LLM messages token-by-token together with metadata for any LLM invocations inside nodes or
tasks") and `"custom"` ("Emit custom data from inside nodes or tasks using `StreamWriter`"). What it
does not document is any durable meaning for a streamed piece: `durability` persists "changes" per
step ("`sync`: Changes are persisted synchronously before the next step starts"), `"checkpoints"`
mode emits "when a checkpoint is created", and nothing says what a token already streamed is after a
crash — whether it is re-streamed, kept, or charged. The bar for W7's second arm was documented durable
semantics for the stream, so W7 and `model_stream_truncate` are N/A here until a version documents
them; the adapter's model call stays one non-streamed call in the agent node.

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the framework does not do itself, no dedup in the adapter,
no key synthesised. The graph shape is fixed and identical across all three configs — agent node =
one model call, tool node = one `@task` tool call, one superstep each — so a difference between
columns is a difference in `durability` and nothing else.

## Proxy mode

`bench/specs/week2_w1_proxy.yaml` puts the injector between the graph and the World instead of
inside the `@task` ([`bench/reports/v1_w1_proxy.md`](../../bench/reports/v1_w1_proxy.md)). Nothing
in the adapter changes for it, and nothing is translated: a 5xx, a dropped connection or a body that
is not JSON reaches the `@task` as an exception, the node fails, the process exits, the supervisor
restarts it, and the task — whose result was never persisted — re-runs and re-fires the effect.
`tool_500`, `tool_dropped_response` and `tool_malformed` each show two applied effects on the
`dedup:false` endpoint with one restart, 30 of 30 in every config (`+calls 1` in `exit`, 0 in the
other two). That is the documented at-least-once for an un-wrapped effect, PASS against the declared
claim, printed raw beside Keel's one — and it is the same finding the shim's `tool_500` row already
made, now made with no harness code firing inside the SUT: the shim rides along observe-only
(`CRASHPROOF_MODE=proxy`), counting calls at the wire, and the worker writes `sut/pid-<n>` so the
proxy can aim a kill.

`kill@after:tool_return` is the cell the edge cannot reach the way the shim does. From the wire the
kill is a `taskkill` issued once the response has passed, and where it lands depends on what the
framework still has to do. A kill row is stamped `executed: false` unless the incarnation it aimed
at ended on its own terms — `executed_flags` demands an incarnation at that `recovery_index` with a
non-zero, non-`None` exit code that the harness did not stop, so a clean exit, a process still
running at the end of the trial and a row with no matching incarnation all stamp false, and the row
does not say which of them it was. That trial is void, `--resume` re-takes it, and the page folds
the last row per seed. `sync` has a checkpoint to write: on the page neither variant voids a trial —
every seed folds to a scored row, so the kill landed 30 of 30 — and both read
`dup_eff 0 · dup_rcpt 0`. Two things sit beneath that fold. The page prints no restart column, and
under it 5 `EXTERNAL` and 12 `IDEMPOTENT` trials carry no restart with the fault row still
`executed: true`, the run finishing before the kill being the reading. And `sync` has 6 first
attempts that did void (34 and 32 rows for 30 seeds, at `restarts 0`) and were replaced by their
re-takes; the page is the re-take's reading, which is what `--resume` is for. `async` writes that checkpoint off the loop, and its `EXTERNAL` cell is one of the
proxy cells the confirmation tier re-ran: at 300 seeds the World applied the effect twice in **294
of 300**, `dup_rcpt 428`, `diverged 294/300`, `+calls 2`, where screening's 30 read `dup_eff 29` and
`diverged 29/30` (the appendix) — the one config whose proxy T3 duplicates the effect at all: `sync`
reads `dup_eff 0` and `exit` is withdrawn. It is not the shim's reading of the same cell. The
agreement page pairs this exact twin over the 30 seeds both instruments ran — its `n` reads
`30 (+300 proxy only)`, the proxy's confirmation seeds folded into neither side — and prints **no**
for *both* raw counts
([`bench/reports/agreement_v1.md`](../../bench/reports/agreement_v1.md)): `duplicate_effects 30 / 29`
and `duplicate_receipts 60 / 30`, under its rule that a twin agrees only where the two instruments
match on every safety verdict and every raw count. Over those 30 seeds the shim carries
`dup_eff 30 · dup_rcpt 60`, exactly two duplicate receipts in every trial, where the proxy carries 29
and 30 spread unevenly — 28 trials with one duplicate receipt, one with two, one with none, and the
same one trial carrying the missing duplicate effect; the grid's `dup_rcpt 428` is the proxy's own n = 300 tier and not the paired side. Its
`IDEMPOTENT` twin stayed at 30 seeds and shows the receiver absorbing a second send:
`dup_eff 0` beside `dup_rcpt 34`. That the kill beat the checkpoint write is the reading of those
duplicates, not a field: no row records whether a checkpoint was in flight. `exit` persists nothing
until the graph is done: **21 of 30** `EXTERNAL` and **25 of 30** `IDEMPOTENT` seeds stayed void
through every re-take (152 and 163 rows for 30 seeds), their fault row `executed: false`, all 46 at
`restarts 1` where the `exit` baseline restarts in none, and at the baseline's 3 model calls. The
row carries no reason, and nothing in it records when the worker finished; that the `taskkill` from
outside lands after exit mode's own process exit is the reading, and a kill that did not happen is a
trial voided rather than scored. Both cells are over §30's 5 % void threshold, so the page withdraws
them under K7: it prints the void count and the raw counts — `dup_eff 0`, `dup_rcpt 0` — and no
verdict from the 9 and the 5 that remain.
