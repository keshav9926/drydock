# ambiguity_window_width — World receipt → the runtime's outcome commit (§27, §29.2, K4)

Over the **baseline** trials, per runtime and per effect: from the World's receipt of the call to the runtime's own record of its outcome committing (§19.5's placement join). A crash inside that interval leaves an effect applied that the runtime has no record of — the window every aimed cell targets. Each side is read on the clock named beside it; a width that goes negative is two clocks disagreeing, printed rather than dropped. Where the records name their step, the join takes the tool's own outcome record; where they do not (checkpoints, DBOS's native loop), the first record after the receipt — which, for an effect whose step is interrupted before it returns, does not hold the effect, and the width is then a lower bound.

Rows through 2026-09-19T13:20:53+00:00 (the last trial's end).

| results | rows | keel_commit |
|---|---|---|
| `v1/combined_week2_w1_shim` | 6241 | `251e52d` ×6241 |

| runtime | effect | median ms | IQR ms | n | not placed | commit record | clock |
|---|---|---|---|---|---|---|---|
| `dbos.native` | `create_issue` | 8.2 | [7.8, 8.6] | 60 | 0 | `operation_outputs.completed_at_epoch_ms` (sut/steps.json) | host: the worker's `time.time()` just before the insert, 1 ms resolution |
| `dbos.pydantic_ai` | `create_issue` | 9.8 | [9.3, 11.0] | 60 | 0 | `operation_outputs.completed_at_epoch_ms` (sut/steps.json) | host: the worker's `time.time()` just before the insert, 1 ms resolution |
| `keel.default` | `create_issue` | 9.0 | [8.7, 9.6] | 60 | 0 | journal outcome event (STEP_COMPLETED/FAILED/AMBIGUOUS/RESOLVED/CANCELLED) | host: the store's clock shifted by the trial's measured store_clock offset |
| `langgraph.async` | `create_issue` | 12.9 | [12.1, 14.0] | 60 | 0 | checkpoint write (`checkpoints.ts`) | host: stamped in the SUT's own process |
| `langgraph.exit` | `create_issue` | 21.1 | [19.7, 22.9] | 60 | 0 | checkpoint write (`checkpoints.ts`) | host: stamped in the SUT's own process |
| `langgraph.sync` | `create_issue` | 13.4 | [12.6, 14.4] | 60 | 0 | checkpoint write (`checkpoints.ts`) | host: stamped in the SUT's own process |
| `restate.pydantic_ai` | `create_issue` | 16.1 | [15.0, 17.4] | 60 | 0 | `sys_journal` `Notification: Run` appended_at (sut/journal.json) | WSL: restate-server's, which the World and the worker share |
| `temporal.pydantic_ai` | `create_issue` | 26.6 | [21.1, 34.8] | 60 | 0 | `ActivityTask{Completed,Failed,TimedOut}` event_time (sut/history.json) | host: the Temporal dev server's |

K4 (§30) reads the median and needs two things this table does not supply: a realistic kill rate λ, from which natural exposure per effect is ≈ λ × width, and evidence that every arm recovers correctly from every kill placed *outside* a window (the placement page's out-of-window faults, joined to their trials' recovery and duplicate counts).
