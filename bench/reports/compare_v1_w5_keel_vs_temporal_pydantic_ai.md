# compare — `keel.*` (A) vs `temporal.pydantic_ai.*` (B)

150 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-18T18:56:41+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w5` | 300 | `251e52d` ×300 |

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
| `GATED·approval_expiry@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill@after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·kill_while_waiting@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## logical_correctness · approval_gated_deploy · GATED

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `GATED·approval_expiry@supervisor` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
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
| `GATED·approval_delay@supervisor` (n=30) | 211.1 | 189.2 | 18.5 | [3.4, 25.8] | 0.005 | 0.005 | 31.18 | too noisy to claim (|Δ| below MDD 31.2 at n=30) |
| `GATED·approval_expiry@supervisor` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill@after:tool_effect` (n=30) | 2393.4 | 4071.7 | -1678.5 | [-2006.6, -1593.9] | 0.0000 | 0.0000 | 183.74 | B higher |
| `GATED·kill_while_waiting@supervisor` (n=30) | 1598.8 | 4958.6 | -3356.1 | [-3468.6, -3060.8] | 0.0000 | 0.0000 | 216.30 | B higher |

## extra_model_calls · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·approval_expiry@supervisor` (n=30) | -1.0 | -1.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_tokens · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·approval_expiry@supervisor` (n=30) | -158.0 | -773.0 | 615.0 | [615.0, 615.0] | 0.0000 | 0.0000 | 0.00 | A higher |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill@after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `GATED·kill_while_waiting@supervisor` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## wall_clock_overhead_ms · approval_gated_deploy · GATED

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `GATED·approval_delay@supervisor` (n=30) | 444.1 | 244.9 | 229.6 | [-6.9, 676.4] | 0.200 | 0.200 | 441.47 | too noisy to claim |
| `GATED·approval_expiry@supervisor` (n=30) | 4892.7 | 4169.6 | 720.9 | [428.1, 923.3] | 0.0003 | 0.0006 | 441.24 | A higher |
| `GATED·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `GATED·kill@after:tool_effect` (n=30) | 2405.8 | 6694.3 | -4297.6 | [-5152.3, -3972.4] | 0.0000 | 0.0000 | 590.78 | B higher |
| `GATED·kill_while_waiting@supervisor` (n=30) | 1323.4 | 5380.7 | -4003.1 | [-4531.8, -3433.5] | 0.0000 | 0.0000 | 507.11 | B higher |

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
