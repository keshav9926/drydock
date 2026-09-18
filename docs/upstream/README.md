# Upstream reports

These are drafts of §29.3's *"one issue per finding"*, in the form set by
[`../upstream-report-template.md`](../upstream-report-template.md). **Nothing here has been filed.**
Filing is the owner's decision, made after the unchecked items in each draft's pre-filing notes are
done. Each file's `## Issue body` section is the text a maintainer would read.

| runtime | finding | file | where it would go | status |
|---|---|---|---|---|
| Restate | "Tool side effects are not duplicated" does not hold when the process dies after a `ctx.run` action and before its result is journaled. 2 applied in 30 of 30 at every kill-after-effect cell, including behind an approval. A frozen worker gives 2 or 3. It is probably intended at-least-once, so the report is framed as a docs qualifier. | [restate-tool-side-effects-duplicated.md](restate-tool-side-effects-duplicated.md) | restatedev/docs-restate | draft, not filed |
| restate-sdk | `restate-sdk[pydantic-ai]` cannot import `restate.ext.pydantic`: `pydantic_ai.mcp` is imported unconditionally, and the extra does not install `pydantic-ai-slim[mcp]`. | [restate-sdk-pydantic-extra-imports-mcp.md](restate-sdk-pydantic-extra-imports-mcp.md) | restatedev/sdk-python | draft, not filed |

## Considered and not drafted

| candidate | why not |
|---|---|
| **Restate:** 4 of 60 `pause_past_ttl` trials still RUNNING at 60 s | The rows do not support the README's reading, "the documented default backoff outlasting the trial". The trial directories (`EXTERNAL t-30`, `IDEMPOTENT t-12`, read on the machine that ran them) show Restate retrying at 58 ms to 951 ms intervals, with every attempt after the thaw stalling for inactivity plus abort. There is no SUT observation after the freeze and no receipt for the tool. That is a harness question about freeze and thaw, not a Restate finding. It is also on our non-default 2 s / 5 s timeouts and our 60 s trial budget. |
| **pydantic-ai:** `pydantic_ai.mcp` imports `httpx`, which `pydantic-ai-slim[mcp]` did not bring | Real at 2.43.0 (`pydantic_ai/mcp.py:51`), and **already fixed in 2.45.0**. Recorded in the restate-sdk draft's pre-filing notes. |
| **LangGraph 1.2.11:** pre-interrupt code re-runs on resume (W5-pre `notify` 2× in `baseline` and `approval_delay`, with one `sync` baseline trial at 3×, and 3× under `kill_while_waiting`, on all three configs) | Documented, and prominently. The `interrupt()` docstring says *"The graph resumes from the start of the node, **re-executing** all logic."* The [interrupts guide](https://docs.langchain.com/oss/python/langgraph/interrupts) has a pitfall section, *"Do not perform non-idempotent operations before `interrupt()`"*, which warns they will *"create duplicate records on each resume"* and advises separating side effects into their own node. A restart is one more resume, so the 3× adds nothing a reader of that page would act on. The adapter also deliberately does not use the documented mitigation, which is the template's own disqualifier. |
| **LangGraph:** `approval_expiry` waits forever (L1 FAIL 30 of 30 on every config, still WAITING) | LangGraph claims no deadline on `interrupt()`, and the guide mentions none. A deadline is application logic or a feature request, not a contradiction or a sharpening. The cell was built to show the absence and scores L1 FAIL by design. |
| **DBOS 2.31.1:** `after:tool_return` duplicates in 18 of 30 (`native`) and 24 of 30 (`pydantic_ai`) | Both outcomes are within *"Steps are tried at least once but are never re-executed after they complete"*. The step's checkpoint is written off the event loop and sometimes commits before the shim's kill. K3 marks the `after:tool_return` cells (both configs, both bands) as exploratory: they measure the kill's timing. DBOS already documents at-least-once, so there is nothing to sharpen. |
