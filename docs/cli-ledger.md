# CLI ledger — every difference between §25's command trees and what is built

§25.2 and §25.3 declare two command trees. This is every place the code differs from them, in both
directions, with the reason. It exists for the same rule the verifier runs on: **a missing input is
named individually, never folded into a pass and never omitted from the grid** (§15.11). A command
tree is a contract, and an undocumented gap in one is the same kind of defect as an `N/A` printed as
`PASS`.

Commands are in the [README's departures table](../README.md#layout-and-where-it-departs-from-231).
This file is the flag-level detail, plus the §24.1 Python calls that are the same contract one layer
down.

## Declared, not built

| Surface | Declared | Why not, and when |
|---|---|---|
| `inject`/`chaos --mode hook\|shim\|proxy` | §25.3 | Mode is a property of the **spec file** (`mode: shim`), where it is validated — it decides which fault vocabulary is legal, and a CLI override would be a second source of truth for exactly the field that must not have one. `hook` cells run under `pytest tests/conformance`; `shim` and `proxy` specs run through `chaos`/`bench` unchanged, the mode deciding where the injector sits (`bench/specs/tier1p.yaml` is the proxy twin of matrix v0 and tier1a). |
| `inject --trial-dir D` | §25.3 | `--out` already names where the trial directory goes, and the trial id inside it is `t-<seed>` by rule. |
| `bench --tier screening\|confirmation` | §25.3 | The confirmation tier at n = 300 on fresh seeds is week 3. Today the whole of it is `--seeds 300 --base-seed <fresh>`; the flag arrives when the *selection* rule does — every non-unanimous cell and every cell under a claimed difference (§15.3). |
| `verify --claims F` | §25.3 | Claims are an **adapter declaration** (§13.3), not an input. A claims file would let the thing being judged pick its own bar, which is the one property the Jepsen rule cannot survive. |
| `compare --metric m ...` | §25.3 | Every metric fits on one page and each is its own family (§15.6). A filter would let a reader — or an author — publish the metrics that went their way. |
| `compare --paired` | §25.3 | Not a flag because pairing is the only mode: an unpaired comparison of two runtimes is not a weaker claim, it is a different one. |
| `report --fmt html` | §25.3 | Week 3. It refuses with the reason and exit 2 rather than rendering Markdown under an `html` flag. |
| `crashproof export` | §25.3 (v1) | Parquet/CSV over the same rows. Nothing in phases 1–8 reads it and `results.jsonl` is already `grep`- and `jq`-able; it arrives with DuckDB in week 3, or not at all. |
| `keel run --model provider:model` | §25.2 | Needs the real provider. Real-model validation is its own mode with its own contamination rules (§14.6), not a flag on the scripted path. |
| `keel run --seed N` | §25.2 | The scripted provider is deterministic. There is nothing to seed until a real model is in the loop, and a flag that seeds nothing is worse than no flag. |
| `keel run --args-file F` | §25.2 | `--args "$(cat f)"` is the same thing in the shell that is already open. |
| `keel worker --concurrency N` | §25.2 | v1. One lease per worker is the MVP model; the matrix's `worker_count` is separate **processes**, which is what the `pause_past_ttl` cell actually needs. |
| `keel events --raw` | §25.2 | Built as `--json`, which is the spelling §28.5's own fixture-capture line uses (`keel events $RUN --json > tests/journals/<name>.jsonl`). One flag, one name. |
| `keel effects --class C` | §25.2 (MVP) | Not built, and no decision was recorded against it: `--ambiguous` is the only filter. `keel effects RUN --json` carries each row's `effect_class` for a `jq` filter meanwhile. |
| `keel signal RUN --resolve STEP=completed\|failed\|cancelled [--evidence S]`, `--compensate STEP` | §25.2 (v1) | Not built, and neither is `Keel.compensate` (§27.9, v1). The consequence is concrete: a run SUSPENDED on a `RESOLVED_UNKNOWN` step — an EXTERNAL effect with no probe, or a probe that could not tell — has no way out but `keel cancel`, because `keel resume` replays to that step and suspends again. |
| `keel watch` | §25.2 (v1, day 7) | **Cut**, per §28.7's own cut line — not pending. `keel events --follow` shows the same BEFORE CRASH / AFTER RESTART split, in the event stream where it already lives. |
| `keel fork` | §25.2 (v1) | Cut from phase 5 by §28.5's own cut line; week 3 with the counterfactual story. |

## Built, in a different shape

| Declared | Built | Why |
|---|---|---|
| `keel rebind RUN --model provider:model` (§25.2, v1) | `keel rebind RUN [--provider P] [--model M] [--client-key K]` | The binding is the run's `model_config` mapping, so the CLI builds it from its two keys and refuses neither-given with exit 2. The drained row is journaled as `MODEL_BINDING_CHANGED{model_config, previous}` and replaces the binding whole; it reaches live MODEL steps and children spawned afterwards, never a memoized step (§16.7). |
| `keel diff RUN [--against RUN2]` (§25.2, v1) — "SUSPENDED diff, or step-sequence diff base vs fork" | `keel diff RUN_A RUN_B [--json]` | Two positional runs, compared by their logical projections (§10.5), so a run that crashed and probed its way to the answer reads as identical to one that never crashed. The single-run form diffs a SUSPENDED run's journal against the current program, which is what `keel replay RUN --verify` already prints (`step N: journal … != program …`); the base-vs-fork form needs FORK, which is cut. |

## Python API (§24.1)

`Keel.pause`, `cancel`, `approve`, `reject` and `rebind` (§27.9: v1, week 2) are built. Each is one
row in the inbox through `Keel.signal` — the same row the CLI writes — and nothing else. Where they
differ from §24.1:

| §24.1 | Built | Why |
|---|---|---|
| every control call returns `SignalId` | returns `bool`: whether the row was inserted | The insert refuses a row for a terminal run and one with a `client_key` already used; that refusal is what a caller branches on, and `keel <cmd>` exits 1 on it. |
| `rebind(run_id, model_config)` | `rebind(run_id, model_config, *, client_key=None)` | A retried rebind dedups on `client_key` the way `pause`, `cancel`, `approve` and `reject` already do. |
| `approve`/`reject(run_id, approval_id, *, by, …)` | the same, and the id always travels in the row | A decision names its gate: one for an approval already decided is `SIGNAL_IGNORED{approval_terminal}` at the drain, never applied to whichever approval is open by then (§7.5). `keel approve\|reject` without `--approval` resolve the open approval from the journal and write its id into the row. |

Not built from §27.9's Python list: `Keel.compensate` (above), `Keel.fork` and `Keel.replay` (FORK is
cut; VERIFY is `keel replay --verify`), `Keel.inspect`, `Keel.tail` and `Keel.state`.

### Built since this file was written

`keel cancel`, `keel pause`, `keel signal`, `keel approve`, `keel reject` and `keel rebind` are
declared in §25.2 and now exist, each as one row in the signals inbox and nothing else. `keel resume`
moved onto the same path: the MVP's direct conditional UPDATE of `runs.runnable_at` was **deleted**,
not kept beside it — §27.2 said *replaced*, and two ways to influence a run is one more than the fence
can defend. `JournalBackend.mark_runnable` went with it.

Delegation (§17) adds no command: §25.2 declares none, and a parent's children are reached the
way §17.3 allows — through the `delegations` rows, which `keel show <parent>` now prints as a
`children` table (ordinal, retry, child run id, role, status, reserved, settled). A child is a run,
so `keel show <child>`, `keel events <child>` and `keel cancel <child>` already work on it; a
`cancel` of the parent propagates to every open child on its own (§7.6.2).

## Built, not declared

| Surface | Why |
|---|---|
| `crashproof workloads` | One table of the workload declaration — variant, `key_source`, tool, class, endpoint, required effects — over machinery `chaos` already loads. It lists `tool_chain_1_effect` only: the W5 workloads (`approval_gated_deploy`, `approval_gated_deploy_pre`, variant `GATED`) are not in it yet. |
| `crashproof placement RESULTS_DIR [--out F]` | §19.5's view 4 and K3's two numbers (§30), per cell: where each fired fault landed across the seeds, a *mis-aimed* flag when the modal landing is outside the window, the ≥ 90 % in-window clause, and per `(variant, trigger)` the ≤ 10-point between-arms clause. Its own command because it reads the trial directories' `facts.json`, which a page folded from rows cannot. The runtime side is Keel's journal, LangGraph's checkpoints, or an engine's commit records (DBOS step completions, Temporal activity outcomes, Restate run completions) — from `facts.json`'s `sut_commits`, or from the export beside it for trials that predate the field. A fault the artefacts cannot place is counted as neither in nor out, and a clause with one in it prints *not computable* (a between-arms clause that two placed arms already fail prints FAIL). Exits 0: K3 is a kill criterion a person decides on, not an invariant. |
| `crashproof placement RESULTS_DIR --window` | `ambiguity_window_width` (§27's derived diagnostic, §29.2), which §25.3 predates: the same join over the **baseline** trials — World receipt → the runtime's outcome commit — as one row per `(runtime, non-PURE tool)` with median, IQR, n, what could not be placed and why, the commit record read and the clock it is on. A flag on `placement` rather than a command because it is the same join over the same directories. K4 reads the median; the kill rate and the out-of-window recovery check K4 also needs are not computed. |
| `crashproof agree --shim D --proxy D [--out F]` | §29.1's proxy/shim agreement column, as its own page rather than a column: the same cells paired on `(cell, seed)` across the two modes, safety verdicts and raw counts side by side, no p-value. `compare` cannot do it — it pairs on `spec_hash`, and the mode is in the hash — and it should not: agreement is a check on the harness, not a claim about runtimes. A twin whose sides differ in `keel_commit` or `config_pin` is printed with what differs and counted as neither agreeing nor disagreeing. |
| `keel reap` | One reaper sweep, printed. The predicate is the load-bearing statement of §8.4 and a worker runs it on a timer; running exactly one and seeing what it returns is how the predicate gets debugged without a stopwatch. |
| `keel worker --reaper/--no-reaper` | On by default. Off is how a trial establishes that the *reaper* orphaned a run rather than the successor's own claim racing it. |
| `keel reject\|cancel\|pause\|signal\|resume\|rebind --client-key K` | §25.2 gives `--client-key` to `approve` only; §24.1 gives `client_key` to `pause`, `cancel`, `signal`, `approve` and `reject`. Each of these commands is one inbox row, and the key is what makes a retried command the same row rather than a second one — `resume` and `rebind` included. |
| `keel replay --strict` | Declared in §10.9, not in §25.2's tree: a `PromptDrift` exits 6 as well as a nondeterministic step. |
| `inject`/`chaos --variant EXTERNAL\|IDEMPOTENT\|GATED` | The published bands. `GATED` is W5's, with `--workload approval_gated_deploy` or `approval_gated_deploy_pre`. Without the flag the developer form can only reach one of them, and the band is the axis the whole matrix is split on. |
| `demo --variant`, `--out`, `--canonical` | `--canonical` is what CI diffs; the other two are the ordinary escapes. `--variant` is `EXTERNAL\|IDEMPOTENT`: the demo runs `tool_chain_1_effect` only. |
| `world --host`, `--natural`, `--workload` | `--natural` is the second half of the `dedup` axis (a receiver that dedups on logical identity rather than on a presented key) and the IDEMPOTENT band is meaningless without it. |
| `report --mdd` | In §25.3's tree, but note it does not **gate** the tables: they print in every rendered report (§15.11 rule 6). The flag echoes them to stdout, which is what §28.6's demo line does with it. |
| `compare --a`/`--b`/`--strict`/`--seed`/`--out` | The shape departure (globs over cells instead of two files) is in the README's table with its reason. `--strict` is the §25.2 exit-code gate; `--seed` pins the bootstrap so a comparison is reproducible; `--out` writes the page to a file instead of stdout, which is how `scripts/render_reports.py` renders the published ones. |
| `verify --recheck`/`--placement`/`--effects` | Not in §25.3's tree, which gives `verify` only `--claims` and `--invariant`: §27.9's CLI row stages all three v1 (day 6) and §28.6 lists them as deliverables, and they were built there. |
| `verify` exit **9** | A local code beside §25.1's: some row of a `results.jsonl` has no `facts.json` in its trial directory, so it could not be re-verified — a clone's rows, or a trial from before the file existed. Not a verdict, and not 0 either: a publication gate that checked nothing must not go green. **7 outranks it.** |
| `verify --recheck` gates on drift or instability | §25.1 makes 7 an invariant FAIL for `verify`, and without `--recheck` that stands. Under `--recheck` the gate is the one §11 and §29.3 describe — the verdict is a function of the facts and matches the published row — so 7 means a verdict drifted from its row or the verifier gave two answers, and a FAIL that re-verifies unchanged prints as *published FAIL, reproduced unchanged* without gating. On a single trial directory `--recheck` gates only on determinism. |
| `bench` exit **2** on a key-source conflict | A matrix that declares an adapter at a `key_source` the adapter cannot present (`LangGraphAdapter.key_sources == {none}`) is refused before any trial: the rows record the key source in effect, and a page folded from them would contradict the matrix file it claims to be the result of. |
| matrix-file keys `timeout`, `landmark`, `model_landmark`, `approval_delay_ms`, `approval_duplicate_gap_ms` | Not in §25.3's example. `timeout` is the trial's terminal-state deadline; `landmark` and `model_landmark` aim tool and model faults; `approval_delay_ms` is how long the harness-as-human waits under `approval_delay`; `approval_duplicate_gap_ms` turns on §11.4 spec C's second, unkeyed approve that many ms after the first (unset, the human clicks once). Each lands on the fault spec and so in `spec_hash`. The example's `verifier` and `t_recover_s` are accepted and ignored: every row carries every invariant's verdict. |
