# Proxy / shim agreement — `matrix_v0+tier1a` vs `tier1p`

The same cells, measured from inside the SUT (`shim`) and from the network edge (`proxy`),
paired on `(cell, seed)` and folded over the seeds both ran. §29.1's agreement column: a
cell where the two instruments agree on every safety verdict and every raw count is a
window that is real and not an artefact of where the instrument sat; a cell where they
differ is a finding about the instrument, printed with both numbers.

No p-values. Agreement is a check on the harness, not a hypothesis about runtimes. A twin
whose two sides ran at different commits or under different config pins is printed with
what differs and left out of the tally: its difference may be the runtime, not the instrument.
`n` is the seeds both sides ran; seeds only one side ran are counted beside it and folded
into neither.

Rows through 2026-09-15T15:14:33+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/matrix_v0` | 1200 | `cf7fff6` ×540, `7c4c2be` ×360, `198b456` ×240, `cefd652` ×60 |
| `bench/results/tier1a` | 960 | `e0d94e7` ×960 |
| `bench/results/tier1p` | 1080 | `8ee372d` ×848, `77488a2` ×154, `426b7df` ×78 |

| cell | n | safety (shim) | safety (proxy) | dup_eff | dup_rcpt | recovery | latency | agree |
|---|---|---|---|---|---|---|---|---|
| `keel.default.EXTERNAL.baseline` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | not comparable: pins differ — keel_commit e0d94e7 / 77488a2 |
| `keel.default.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 2.3s | not comparable: pins differ — keel_commit 198b456 / 77488a2; claim_poll_s null / 0.2; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; reaper_period_s null / 0.2; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.3s / — | not comparable: pins differ — keel_commit 198b456 / 426b7df,77488a2; claim_poll_s null / 0.2; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; reaper_period_s null / 0.2; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 2.3s | not comparable: pins differ — keel_commit 198b456 / 426b7df; claim_poll_s null / 0.2; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; reaper_period_s null / 0.2; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 11 / 30 | 11 / 30 | 30/30 / 30/30 | 2.6s / 1.0s | not comparable: pins differ — keel_commit cefd652 / 426b7df,8ee372d; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `keel.default.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 0.0s / 0.0s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `keel.default.IDEMPOTENT.baseline` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | not comparable: pins differ — keel_commit e0d94e7 / 77488a2 |
| `keel.default.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 3.1s / 2.4s | not comparable: pins differ — keel_commit 198b456 / 8ee372d; claim_poll_s null / 0.2; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; reaper_period_s null / 0.2; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 3.1s / — | not comparable: pins differ — keel_commit 198b456 / 8ee372d; claim_poll_s null / 0.2; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; reaper_period_s null / 0.2; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.2s / 2.4s | not comparable: pins differ — keel_commit 198b456 / 8ee372d; claim_poll_s null / 0.2; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; reaper_period_s null / 0.2; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 10 / 30 | 30/30 / 30/30 | 2.7s / 1.1s | not comparable: pins differ — keel_commit cefd652 / 8ee372d; extra null / {"model_timeout_s": 2.0, "world_client_timeout_s": 5.0}; retry "max_attempts=1" / "max_attempts=3, backoff=exponential+jitter" |
| `keel.default.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.1s / 0.1s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `keel.default.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ | S1✓ S2✓ S3✓ S4✓ S5✓ L1✓ L2✓ C1✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `langgraph.sync.EXTERNAL.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | not comparable: pins differ — keel_commit e0d94e7 / 77488a2 |
| `langgraph.sync.EXTERNAL.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 2.1s / 2.6s | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.EXTERNAL.kill@after:tool_return` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 0 | 30 / 0 | 30/30 / 30/30 | 2.2s / — | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.EXTERNAL.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.1s / 2.6s | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.EXTERNAL.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.EXTERNAL.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 2.7s / 2.5s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `langgraph.sync.EXTERNAL.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 30 / 30 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `langgraph.sync.IDEMPOTENT.baseline` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | — / — | not comparable: pins differ — keel_commit e0d94e7 / 77488a2 |
| `langgraph.sync.IDEMPOTENT.kill@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.2s / 2.2s | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.IDEMPOTENT.kill@after:tool_return` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 0 | 30/30 / 30/30 | 2.2s / — | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.IDEMPOTENT.kill@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 2.1s / 2.3s | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.IDEMPOTENT.pause_past_ttl@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 0 / 0 | 30/30 / 30/30 | 3.1s / 3.1s | not comparable: pins differ — keel_commit cf7fff6 / 8ee372d; extra null / {"step_timeout": "none documented", "world_client_timeout_s": 5.0} |
| `langgraph.sync.IDEMPOTENT.tool_500@after:tool_effect` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 2.8s / 2.3s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |
| `langgraph.sync.IDEMPOTENT.tool_timeout@before:tool_call` | 30 | S1✓ S3✓ L1✓ L2✓ | S1✓ S3✓ L1✓ L2✓ | 0 / 0 | 30 / 30 | 30/30 / 30/30 | 0.0s / 0.0s | not comparable: pins differ — keel_commit e0d94e7 / 8ee372d |

## Cells with no twin

A fault only one mode can deliver, or a cell one side has not run yet. Listed, never
folded into the agreement count.

| cell | side | n | why |
|---|---|---|---|
| `keel.default.EXTERNAL.model_500@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.model_timeout@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.sigterm_grace_ok@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.EXTERNAL.tool_delay@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `keel.default.EXTERNAL.tool_dropped_response@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.EXTERNAL.tool_malformed@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.IDEMPOTENT.model_500@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.model_timeout@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `keel.default.IDEMPOTENT.tool_delay@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `keel.default.IDEMPOTENT.tool_dropped_response@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `keel.default.IDEMPOTENT.tool_malformed@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.async.EXTERNAL.baseline` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.EXTERNAL.kill@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.EXTERNAL.kill@after:tool_return` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.EXTERNAL.kill@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.EXTERNAL.pause_past_ttl@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.IDEMPOTENT.baseline` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.IDEMPOTENT.kill@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.IDEMPOTENT.kill@after:tool_return` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.IDEMPOTENT.kill@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.async.IDEMPOTENT.pause_past_ttl@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.EXTERNAL.baseline` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.EXTERNAL.kill@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.EXTERNAL.kill@after:tool_return` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.EXTERNAL.kill@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.EXTERNAL.pause_past_ttl@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.IDEMPOTENT.baseline` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.IDEMPOTENT.kill@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.IDEMPOTENT.kill@after:tool_return` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.IDEMPOTENT.kill@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.exit.IDEMPOTENT.pause_past_ttl@before:tool_call` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.sync.EXTERNAL.model_500@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.model_timeout@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.sigterm_grace_ok@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.sigterm_grace_too_short@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.EXTERNAL.tool_delay@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.sync.EXTERNAL.tool_dropped_response@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.EXTERNAL.tool_malformed@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.IDEMPOTENT.model_500@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.model_timeout@before:model_call` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.sigterm_grace_ok@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.sigterm_grace_too_short@after:tool_effect` | matrix_v0+tier1a | 30 | shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built |
| `langgraph.sync.IDEMPOTENT.tool_delay@after:tool_effect` | matrix_v0+tier1a | 30 | the other side has not run this cell |
| `langgraph.sync.IDEMPOTENT.tool_dropped_response@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |
| `langgraph.sync.IDEMPOTENT.tool_malformed@after:tool_effect` | tier1p | 30 | proxy-only: a shim sits inside the client and cannot do to a socket what a network does |

## Reading it

0 of 0 comparable twinned cells agree. 28 of 28 twins are not comparable — their commits or config pins differ — and are counted in neither.

What the proxy realisation loses, per §11.2: `before:tool_call` fires on a request that
has already left the SUT (the shim's fires with nothing sent); `after:tool_return` lands
before the SUT parses the bytes (the shim's lands inside the checkpoint write, via
`call_soon`); a freeze parks the request at the proxy and forwards it at the thaw, and the
process frozen is the one named by `sut/pid-<n>` — which, in rows from before a Keel
successor wrote its pid under its own name, may have been the idle successor rather than the
worker holding the run. The `after:tool_effect` window — applied, receipted, nobody told —
is the same window in both.
