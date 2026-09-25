# compare — `keel.*` (A) vs `langgraph.sync.*` (B)

540 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-15T15:14:33+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/tier1p` | 1080 | `8ee372d` ×848, `77488a2` ×154, `426b7df` ×78 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 30 | 150 |
| `duplicate_receipts` | 210 | 300 |
| `missing_required` | 0 | 0 |

## recovery_rate · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_rate · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## logical_correctness · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·kill@after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | B better (p=0.0000) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## logical_correctness · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## replay_divergence · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·kill@after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | B better (p=0.0000) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## replay_divergence · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_latency_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 2326.4 | 2612.6 | -279.9 | [-308.1, -233.1] | 0.0000 | — | 69.02 | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_return` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 2306.5 | 2640.8 | -296.2 | [-342.1, -274.8] | 0.0000 | — | 74.25 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 1020.2 | 3059.4 | -2040.4 | [-2050.9, -2015.6] | 0.0000 | — | 315.27 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 36.0 | 2534.9 | -2492.5 | [-2541.4, -2443.7] | 0.0000 | — | 79.31 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 35.5 | 2451.2 | -2421.0 | [-2466.0, -2369.0] | 0.0000 | — | 47.22 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 33.4 | 2250.2 | -2211.7 | [-2322.7, -2117.0] | 0.0000 | — | 97.77 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 7.3 | 8.5 | -0.9 | [-8.1, -0.2] | 0.043 | — | 4.89 | not claimable (detection = harness for one arm) |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 2372.1 | 2248.2 | 121.5 | [49.8, 162.9] | 0.016 | — | 96.56 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_return` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 2445.3 | 2290.5 | 190.5 | [35.1, 254.9] | 0.005 | — | 111.91 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 1121.2 | 3055.7 | -1928.0 | [-1953.4, -728.3] | 0.0000 | — | 332.75 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 119.2 | 2253.0 | -2142.6 | [-2293.9, -2080.9] | 0.0000 | — | 120.09 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 127.0 | 2196.4 | -2058.0 | [-2117.7, -2031.3] | 0.0000 | — | 162.70 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 120.0 | 2122.5 | -1983.4 | [-2075.8, -1963.3] | 0.0000 | — | 68.52 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 9.2 | 17.1 | -0.2 | [-6.0, 1.2] | 1.000 | — | 6.13 | not claimable (detection = harness for one arm) |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_model_calls · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_tokens · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 2346.5 | 3106.1 | -749.7 | [-853.3, -701.1] | 0.0000 | — | 653.68 | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_return` (n=30) | 347.7 | 610.5 | -284.2 | [-432.8, -130.4] | 0.0001 | — | 348.57 | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 2335.8 | 3124.6 | -759.1 | [-857.9, -633.1] | 0.0000 | — | 207.53 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 3387.7 | 3515.7 | -125.3 | [-226.7, -23.6] | 0.016 | — | 117.53 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | -14.3 | 3030.7 | -3034.1 | [-3118.3, -2942.5] | 0.0000 | — | 145.92 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 32.9 | 2839.6 | -2769.3 | [-2903.9, -2697.8] | 0.0000 | — | 89.77 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 141.0 | 2523.4 | -2268.0 | [-2716.3, -2039.5] | 0.0000 | — | 265.55 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 1004.3 | 7262.1 | -6242.7 | [-6322.6, -6179.1] | 0.0000 | — | 150.93 | not claimable (detection = harness for one arm) |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 2482.6 | 2212.2 | 334.0 | [246.2, 478.4] | 0.001 | — | 154.99 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 507.8 | 433.5 | 85.8 | [-73.8, 336.8] | 0.362 | — | 328.68 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 2702.9 | 2278.1 | 410.8 | [322.3, 765.9] | 0.0000 | — | 203.92 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3675.0 | 3113.5 | 592.3 | [533.4, 665.2] | 0.0000 | — | 244.62 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 173.2 | 2368.6 | -2204.6 | [-2387.2, -2106.7] | 0.0000 | — | 256.72 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 266.3 | 2202.0 | -1950.4 | [-2046.6, -1809.6] | 0.0000 | — | 602.69 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 274.3 | 2016.6 | -1746.1 | [-1928.4, -1629.7] | 0.0000 | — | 255.00 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 1402.1 | 7169.9 | -5709.9 | [-5928.8, -5561.8] | 0.0000 | — | 286.54 | not claimable (detection = harness for one arm) |

A safety observation is a count of what happened, so it carries no p-value: whether a runtime filed the issue twice is not a sample from a population. The estimates above it are, and every one of them is made per `(location, fault)` cell — averaging a kill at `after:tool_effect` together with a `pause_past_ttl` answers neither question. Holm runs across the cells of one metric table and nowhere else (§15.6). Every row with a p-value counts toward `m` and prints its adjusted p, including rows rules 1–4 already disqualified; only rows confounded by `detection = harness` are out.

Two departures from §15.5, named: binary rows use McNemar's exact test at every discordant count (§15.5 names the continuity-corrected χ² from b + c ≥ 25), and they print no Wilson interval on b/(b + c) — the discordant counts and δ are printed instead.

`too noisy to claim` is a real answer — at thirty seeds it is the most common honest one, and the failing rule is named beside it. The point estimate, the interval and the adjusted p stay on the page whatever the verdict: a rule that fails takes away the verb, never the numbers.

**The model is a fixture.** Every cell here ran against the scripted provider, which answers from request content alone. K11(b)'s `real-model` validation subset was not run, so a model-boundary cell (`model_500`, `model_timeout`, `provider_outage`, `model_reask_alternate`) says what the runtime did with a scripted answer, and nothing about what a real provider would have said.

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

**3. This page is the screening tier only.** Every cell here is at n ≤ 30. §15.3's confirmation
tier — every non-unanimous cell and every cell under a claimed difference re-run at n = 300 on fresh
seeds, together with the arm it is compared against — has not been run for these rows, so no
difference on this page is confirmed.

**4. The variance being sampled is the right one.** Schedules are seeded and shared between arms, so
the residual variance is the SUT's own internal timing — which is precisely the quantity a
durability claim is about. Thirty samples of "does the reaper beat the zombie" are thirty draws from
the distribution a user would experience.

**5. Everything is reproducible.** Every row carries `(spec_hash, seed, keel_commit)` and its
`config_pin`, framework versions included. `keel_commit` pins the adapters as well as Keel, because
they live in the same repository, and it is marked `-dirty` when the tree had uncommitted changes.
`crashproof verify <dir>/results.jsonl --recheck` re-runs the verifier over each trial's own facts
and fails if a verdict moved or a row cannot be re-verified. Disagreement is settled by running it.
