# compare — `keel.*` (A) vs `dbos.native.*` (B)

540 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-19T13:17:08+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_proxy` | 1084 | `251e52d` ×1084 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 30 | 30 |
| `duplicate_receipts` | 210 | 60 |
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
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## replay_divergence · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·kill@after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | B better (p=0.0000) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

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
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 2342.5 | 3398.6 | -1066.0 | [-1115.5, -993.2] | 0.0000 | 0.0000 | 69.78 | B higher |
| `EXTERNAL·kill@after:tool_return` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@before:tool_call` (n=30) | 2358.5 | 3442.9 | -1059.8 | [-1134.5, -977.1] | 0.0000 | 0.0000 | 102.82 | B higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 2415.7 | 3068.7 | -661.1 | [-673.8, -639.4] | 0.0000 | 0.0000 | 57.65 | B higher |
| `EXTERNAL·tool_500@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 9.2 | 10.1 | -0.6 | [-1.4, 0.0] | 0.099 | 0.099 | 4.29 | too noisy to claim |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 2345.5 | 3293.7 | -932.1 | [-957.6, -885.7] | 0.0000 | 0.0000 | 73.58 | B higher |
| `IDEMPOTENT·kill@after:tool_return` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 2360.4 | 3312.9 | -905.3 | [-975.1, -862.4] | 0.0000 | 0.0000 | 100.80 | B higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 2433.8 | 3077.5 | -646.5 | [-661.0, -630.2] | 0.0000 | 0.0000 | 33.30 | B higher |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 9.0 | 10.0 | -1.4 | [-3.2, 0.2] | 0.200 | 0.200 | 5.74 | too noisy to claim |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## extra_model_calls · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## extra_tokens · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·kill@after:tool_effect` (n=30) | 2206.3 | 3629.4 | -1365.8 | [-1438.4, -1323.0] | 0.0000 | 0.0000 | 118.62 | B higher |
| `EXTERNAL·kill@after:tool_return` (n=30) | 279.4 | 569.4 | -336.8 | [-381.7, -230.1] | 0.0000 | 0.0000 | 115.87 | B higher |
| `EXTERNAL·kill@before:tool_call` (n=30) | 2323.0 | 3647.3 | -1312.3 | [-1386.6, -1176.4] | 0.0000 | 0.0000 | 119.18 | B higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 3308.0 | 3328.0 | -20.2 | [-116.8, 45.4] | 0.585 | 0.585 | 74.93 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | -113.6 | 148.1 | -248.3 | [-334.6, -181.8] | 0.0000 | 0.0000 | 74.74 | B higher |
| `EXTERNAL·tool_dropped_response@after:tool_effect` (n=30) | -99.3 | 138.1 | -232.4 | [-280.6, -183.9] | 0.0000 | 0.0000 | 63.14 | B higher |
| `EXTERNAL·tool_malformed@after:tool_effect` (n=30) | -99.1 | 146.0 | -254.6 | [-326.2, -207.2] | 0.0000 | 0.0000 | 84.19 | B higher |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 888.4 | 5053.8 | -4169.9 | [-4228.3, -4124.3] | 0.0000 | 0.0000 | 72.58 | B higher |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·kill@after:tool_effect` (n=30) | 2260.3 | 3392.2 | -1090.6 | [-1207.5, -1050.5] | 0.0000 | 0.0000 | 115.47 | B higher |
| `IDEMPOTENT·kill@after:tool_return` (n=30) | 303.7 | 446.7 | -182.3 | [-222.9, -26.7] | 0.016 | 0.016 | 107.99 | B higher |
| `IDEMPOTENT·kill@before:tool_call` (n=30) | 2469.1 | 3329.3 | -890.4 | [-941.2, -806.0] | 0.0000 | 0.0000 | 171.40 | B higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3476.0 | 3209.3 | 297.0 | [157.8, 430.4] | 0.0000 | 0.0000 | 114.83 | A higher |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 702.7 | 155.9 | 479.7 | [353.5, 730.2] | 0.0000 | 0.0000 | 165.59 | A higher |
| `IDEMPOTENT·tool_dropped_response@after:tool_effect` (n=30) | 587.7 | 159.4 | 477.5 | [232.4, 547.8] | 0.0003 | 0.0006 | 180.84 | A higher |
| `IDEMPOTENT·tool_malformed@after:tool_effect` (n=30) | 522.9 | 145.7 | 292.3 | [176.6, 470.9] | 0.0000 | 0.0000 | 151.99 | A higher |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 1576.4 | 5091.3 | -3454.8 | [-3656.4, -3287.1] | 0.0000 | 0.0000 | 160.05 | B higher |

A safety observation is a count of what happened, so it carries no p-value: whether a runtime filed the issue twice is not a sample from a population. The estimates above it are, and every one of them is made per `(location, fault)` cell — averaging a kill at `after:tool_effect` together with a `pause_past_ttl` answers neither question. Holm runs across the cells of one metric table and nowhere else (§15.6). Every row with a p-value counts toward `m` and prints its adjusted p, including rows rules 1–4 already disqualified; only rows confounded by `detection = harness` are out.

Two departures from §15.5, named: binary rows use McNemar's exact test at every discordant count (§15.5 names the continuity-corrected χ² from b + c ≥ 25), and they print no Wilson interval on b/(b + c) — the discordant counts and δ are printed instead.

`too noisy to claim` is a real answer — at thirty seeds it is the most common honest one, and the failing rule is named beside it. The point estimate, the interval and the adjusted p stay on the page whatever the verdict: a rule that fails takes away the verb, never the numbers.

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
