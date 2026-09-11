# compare — `keel.*` (A) vs `langgraph.sync.*` (B)

480 paired trials on (workload, variant, trigger, spec_hash, seed).

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 0 | 120 |
| `duplicate_receipts` | 90 | 240 |
| `missing_required` | 0 | 0 |

## Liveness — McNemar over discordant pairs

| metric | A only | B only | verdict |
|---|---|---|---|
| `recovery_rate` | 0 | 0 | too noisy to claim (0 discordant pairs) |
| `logical_correctness` | 120 | 0 | A better (p=0.0000) |

## Economy — paired bootstrap on the median difference

| metric | A median | B median | A−B | 95% CI | verdict |
|---|---|---|---|---|---|
| `recovery_latency_ms` | 143.3 | 2325.8 | -1242.6 | [-2514.2, -26.6] | not claimable (detection = harness for one arm) |
| `extra_model_calls` | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | too noisy to claim |
| `extra_tokens` | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | too noisy to claim |
| `wall_clock_overhead_ms` | 1156.7 | 2541.6 | -1182.2 | [-1366.4, -1055.4] | not claimable (detection = harness for one arm) |

A safety observation is a count of what happened, so it carries no p-value: whether a runtime filed the issue twice is not a sample from a population. The estimates below it are, and `too noisy to claim` is a real answer — at thirty seeds it is the most common honest one, and saying so is the point of printing the interval rather than the point estimate alone.
