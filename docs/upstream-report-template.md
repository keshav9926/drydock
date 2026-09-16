# Upstream report template

What a Crashproof finding has to look like before it goes to someone else's issue tracker.

Most cells in the matrix are **not** upstream reports and must never be filed as ones. A runtime
that declares `at_least_once` and re-fires an effect after a crash has done exactly what it
documents; an issue titled *"X duplicates effects"* gets closed as working-as-intended, correctly,
and the next report from the same source gets read with less patience. §30's *Exceptional* bar is
specific about what does clear it:

> ≥ 1 upstream issue report with a one-command repro acknowledged by a maintainer; a
> `pause_past_ttl` or `after:tool_effect` result that **contradicts or sharpens a runtime's
> documented semantics, printed with the doc quote beside it**.

Two words carry the bar. *Contradicts*: the runtime does something its documentation says it does
not. *Sharpens*: the documentation is true but incomplete in a way a user would act on — and the
sharpening is the contribution, filed as a docs issue rather than as a bug.

## Before filing

- [ ] **The doc quote is in hand, from the version under test.** Not remembered, not paraphrased.
      Frameworks move; the `framework_versions` pin on the row names which one was measured, and the
      quote has to come from that one.
- [ ] **The finding survives *"your adapter is wrong"*.** This is the objection that closes reports.
      Every claim about the framework has to be citable in the framework's own code or docs, not in
      our table. Re-read §13.3's adapter rules against the adapter first: no counter, no pre-send
      lookup, no retry, no dedup, no synthesised key — and no *missing* documented primitive either.
      If the framework offers something the adapter did not use, the finding is about the adapter.
- [ ] **It is not the documented semantics restated.** Check the declared `claims` for the class.
      If the arm claims `at_least_once` and the observation is a duplicate, there is no report here
      unless something *else* is also true.
- [ ] **The repro is one command from a clean clone**, and it has been run from one.
- [ ] **The counterexample is a specific `(spec_hash, seed, trial_id)`**, not a rate.
- [ ] **`crashproof verify <dir>/results.jsonl --recheck` exits 0** on the rows being cited. 7 is a
      verdict that drifted from its row or a verifier that answered twice; 9 is a row with no
      `facts.json` behind it, which is a row nobody can re-check — cite neither.
- [ ] **The cited rows are not due a re-run.** The README's status section names the published cells
      that are; a finding from one of them is re-measured before it is filed.

## The report

> **Title** — what the runtime does, in its own vocabulary. Not "X is unsafe".
>
> **What the docs say.** The quote, with a link and the version it came from.
>
> **What happens.** The observation, as counts rather than adjectives: requests the receiver
> received, effects it applied, what the runtime's own store held at the instant of the fault. State
> the fault as a *window* — "the process was killed after the tool call returned and before the
> checkpoint was written" — because that is the part a maintainer has to be able to picture.
>
> **Why it is not the documented behaviour** (contradicts), **or what the documentation does not
> say** (sharpens). One paragraph. This is the whole report; everything else is evidence.
>
> **Reproduction.**
> ```bash
> git clone <repo> && cd <repo> && uv sync --extra dev --extra langgraph   # the arm's extra; Keel needs none
> docker compose up -d postgres
> uv run crashproof demo --adapter <arm> --config <config> --fault <fault> --seed <n>
> ```
> Paste the printed BEFORE CRASH / AFTER RESTART pair. It is read off the trial's own artefacts, so
> a maintainer who runs it and gets different lines has found something we want to know about.
>
> `demo` runs `tool_chain_1_effect` only. A finding from another workload — W5's approval wait, say —
> is reproduced from its matrix file, one cell and one seed, with the trial's effect ledger as the
> evidence to paste:
> ```bash
> uv run crashproof bench --matrix bench/specs/<matrix>.yaml --cells '<cell id>' --seeds 1 --base-seed <n> --out out/repro
> uv run crashproof verify out/repro/<cell dir>/t-<n> --effects
> ```
> For the LangGraph tier-2 `notify` re-fire that is `--matrix bench/specs/w5_pre.yaml --cells
> 'langgraph.sync.GATED.baseline'`, and the ledger's `notify.send` row shows 2 receipts and 2 applied.
> `<cell dir>` is the cell id with every character outside `A-Za-z0-9._-` replaced by `_` (so `@` and
> `:` become `_`); `langgraph.sync.GATED.baseline` is its own.
>
> **What this is not a claim about.** Name it explicitly: the harness kills processes at a window a
> random production crash would reach rarely; the numbers are from n seeds with the interval
> printed; nothing here says the runtime is unsuitable for anything. A report that overreaches once
> is a source that gets filtered afterwards.
>
> **Everything needed to disagree.** The adapter (a link — it is short and public on purpose), the
> spec file, the seed, the `config_pin`, the framework versions, the World's receipt log. The
> contamination stance (§15.10) is that all of this is public *before* results are; a maintainer who
> changes the framework to pass a published schedule has fixed a bug, and the report says so with
> the commit that fixed it.

## After filing

A fix upstream is a row that changes. Re-run the cell at the new version, publish both rows with
their `framework_versions`, and mark the old one stale rather than deleting it — the point of the
matrix is that it can be checked, which includes checking what it used to say.
