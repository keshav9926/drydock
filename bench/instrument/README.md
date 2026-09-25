# The instrument's own measurements

The pages beside `bench/reports/` are pure functions of the committed rows, and CI re-renders them. These
are not: they read the per-trial directories (journals, receipt logs, fault logs, `facts.json`) or a
separate audit run, which stay on the machine that ran them. They are published as measured, with the
command that produced each.

| page | what it measures | produced by |
|---|---|---|
| [`placement_v1_w1_shim.md`](placement_v1_w1_shim.md) | K3 (§30): where every fired fault landed against each runtime's own commit record, per cell, and the between-arms clause — the release screening trials | `crashproof placement v1/combined_week2_w1_shim` |
| [`placement_v1_w1_shim_confirm.md`](placement_v1_w1_shim_confirm.md) | the same, over the confirmation tier's shim trials (n = 300) | `crashproof placement v1_w1_shim_confirm` |
| [`window_v1_w1_shim.md`](window_v1_w1_shim.md) | K4: `ambiguity_window_width`, World receipt → the runtime's outcome commit, over the baselines | `crashproof placement v1/combined_week2_w1_shim --window` |
| [`k11_audit.md`](k11_audit.md), [`k11_audit.jsonl`](k11_audit.jsonl) | K11(a): the World killed mid-request 500 times, and the log it left read back | `python scripts/k11_oracle_audit.py --seeds 300 --out bench/instrument/k11_audit.md` |

The placement pages cover every trial at `251e52d`, re-takes included (the page's row count is the
directory's, not the published cell's). The K11 audit ran on 2026-09-20 against the World as it is at
`251e52d`: `crashproof/world/services.py` last changed in `2c91744`, before that commit, and since
then only in a comment.
