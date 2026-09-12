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


def placement(facts: TrialFacts) -> list[dict[str, Any]]:
    """One row per fired fault: where the schedule aimed, and where it landed.

    The journal coordinates are the ones a reader needs to tell a kill *inside* an open attempt
    from one between two steps — the last committed seq before the fault, whatever attempt was
    open at that instant, and the first seq of the epoch that came after. The World's last receipt
    before and first receipt after put the same instant on the other side of the wire, which is
    the only way to see a kill that landed after the effect but before the journal heard.
    """
    events = sorted(facts.journal or [], key=lambda e: e["seq"])
    receipts = sorted(facts.world_receipts, key=lambda r: iso(r["ts"]))
    rows = []
    for fault in facts.faults:
        at = float(fault.get("trigger_observed_at") or 0.0)
        before = [e for e in events if at and iso(e["ts"]) <= at]
        after = [e for e in events if at and iso(e["ts"]) > at]
        open_attempt = _open_attempt(before)
        rows.append(
            {
                "fault_id": fault.get("fault_id", ""),
                "type": fault.get("type", ""),
                "boundary": fault.get("boundary", ""),
                "landmark": fault.get("landmark", ""),
                "occurrence": fault.get("occurrence", 0),
                "recovery_index": fault.get("recovery_index", 0),
                "executed": fault.get("executed", True),
                "trigger_observed_at": at,
                "last_seq_before": before[-1]["seq"] if before else None,
                "last_type_before": before[-1]["type"] if before else None,
                "open_step": open_attempt,
                "first_seq_after": after[0]["seq"] if after else None,
                # The successor's own first append. A fault with no RECOVERY_STARTED after it
                # either did not kill anything or nothing came back for the work it interrupted.
                "recovery_seq": next(
                    (e["seq"] for e in after if e["type"] == "RECOVERY_STARTED"), None
                ),
                "receipt_before": _receipt_label(
                    [r for r in receipts if at and iso(r["ts"]) <= at], -1
                ),
                "receipt_after": _receipt_label(
                    [r for r in receipts if at and iso(r["ts"]) > at], 0
                ),
            }
        )
    return rows


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
