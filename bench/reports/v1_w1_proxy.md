# v1_w1_proxy

Workload `tool_chain_1_effect`. One cell is n **seeds**, not n trials of one seed.

## EXTERNAL  ·  key_source=none

| (location, fault) | `dbos.native` | `dbos.pydantic_ai` | `keel.default` | `langgraph.async` | `langgraph.exit` | `langgraph.sync` | `restate.pydantic_ai` | `temporal.pydantic_ai` |
|---|---|---|---|---|---|---|---|---|
|  | recovery=self<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once | recovery=self<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once | recovery=self<br>claims: PURE effectively-once · IDEM effectively-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=engine<br>claims: PURE exactly-once · IDEM exactly-once · EXT exactly-once | recovery=engine<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once |
| `baseline` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 300/300 [0.99–1.00]<br>dup_eff 0 · dup_rcpt 3 · lost 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 300/300 [0.99–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 300/300 [0.99–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 |
| `kill@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 3.4s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 4.7s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 2.3s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.4s · +calls 0 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 60<br>lat 2.4s · +calls 2 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.7s · +calls 0 · diverged 30/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 3.7s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 5.4s · +calls 0 · diverged 30/30 |
| `kill@after:tool_return` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 300/300 [0.99–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 1/300 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 300/300 [0.99–1.00]<br>dup_eff 294 · dup_rcpt 428<br>lat 2.8s · +calls 2 · diverged 294/300 | **withdrawn — K7**<br>void 21 of 30<br>dup_eff 0 · dup_rcpt 0<br>no verdict from n 9 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>+calls 0 · diverged 0/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 300/300 [0.99–1.00]<br>dup_eff 97 · dup_rcpt 97 · lost 0<br>lat 3.8s · +calls 0 · diverged 97/300 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 |
| `kill@before:tool_call` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.4s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 4.5s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 2.4s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 2.4s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.3s · +calls 2 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 2.8s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.7s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 7.1s · +calls 0 · diverged 0/30 |
| `pause_past_ttl@before:tool_call` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 2.4s · +calls 0 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 50 · dup_rcpt 50 · lost 0<br>lat 21.5s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 50 · dup_rcpt 50 · lost 0<br>lat 6.3s · +calls 0 · diverged 30/30 |
| `tool_500@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.8s · +calls 0 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.4s · +calls 1 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 3.6s · +calls 0 · diverged 30/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 0.1s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 1.1s · +calls 0 · diverged 30/30 |
| `tool_dropped_response@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.9s · +calls 0 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.4s · +calls 1 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 4.6s · +calls 0 · diverged 30/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 0.1s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 1.1s · +calls 0 · diverged 30/30 |
| `tool_malformed@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.9s · +calls 0 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 2.3s · +calls 1 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 3.2s · +calls 0 · diverged 30/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 0.1s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 1.1s · +calls 0 · diverged 30/30 |
| `tool_timeout@before:tool_call` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 0.0s · +calls 0 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 0.0s · +calls 1 · diverged 30/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30<br>lat 0.0s · +calls 0 · diverged 30/30 | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 0.0s · +calls 0 · diverged 30/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 30 · dup_rcpt 30 · lost 0<br>lat 0.0s · +calls 0 · diverged 30/30 |

## IDEMPOTENT  ·  key_source=framework, none

| (location, fault) | `dbos.native` | `dbos.pydantic_ai` | `keel.default` | `langgraph.async` | `langgraph.exit` | `langgraph.sync` | `restate.pydantic_ai` | `temporal.pydantic_ai` |
|---|---|---|---|---|---|---|---|---|
|  | recovery=self<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once | recovery=self<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once | recovery=self<br>claims: PURE effectively-once · IDEM effectively-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=harness<br>claims: PURE at-least-once · IDEM at-least-once · EXT at-least-once | recovery=engine<br>claims: PURE exactly-once · IDEM exactly-once · EXT exactly-once | recovery=engine<br>claims: PURE at-least-once · IDEM effectively-once · EXT at-least-once |
| `baseline` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 |
| `kill@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 3.3s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 4.4s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 2.3s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.5s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 60<br>lat 2.4s · +calls 2 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 3.2s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 3.7s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 5.1s · +calls 0 · diverged 0/30 |
| `kill@after:tool_return` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 34<br>lat 2.4s · +calls 2 · diverged 0/30 | **withdrawn — K7**<br>void 25 of 30<br>dup_eff 0 · dup_rcpt 0<br>no verdict from n 5 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>+calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 8 · lost 0<br>lat 3.6s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 |
| `kill@before:tool_call` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.3s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 4.5s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 2.4s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 2.3s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.4s · +calls 2 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.3s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.7s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 5.1s · +calls 0 · diverged 0/30 |
| `pause_past_ttl@before:tool_call` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 2.4s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0<br>lat 3.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 50 · lost 0<br>lat 22.0s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 50 · lost 0<br>lat 6.3s · +calls 0 · diverged 0/30 |
| `tool_500@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.6s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.7s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.4s · +calls 1 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 3.6s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 1.1s · +calls 0 · diverged 0/30 |
| `tool_dropped_response@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.5s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.7s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.4s · +calls 1 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 3.6s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 1.1s · +calls 0 · diverged 0/30 |
| `tool_malformed@after:tool_effect` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.4s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.6s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 2.7s · +calls 1 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 3.6s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.1s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 1.1s · +calls 0 · diverged 0/30 |
| `tool_timeout@before:tool_call` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>lat 0.0s · +calls -1 · diverged 0/30 | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 0.0s · +calls 1 · diverged 0/30 | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 30 · lost 0<br>lat 0.0s · +calls 0 · diverged 0/30 |

## Appendix — the screening tier of the confirmed cells (§15.3)

The grid reports these cells at the confirmation tier (seeds ≥ 100,000); this is what the screening tier showed for them. A safety FAIL in either tier is a FAIL in the grid.

| cell | screening |
|---|---|
| `keel.default.EXTERNAL.baseline` | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 |
| `keel.default.EXTERNAL.kill@after:tool_return` | S1✓ S2✓ S3✓ S4✓ S5✓ S6· S7· C1✓<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0<br>+calls 0 · diverged 0/30 |
| `langgraph.async.EXTERNAL.baseline` | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 |
| `langgraph.async.EXTERNAL.kill@after:tool_return` | S1✓ S2· S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 29 · dup_rcpt 30<br>lat 2.4s · +calls 2 · diverged 29/30 |
| `restate.pydantic_ai.EXTERNAL.baseline` | S1✓ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 0 · dup_rcpt 0 · lost 0 |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1✗ S2✓ S3✓ S4· S5· S6· S7· C1·<br>L1 30/30 [0.89–1.00]<br>dup_eff 12 · dup_rcpt 12 · lost 0<br>lat 3.8s · +calls 0 · diverged 12/30 |

## Counterexamples

| cell | invariant | spec_hash | seed | trial | detail |
|---|---|---|---|---|---|
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 7 | `t-7` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 8 | `t-8` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 10 | `t-10` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 11 | `t-11` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 12 | `t-12` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 14 | `t-14` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 15 | `t-15` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 18 | `t-18` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 19 | `t-19` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 20 | `t-20` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 23 | `t-23` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 24 | `t-24` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 26 | `t-26` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 30 | `t-30` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 31 | `t-31` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 33 | `t-33` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 34 | `t-34` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_effect` | S1 | `bc86bef89209` | 36 | `t-36` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100016 | `t-100016` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100017 | `t-100017` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100018 | `t-100018` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100026 | `t-100026` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100031 | `t-100031` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100035 | `t-100035` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100038 | `t-100038` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100039 | `t-100039` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100042 | `t-100042` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100043 | `t-100043` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100048 | `t-100048` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100052 | `t-100052` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100053 | `t-100053` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100054 | `t-100054` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100059 | `t-100059` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100061 | `t-100061` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100063 | `t-100063` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100064 | `t-100064` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100065 | `t-100065` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100068 | `t-100068` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100069 | `t-100069` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100070 | `t-100070` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100077 | `t-100077` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100082 | `t-100082` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100087 | `t-100087` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100088 | `t-100088` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100090 | `t-100090` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100092 | `t-100092` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100094 | `t-100094` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100098 | `t-100098` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100102 | `t-100102` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100105 | `t-100105` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100106 | `t-100106` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100109 | `t-100109` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100110 | `t-100110` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100119 | `t-100119` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100121 | `t-100121` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100124 | `t-100124` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100126 | `t-100126` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100129 | `t-100129` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100133 | `t-100133` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100135 | `t-100135` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100136 | `t-100136` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100137 | `t-100137` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100140 | `t-100140` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100145 | `t-100145` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100147 | `t-100147` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100149 | `t-100149` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100152 | `t-100152` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100154 | `t-100154` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100158 | `t-100158` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100161 | `t-100161` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100164 | `t-100164` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100166 | `t-100166` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100170 | `t-100170` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100179 | `t-100179` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100182 | `t-100182` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100184 | `t-100184` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100185 | `t-100185` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100187 | `t-100187` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100188 | `t-100188` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100189 | `t-100189` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100190 | `t-100190` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100194 | `t-100194` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100196 | `t-100196` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100197 | `t-100197` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100199 | `t-100199` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100201 | `t-100201` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100208 | `t-100208` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100216 | `t-100216` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100218 | `t-100218` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100219 | `t-100219` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100220 | `t-100220` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100224 | `t-100224` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100230 | `t-100230` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100235 | `t-100235` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100239 | `t-100239` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100241 | `t-100241` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100245 | `t-100245` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100251 | `t-100251` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100254 | `t-100254` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100257 | `t-100257` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100264 | `t-100264` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100265 | `t-100265` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100266 | `t-100266` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100269 | `t-100269` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100271 | `t-100271` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100272 | `t-100272` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100273 | `t-100273` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100274 | `t-100274` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100277 | `t-100277` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100283 | `t-100283` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100285 | `t-100285` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100287 | `t-100287` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100291 | `t-100291` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100295 | `t-100295` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 100296 | `t-100296` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.kill@after:tool_return` | S1 | `78b881f297eb` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 7 | `t-7` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 8 | `t-8` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 10 | `t-10` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 11 | `t-11` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 12 | `t-12` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 14 | `t-14` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 15 | `t-15` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 18 | `t-18` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 19 | `t-19` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 20 | `t-20` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 23 | `t-23` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 24 | `t-24` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 26 | `t-26` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 30 | `t-30` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 31 | `t-31` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 33 | `t-33` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 34 | `t-34` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.pause_past_ttl@before:tool_call` | S1 | `144459871383` | 36 | `t-36` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 7 | `t-7` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 8 | `t-8` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 10 | `t-10` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 11 | `t-11` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 12 | `t-12` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 14 | `t-14` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 15 | `t-15` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 18 | `t-18` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 19 | `t-19` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 20 | `t-20` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 23 | `t-23` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 24 | `t-24` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 26 | `t-26` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 30 | `t-30` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 31 | `t-31` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 33 | `t-33` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 34 | `t-34` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_500@after:tool_effect` | S1 | `fc98c5350365` | 36 | `t-36` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 7 | `t-7` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 8 | `t-8` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 10 | `t-10` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 11 | `t-11` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 12 | `t-12` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 14 | `t-14` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 15 | `t-15` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 18 | `t-18` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 19 | `t-19` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 20 | `t-20` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 23 | `t-23` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 24 | `t-24` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 26 | `t-26` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 30 | `t-30` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 31 | `t-31` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 33 | `t-33` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 34 | `t-34` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_dropped_response@after:tool_effect` | S1 | `9138bb6c1b67` | 36 | `t-36` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 7 | `t-7` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 8 | `t-8` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 10 | `t-10` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 11 | `t-11` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 12 | `t-12` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 14 | `t-14` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 15 | `t-15` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 18 | `t-18` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 19 | `t-19` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 20 | `t-20` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 23 | `t-23` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 24 | `t-24` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 26 | `t-26` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 30 | `t-30` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 31 | `t-31` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 33 | `t-33` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 34 | `t-34` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_malformed@after:tool_effect` | S1 | `4f1e72a1b11f` | 36 | `t-36` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 7 | `t-7` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 8 | `t-8` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 9 | `t-9` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 10 | `t-10` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 11 | `t-11` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 12 | `t-12` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 13 | `t-13` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 14 | `t-14` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 15 | `t-15` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 16 | `t-16` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 17 | `t-17` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 18 | `t-18` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 19 | `t-19` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 20 | `t-20` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 21 | `t-21` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 22 | `t-22` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 23 | `t-23` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 24 | `t-24` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 25 | `t-25` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 26 | `t-26` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 27 | `t-27` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 28 | `t-28` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 29 | `t-29` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 30 | `t-30` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 31 | `t-31` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 32 | `t-32` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 33 | `t-33` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 34 | `t-34` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 35 | `t-35` | claim=exactly_once but applied more than once |
| `restate.pydantic_ai.EXTERNAL.tool_timeout@before:tool_call` | S1 | `94d62276ca0b` | 36 | `t-36` | claim=exactly_once but applied more than once |

## Provenance

Rows through 2026-09-19T22:44:48+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `bench/results/v1_w1_proxy` | 6403 | `251e52d` ×6403 |

| config | pin |
|---|---|
| `dbos.native` | backend=postgres (DBOS system database, one per trial), durability=step checkpoint, extra={'agent_code': 'native', 'application_version': 'DBOS default: hash of workflow source', 'executor_id': 'local (no Conductor)', 'max_recovery_attempts': 100, 'recv_timeout': 'run input expires_in', 'step_timeout': 'none', 'world_client_timeout_s': 5.0}, retry=none: @DBOS.step(retries_allowed=False), worker_count=1 |
| `dbos.pydantic_ai` | backend=postgres (DBOS system database, one per trial), durability=step checkpoint, extra={'agent_code': 'pydantic_ai', 'application_version': 'DBOS default: hash of workflow source', 'executor_id': 'local (no Conductor)', 'max_recovery_attempts': 100, 'model_step_config': 'default (retries_allowed=False)', 'parallel_execution_mode': 'parallel_ordered_events (default)', 'recv_timeout': 'run input expires_in', 'step_timeout': 'none', 'world_client_timeout_s': 5.0}, retry=none: @DBOS.step(retries_allowed=False), worker_count=1 |
| `keel.default` | backend=postgres, claim_poll_s=0.2, durability=journal, extra={'breaker': 'n_open=5, cooldown_s=30', 'model_timeout_s': 2.0, 'world_client_timeout_s': 5.0}, heartbeat_s=0.666667, lease_ttl_s=2, pause_ms=3000, reaper_period_s=0.2, retry=tools max_attempts=3 base=1s cap=30s; model max_attempts=5 base=2s cap=60s; x2 full jitter; a wait of 1 s or more parks with the lease released (§8), successor_start_delay_s=1.5, tool_timeout_s=1, worker_count=1|2 |
| `langgraph.async` | backend=AsyncPostgresSaver, durability=async, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `langgraph.exit` | backend=AsyncPostgresSaver, durability=exit, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `langgraph.sync` | backend=AsyncPostgresSaver, durability=sync, extra={'step_timeout': 'none documented', 'world_client_timeout_s': 5.0}, retry=framework default, worker_count=1 |
| `restate.pydantic_ai` | backend=restate-server single binary, fresh RESTATE_BASE_DIR per trial, wiped at teardown, detection_timeout_s=7, durability=invocation journal; agent_code=pydantic_ai (RestateAgent wrapper, not a capability), extra={'abort_timeout_s': 5.0, 'approval_wait': 'ctx.awakeable + restate.select(ctx.sleep(expires_in))', 'asgi': 'hypercorn.asyncio.serve in the worker process, 127.0.0.1:<port fixed per trial>', 'client_retries': 'none (FunctionModel has no provider client; the World client does not retry)', 'inactivity_timeout_s': 2.0, 'journal_retention': '1d', 'platform': 'linux (WSL2)', 'server_env': {'RESTATE_BOOTSTRAP_NUM_PARTITIONS': '1', 'RESTATE_DEFAULT_NUM_PARTITIONS': '1', 'RESTATE_DISABLE_TELEMETRY': 'true', 'RESTATE_LISTEN_MODE': 'tcp', 'RESTATE_ROCKSDB_TOTAL_MEMORY_SIZE': '32 MB'}, 'tools': 'restate_context().run_typed per call (RestateAgent auto_wrap_tools=False)', 'world_client_timeout_s': 5.0}, retry=InvocationRetryPolicy(initial_interval=50ms, exponentiation_factor=2.0, max_interval=60s, max_attempts=70, on_max_attempts=pause); ctx.run with default RunOptions (the invocation policy), worker_count=1 |
| `temporal.pydantic_ai` | backend=temporal server start-dev --db-filename (SQLite), one per trial, detection_timeout_s=2, durability=event history; agent_code=pydantic_ai (TemporalDurability), extra={'applies_to': 'model-request and tool-call activities alike', 'client_retries': 'none (FunctionModel has no provider client; the World client does not retry)', 'heartbeat_throttle': 'SDK default: 0.8 x heartbeat_timeout', 'heartbeat_timeout_s': 2.0, 'start_to_close_s': 5.0, 'sticky_queue_schedule_to_start_timeout_s': 2.0, 'workflow_task_timeout_s': 10.0, 'world_client_timeout_s': 5.0}, heartbeat_s=2, retry=RetryPolicy(initial_interval=1s, backoff_coefficient=2.0, maximum_interval=100s, maximum_attempts=0) + TemporalDurability non_retryable_error_types, tool_timeout_s=5, worker_count=1 |

**Mixed n.** Cells in this report were run at different seed counts ([5, 9, 30, 300]); each cell prints its own n in the liveness line. A reduced-n cell is a weaker estimate, not a different verdict: safety is still PASS only on zero violations in the n that ran, and the interval beside it widens to say so (§15.3).

**How to read a cell.** The first line is safety: PASS means zero violations in n, and a single violation is a FAIL with its counterexample listed above — safety is never a proportion. The second line is liveness with a Wilson interval. The third is raw observation, published whatever the verdicts say: `dup_eff` counts effects the World actually applied more than once, `dup_rcpt` counts requests it received more than once. The gap between them is what the receiver's idempotency bought, and the runtime gets no credit for it. A cell marked **withdrawn — K7** has a void rate over §30's 5 % threshold: its trials measured the harness rather than the runtime, so its counts are printed and no verdict is published from it.

**Judged against claims.** An arm that declares `at_least_once` and produces a duplicate has not failed S1; the duplicate is in the table regardless. An arm that declares `effectively_once` and applies twice has failed, and the seed that did it is named.

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

**3. Confirmation is automatic where it matters.** Every non-unanimous cell and every cell under a
claimed difference goes to n = 300 on fresh seeds, together with the arm it is compared against.
Unanimous cells that no claim depends on stay at thirty, because three hundred more of the same
outcome tighten an interval nothing rests on.

**4. The variance being sampled is the right one.** Schedules are seeded and shared between arms, so
the residual variance is the SUT's own internal timing — which is precisely the quantity a
durability claim is about. Thirty samples of "does the reaper beat the zombie" are thirty draws from
the distribution a user would experience.

**5. Everything is reproducible.** Every row carries `(spec_hash, seed, keel_commit)` and its
`config_pin`, framework versions included. `keel_commit` pins the adapters as well as Keel, because
they live in the same repository, and it is marked `-dirty` when the tree had uncommitted changes.
`crashproof verify <dir>/results.jsonl --recheck` re-runs the verifier over each trial's own facts
and fails if a verdict moved or a row cannot be re-verified. Disagreement is settled by running it.
