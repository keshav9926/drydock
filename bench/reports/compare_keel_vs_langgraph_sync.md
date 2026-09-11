# compare — `keel.*` (A) vs `langgraph.sync.*` (B)

300 paired trials on (workload, variant, trigger, spec_hash, seed).

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 11 | 60 |
| `duplicate_receipts` | 81 | 120 |
| `missing_required` | 0 | 0 |

## Liveness — McNemar over discordant pairs

| metric | A only | B only | verdict |
|---|---|---|---|
| `recovery_rate` | 0 | 0 | too noisy to claim (0 discordant pairs) |
| `logical_correctness` | 60 | 11 | A better (p=0.0000) |

## Economy — paired bootstrap on the median difference

| metric | A median | B median | A−B | 95% CI | verdict |
|---|---|---|---|---|---|
| `recovery_latency_ms` | 2711.1 | 2184.7 | 255.7 | [104.9, 905.9] | not claimable (detection = harness for one arm) |
| `extra_model_calls` | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | too noisy to claim |
| `extra_tokens` | — | — | — | — | too noisy to claim (0 paired observations) |
| `wall_clock_overhead_ms` | 3177.7 | 2022.0 | 1012.4 | [879.6, 1104.6] | not claimable (detection = harness for one arm) |

A safety observation is a count of what happened, so it carries no p-value: whether a runtime filed the issue twice is not a sample from a population. The estimates below it are, and `too noisy to claim` is a real answer — at thirty seeds it is the most common honest one, and saying so is the point of printing the interval rather than the point estimate alone.
