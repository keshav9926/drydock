# compare — `keel.*` (A) vs `langgraph.sync.*` (B)

90 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-15T17:08:50+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/w5_pre` | 180 | `a787cbe` ×180 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 0 | 120 |
| `duplicate_receipts` | 0 | 120 |
| `missing_required` | 0 | 0 |

## recovery_rate · approval_gated_deploy_pre · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## logical_correctness · approval_gated_deploy_pre · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `GATED·baseline` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## replay_divergence · approval_gated_deploy_pre · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0/30 | 30/30 | -1.00 | 0/30 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |

## recovery_latency_ms · approval_gated_deploy_pre · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 223.9 | 90.7 | 129.5 | [115.3, 155.5] | 0.0000 | — | 20.78 | not claimable (detection = harness for one arm) |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 1589.0 | 2367.2 | -774.9 | [-812.2, -755.9] | 0.0000 | — | 33.79 | not claimable (detection = harness for one arm) |

## extra_model_calls · approval_gated_deploy_pre · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0.0 | 1.0 | -1.0 | [-1.0, -1.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## extra_tokens · approval_gated_deploy_pre · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0.0 | 54.0 | -54.0 | [-54.0, -54.0] | 0.0000 | 0.0000 | 0.00 | B higher |

## wall_clock_overhead_ms · approval_gated_deploy_pre · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 494.5 | 551.3 | -60.1 | [-118.8, 13.9] | 0.099 | — | 88.18 | not claimable (detection = harness for one arm) |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 1308.8 | 2385.8 | -1107.1 | [-1122.4, -986.1] | 0.0000 | — | 84.97 | not claimable (detection = harness for one arm) |

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
