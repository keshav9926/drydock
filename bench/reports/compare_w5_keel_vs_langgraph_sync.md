# compare — `keel.*` (A) vs `langgraph.sync.*` (B)

150 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-15T16:50:45+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/w5` | 300 | `ad87b71` ×300 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 0 | 30 |
| `duplicate_receipts` | 0 | 30 |
| `missing_required` | 0 | 0 |

## recovery_rate · approval_gated_deploy · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·approval_expiry@supervisor` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `GATED·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## logical_correctness · approval_gated_deploy · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·approval_expiry@supervisor` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `GATED·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill@after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## replay_divergence · approval_gated_deploy · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·approval_expiry@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill@after:tool_effect` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_latency_ms · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 223.3 | 162.2 | 57.2 | [41.5, 73.9] | 0.0001 | — | 21.65 | not claimable (detection = harness for one arm) |
| `GATED·approval_expiry@supervisor` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `GATED·kill@after:tool_effect` (n=30) | 2263.4 | 1986.7 | 325.0 | [243.7, 369.8] | 0.0000 | — | 61.43 | not claimable (detection = harness for one arm) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 1588.0 | 2553.0 | -931.3 | [-1003.9, -896.9] | 0.0000 | — | 38.67 | not claimable (detection = harness for one arm) |

## extra_model_calls · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·approval_expiry@supervisor` (n=30) | -1.0 | -2.0 | 1.0 | [1.0, 1.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## extra_tokens · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·approval_expiry@supervisor` (n=30) | -158.0 | -155.0 | -3.0 | [-3.0, -3.0] | 0.0000 | 0.0000 | 0.00 | B higher |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0.0 | 54.0 | -54.0 | [-54.0, -54.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## wall_clock_overhead_ms · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 579.4 | 558.7 | 22.3 | [-75.9, 229.6] | 1.000 | — | 128.53 | not claimable (detection = harness for one arm) |
| `GATED·approval_expiry@supervisor` (n=30) | 5035.5 | 57205.0 | -52130.5 | [-52282.9, -52010.0] | 0.0000 | — | 662.75 | not claimable (detection = harness for one arm) |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `GATED·kill@after:tool_effect` (n=30) | 2399.5 | 1941.6 | 467.2 | [366.8, 579.0] | 0.0001 | — | 148.44 | not claimable (detection = harness for one arm) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 1404.2 | 2320.3 | -932.6 | [-1096.4, -750.0] | 0.0000 | — | 143.67 | not claimable (detection = harness for one arm) |

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
