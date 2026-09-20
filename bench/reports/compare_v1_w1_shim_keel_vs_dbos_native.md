# compare — `keel.*` (A) vs `dbos.native.*` (B)

1380 paired trials on (workload, variant, trigger, spec_hash, seed). Unpaired: 300 in A, 0 in B.

2 cell(s) ran at the confirmation tier (seeds ≥ 100,000) and are compared at that n only; their screening numbers are in the appendix. Holm runs over each family with mixed n — each p is valid at its own n, printed beside it (§15.3, §15.6).

Rows through 2026-09-19T22:44:10+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_shim` | 3079 | `251e52d` ×3079 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 4 | 350 |
| `duplicate_receipts` | 172 | 459 |
| `missing_required` | 0 | 0 |

## recovery_rate · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·after:tool_return` (n=300) | 300/300 | 298/300 | — | 2/0 | 0.500 | 1.000 | — | too noisy to claim (2 discordant pairs) |
| `EXTERNAL·baseline` (n=300) | 300/300 | 300/300 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `EXTERNAL·after:tool_return` (n=300) | 300/300 | 59/300 | 0.80 | 241/0 | 0.0000 | 0.0000 | 0.14 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=300) | 300/300 | 300/300 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 26/30 | 30/30 | — | 0/4 | 0.125 | 0.625 | — | too noisy to claim (4 discordant pairs) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
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
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## replay_divergence · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·after:tool_return` (n=300) | 0/300 | 239/300 | -0.80 | 0/239 | 0.0000 | 0.0000 | 0.14 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=300) | 0/300 | 0/300 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·model_500@before:model_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 4/30 | 0/30 | — | 4/0 | 0.125 | 0.875 | — | too noisy to claim (4 discordant pairs) |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## replay_divergence · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_latency_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 2334.6 | 3118.9 | -759.7 | [-822.6, -728.4] | 0.0000 | 0.0000 | 62.73 | B higher |
| `EXTERNAL·after:tool_return` (n=239) | 2334.3 | 3342.8 | -1045.7 | [-1118.6, -971.0] | 0.0000 | 0.0000 | 476.60 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 2349.0 | 3088.1 | -744.7 | [-838.2, -667.5] | 0.0000 | 0.0000 | 112.11 | B higher |
| `EXTERNAL·model_500@before:model_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 3834.4 | 2056.9 | 1769.2 | [1044.4, 2009.7] | 0.0000 | 0.0000 | 417.40 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 2438.5 | 3065.9 | -627.3 | [-651.7, -602.2] | 0.0000 | 0.0000 | 48.54 | B higher |
| `EXTERNAL·provider_outage@before:model_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·tool_500@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·tool_delay@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 26.4 | 26.1 | -0.2 | [-6.2, 1.1] | 1.000 | 1.000 | 9.29 | too noisy to claim |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 2339.8 | 3096.4 | -768.5 | [-806.7, -728.5] | 0.0000 | 0.0000 | 57.56 | B higher |
| `IDEMPOTENT·after:tool_return` (n=19) | 2352.8 | 3056.8 | -713.9 | [-769.2, -633.0] | 0.0000 | 0.0000 | 104.56 | B higher |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 2355.9 | 3026.4 | -683.9 | [-731.6, -623.6] | 0.0000 | 0.0000 | 54.03 | B higher |
| `IDEMPOTENT·model_500@before:model_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 3720.8 | 2062.9 | 1656.6 | [1560.1, 1944.2] | 0.0000 | 0.0000 | 334.02 | A higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 2447.9 | 3070.1 | -623.8 | [-703.4, -603.7] | 0.0000 | 0.0000 | 52.11 | B higher |
| `IDEMPOTENT·provider_outage@before:model_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 26.6 | 21.9 | 1.5 | [-10.0, 10.7] | 0.856 | 0.856 | 12.21 | too noisy to claim |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·after:tool_return` (n=300) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 0.500 | 1.000 | 0.01 | too noisy to claim |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·model_500@before:model_call` (n=30) | 1.0 | -2.0 | 3.0 | [3.0, 3.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 1.0 | 0.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 3.0 | -2.0 | 5.0 | [5.0, 5.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## extra_model_calls · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1.0 | -2.0 | 3.0 | [3.0, 3.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 1.0 | 0.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 3.0 | -2.0 | 5.0 | [5.0, 5.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | -1.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·after:tool_return` (n=300) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 0.500 | 1.000 | 1.34 | too noisy to claim |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·model_500@before:model_call` (n=30) | 31.0 | -151.0 | 182.0 | [182.0, 182.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 31.0 | 0.0 | 31.0 | [31.0, 31.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 93.0 | -151.0 | 244.0 | [244.0, 244.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## extra_tokens · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 31.0 | -151.0 | 182.0 | [182.0, 182.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 31.0 | 0.0 | 31.0 | [31.0, 31.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 93.0 | -151.0 | 244.0 | [244.0, 244.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 0.0 | -102.0 | 102.0 | [102.0, 102.0] | 0.0000 | 0.0000 | 0.00 | A higher |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 2832.2 | 3240.9 | -378.7 | [-500.0, -276.4] | 0.0003 | 0.0010 | 166.61 | B higher |
| `EXTERNAL·after:tool_return` (n=300) | 1770.5 | 3036.4 | -1394.8 | [-1572.1, -1292.7] | 0.0000 | 0.0000 | 1186.22 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 2757.7 | 3275.7 | -482.0 | [-680.6, -438.9] | 0.0000 | 0.0000 | 238.29 | B higher |
| `EXTERNAL·model_500@before:model_call` (n=30) | 2392.0 | 682.8 | 1066.3 | [622.2, 1925.3] | 0.0001 | 0.0002 | 617.17 | A higher |
| `EXTERNAL·model_timeout@before:model_call` (n=30) | 4260.3 | 2644.7 | 1650.7 | [616.3, 1841.8] | 0.0003 | 0.0010 | 478.42 | A higher |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 4387.5 | 3483.7 | 982.6 | [516.0, 1136.2] | 0.0000 | 0.0000 | 361.91 | A higher |
| `EXTERNAL·provider_outage@before:model_call` (n=30) | 8434.6 | 36.7 | 8412.9 | [6324.1, 9814.9] | 0.0000 | 0.0000 | 1573.31 | A higher |
| `EXTERNAL·sigterm_grace_ok@after:tool_effect` (n=30) | 4792.8 | 3222.4 | 1540.8 | [1400.9, 1602.1] | 0.0000 | 0.0000 | 202.41 | A higher |
| `EXTERNAL·sigterm_grace_too_short@after:tool_effect` (n=30) | 1716.5 | 3182.0 | -1457.8 | [-1526.4, -1328.7] | 0.0000 | 0.0000 | 197.89 | B higher |
| `EXTERNAL·tool_500@after:tool_effect` (n=30) | 228.5 | 158.4 | 19.5 | [-51.4, 100.5] | 0.362 | 0.362 | 140.63 | too noisy to claim |
| `EXTERNAL·tool_delay@after:tool_effect` (n=30) | 1180.3 | 2243.9 | -1055.6 | [-1150.0, -984.4] | 0.0000 | 0.0000 | 106.70 | B higher |
| `EXTERNAL·tool_timeout@before:tool_call` (n=30) | 1165.7 | 5219.2 | -4030.0 | [-4174.6, -3904.9] | 0.0000 | 0.0000 | 138.75 | B higher |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 2509.9 | 3284.8 | -780.2 | [-893.5, -578.4] | 0.0000 | 0.0000 | 157.84 | B higher |
| `IDEMPOTENT·after:tool_return` (n=30) | 2493.9 | 3130.7 | -624.2 | [-737.2, -536.6] | 0.0000 | 0.0000 | 154.71 | B higher |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 2546.5 | 3149.7 | -623.8 | [-801.6, -427.3] | 0.0000 | 0.0000 | 135.56 | B higher |
| `IDEMPOTENT·model_500@before:model_call` (n=30) | 1851.0 | -44.5 | 1948.9 | [1123.6, 2208.1] | 0.0000 | 0.0000 | 428.02 | A higher |
| `IDEMPOTENT·model_timeout@before:model_call` (n=30) | 3888.2 | 2149.5 | 1801.6 | [1268.9, 2022.7] | 0.0000 | 0.0000 | 359.34 | A higher |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3680.5 | 3207.8 | 493.8 | [387.2, 635.9] | 0.0000 | 0.0000 | 126.78 | A higher |
| `IDEMPOTENT·provider_outage@before:model_call` (n=30) | 8026.3 | -53.0 | 7974.4 | [7062.8, 9363.5] | 0.0000 | 0.0000 | 1194.06 | A higher |
| `IDEMPOTENT·sigterm_grace_ok@after:tool_effect` (n=30) | 4424.5 | 3228.0 | 1189.9 | [1108.3, 1380.6] | 0.0000 | 0.0000 | 214.35 | A higher |
| `IDEMPOTENT·sigterm_grace_too_short@after:tool_effect` (n=30) | 1571.6 | 3116.2 | -1566.7 | [-1707.9, -1451.4] | 0.0000 | 0.0000 | 157.68 | B higher |
| `IDEMPOTENT·tool_500@after:tool_effect` (n=30) | 709.2 | 133.9 | 647.2 | [426.3, 784.9] | 0.0000 | 0.0000 | 194.14 | A higher |
| `IDEMPOTENT·tool_delay@after:tool_effect` (n=30) | 1800.2 | 2152.9 | -357.2 | [-408.4, -221.1] | 0.0000 | 0.0000 | 150.83 | B higher |
| `IDEMPOTENT·tool_timeout@before:tool_call` (n=30) | 1665.2 | 5105.1 | -3411.1 | [-3598.8, -3120.6] | 0.0000 | 0.0000 | 190.58 | B higher |

## Appendix — the screening tier of the confirmed cells (§15.3)

### recovery_rate · tool_chain_1_effect · EXTERNAL · screening

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

### logical_correctness · tool_chain_1_effect · EXTERNAL · screening

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=30) | 30/30 | 9/30 | 0.70 | 21/0 | 0.0000 | 0.0000 | 0.43 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

### replay_divergence · tool_chain_1_effect · EXTERNAL · screening

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=30) | 0/30 | 21/30 | -0.70 | 0/21 | 0.0000 | 0.0000 | 0.43 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

### recovery_latency_ms · tool_chain_1_effect · EXTERNAL · screening

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=21) | 2375.0 | 3039.4 | -665.1 | [-709.1, -633.8] | 0.0000 | 0.0000 | 59.20 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |

### extra_model_calls · tool_chain_1_effect · EXTERNAL · screening

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |

### extra_tokens · tool_chain_1_effect · EXTERNAL · screening

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |

### wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL · screening

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_return` (n=30) | 2704.7 | 3143.3 | -467.0 | [-547.6, -341.0] | 0.0000 | 0.0001 | 160.85 | B higher |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |

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
