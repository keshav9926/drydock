# compare — `keel.*` (A) vs `langgraph.exit.*` (B)

780 paired trials on (workload, variant, trigger, spec_hash, seed). Unpaired: 900 in A, 0 in B.

Rows through 2026-09-19T22:44:10+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_shim` | 2477 | `251e52d` ×2477 |

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
| `EXTERNAL·after:tool_effect` (n=30) | 2334.6 | 2203.0 | 127.1 | [80.5, 180.8] | 0.0000 | — | 67.90 | not claimable (detection = harness for one arm) |
| `EXTERNAL·after:tool_return` (n=30) | 2375.0 | 2181.5 | 170.3 | [141.7, 193.2] | 0.0001 | — | 57.82 | not claimable (detection = harness for one arm) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·before:tool_call` (n=30) | 2349.0 | 2161.9 | 186.1 | [159.0, 217.7] | 0.0000 | — | 49.99 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 1615.7 | 2485.0 | -852.1 | [-1597.9, -582.3] | 0.0000 | — | 430.01 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 3834.4 | 2035.7 | 1796.9 | [1059.5, 2039.5] | 0.0000 | — | 419.13 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 2438.5 | 3057.9 | -625.4 | [-639.4, -599.7] | 0.0000 | — | 44.56 | not claimable (detection = harness for one arm) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 7749.5 | 7597.5 | 88.6 | [-1735.8, 1819.4] | 1.000 | — | 1543.11 | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 31.3 | 2596.8 | -2574.0 | [-2601.4, -2529.5] | 0.0000 | — | 48.43 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 26.4 | 33.4 | 0.4 | [-9.7, 3.2] | 1.000 | — | 10.26 | not claimable (detection = harness for one arm) |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 2339.8 | 2197.5 | 153.3 | [123.7, 209.1] | 0.0003 | — | 94.77 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·after:tool_return` (n=30) | 2352.8 | 2182.6 | 173.4 | [123.3, 211.9] | 0.0000 | — | 58.41 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·before:tool_call` (n=30) | 2355.9 | 2177.0 | 181.4 | [142.0, 238.4] | 0.0000 | — | 68.54 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1724.1 | 2546.9 | -834.3 | [-1538.1, -554.1] | 0.0000 | — | 383.02 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 3720.8 | 2036.8 | 1687.3 | [1597.1, 1978.9] | 0.0000 | — | 336.73 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 2447.9 | 3065.3 | -615.9 | [-701.2, -607.4] | 0.0000 | — | 52.03 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 7963.9 | 7688.6 | 182.2 | [-894.7, 1465.1] | 0.585 | — | 1192.76 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 631.8 | 2695.2 | -2307.7 | [-2470.5, -2066.1] | 0.0000 | — | 871.97 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 26.6 | 39.0 | -7.1 | [-19.2, 1.9] | 0.362 | — | 11.27 | not claimable (detection = harness for one arm) |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·model_500@before:model_call` (n=30) | 1.0 | 1.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 1.0 | 0.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 3.0 | 3.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 2.0 | -2.0 | [-2.0, -2.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |

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
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·model_500@before:model_call` (n=30) | 31.0 | 6.0 | 25.0 | [25.0, 25.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 31.0 | 0.0 | 31.0 | [31.0, 31.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 93.0 | 18.0 | 75.0 | [75.0, 75.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 58.0 | -58.0 | [-58.0, -58.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |

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
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | 103.0 | -103.0 | [-103.0, -103.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 2832.2 | 2104.1 | 754.4 | [655.5, 1060.0] | 0.0000 | — | 197.17 | not claimable (detection = harness for one arm) |
| `EXTERNAL·after:tool_return` (n=30) | 2704.7 | 2145.2 | 601.0 | [451.2, 741.0] | 0.0000 | — | 177.79 | not claimable (detection = harness for one arm) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·before:tool_call` (n=30) | 2757.7 | 2025.2 | 781.2 | [641.7, 951.3] | 0.0000 | — | 184.50 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 2392.0 | 2326.2 | -87.5 | [-814.4, 285.5] | 0.585 | — | 468.65 | not claimable (detection = harness for one arm) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 4260.3 | 1906.5 | 2251.1 | [1513.3, 2504.2] | 0.0000 | — | 468.74 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 4387.5 | 2928.1 | 1490.9 | [1185.7, 1824.6] | 0.0000 | — | 342.87 | not claimable (detection = harness for one arm) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 8434.6 | 7393.4 | 1085.1 | [-692.0, 2731.8] | 0.585 | — | 1534.79 | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 4792.8 | 2074.8 | 2700.1 | [2535.7, 2932.0] | 0.0000 | — | 207.84 | not claimable (detection = harness for one arm) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 1716.5 | 2078.6 | -362.3 | [-468.0, -184.6] | 0.0003 | — | 198.85 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 228.5 | 2476.7 | -2327.6 | [-2432.3, -2121.7] | 0.0000 | — | 157.63 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 1180.3 | 1930.6 | -751.5 | [-860.9, -649.8] | 0.0000 | — | 166.27 | not claimable (detection = harness for one arm) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 1165.7 | 7814.6 | -6689.1 | [-6780.3, -6514.0] | 0.0000 | — | 170.93 | not claimable (detection = harness for one arm) |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 2509.9 | 2050.0 | 449.6 | [334.7, 572.9] | 0.0000 | — | 154.93 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·after:tool_return` (n=30) | 2493.9 | 2080.3 | 468.4 | [334.1, 567.8] | 0.0000 | — | 118.01 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·before:tool_call` (n=30) | 2546.5 | 2051.1 | 452.6 | [391.0, 533.8] | 0.0000 | — | 157.90 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1851.0 | 2364.6 | -626.8 | [-1130.6, -266.2] | 0.005 | — | 429.10 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 3888.2 | 1868.2 | 2077.9 | [1878.3, 2399.8] | 0.0000 | — | 375.52 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3680.5 | 2939.0 | 736.9 | [642.9, 871.1] | 0.0000 | — | 119.19 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 8026.3 | 7450.8 | 280.9 | [-346.9, 1993.0] | 0.585 | — | 1203.67 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 4424.5 | 2146.1 | 2384.1 | [2223.9, 2482.3] | 0.0000 | — | 191.73 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 1571.6 | 2014.4 | -450.2 | [-605.4, -372.3] | 0.0000 | — | 207.21 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 709.2 | 2643.9 | -2212.9 | [-2450.5, -1706.7] | 0.0000 | — | 1094.84 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 1800.2 | 1995.4 | -256.5 | [-486.3, -129.1] | 0.005 | — | 286.75 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 1665.2 | 8004.4 | -6310.1 | [-6504.8, -6086.6] | 0.0000 | — | 255.58 | not claimable (detection = harness for one arm) |

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
