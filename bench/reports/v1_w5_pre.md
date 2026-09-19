# v1_w5_pre

Workload `approval_gated_deploy_pre`. One cell is n **seeds**, not n trials of one seed.

## GATED  ·  key_source=none

| (location, fault) | `dbos.native` | `dbos.pydantic_ai` | `keel.default` | `langgraph.async` | `langgraph.exit` | `langgraph.sync` | `restate.pydantic_ai` | `temporal.pydantic_ai` |
|---|---|---|---|---|---|---|---|---|
|  | recovery=self<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once | recovery=self<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once | recovery=self<br>claims: PURE effectively-once · IDEM effectively-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=engine<br>claims: PURE exactly-once · IDEM exactly-once · EXT exactly-once | recovery=engine<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once |
| `baseline` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7✓ C1✓<br>L1 300/300 [0.99–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 300/300 [0.99–1.00]<br>dup_eff 300 · dup_rcpt 300 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 |
| `approval_delay@supervisor` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7✓ C1✓<br>L1 300/300 [0.99–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.2s · +calls 0 · diverged 0/300 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 300/300 [0.99–1.00]<br>dup_eff 301 · dup_rcpt 301<br>lat 0.1s · +calls 0 · diverged 1/300 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.2s · +calls 0 · diverged 0/30 |
| `kill_while_waiting@supervisor` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.5s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 4.7s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7✓ C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 1.7s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 60 · dup_rcpt 60<br>lat 3.8s · +calls 1 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 60 · dup_rcpt 60<br>lat 2.6s · +calls 1 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 60 · dup_rcpt 60<br>lat 2.6s · +calls 1 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 7.5s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 4.6s · +calls 0 · diverged 0/30 |

## Appendix — the screening tier of the confirmed cells (§15.3)

The grid reports these cells at the confirmation tier (seeds ≥ 100,000); this is what the screening tier showed for them. A safety FAIL in either tier is a FAIL in the grid.

| cell | screening |
|---|---|
| `keel.default.GATED.approval_delay@supervisor` | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7✓ C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.2s · +calls 0 · diverged 0/30 |
| `keel.default.GATED.baseline` | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7✓ C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 |
| `langgraph.sync.GATED.approval_delay@supervisor` | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 31 · dup_rcpt 31<br>lat 0.1s · +calls 0 · diverged 1/30 |
| `langgraph.sync.GATED.baseline` | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 |

## Counterexamples

None. Every safety invariant held in every scored trial.

## Provenance

Rows through 2026-09-19T20:56:11+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w5_pre` | 1920 | `251e52d` ×1920 |

| config | pin |
|---|---|
| `dbos.native` | backend=postgres (DBOS system database, one per trial), durability=step checkpoint, extra={'agent_code': 'native', 'application_version': 'DBOS default: hash of workflow source', 'executor_id': 'local (no Conductor)', 'max_recovery_attempts': 100, 'recv_timeout': 'run input expires_in', 'step_timeout': 'none', 'world_client_timeout_s': 5.0}, retry=none: @DBOS.step(retries_allowed=False), worker_count=1 |
| `dbos.pydantic_ai` | backend=postgres (DBOS system database, one per trial), durability=step checkpoint, extra={'agent_code': 'pydantic_ai', 'application_version': 'DBOS default: hash of workflow source', 'executor_id': 'local (no Conductor)', 'max_recovery_attempts': 100, 'model_step_config': 'default (retries_allowed=False)', 'parallel_execution_mode': 'parallel_ordered_events (default)', 'recv_timeout': 'run input expires_in', 'step_timeout': 'none', 'world_client_timeout_s': 5.0}, retry=none: @DBOS.step(retries_allowed=False), worker_count=1 |
| `keel.default` | backend=postgres, claim_poll_s=0.2, durability=journal, extra={'breaker': 'n_open=5, cooldown_s=30', 'model_timeout_s': 2.0, 'world_client_timeout_s': 5.0}, heartbeat_s=0.666667, lease_ttl_s=2, pause_ms=3000, reaper_period_s=0.2, retry=tools max_attempts=3 base=1s cap=30s; model max_attempts=5 base=2s cap=60s; x2 full jitter; a wait of 1 s or more parks with the lease released (§8), tool_timeout_s=1, worker_count=1 |
| `langgraph.async` | backend=AsyncPostgresSaver, durability=async, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `langgraph.exit` | backend=AsyncPostgresSaver, durability=exit, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `langgraph.sync` | backend=AsyncPostgresSaver, durability=sync, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `restate.pydantic_ai` | backend=restate-server single binary, fresh RESTATE_BASE_DIR per trial, wiped at teardown, detection_timeout_s=7, durability=invocation journal; agent_code=pydantic_ai (RestateAgent wrapper, not a capability), extra={'abort_timeout_s': 5.0, 'approval_wait': 'ctx.awakeable + restate.select(ctx.sleep(expires_in))', 'asgi': 'hypercorn.asyncio.serve in the worker process, 127.0.0.1:<port fixed per trial>', 'client_retries': 'none (FunctionModel has no provider client; the World client does not retry)', 'inactivity_timeout_s': 2.0, 'journal_retention': '1d', 'platform': 'linux (WSL2)', 'server_env': {'RESTATE_BOOTSTRAP_NUM_PARTITIONS': '1', 'RESTATE_DEFAULT_NUM_PARTITIONS': '1', 'RESTATE_DISABLE_TELEMETRY': 'true', 'RESTATE_LISTEN_MODE': 'tcp', 'RESTATE_ROCKSDB_TOTAL_MEMORY_SIZE': '32 MB'}, 'tools': 'restate_context().run_typed per call (RestateAgent auto_wrap_tools=False)', 'world_client_timeout_s': 5.0}, retry=InvocationRetryPolicy(initial_interval=50ms, exponentiation_factor=2.0, max_interval=60s, max_attempts=70, on_max_attempts=pause); ctx.run with default RunOptions (the invocation policy), worker_count=1 |
| `temporal.pydantic_ai` | backend=temporal server start-dev --db-filename (SQLite), one per trial, detection_timeout_s=2, durability=event history; agent_code=pydantic_ai (TemporalDurability), extra={'applies_to': 'model-request and tool-call activities alike', 'client_retries': 'none (FunctionModel has no provider client; the World client does not retry)', 'heartbeat_throttle': 'SDK default: 0.8 x heartbeat_timeout', 'heartbeat_timeout_s': 2.0, 'start_to_close_s': 5.0, 'sticky_queue_schedule_to_start_timeout_s': 2.0, 'workflow_task_timeout_s': 10.0, 'world_client_timeout_s': 5.0}, heartbeat_s=2, retry=RetryPolicy(initial_interval=1s, backoff_coefficient=2.0, maximum_interval=100s, maximum_attempts=0) + TemporalDurability non_retryable_error_types, tool_timeout_s=5, worker_count=1 |

**Mixed n.** Cells in this report were run at different seed counts ([30, 300]); each cell prints its own n in the liveness line. A reduced-n cell is a weaker estimate, not a different verdict: safety is still PASS only on zero violations in the n that ran, and the interval beside it widens to say so (§15.3).

**How to read a cell.** The first line is safety: PASS means zero violations in n, and a single violation is a FAIL with its counterexample listed above — safety is never a proportion. The second line is liveness with a Wilson interval. The third is raw observation, published whatever the verdicts say: `dup_eff` counts effects the World actually applied more than once, `dup_rcpt` counts requests it received more than once. The gap between them is what the receiver's idempotency bought, and the runtime gets no credit for it.

**Judged against claims.** An arm that declares `at_least_once` and produces a duplicate has not failed S1; the duplicate is in the table regardless. An arm that declares `effectively_once` and applies twice has failed, and the seed that did it is named.

### Minimum detectable difference (§15.7)

Two-sided α = 0.05, power = 0.80, equal `n` per arm.

**Unpaired difference in proportions** — the smallest drop from a baseline `p₀` that is detectable.

| `p₀` | n = 30 | n = 100 | n = 300 |
|---|---|---|---|
| 0.99 | 0.24 | 0.09 | 0.04 |
| 0.95 | 0.28 | 0.12 | 0.06 |
| 0.90 | 0.31 | 0.15 | 0.08 |
| 0.80 | 0.34 | 0.18 | 0.10 |
| 0.50 | 0.33 | 0.19 | 0.11 |

At n = 30 a recovery-rate gap smaller than ~30 percentage points is invisible. That is the honest
size of a screening tier, and it is why screening exists to find unanimity and to triage, not to
rank.

**Paired binary (McNemar / exact)** by discordance rate `ψ = (b+c)/n` — the smallest
`δ = (b−c)/n` detectable.

| `ψ` | n = 30 | n = 100 | n = 300 |
|---|---|---|---|
| 0.05 | — (≈1.5 discordant pairs expected; nothing detectable) | — (5 expected; below the 6-pair floor) | 0.036 |
| 0.10 | — (3 expected) | 0.088 (of 10 discordant, ≥ 9 one way) | 0.051 |
| 0.20 | ≥ `ψ` (6 expected; detectable only if all 6 fall one way, p = 0.031) | 0.12 | 0.07 |
| 0.40 | 0.31 | 0.18 | 0.10 |

Pairing helps only when the arms actually disagree on some seeds: two runtimes that both recover
30/30 have `ψ = 0`, and no test can separate them.

**Paired continuous, standardised** (`δ / σ_d`): `MDD = (1.96 + 0.84) / √n` — **0.51** at n = 30,
**0.28** at n = 100, **0.16** at n = 300. The report multiplies by each cell's observed `σ_d` and
prints the result in ms or tokens.


### "You only ran this thirty times" (§15.9)

**1. For safety rows the objection points the wrong way.** Thirty passing trials are not a claim of
safety, and this report never makes that claim. One *failing* trial is a proof of a bug with a
reproducible `(spec_hash, seed)`; thirty of them would add nothing. Jepsen finds consensus bugs in a
handful of runs because the faults are aimed at the mechanism rather than sampled from production,
and every trial here is aimed at a named window — `after:tool_effect` with the response held — that
a random production crash would reach rarely.

**2. For estimate rows the printed interval is the answer.** `28/30 [0.79, 0.98]` says exactly what
thirty trials can and cannot exclude, and the MDD table above says what gap would have been visible
at all. Neither is hidden behind a flag.

**3. Confirmation is automatic where it matters.** Every non-unanimous cell and every cell under a
claimed difference goes to n = 300 on fresh seeds, together with the arm it is compared against.
Unanimous cells that no claim depends on stay at thirty, because three hundred more of the same
outcome tighten an interval nothing rests on.

**4. The variance being sampled is the right one.** Schedules are seeded and shared between arms, so
the residual variance is the SUT's own internal timing — which is precisely the quantity a
durability claim is about. Thirty samples of "does the reaper beat the zombie" are thirty draws from
the distribution a user would experience.

**5. Everything is reproducible.** Every row carries `(spec_hash, seed, keel_commit)` and its
`config_pin`, framework versions included. `keel_commit` pins the adapters as well as Keel, because
they live in the same repository, and it is marked `-dirty` when the tree had uncommitted changes.
`crashproof verify <dir>/results.jsonl --recheck` re-runs the verifier over each trial's own facts
and fails if a verdict moved or a row cannot be re-verified. Disagreement is settled by running it.
