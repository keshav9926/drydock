# CLI ledger — every difference between §25's command trees and what is built

§25.2 and §25.3 declare two command trees. This is every place the code differs from them, in both
directions, with the reason. It exists for the same rule the verifier runs on: **a missing input is
named individually, never folded into a pass and never omitted from the grid** (§15.11). A command
tree is a contract, and an undocumented gap in one is the same kind of defect as an `N/A` printed as
`PASS`.

Commands are in the [README's departures table](../README.md#layout-and-where-it-departs-from-231).
This file is the flag-level detail.

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
| `crashproof export` | §25.3 (v1) | Parquet/CSV over the same rows. Nothing in phases 1–7 reads it and `results.jsonl` is already `grep`- and `jq`-able; it arrives with DuckDB in week 3, or not at all. |
| `keel run --model provider:model` | §25.2 | Needs the real provider. Real-model validation is its own mode with its own contamination rules (§14.6), not a flag on the scripted path. |
| `keel run --seed N` | §25.2 | The scripted provider is deterministic. There is nothing to seed until a real model is in the loop, and a flag that seeds nothing is worse than no flag. |
| `keel run --args-file F` | §25.2 | `--args "$(cat f)"` is the same thing in the shell that is already open. |
| `keel worker --concurrency N` | §25.2 | v1. One lease per worker is the MVP model; the matrix's `worker_count` is separate **processes**, which is what the `pause_past_ttl` cell actually needs. |
| `keel events --raw` | §25.2 | Built as `--json`, which is the spelling §28.5's own fixture-capture line uses (`keel events $RUN --json > tests/journals/<name>.jsonl`). One flag, one name. |
| `keel watch` | §25.2 (v1, day 7) | **Cut**, per §28.7's own cut line — not pending. `keel events --follow` shows the same BEFORE CRASH / AFTER RESTART split, in the event stream where it already lives. |
| `keel rebind` | §25.2 (v1) | Needs `MODEL_BINDING_CHANGED` and a live MODEL step to affect. Week 2. |
| `keel fork` | §25.2 (v1) | Cut from phase 5 by §28.5's own cut line; week 3 with the counterfactual story. |

### Built since this file was written

`keel cancel`, `keel pause`, `keel signal`, `keel approve` and `keel reject` are declared in §25.2
and now exist, each as one row in the signals inbox and nothing else. `keel resume` moved onto the same path: the MVP's direct
conditional UPDATE of `runs.runnable_at` was **deleted**, not kept beside it — §27.2 said *replaced*,
and two ways to influence a run is one more than the fence can defend. `JournalBackend.mark_runnable`
went with it.

Delegation (§17) adds no command: §25.2 declares none, and a parent's children are reached the
way §17.3 allows — through the `delegations` rows, which `keel show <parent>` now prints as a
`children` table (ordinal, retry, child run id, role, status, reserved, settled). A child is a run,
so `keel show <child>`, `keel events <child>` and `keel cancel <child>` already work on it; a
`cancel` of the parent propagates to every open child on its own (§7.6.2).

## Built, not declared

| Surface | Why |
|---|---|
| `crashproof workloads` | One table of the workload declaration — variant, `key_source`, tool, class, endpoint, required effects. It is what an adapter author and a matrix reader both have to check, over machinery `chaos` already loads. |
| `keel reap` | One reaper sweep, printed. The predicate is the load-bearing statement of §8.4 and a worker runs it on a timer; running exactly one and seeing what it returns is how the predicate gets debugged without a stopwatch. |
| `keel worker --reaper/--no-reaper` | On by default. Off is how a trial establishes that the *reaper* orphaned a run rather than the successor's own claim racing it. |
| `inject`/`chaos --variant EXTERNAL\|IDEMPOTENT` | The two published bands. Without it the developer form can only reach one of them, and the band is the axis the whole matrix is split on. |
| `demo --variant`, `--out`, `--canonical` | `--canonical` is what CI diffs; the other two are the ordinary escapes. |
| `world --host`, `--natural`, `--workload` | `--natural` is the second half of the `dedup` axis (a receiver that dedups on logical identity rather than on a presented key) and the IDEMPOTENT band is meaningless without it. |
| `report --mdd` | In §25.3's tree, but note it does not **gate** the tables: they print in every rendered report (§15.11 rule 6). The flag echoes them to stdout, which is what §28.6's demo line does with it. |
| `compare --a`/`--b`/`--strict`/`--seed` | The shape departure (globs over cells instead of two files) is in the README's table with its reason. `--strict` is the §25.2 exit-code gate; `--seed` pins the bootstrap so a comparison is reproducible. |
| `verify --recheck`/`--placement`/`--effects` | Declared in §25.3 as v1 (day 6) and built there. Listed here only because the base command is v1 too. |
