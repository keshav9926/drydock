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
the receiver bought.

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

## Adapter rules obeyed

No counter, no pre-send lookup, no retry the framework does not do itself, no dedup in the adapter,
no key synthesised. The graph shape is fixed and identical across all three configs — agent node =
one model call, tool node = one `@task` tool call, one superstep each — so a difference between
columns is a difference in `durability` and nothing else.
