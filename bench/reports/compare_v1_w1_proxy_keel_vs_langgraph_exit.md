# compare — `keel.*` (A) vs `langgraph.exit.*` (B)

494 paired trials on (workload, variant, trigger, spec_hash, seed). Unpaired: 646 in A, 0 in B.

Rows through 2026-09-19T22:44:48+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_proxy` | 1957 | `251e52d` ×1957 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 30 | 150 |
| `duplicate_receipts` | 210 | 420 |
| `missing_required` | 0 | 0 |

## recovery_rate · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_return` (n=9) | 9/9 | 9/9 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `IDEMPOTENT·kill@after:tool_return` (n=5) | 5/5 | 5/5 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `EXTERNAL·kill@after:tool_return` (n=9) | 9/9 | 9/9 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `IDEMPOTENT·kill@after:tool_return` (n=5) | 5/5 | 5/5 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `EXTERNAL·kill@after:tool_return` (n=9) | 0/9 | 0/9 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `IDEMPOTENT·kill@after:tool_return` (n=5) | 0/5 | 0/5 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `EXTERNAL·kill@after:tool_effect` (n=30) | 2342.5 | 2391.3 | -59.9 | [-79.2, -40.0] | 0.005 | — | 52.65 | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_return` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 2358.5 | 2329.4 | 31.6 | [-4.0, 63.7] | 0.362 | — | 87.39 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 2415.7 | 3072.8 | -666.8 | [-688.0, -647.9] | 0.0000 | — | 52.70 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 40.0 | 2371.3 | -2331.5 | [-2360.9, -2297.4] | 0.0000 | — | 33.38 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 39.3 | 2406.0 | -2369.3 | [-2410.1, -2302.6] | 0.0000 | — | 40.87 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 42.7 | 2339.0 | -2302.1 | [-2373.6, -2264.6] | 0.0000 | — | 46.48 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 9.2 | 10.3 | -1.0 | [-6.6, 0.4] | 0.200 | — | 5.32 | not claimable (detection = harness for one arm) |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 2345.5 | 2389.0 | -58.4 | [-113.7, 1.7] | 0.099 | — | 67.63 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_return` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 2360.4 | 2382.1 | -25.3 | [-82.9, 77.7] | 0.585 | — | 82.45 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 2433.8 | 3062.1 | -635.6 | [-645.3, -615.6] | 0.0000 | — | 29.61 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 619.7 | 2394.3 | -1716.9 | [-1934.6, -1554.6] | 0.0000 | — | 171.73 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 520.6 | 2431.0 | -1902.4 | [-2136.3, -1695.0] | 0.0000 | — | 149.15 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 427.9 | 2690.2 | -2201.2 | [-2342.2, -2167.0] | 0.0000 | — | 151.24 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 9.0 | 9.4 | -0.7 | [-1.5, -0.2] | 0.043 | — | 5.51 | not claimable (detection = harness for one arm) |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·kill@after:tool_return` (n=9) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## extra_model_calls · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·kill@after:tool_return` (n=5) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·kill@after:tool_return` (n=9) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## extra_tokens · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·kill@after:tool_return` (n=5) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 2206.3 | 2320.8 | -135.8 | [-228.4, -42.8] | 0.016 | — | 148.85 | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@after:tool_return` (n=9) | 234.0 | 2204.0 | -1925.8 | [-2200.0, -1177.0] | 0.004 | — | 805.09 | not claimable (detection = harness for one arm) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 2323.0 | 2238.5 | 146.9 | [20.4, 223.4] | 0.099 | — | 112.46 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 3308.0 | 2910.6 | 397.5 | [278.6, 465.5] | 0.0000 | — | 85.21 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | -113.6 | 2210.9 | -2303.3 | [-2448.8, -2236.8] | 0.0000 | — | 93.57 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | -99.3 | 2261.5 | -2315.1 | [-2462.4, -2281.7] | 0.0000 | — | 102.44 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | -99.1 | 2225.6 | -2300.5 | [-2402.9, -2220.4] | 0.0000 | — | 94.76 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 888.4 | 7358.0 | -6475.4 | [-6580.0, -6351.4] | 0.0000 | — | 120.42 | not claimable (detection = harness for one arm) |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 2260.3 | 2356.9 | -94.9 | [-172.3, -0.1] | 0.099 | — | 122.14 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@after:tool_return` (n=5) | 250.5 | 1994.0 | -1798.0 | [-4899.6, 258.5] | 0.375 | — | 2462.63 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 2469.1 | 2310.6 | 217.1 | [85.6, 303.4] | 0.016 | — | 155.40 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3476.0 | 3017.8 | 503.3 | [370.6, 548.9] | 0.0000 | — | 92.34 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 702.7 | 2295.2 | -1622.0 | [-1754.3, -1496.5] | 0.0000 | — | 164.04 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 587.7 | 2377.0 | -1790.7 | [-1934.7, -1646.5] | 0.0000 | — | 181.95 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 522.9 | 2904.0 | -2434.8 | [-2538.3, -2268.6] | 0.0000 | — | 218.51 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 1576.4 | 7979.9 | -6285.4 | [-6586.8, -6094.4] | 0.0000 | — | 221.73 | not claimable (detection = harness for one arm) |

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
