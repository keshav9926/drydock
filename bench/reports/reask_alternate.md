# reask_alternate

Workload `tool_chain_1_effect`. One cell is n **seeds**, not n trials of one seed.

## EXTERNAL  ·  key_source=none

| (location, fault) | `keel.default` | `langgraph.async` | `langgraph.sync` |
|---|---|---|---|
|  | recovery=self<br>claims: PURE effectively-once · IDEM effectively-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once |
| `baseline` | S1✓ S2✓ S3✓ S4✓ S5✓ C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2· S3✓ S4· S5· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2· S3✓ S4· S5· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 |
| `kill@after:tool_effect+model_reask_alternate@before:model_call` | S1✓ S2✓ S3✓ S4✓ S5✓ C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 0.0s · +calls 2 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>+calls 0 · diverged 30/30 |

## Counterexamples

None. Every safety invariant held in every scored trial.

## Provenance

Generated 2026-09-12T08:02:43+00:00.

| config | pin |
|---|---|
| `keel.default` | backend=postgres, claim_poll_s=0.2, durability=journal, extra={'model_timeout_s': 2.0, 'world_client_timeout_s': 5.0}, heartbeat_s=0.666667, lease_ttl_s=2, pause_ms=3000, reaper_period_s=0.2, retry=max_attempts=3, backoff=exponential+jitter, tool_timeout_s=1, worker_count=1 |
| `langgraph.async` | backend=AsyncPostgresSaver, durability=async, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `langgraph.sync` | backend=AsyncPostgresSaver, durability=sync, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |

**How to read a cell.** The first line is safety: PASS means zero violations in n, and a single violation is a FAIL with its counterexample listed above — safety is never a proportion. The second line is liveness with a Wilson interval. The third is raw observation, published whatever the verdicts say: `dup_eff` counts effects the World actually applied more than once, `dup_rcpt` counts requests it received more than once. The gap between them is what the receiver's idempotency bought, and the runtime gets no credit for it.

**Judged against claims.** An arm that declares `at_least_once` and produces a duplicate has not failed S1; the duplicate is in the table regardless. An arm that declares `effectively_once` and applies twice has failed, and the seed that did it is named.
