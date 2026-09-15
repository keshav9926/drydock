"""The proxy/shim agreement column (§29.1): a check on the harness, not a claim about runtimes.

Two sides, the same cells, the same seeds. A cell agrees when both instruments folded over the
shared seeds give the same safety verdicts and the same raw counts; a cell that differs names what
differs and never carries a p-value. A seed only one side ran is counted and never folded, and a
cell only one side can run — a proxy-only fault — is listed with the reason rather than scored.
"""

from __future__ import annotations

from typing import Any

from crashproof.report.agreement import agreement, render


def _row(cell: str, seed: int, mode: str, *, dup: int = 0, s1: str = "PASS", valid: bool = True) -> dict[str, Any]:
    adapter, config, variant, trigger = cell.split(".", 3)
    return {
        "cell_id": cell, "seed": seed, "mode": mode, "spec_hash": f"{mode}-{trigger}", "trial_id": f"t-{seed}",
        "workload": "w", "workload_variant": variant, "valid": valid,
        "key_source": "none", "recovery_mechanism": "self", "claims": {}, "config_pin": {},
        "verdicts": {"S1": s1, "S2": "PASS", "S3": "PASS", "S4": "PASS", "S5": "PASS", "L1": "PASS", "L2": "PASS"},
        "counterexamples": [],
        "metrics": {"recovery_rate": 1, "logical_correctness": 1, "replay_divergence": None,
                    "duplicate_effects": dup, "duplicate_receipts": dup, "missing_required": 0,
                    "lost_effects": 0, "recovery_latency_ms": 100.0, "raw": {}},
    }


KILL = "keel.default.EXTERNAL.kill@after:tool_effect"
PAUSE = "keel.default.EXTERNAL.pause_past_ttl@before:tool_call"
DROPPED = "keel.default.EXTERNAL.tool_dropped_response@after:tool_effect"


def test_agreement_pairs_on_cell_and_seed_and_names_what_differs() -> None:
    shim = [_row(KILL, s, "shim") for s in (7, 8, 9)] + [_row(PAUSE, s, "shim") for s in (7, 8)]
    proxy = [_row(KILL, s, "proxy") for s in (7, 8)] + [_row(PAUSE, 7, "proxy", dup=1), _row(PAUSE, 8, "proxy")]
    proxy.append(_row(DROPPED, 7, "proxy"))

    a = agreement(shim, proxy, shim_name="v0", proxy_name="p")
    by = {c.cell_id: c for c in a.cells}

    kill = by[KILL]
    assert kill.twin and kill.n == 2 and kill.shim_only == 1 and kill.proxy_only == 0
    assert kill.agrees and kill.differences() == []
    assert kill.shim is not None and kill.shim.n == 2, "folded over the shared seeds only"

    pause = by[PAUSE]
    assert pause.twin and pause.n == 2 and not pause.agrees
    assert pause.differences() == ["duplicate_effects 0/1", "duplicate_receipts 0/1"]

    dropped = by[DROPPED]
    assert not dropped.twin and dropped.proxy_only == 1 and dropped.shim is None
    assert a.disagreeing == [pause]


def test_a_bare_boundary_is_a_kill_and_a_column_one_side_never_had_is_not_a_disagreement() -> None:
    """Matrix v0 spells the T2 kill `after:tool_effect`; tier1p spells it `kill@after:tool_effect`;
    `Matrix._fault` reads both as the same fault, so the twins must find each other. And v0 ran
    before C1 existed: N/A on one side is a cell from before the column, not a difference."""
    v0 = _row("keel.default.EXTERNAL.after:tool_effect", 7, "shim")
    v0["verdicts"]["C1"] = "N/A"
    p = _row(KILL, 7, "proxy")
    p["verdicts"]["C1"] = "PASS"
    a = agreement([v0], [p])
    [kill] = a.cells
    assert kill.cell_id == KILL and kill.twin and kill.n == 1
    assert kill.agrees, kill.differences()


def test_a_void_trial_pairs_with_nothing_and_a_retake_pairs_with_its_retake() -> None:
    shim = [_row(KILL, 7, "shim", valid=False), _row(KILL, 7, "shim", dup=0)]
    proxy = [_row(KILL, 7, "proxy", dup=1), _row(KILL, 7, "proxy", dup=0)]  # the retake wins
    a = agreement(shim, proxy)
    [kill] = a.cells
    assert kill.n == 1 and kill.agrees, "last write wins on both sides, and the void row is gone"
    a = agreement([_row(KILL, 7, "shim", valid=False)], [_row(KILL, 7, "proxy")])
    [kill] = a.cells
    assert not kill.twin and kill.proxy_only == 1


def test_the_page_prints_both_numbers_and_never_a_p_value() -> None:
    shim = [_row(KILL, 7, "shim"), _row(PAUSE, 7, "shim")]
    proxy = [_row(KILL, 7, "proxy"), _row(PAUSE, 7, "proxy", dup=1), _row(DROPPED, 7, "proxy")]
    page = render(agreement(shim, proxy, shim_name="v0", proxy_name="p"))
    assert "| `" + KILL + "` | 1 |" in page and "| yes |" in page
    assert "**no** — duplicate_effects 0/1" in page
    assert "1 of 2 twinned cells agree" in page
    assert "proxy-only" in page and DROPPED in page
    assert "p-value" not in page.lower().replace("no p-values", "")
