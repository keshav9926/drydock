# Adapter: Keel

The reference implementation, measured by its own harness. It gets no special path through
Crashproof: the same shim, the same World, the same verifier, the same spec files. Where it does
get something the other arms do not — the `hook`-mode conformance cells of §14.5 — those results
live in [their own table](../../bench/keel_conformance/table.md) and are never unioned with a
cross-runtime row, because a boundary only one runtime exposes is not a fair column.

Source: [`crashproof/adapters/keel.py`](../../crashproof/adapters/keel.py).
Workload binding: [`keel/agents/demo.py`](../../keel/agents/demo.py).

## Declarations

| | |
|---|---|
| `recovery_mechanism` | **`self`** — the restarted process scans its own store and finds its work. Nothing tells it which run to resume, and the `worker_argv` the supervisor re-spawns carries no run id. |
| `key_sources` | `none` (F0) and `framework` (F1) |
| `claims` | PURE `effectively_once` · IDEMPOTENT `effectively_once` · EXTERNAL `at_least_once` |
| Per-trial dependency | a Postgres database cloned from a migrated template |
| Durable unit | one step: `STEP_INTENDED` → `STEP_ATTEMPT_STARTED` → outcome |

The EXTERNAL claim is the one worth reading twice. A fence protects journal appends; it cannot
reach a third party. So the only classes that may claim more than at-least-once are the ones where
the **receiver** is doing the work — which is why IDEMPOTENT is `effectively_once` and EXTERNAL is
not, and why an EXTERNAL duplicate in the matrix is a printed cost rather than a failure.

## `key_source` formula

```
effect_key = sha256(run_root_id ‖ 0x1f ‖ step_index ‖ 0x1f ‖ tool_name ‖ 0x1f ‖ canonical_args)[:32]
```
— [`keel/core/hashing.py:effect_key`](../../keel/core/hashing.py)

Every term is there for a property the fairness level depends on (§13.6, F1):

- **`run_root_id`** — the run's root, not the run. A fork gets a new root, so a forked run's effects
  are new logical effects and cannot dedup against the base run's.
- **`step_index`** — never repeats within a run root, so two calls to the same tool with the same
  arguments are two logical effects rather than one.
- **`tool_name`** and **`canonical_args`** — the identity of the call. `canonical_args` is total and
  process-independent by construction: sorted keys, no whitespace, bytes as base64, and `set`/
  `frozenset` fields *refused at registration* because their iteration order follows per-process
  hash randomisation, which would make two workers hash the same call differently.

It is a pure function of identifiers Keel itself persists and restores, which is what `framework`
means. It is stable across attempts and across recoveries — the same crashed step, re-attempted by
a successor three seconds later, presents the same key — and that is the entire mechanism behind
the IDEMPOTENT band's `effectively_once`.

**Which level a cell runs at is the *variant's* choice, not the adapter's**, and the workload spec
carries it:

| Variant | Endpoint | `dedup` | Key sent | Level |
|---|---|---|---|---|
| EXTERNAL | `issues.create` | `false` | none | **F0** (`key_source=none`) |
| IDEMPOTENT | `issues.upsert` | `true, natural: true` | `Idempotency-Key: <effect_key>` | **F1** (`key_source=framework`) |

One tool name, two registrations, and the program cannot tell them apart — that is what makes the
two bands comparable rather than two different programs.

## What a restart does

1. The reaper marks the run ORPHANED when `now() > lease_expires_at`, *and additionally*
   `now() > attempt_deadline` when a non-PURE attempt is open. One conditional `UPDATE` with a
   correlated subquery; no successor-side wait.
2. A worker claims it with `SELECT … FOR UPDATE SKIP LOCKED` and a conditional
   `UPDATE … lease_epoch = lease_epoch + 1`. The returned epoch is the fence: every subsequent
   append begins by re-checking it, so the previous worker — alive or not — cannot write again.
3. `RECOVERY_STARTED{cause=ORPHANED}`, then memoized re-execution to the first un-journaled step.
4. A step with `STARTED` and no outcome is disposed of **by effect class**: PURE re-runs,
   IDEMPOTENT re-fires under the same key, EXTERNAL goes `STEP_AMBIGUOUS` → probe →
   `STEP_RESOLVED`. Never a guess.

## W5 — the human in the loop

The wait is `ctx.approve(payload, gates=(tool, args))`, one transaction — INTENT, STARTED,
`APPROVAL_REQUESTED`, `RUN_WAITING`, and as its last statement the release, which leaves **both**
`lease_expires_at` and `runnable_at` NULL. The first NULL is why the wait costs no compute; the second
is why it costs no ticks: nothing polls a parked run, and a worker looking for work finds none. The
release is guarded by `runnable_at IS NULL`, so a signal that landed since the holder's last drain
rolls the whole park back and the engine drains and parks again — a grant can arrive at any instant
and never be erased by the park it arrived beside.

The harness grants by inserting one `approve` row in the inbox and nothing else, naming the approval
it decides: the open one, or once nothing is open the most recent. Whichever worker is alive claims
the run and journals the decision at its own drain — which is why `kill_while_waiting` yields exactly
one gated effect: the grant was never in a process's memory to lose. Under `approval_delay` the human
clicks twice (§11.4 spec C, `approval_duplicate_gap_ms: 0` in the W5 matrices), and the second row
names the same approval, unkeyed; the drain journals it `SIGNAL_IGNORED{approval_terminal}` rather
than granting anything a second time. The published W5 rows predate the second click and the named
approval, so those cells are due a re-run.

`binds_effect_key = effect_key(run_root_id, i+1, tool, args)` is computed before anyone decides,
because the runtime owns the step counter, so the approval names the effect it authorises rather
than "whatever happens next". The step after the approval must be that call: anything else fails with
`ApprovalBindingError` before an attempt starts. The gate is read before STARTED; a refusal writes
`attempt_no=0` and a `DENIED` effects row, so no attempt began and no effect was reachable (S7, which
the verifier judges against the World's applied counts). Expiry is judged by the store's clock at
drain time and outranks arrival order: an `approve` drained after `expires_at` is ignored and the
approval expires. Under `approval_expiry` the run completes with `not done: approval expired` and
nothing deployed — the correct end state, declared on the cell's spec as `deploy.service#1` applied
zero times, so S3 does not mistake a refusal for a phantom completion and a deploy under an expired
wait fails `logical_correctness` for any arm.

## Pins

`tool.timeout = 1 s`, `lease_ttl = 2 s`, heartbeat `≈ 0.67 s`, `attempt_deadline = started_at + 1 s`,
`pause_past_ttl` pause 3 s (pinned, not drawn), `worker_count = 2` in `pause_past_ttl` cells and 1
elsewhere, retry `max_attempts = 3` with exponential backoff and full jitter, and the circuit breaker's
`n_open = 5`, `cooldown_s = 30` (rows written before `182994a` do not carry the breaker). Every one of
them travels in `config_pin` on every row, because "Keel recovers faster" is a claim about timeouts
unless both arms' timeouts are printed beside it.

`lease_ttl > max(registered tool.timeout)` is an operator rule, not a suggestion: the pre-dispatch
check refuses to dispatch any non-PURE effect unless `lease_valid_until − now ≥ tool.timeout`, and
`keel worker` refuses to start when the inequality does not hold, naming the offending tool.

## Adapter rules obeyed

Per §13.3 an adapter expresses the workload in its framework's **documented** primitives and adds
nothing. Keel's adapter is held to that as strictly as any other arm: no counter, no pre-send
lookup, no retry the framework does not do itself, no dedup in the adapter. It calls
`keel.client`'s public API and nothing private, and the workload binding it uses
(`keel/agents/demo.py`) is a program a user could write.

## Proxy mode

`bench/specs/tier1p.yaml` runs the matrix-v0 and tier1a windows with the injector *outside* the
SUT: the worker is pointed at `crashproof/proxy`, which is pointed at the World, and the shim in
the worker rides along observe-only so model calls are still counted at the wire. Nothing in the
adapter changes for it. Two translations the adapter already made for the shim now also apply to
what arrives over the wire, and they are the whole of its involvement: a 5xx status is
`UnknownOutcome` and a 4xx is `Rejected` (the receiver's semantics, §9.2), and a dropped connection
or an unparseable body is `UnknownOutcome` too (§8.5's transport ambiguity). The class then decides:
EXTERNAL becomes AMBIGUOUS, the probe finds COMMITTED, and the effect is not re-fired — which is
what the `tool_dropped_response` and `tool_malformed` rows show, one applied effect each.

`pause_past_ttl@before:tool_call` is the cell whose proxy realisation is meant to differ from its
shim twin: the worker's request is parked *at the proxy* and the worker itself is frozen past its
lease, so the successor takes over, probes (ABSENT — the request is still parked), re-attempts and
applies, and the parked request is forwarded at the thaw and lands second — the zombie residual of
§8.4 by a different road, at-least-once against the declared claim.

**The published tier1p rows mostly did not measure that.** The proxy freezes the process named by
`sut/pid-<n>`, and until `22f53d9` the successor wrote `pid-0` as well, so whichever of the two wrote
last was frozen. Read from the trial journals, in 41 of the 60 Keel trials (23 of 30 `EXTERNAL`, 18 of
30 `IDEMPOTENT`) the idle successor was frozen and the worker holding the run kept appending: its own
1 s tool timeout fired on the parked request, it probed (ABSENT), re-attempted and completed the run,
and the parked request applied again at the thaw. The duplicate counts on the page (30 of 30
`EXTERNAL`) come out the same either way, but the mechanism above ran in 19 of the 60, and the cell's
`lat 1.0s` is the tool timeout. Only the worker under test now writes `pid-<n>` (the successor writes
`pid-successor-<n>`), and a proxy that stops drops a request still parked instead of forwarding it
after the trial. The cell is due a re-run.
