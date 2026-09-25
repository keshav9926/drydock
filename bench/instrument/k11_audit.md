# K11(a) — the oracle audited by killing it (§30, §28.2)

The World writes a receipt and fsyncs it *before* it computes the response (`crashproof/world/services.py`), which is what every `after:tool_effect` cell in the matrix rests on. This audit kills the World process mid-request and reads the log the dead process left. It convicts on one outcome: a client **answered** for a request with no receipt.

Run 2026-09-20T06:00:22+0530 · 500 trials · 1808 s · natural 300 · held 100 · calibration 100

| band | answered + receipt | killed in the window (receipt, no answer) | before the receipt | **answered, no receipt** |
|---|---|---|---|---|
| `natural` | 300 | 0 | 0 | **0** |
| `held` | 0 | 100 | 0 | **0** |
| `mutant` — calibration | 0 | 0 | 0 | **100** |

**Calibration: the audit convicts the mis-ordered World.** `scripts/_k11_world.py` defers the receipt 4000 ms past the answer — the implementation K11(a) exists to catch — and the `mutant` band scores it a violation, so the instrument has power.

**K11(a): not fired** — 0 of 400 audited trials were answered without a receipt in the log.

**Reach.** A kill from outside is itself slow — 0.5 to 1.1 s on this platform, which is `taskkill` spawning — so this audit sees a mis-ordering whose gap is of that order or wider (calibrated at 4000 ms) and cannot see one of microseconds; the `natural` band's kills land after the answer for that reason, and the `held` band's land after the receipt because a held response is withheld *after* `receive` has logged, applied and computed it. What no post-mortem of a killed World can see is an effect that crossed into its memory without a receipt: `applied` is in-memory and dies with the process, so the receipt log is the whole of what it leaves behind. The ordering itself is asserted structurally by `tests/unit/test_world.py::test_receipt_is_durable_before_the_response_is_computed`, and this audit's power is pinned in CI by `tests/unit/test_k11_audit.py`.
