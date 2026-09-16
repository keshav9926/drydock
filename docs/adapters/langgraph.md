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

**`kill@after:tool_effect` + `model_reask_alternate`, `async`: `replay_divergence` 30/30 with
`duplicate_effects` 0.** The interrupted step is not re-*done*, it is re-*decided*: the model is
re-invoked, returns a different tool call, and the recovered run follows a different branch and
files a different issue. Nothing was duplicated, so every duplicate-counting safety metric scores
the cell clean — which is the whole reason `replay_divergence` exists as a column
([`bench/reports/reask_alternate.md`](../../bench/reports/reask_alternate.md)).

## W5 — the human in the loop, measured (§13.7 H7)

The wait primitive is `interrupt()`; resumption is a fresh `ainvoke(Command(resume=...))` on the
same thread, made by the worker on the harness's instruction (a file in the trial directory — the
human's decision, written once and never deleted). Thirty seeds per cell, the `sync` and `async`
configs ([`bench/reports/w5.md`](../../bench/reports/w5.md), [`w5_pre.md`](../../bench/reports/w5_pre.md)).
Every row below held 30/30 in both configs; the `sync` column is printed. Each is a raw count beside a
declared `at_least_once` — none of them fails S1 — and the one verdict that fails is named in its row:

| cell | LangGraph sync | Keel | what it says |
|---|---|---|---|
| `approval_delay` (headline) | deploy **1**, 4 model calls | deploy **1**, 3 model calls | The gated effect after `interrupt()` fires once. No difference in effects, and that is the honest result; the resume re-runs the interrupting node, one model call. |
| `kill_while_waiting` (headline) | deploy **1**, 5 model calls | deploy **1**, 3 model calls | H7 held: `interrupt()` is checkpointed, so the successor is granted once. The interrupting node re-ran on the restart as well as on the resume. |
| `kill@after:tool_effect` | deploy **2** | deploy **1** | The day-3 window behind the gate: after the decision and the deploy, before the checkpoint. The node re-runs and deploys again, in 30 of 30 trials in both configs — the at-least-once cost, printed. |
| `approval_expiry` | **still WAITING at 60 s**, **L1 FAIL** (by design), nothing deployed | expired at 5 s, COMPLETED `not done`, nothing deployed | There is no deadline on `interrupt()`. A human who never answers is a run that never ends. S3 holds either way — nothing was deployed. S7 is N/A for LangGraph: it has no journal to bind an applied effect to an approval. |
| **tier-2** baseline (`notify` before the gate) | notify **2**, deploy 1 | notify **1**, deploy 1 | H7 held: pre-interrupt code re-runs on resume. |
| **tier-2** `kill_while_waiting` | notify **3**, deploy 1 | notify **1**, deploy 1 | Every re-entry of the interrupting node re-runs what came before the interrupt: original, restart, resume. Across W5-pre's 180 LangGraph trials that is 240 extra `notify` effects — 120 per config, 30 + 30 + 60 from baseline, `approval_delay` and `kill_while_waiting` — none of them a deploy. |

What these rows do not cover. The `exit` config did not run. Neither did `kill @
landmark:approval_decided`, the clause of H7 that predicts a duplicate gated effect for every
at-least-once arm, nor the rest of §14.2's tier-1 W5 pairs (the day-4 faults, the reask arm,
`pause_past_ttl`, the other kill locations). H7 also calls the tier-2 re-fire an S7 counterexample at
F0; with S7 N/A for this arm the verifier cannot score it, so here it is a count and not a verdict.
`approval_delay` in the matrix files now sends §11.4 spec C's duplicate click: a second, unkeyed
approve right after the first. The second click rewrites the same decision to the same `sut/resume`
file — LangGraph's resume primitive carries no approval id, so it reaches the framework only if the
graph interrupts again. The published rows predate the second click, and the `approval_expiry` spec
now names `deploy.service#1` as forbidden; both changed their cells' `spec_hash`, so both pages are
due a re-run.

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

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the framework does not do itself, no dedup in the adapter,
no key synthesised. The graph shape is fixed and identical across all three configs — agent node =
one model call, tool node = one `@task` tool call, one superstep each — so a difference between
columns is a difference in `durability` and nothing else.

## Proxy mode

`bench/specs/tier1p.yaml` puts the injector between the graph and the World instead of inside the
`@task`. Nothing in the adapter changes for it, and nothing is translated: a 5xx, a dropped
connection or a body that is not JSON reaches the `@task` as an exception, the node fails, the
process exits, the supervisor restarts it, and the task — whose result was never persisted —
re-runs and re-fires the effect. `tool_500`, `tool_dropped_response` and `tool_malformed` each
show two applied effects on the `dedup:false` endpoint, with one restart. That is the documented
at-least-once for an un-wrapped effect, PASS against the declared claim, printed raw beside Keel's
one — and it is the same finding the shim's `tool_500` row already made, now made with no harness
code firing inside the SUT: the shim rides along observe-only (`CRASHPROOF_MODE=proxy`), counting
calls at the wire, and the worker writes `sut/pid-<n>` so the proxy can aim a kill.

`kill@after:tool_return` is the cell the edge cannot reach the way the shim does: 14 of its 30
`EXTERNAL` trials and 3 of its 30 `IDEMPOTENT` trials record no restart, because the run had finished
before the kill landed. Under the current scoring a kill that never landed makes the trial void, so
that cell is due a re-run before either count means anything.
