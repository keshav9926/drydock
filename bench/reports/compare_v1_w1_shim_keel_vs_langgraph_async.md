# compare — `keel.*` (A) vs `langgraph.async.*` (B)

780 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-19T08:46:48+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_shim` | 1560 | `251e52d` ×1560 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 4 | 180 |
| `duplicate_receipts` | 172 | 660 |
| `missing_required` | 0 | 0 |

## recovery_rate · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_rate · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## logical_correctness · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·after:tool_return` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 26/30 | 30/30 | — | 0/4 | 0.125 | 0.875 | — | too noisy to claim (4 discordant pairs) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## logical_correctness · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## replay_divergence · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·after:tool_return` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 4/30 | 0/30 | — | 4/0 | 0.125 | 0.875 | — | too noisy to claim (4 discordant pairs) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## replay_divergence · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_latency_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 2334.6 | 2588.6 | -238.3 | [-343.5, -166.4] | 0.0000 | — | 108.60 | not claimable (detection = harness for one arm) |
| `EXTERNAL·after:tool_return` (n=30) | 2375.0 | 2503.4 | -182.2 | [-274.2, -86.2] | 0.001 | — | 110.06 | not claimable (detection = harness for one arm) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·before:tool_call` (n=30) | 2349.0 | 2520.9 | -161.3 | [-250.6, -77.1] | 0.0001 | — | 89.83 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 1615.7 | 2956.3 | -1325.8 | [-1920.9, -1112.6] | 0.0000 | — | 392.01 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 3834.4 | 2032.8 | 1792.0 | [1060.9, 2050.8] | 0.0000 | — | 419.61 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 2438.5 | 3051.6 | -610.2 | [-653.1, -589.7] | 0.0000 | — | 50.09 | not claimable (detection = harness for one arm) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 7749.5 | 7725.1 | 29.2 | [-2061.0, 1850.9] | 1.000 | — | 1583.92 | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 31.3 | 3142.7 | -3109.0 | [-3203.7, -3000.5] | 0.0000 | — | 134.24 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 26.4 | 24.8 | 2.4 | [-9.3, 10.1] | 0.200 | — | 10.70 | not claimable (detection = harness for one arm) |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 2339.8 | 2120.1 | 213.5 | [183.6, 262.9] | 0.0000 | — | 48.40 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·after:tool_return` (n=30) | 2352.8 | 2195.6 | 157.8 | [110.5, 200.3] | 0.0001 | — | 59.09 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·before:tool_call` (n=30) | 2355.9 | 2125.5 | 230.3 | [191.3, 252.4] | 0.0000 | — | 66.40 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1724.1 | 2580.1 | -989.0 | [-1551.3, -638.7] | 0.0000 | — | 370.87 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 3720.8 | 2034.0 | 1686.6 | [1576.6, 1969.6] | 0.0000 | — | 333.57 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 2447.9 | 3065.1 | -624.9 | [-704.7, -599.9] | 0.0000 | — | 53.35 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 7963.9 | 8214.1 | -267.0 | [-1461.1, 746.4] | 0.362 | — | 1219.49 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 631.8 | 3666.3 | -3118.2 | [-3456.6, -2760.2] | 0.0000 | — | 481.72 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 26.6 | 33.7 | -7.5 | [-15.6, 0.8] | 0.200 | — | 10.35 | not claimable (detection = harness for one arm) |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.09 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.09 | B higher |
| `EXTERNAL·model_500@before:model_call` (n=30) | 1.0 | 1.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 1.0 | 0.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 3.0 | 3.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.13 | B higher |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.13 | B higher |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_model_calls · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·after:tool_return` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1.0 | 1.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 1.0 | 0.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 3.0 | 3.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.56 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.56 | B higher |
| `EXTERNAL·model_500@before:model_call` (n=30) | 31.0 | 6.0 | 25.0 | [25.0, 25.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 31.0 | 0.0 | 31.0 | [31.0, 31.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 93.0 | 18.0 | 75.0 | [75.0, 75.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.78 | B higher |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.78 | B higher |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_tokens · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·after:tool_return` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 31.0 | 6.0 | 25.0 | [25.0, 25.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 31.0 | 0.0 | 31.0 | [31.0, 31.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 93.0 | 18.0 | 75.0 | [75.0, 75.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 2832.2 | 2694.4 | 123.3 | [-2.0, 366.8] | 0.099 | — | 175.34 | not claimable (detection = harness for one arm) |
| `EXTERNAL·after:tool_return` (n=30) | 2704.7 | 2607.3 | 143.8 | [-97.0, 358.2] | 0.362 | — | 219.29 | not claimable (detection = harness for one arm) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·before:tool_call` (n=30) | 2757.7 | 2472.7 | 302.8 | [95.8, 579.8] | 0.0000 | — | 196.40 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 2392.0 | 2938.1 | -731.0 | [-1170.7, -403.1] | 0.0001 | — | 487.42 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 4260.3 | 1651.9 | 2498.6 | [1745.9, 2815.8] | 0.0000 | — | 455.21 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 4387.5 | 2720.8 | 1575.6 | [1388.2, 1858.9] | 0.0000 | — | 347.58 | not claimable (detection = harness for one arm) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 8434.6 | 7312.2 | 1071.2 | [-780.4, 2823.2] | 0.362 | — | 1612.92 | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 4792.8 | 2360.7 | 2325.3 | [2235.7, 2671.8] | 0.0000 | — | 327.60 | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 1716.5 | 2440.7 | -735.0 | [-892.0, -516.7] | 0.0000 | — | 213.99 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 228.5 | 2658.1 | -2438.3 | [-2693.2, -2347.5] | 0.0000 | — | 244.45 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 1180.3 | 1470.1 | -336.1 | [-425.9, -262.2] | 0.0000 | — | 156.47 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 1165.7 | 7926.4 | -6929.1 | [-7218.8, -6523.0] | 0.0000 | — | 349.34 | not claimable (detection = harness for one arm) |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 2509.9 | 1761.4 | 745.5 | [595.0, 834.0] | 0.0000 | — | 181.39 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·after:tool_return` (n=30) | 2493.9 | 1925.2 | 577.6 | [480.4, 646.4] | 0.0000 | — | 3291.57 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·before:tool_call` (n=30) | 2546.5 | 1737.9 | 783.6 | [631.9, 834.5] | 0.0000 | — | 267.99 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1851.0 | 2220.5 | -382.0 | [-797.8, -77.4] | 0.043 | — | 439.12 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 3888.2 | 1770.8 | 2250.6 | [1680.7, 2431.9] | 0.0000 | — | 356.54 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3680.5 | 2983.4 | 719.6 | [609.2, 757.1] | 0.0000 | — | 188.38 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 8026.3 | 8141.4 | 333.8 | [-1417.6, 1271.7] | 0.856 | — | 1238.91 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 4424.5 | 1999.4 | 2468.1 | [2304.6, 2573.2] | 0.0000 | — | 158.09 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 1571.6 | 2053.7 | -473.5 | [-575.9, -262.4] | 0.0000 | — | 215.10 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 709.2 | 3867.9 | -3075.9 | [-3625.0, -2737.8] | 0.0000 | — | 666.75 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 1800.2 | 1925.4 | -169.4 | [-351.3, 5.5] | 0.099 | — | 276.76 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 1665.2 | 7368.2 | -5844.9 | [-6043.3, -5649.5] | 0.0000 | — | 302.06 | not claimable (detection = harness for one arm) |

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
