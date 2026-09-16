"""The fault-analysis views (§19.5).

A trial's record is a three-way join — fault log × journal × World log — and a verdict is the last
line of it, not the whole of it. These are the two views that show the join itself, because a FAIL
nobody can read is a FAIL nobody will act on, and because one of them answers a question the
publication rule requires be asked of every *passing* cell too.

**Placement** answers "did the kill land where the schedule aimed?". §11.2 lets a trigger name a
landmark rather than an ordinal, which is what makes a fix have to be semantic; the price is that
the landmark has to be checked afterwards rather than assumed. A cell whose faults all fired at
the right boundary is a cell whose numbers mean what the column heading says. One that did not is
a mis-aimed schedule, which is a harness defect and never a finding about the runtime.

**The effect ledger** is one row per logical effect, with the journal on one side and the World on
the other. Journal columns are empty for a runtime that exposes no journal, and the verdicts in
those rows print `N/A` rather than PASS (§12.4) — the arm with the weakest guarantee does not get
the cleanest column for having nothing to check.

Both are pure over `TrialFacts`, so `crashproof verify` runs them on a directory and the report
embeds the same rows beside a counterexample without re-running anything.
"""

from __future__ import annotations

from typing import Any

from crashproof.verifier.invariants import AT_MOST_ONE_APPLIED, TrialFacts, iso

#: Events that open and close an attempt. `STEP_RESOLVED` closes one that was ambiguous, which is
#: the whole point of the band, so the ledger counts it as an outcome like any other.
OUTCOME_TYPES = ("STEP_COMPLETED", "STEP_FAILED", "STEP_AMBIGUOUS", "STEP_RESOLVED", "STEP_CANCELLED")


#: The boundaries K3's window is defined at: a tool call, seen from the World and from the SUT.
WINDOW_BOUNDARIES = ("before:tool_call", "after:tool_effect", "after:tool_return")


def placement(facts: TrialFacts, endpoints: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """One row per fired fault: where the schedule aimed, and where it landed.

    Each side of the join is read on its own clock, never across them:

    - **the journal, causally.** Journal timestamps are the store's clock and `trigger_observed_at`
      is the SUT host's, and a few milliseconds between them put a kill after a commit that could
      not have happened yet. So the cut is the fault row's `sut_ref` — the attempt the injector was
      inside when it fired (§11.7) — and the last committed record at firing time is that attempt's
      STEP_ATTEMPT_STARTED (§11.8: the outcome seq never exists for it). Without a `sut_ref` the
      journal columns are empty and `join` says why.
    - **checkpoints, where the runtime keeps them instead** (LangGraph): each checkpoint's `ts` is
      stamped in the SUT's process, on the same host clock as the trigger.
    - **the World**, whose receipt timestamps are the same host clock.

    `in_window` is K3's test (§30): the trigger fell between the World receipt of the aimed tool and
    the SUT's next committed record — for `before:tool_call`, before any receipt of it. `None` where
    one side is not observable, which is never counted as either. `where` is the histogram bucket
    (§19.5 view 4). `endpoints` maps the workload's tool names to World endpoints; without it the
    receipt side cannot be aimed and `in_window` is `None`.
    """
    events = sorted(facts.journal or [], key=lambda e: e["seq"])
    receipts = sorted(facts.world_receipts, key=lambda r: iso(r["ts"]))
    checkpoints = sorted(facts.sut_checkpoints or [], key=lambda c: iso(c["ts"]))
    rows = []
    for fault in facts.faults:
        at = float(fault.get("trigger_observed_at") or 0.0)
        cut, join = _cut(facts, events, fault.get("sut_ref") or {})
        before = [e for e in events if cut is not None and e["seq"] <= cut]
        after = [e for e in events if cut is not None and e["seq"] > cut]
        open_attempt = _open_attempt(before) if cut is not None else None
        last_ckpt = [c for c in checkpoints if at and iso(c["ts"]) <= at]
        next_ckpt = [c for c in checkpoints if at and iso(c["ts"]) > at]
        row = {
            "fault_id": fault.get("fault_id", ""),
            "type": fault.get("type", ""),
            "boundary": fault.get("boundary", ""),
            "landmark": fault.get("landmark", ""),
            "occurrence": fault.get("occurrence", 0),
            "recovery_index": fault.get("recovery_index", 0),
            "executed": fault.get("executed", True),
            "trigger_observed_at": at,
            "join": join,
            "last_seq_before": before[-1]["seq"] if before else None,
            "last_type_before": before[-1]["type"] if before else None,
            "open_step": open_attempt,
            "first_seq_after": after[0]["seq"] if after else None,
            # The successor's own first append. A fault with no RECOVERY_STARTED after it
            # either did not kill anything or nothing came back for the work it interrupted.
            "recovery_seq": next((e["seq"] for e in after if e["type"] == "RECOVERY_STARTED"), None),
            "checkpoint_before": _checkpoint_label(last_ckpt[-1]) if last_ckpt else None,
            "checkpoint_after": _checkpoint_label(next_ckpt[0]) if next_ckpt else None,
            "receipt_before": _receipt_label([r for r in receipts if at and iso(r["ts"]) <= at], -1),
            "receipt_after": _receipt_label([r for r in receipts if at and iso(r["ts"]) > at], 0),
        }
        row["where"] = _where(facts, events, row, open_attempt, last_ckpt, cut)
        row["in_window"] = _in_window(facts, events, fault, row, receipts, checkpoints, endpoints, cut)
        rows.append(row)
    return rows


def _cut(facts: TrialFacts, events: list[dict[str, Any]], ref: dict[str, Any]) -> tuple[int | None, str]:
    """The last committed seq at firing time, from `sut_ref`, and how it was found."""
    if facts.journal is None:
        return None, "no journal"
    if ref.get("seq") is not None:
        return int(ref["seq"]), f"sut_ref seq {ref['seq']}"
    if ref.get("step_index") is None:
        return None, "not placeable: no sut_ref (the journal's clock is not the trigger's)"
    started = next(
        (
            e for e in events
            if e["type"] == "STEP_ATTEMPT_STARTED"
            and e.get("step_index") == ref["step_index"]
            and e.get("attempt_no") == ref.get("attempt_no")
        ),
        None,
    )
    if started is None:
        return None, f"not placeable: sut_ref attempt {ref['step_index']}.{ref.get('attempt_no')} not in the journal"
    return started["seq"], f"sut_ref attempt {ref['step_index']}.{ref.get('attempt_no')} = seq {started['seq']}"


def _step_name(events: list[dict[str, Any]], step: int | None) -> str:
    intent = next(
        (e for e in events if e["type"] in ("STEP_INTENDED", "STEP_INTENT") and e.get("step_index") == step),
        None,
    )
    return str((intent or {}).get("body", {}).get("name") or "")


def _where(facts, events, row, open_attempt, last_ckpt, cut) -> str:
    if cut is not None:
        if open_attempt is None:
            return "between steps"
        step = int(open_attempt.split(".")[0])
        return f"step {open_attempt} {_step_name(events, step)}".rstrip()
    if facts.sut_checkpoints is not None:
        return f"after checkpoint step {last_ckpt[-1].get('step')}" if last_ckpt else "before the first checkpoint"
    return "unobservable"


def _in_window(facts, events, fault, row, receipts, checkpoints, endpoints, cut) -> bool | None:
    boundary, landmark = fault.get("boundary", ""), str(fault.get("landmark", ""))
    kind, _, tool = landmark.partition(":")
    if boundary not in WINDOW_BOUNDARIES or kind != "tool" or not endpoints or tool not in endpoints:
        return None
    at = row["trigger_observed_at"]
    mine = [r for r in receipts if r.get("endpoint") == endpoints[tool]]
    landed = [r for r in mine if iso(r["ts"]) <= at]
    if boundary == "before:tool_call":
        receipt_side = len(landed) < int(fault.get("occurrence") or 1)
    else:
        receipt_side = bool(landed)
    if cut is not None:
        # sut_ref pins the attempt the injector was inside, so nothing of it was committed after
        # the trigger that the journal could have placed before it. What is left to check is that
        # the attempt was the aimed tool's, still open.
        if row["open_step"] is None:
            return False
        return receipt_side and _step_name(events, int(row["open_step"].split(".")[0])) == tool
    if facts.sut_checkpoints is not None:
        if not receipt_side or boundary == "before:tool_call":
            return receipt_side
        receipt_ts = iso(landed[-1]["ts"])
        # Between the receipt and the next committed record: no checkpoint landed in between.
        return not any(receipt_ts < iso(c["ts"]) <= at for c in checkpoints)
    return None


def _checkpoint_label(checkpoint: dict[str, Any]) -> str:
    return f"step {checkpoint.get('step')} ({checkpoint.get('source') or '—'})"


def _open_attempt(before: list[dict[str, Any]]) -> str | None:
    """`step.attempt` of the attempt in flight when the fault landed, or None between steps.

    Read forward rather than backward: an attempt is open from its STARTED until that same step
    settles, and scanning from the end would stop at the last STARTED even when the step it
    belongs to completed three events later.
    """
    open_steps: dict[int, int] = {}
    for e in before:
        step = e.get("step_index")
        if step is None:
            continue
        if e["type"] == "STEP_ATTEMPT_STARTED":
            open_steps[step] = e.get("attempt_no") or 0
        elif e["type"] in OUTCOME_TYPES:
            open_steps.pop(step, None)
    if not open_steps:
        return None
    step, attempt = sorted(open_steps.items())[-1]
    return f"{step}.{attempt}"


def _receipt_label(receipts: list[dict[str, Any]], index: int) -> str | None:
    return receipts[index]["logical_identity"] if receipts else None


def effect_ledger(facts: TrialFacts) -> list[dict[str, Any]]:
    """One row per logical effect, judged individually.

    The trial-level verdicts answer "did this runtime violate S1 anywhere"; these answer "which
    effect, and what did each side of the wire see". Same predicates, per row — an effect the
    runtime committed and the World never applied is S2's counterexample, and printing it beside
    the receipt count is what turns a FAIL into a diagnosis.
    """
    # An effect the runtime started and never landed has no identity in the World at all. It is
    # still a row: a step that opened, did something unknowable and left no identity behind is
    # exactly what the EXTERNAL band is about, and a ledger that listed only successes would never
    # show one. The union runs the other way too — a receipt no effect row claims is a receipt
    # nothing in the runtime admits to, which is the shape S4 exists to catch.
    effects = {
        (e.get("external_ref") or f"(unresolved) {e.get('effect_key', '')}"): e
        for e in facts.sut_effects or []
    }
    identities = (
        set(facts.world_applied)
        | set(facts.sut_committed or ())
        | {r["logical_identity"] for r in facts.world_receipts if r.get("logical_identity")}
        | set(effects)
    )
    return [_row(identity, facts, effects.get(identity)) for identity in sorted(identities)]


def _row(identity: str, facts: TrialFacts, effect: dict[str, Any] | None) -> dict[str, Any]:
    applied = facts.world_applied.get(identity, 0)
    receipts = sum(1 for r in facts.world_receipts if r.get("logical_identity") == identity)
    # The row's own class, not the trial's. A workload runs a PURE read beside the EXTERNAL write
    # under test, and judging that read against the EXTERNAL claim would hold the strictest band to
    # the loosest promise — a PURE step applied twice is a violation of `effectively_once` whatever
    # the cell was aimed at.
    # Empty where the runtime named no class for it — a receipt no effect row claims is a row the
    # runtime told us nothing about, and stamping it with the cell's class would read as a fact.
    # The claim still has to come from somewhere to judge S1 at all, and the class under test is
    # the only one in scope for the cell, so that is what is applied and what prints.
    effect_class = (effect or {}).get("class") or ""
    claim = facts.claims.get(effect_class or facts.effect_class, "none")
    committed = facts.sut_committed is not None and identity in facts.sut_committed
    return {
        "identity": identity,
        "effect_key": (effect or {}).get("effect_key") or next(
            (r.get("effect_key") for r in facts.world_receipts
             if r.get("logical_identity") == identity and r.get("effect_key")),
            "",
        ),
        "effect_class": effect_class,
        "status": (effect or {}).get("status") or ("COMMITTED" if committed else ""),
        "resolution": (effect or {}).get("resolution"),
        "step_index": (effect or {}).get("step_index"),
        **_journal_seqs(facts, (effect or {}).get("step_index")),
        "world_receipts": receipts,
        "world_applied": applied,
        "claim": claim,
        # S1: applied at most once where the claim says so. An arm that claims at-least-once has
        # not violated anything by applying twice, and the count is printed either way.
        "S1": "PASS" if claim not in AT_MOST_ONE_APPLIED or applied <= 1 else "FAIL",
        # S2: committed by the runtime, present in the World. N/A where the runtime cannot say
        # what it committed — never a pass for having nothing to check.
        "S2": "N/A" if facts.sut_committed is None else ("PASS" if not committed or applied else "FAIL"),
        "S3": _s3(identity, facts),
        "S4": _s4(identity, facts),
        # C3 (the effects table agrees with the journal) arrives with the resolution ledger in v1;
        # absent rather than stubbed, so a column that is not computed cannot read as a pass.
        "C3": "N/A",
    }


def _s3(identity: str, facts: TrialFacts) -> str:
    if identity not in facts.required_effects:
        return "N/A"
    if facts.status != "COMPLETED":
        return "PASS"
    return "PASS" if facts.world_applied.get(identity, 0) >= 1 else "FAIL"


def _s4(identity: str, facts: TrialFacts) -> str:
    """A receipt for this effect with no attempt committed before it — the write-ahead rule seen
    from outside, one effect at a time."""
    if facts.journal is None:
        return "N/A"
    mine = [r for r in facts.world_receipts if r.get("logical_identity") == identity]
    if not mine:
        return "N/A"
    starts = [iso(e["ts"]) for e in facts.journal if e["type"] == "STEP_ATTEMPT_STARTED"]
    if not starts:
        return "FAIL"
    return "PASS" if min(starts) <= min(iso(r["ts"]) for r in mine) else "FAIL"


def _journal_seqs(facts: TrialFacts, step_index: int | None) -> dict[str, Any]:
    """Both keys always, empty where the runtime keeps no journal: a column that is missing and a
    column that is empty look the same to a reader, and only one of them crashes the renderer."""
    if facts.journal is None or step_index is None:
        return {"started_seq": None, "outcome_seq": None}
    mine = [e for e in facts.journal if e.get("step_index") == step_index]
    started = [e["seq"] for e in mine if e["type"] == "STEP_ATTEMPT_STARTED"]
    outcome = [e["seq"] for e in mine if e["type"] in OUTCOME_TYPES]
    return {
        "started_seq": min(started) if started else None,
        "outcome_seq": max(outcome) if outcome else None,
    }
