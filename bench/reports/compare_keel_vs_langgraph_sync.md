# compare — `keel.*` (A) vs `langgraph.sync.*` (B)

300 paired trials on (workload, variant, trigger, spec_hash, seed).

Rows through 2026-09-10T23:45:17+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/matrix_v0` | 600 | `198b456` ×240, `cf7fff6` ×240, `7c4c2be` ×60, `cefd652` ×60 |

## Safety — counted, never estimated

| observation | A | B |
|---|---|---|
| `duplicate_effects` | 11 | 60 |
| `duplicate_receipts` | 81 | 120 |
| `missing_required` | 0 | 0 |

## recovery_rate · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_rate · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## logical_correctness · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·after:tool_return` (n=30) | 30/30 | 0/30 | 1.00 | 30/0 | 0.0000 | 0.0000 | 0.51 | A better (p=0.0000) |
| `EXTERNAL·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 19/30 | 30/30 | -0.37 | 0/11 | 0.0010 | 0.003 | 0.31 | B better (p=0.0010) |

## logical_correctness · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 30/30 | 30/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## replay_divergence · tool_chain_1_effect · EXTERNAL

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## replay_divergence · tool_chain_1_effect · IDEMPOTENT

| cell | A | B | δ | discord (A/B) | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·after:tool_return` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·baseline` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0/30 | 0/30 | — | 0/0 | 1.000 | 1.000 | — | too noisy to claim (0 discordant pairs) |

## recovery_latency_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 3113.7 | 2148.5 | 928.1 | [140.7, 1012.5] | 0.0000 | — | 246.66 | not claimable (detection = harness for one arm) |
| `EXTERNAL·after:tool_return` (n=30) | 2289.2 | 2161.9 | 182.6 | [66.5, 943.6] | 0.0001 | — | 244.07 | not claimable (detection = harness for one arm) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·before:tool_call` (n=30) | 3124.4 | 2145.5 | 937.6 | [514.5, 989.7] | 0.0000 | — | 238.56 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 2642.4 | 3071.3 | -431.1 | [-580.6, -409.9] | 0.0000 | — | 57.22 | not claimable (detection = harness for one arm) |

## recovery_latency_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 3136.7 | 2153.0 | 964.3 | [910.7, 999.6] | 0.0000 | — | 207.40 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·after:tool_return` (n=30) | 3146.7 | 2187.5 | 905.1 | [148.3, 974.6] | 0.0001 | — | 238.27 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·before:tool_call` (n=30) | 3169.5 | 2144.8 | 1019.8 | [974.2, 1051.1] | 0.0000 | — | 186.09 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 2656.9 | 3065.6 | -422.0 | [-587.0, -392.2] | 0.0000 | — | 57.38 | not claimable (detection = harness for one arm) |

## extra_model_calls · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_model_calls · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·after:tool_return` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 0.0 | 0.0 | 0.0 | [0.0, 0.0] | 1.000 | 1.000 | 0.00 | too noisy to claim |

## extra_tokens · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·after:tool_return` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·before:tool_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |

## extra_tokens · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·after:tool_return` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·before:tool_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=0) | — | — | — | — | — | — | — | too noisy to claim (0 paired observations) |

## wall_clock_overhead_ms · tool_chain_1_effect · EXTERNAL

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `EXTERNAL·after:tool_effect` (n=30) | 3109.0 | 2033.1 | 880.1 | [310.1, 1096.7] | 0.0000 | — | 250.51 | not claimable (detection = harness for one arm) |
| `EXTERNAL·after:tool_return` (n=30) | 2364.1 | 2105.9 | 414.8 | [196.0, 962.3] | 0.0000 | — | 259.16 | not claimable (detection = harness for one arm) |
| `EXTERNAL·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `EXTERNAL·before:tool_call` (n=30) | 3142.9 | 2083.3 | 998.8 | [581.1, 1137.2] | 0.0000 | — | 276.75 | not claimable (detection = harness for one arm) |
| `EXTERNAL·pause_past_ttl@before:tool_call` (n=30) | 3410.1 | 2978.7 | 403.4 | [346.0, 463.0] | 0.0000 | — | 80.46 | not claimable (detection = harness for one arm) |

## wall_clock_overhead_ms · tool_chain_1_effect · IDEMPOTENT

| cell | A median | B median | Δ | 95% CI | p | Holm p | MDD | verdict |
|---|---|---|---|---|---|---|---|---|
| `IDEMPOTENT·after:tool_effect` (n=30) | 3128.5 | 1552.2 | 1604.9 | [1285.4, 1816.6] | 0.0000 | — | 531.33 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·after:tool_return` (n=30) | 3134.0 | 1577.8 | 1344.8 | [1073.3, 1683.6] | 0.0000 | — | 495.89 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·baseline` (n=0) | — | — | — | — | — | — | — | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·before:tool_call` (n=30) | 3160.3 | 1543.0 | 1508.7 | [1278.4, 1803.0] | 0.0000 | — | 545.51 | not claimable (detection = harness for one arm) |
| `IDEMPOTENT·pause_past_ttl@before:tool_call` (n=30) | 3435.7 | 2470.0 | 930.3 | [801.3, 1137.4] | 0.0000 | — | 499.29 | not claimable (detection = harness for one arm) |

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
