"""The verifier: a pure function from four logs to a verdict (§4.14, §12.4).

Nothing here reads a live process. Every input is a file in the trial directory, which is what
makes `crashproof verify <trial_dir>` possible and what makes the verdict reproducible: run it
twice on the same directory and the two outputs must be byte-identical.

Three rules govern how a verdict is written, and all three exist to stop the harness flattering
either side:

1. **An invariant whose inputs a runtime cannot supply is N/A, never PASS.** LangGraph's
   checkpoint store does not expose a per-attempt STARTED with a timestamp, so S4 is N/A there and
   the report says so. Missing inputs are named individually — a runtime can expose its committed
   set and not its timings — so the N/As are reported separately.
2. **Raw observations are always published.** `world_receipts`, `world_applied` and
   `sut_committed_set` are printed whatever the verdicts say.
3. **Verdicts are judged against the adapter's declared `claims`.** An adapter that declares
   `at_least_once` and produces one duplicate has not violated S1 — and the duplicate is still in
   the table. This is the Jepsen rule: you are held to what you claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Verdict = Literal["PASS", "FAIL", "N/A"]

#: Claims under which more than one *applied* effect is a violation rather than an honest cost.
AT_MOST_ONE_APPLIED = frozenset({"effectively_once", "exactly_once", "at_most_once"})

MVP_INVARIANTS = ("S1", "S2", "S3", "S4", "S5", "L1", "L2")
#: S7 arrives with approvals (v1, week 2). Listed apart from the MVP set for the same reason C1 is:
#: a cell that ran before the column existed is not missing it, and a workload with no approvals in
#: it prints N/A rather than a free PASS.
APPROVAL_INVARIANTS = ("S7",)
#: S6 arrives with cancellation (v1, week 2). Judged by journal order, never by the clock: a World
#: receipt for an effect whose attempt STARTED after CANCEL_ACKNOWLEDGED is a cancel not honoured.
#: No tier-1 cell issues a cancel (§14.3), so it prints N/A there with that reason.
CANCEL_INVARIANTS = ("S6",)
#: S8 arrives with delegation (v1, week 2): no child receipt after the parent's terminal event, and
#: every child terminal before its parent. It needs the *children's* journals beside the parent's,
#: and the collector reads one journal per trial — so the matrix prints N/A with that reason, and
#: the conformance cells, which hold every journal in the tree, judge it themselves.
DELEGATION_INVARIANTS = ("S8",)
#: C1 arrives with replay as a first-class mode (v1, day 5). Listed apart from the MVP set because
#: a cell that never had it is not missing a column — it is a cell from before the column existed.
CONSISTENCY_INVARIANTS = ("C1",)


@dataclass(slots=True)
class Finding:
    invariant: str
    verdict: Verdict
    detail: str = ""
    counterexample: dict[str, Any] | None = None


@dataclass(slots=True)
class Verdicts:
    findings: dict[str, Finding] = field(default_factory=dict)

    def add(self, invariant: str, verdict: Verdict, detail: str = "", counterexample: Any = None) -> None:
        self.findings[invariant] = Finding(invariant, verdict, detail, counterexample)

    def as_dict(self) -> dict[str, str]:
        return {name: f.verdict for name, f in self.findings.items()}

    def counterexamples(self) -> list[dict[str, Any]]:
        return [
            {"invariant": f.invariant, "detail": f.detail, **(f.counterexample or {})}
            for f in self.findings.values()
            if f.verdict == "FAIL"
        ]

    @property
    def failed(self) -> list[str]:
        return [n for n, f in self.findings.items() if f.verdict == "FAIL"]


@dataclass(slots=True)
class TrialFacts:
    """Everything a verdict may be computed from. Assembled by the collector; never a live read."""

    world_receipts: list[dict[str, Any]] = field(default_factory=list)
    world_applied: dict[str, int] = field(default_factory=dict)
    sut_committed: set[str] | None = None
    journal: list[dict[str, Any]] | None = None
    status: str = "UNKNOWN"
    expected_status: str = "COMPLETED"
    required_effects: tuple[str, ...] = ()
    claims: dict[str, str] = field(default_factory=dict)
    effect_class: str = "EXTERNAL"
    faults: list[dict[str, Any]] = field(default_factory=list)
    restarts: int = 0
    max_recoveries: int = 3
    timed_out: bool = False
    reached_terminal: bool = False
    #: The adapter's own replay check, or `None` where the runtime offers none. Computed by the
    #: collector, because this module is a pure function and replaying a journal is I/O.
    replay: dict[str, Any] | None = None
    #: The runtime's effect ledger, where it keeps one. No verdict reads it — §19.5's per-effect
    #: view does, and a view over a trial is a view over its facts.
    sut_effects: list[dict[str, Any]] | None = None
    #: The workload's approval-gated tools, name → World endpoint. S7 is judged on these: an applied
    #: gated effect with no approval behind it is invisible to a check driven by the journal alone.
    gated_tools: dict[str, str] = field(default_factory=dict)
    #: The runtime's checkpoints, where it keeps checkpoints instead of a journal: `{checkpoint_id,
    #: ts, step, source}`, `ts` stamped in the SUT's own process. No verdict reads them; the
    #: placement view does, because they are the one committed record on the trigger's clock.
    sut_checkpoints: list[dict[str, Any]] | None = None
    #: An engine's own record of each step's outcome committing, where it keeps neither a Keel-shaped
    #: journal nor checkpoints (DBOS, Temporal, Restate): `{ts, step, name, tool, source}`, read out of
    #: its export by `views.commits_from_export`. No verdict reads them; the placement view and
    #: `ambiguity_window_width` do.
    sut_commits: list[dict[str, Any]] | None = None


def dump(facts: TrialFacts) -> dict[str, Any]:
    """The facts as JSON, so `crashproof verify <trial_dir>` has every input it needs in a file.

    The verifier being pure over the trial directory is what makes a verdict re-checkable at all
    (§3.5, §19.5) — and it is only true if the directory actually holds the facts rather than the
    live objects they were read from. Sets and tuples are written sorted and as lists, because a
    re-check that is byte-identical only when the iteration order happens to repeat is not a
    re-check of anything.
    """
    from dataclasses import fields

    out = {f.name: getattr(facts, f.name) for f in fields(facts)}
    out["sut_committed"] = None if facts.sut_committed is None else sorted(facts.sut_committed)
    out["required_effects"] = list(facts.required_effects)
    return out


def load(doc: dict[str, Any]) -> TrialFacts:
    from dataclasses import fields

    known = {f.name for f in fields(TrialFacts)}
    kwargs = {k: v for k, v in doc.items() if k in known}
    if kwargs.get("sut_committed") is not None:
        kwargs["sut_committed"] = set(kwargs["sut_committed"])
    kwargs["required_effects"] = tuple(kwargs.get("required_effects") or ())
    return TrialFacts(**kwargs)


def verify(facts: TrialFacts) -> Verdicts:
    v = Verdicts()
    _s1_no_duplicate_applied_effect(facts, v)
    _s2_no_lost_effect(facts, v)
    _s3_no_phantom_completion(facts, v)
    _s4_no_unjournaled_effect(facts, v)
    _s5_monotonic_step_state(facts, v)
    _l1_recovery_completes(facts, v)
    _l2_bounded_recoveries(facts, v)
    _s6_cancel_honoured(facts, v)
    _s7_approval_binding(facts, v)
    _s8_children_before_parent(facts, v)
    _c1_replay_determinism(facts, v)
    return v


def cancel_ordering(f: TrialFacts) -> dict[str, Any] | None:
    """§14.3 S6: each receipt placed against the first CANCEL_ACKNOWLEDGED by journal order. A
    receipt maps to its effect through the runtime's ledger (World label -> step), and the step's
    latest STEP_ATTEMPT_STARTED seq decides: after the acknowledgement is a violation, before it is
    `in_flight_at_cancel` -- allowed, and printed raw. None when there is nothing to order."""
    if f.journal is None:
        return None
    acks = [e["seq"] for e in f.journal if e["type"] == "CANCEL_ACKNOWLEDGED"]
    if not acks:
        return None
    ack = min(acks)
    step_of = {row["external_ref"]: row["step_index"] for row in f.sut_effects or [] if row.get("external_ref")}
    started: dict[int, int] = {}
    for e in f.journal:
        if e["type"] == "STEP_ATTEMPT_STARTED" and e.get("step_index") is not None:
            started[e["step_index"]] = max(started.get(e["step_index"], 0), e["seq"])
    after, in_flight, unplaced = [], [], []
    for r in f.world_receipts:
        step = step_of.get(r["logical_identity"])
        if step is None or step not in started:
            unplaced.append(r["logical_identity"])
        elif started[step] > ack:
            after.append(r["logical_identity"])
        else:
            in_flight.append(r["logical_identity"])
    return {"ack_seq": ack, "after": after, "in_flight_at_cancel": in_flight, "unplaced": unplaced}


def _s6_cancel_honoured(f: TrialFacts, v: Verdicts) -> None:
    """No World receipt for an effect whose STARTED seq is greater than the CANCEL_ACKNOWLEDGED seq
    (§12.4). Receipts whose attempt started before the acknowledgement were in flight when the run
    was told, and are allowed. N/A for a runtime that exposes no acknowledgement ordering, and for a
    trial in which nothing was cancelled."""
    if f.journal is None:
        v.add("S6", "N/A", "the runtime exposes no cancel-acknowledgement ordering")
        return
    order = cancel_ordering(f)
    if order is None:
        v.add("S6", "N/A", "nothing was cancelled in this trial")
        return
    if order["after"]:
        v.add("S6", "FAIL", "an effect started after the cancel was acknowledged reached the World", order)
        return
    v.add("S6", "PASS", f"{len(order['in_flight_at_cancel'])} receipt(s) in flight at cancel, none after it")


def approval_binding_violations(f: TrialFacts) -> int | None:
    """§14.3 ABV = sum over approvals of max(0, applied_gated(a) - 1), plus the gated effects applied
    with no GRANTED approval. The count S7 judges, as a number. None where S7 has nothing to count."""
    if f.journal is None:
        return None
    requested = [e for e in f.journal if e["type"] == "APPROVAL_REQUESTED"]
    gated = set(f.gated_tools.values())
    if not requested and not gated:
        return None
    decisions: dict[str, str] = {}
    for e in f.journal:
        if e["type"] == "APPROVAL_DECIDED":
            decisions.setdefault(str(e["body"]["approval_id"]), str(e["body"].get("decision")))
    labels = {row.get("effect_key"): row.get("external_ref") for row in f.sut_effects or []}
    violations, bound, grants_unlabelled = 0, set(), 0
    for e in requested:
        key = e["body"].get("binds_effect_key")
        if not key:
            continue
        granted = decisions.get(str(e["body"]["approval_id"])) == "granted"
        label = labels.get(key)
        if label is None:
            grants_unlabelled += granted
            continue
        bound.add(label)
        applied = f.world_applied.get(label, 0)
        violations += max(0, applied - 1) if granted else applied
    stray = sum(
        n for label, n in f.world_applied.items()
        if n >= 1 and label not in bound and str(label).rpartition("#")[0] in gated
    )
    return violations + max(0, stray - grants_unlabelled)


def _s8_children_before_parent(f: TrialFacts, v: Verdicts) -> None:
    """No child World receipt after the parent's terminal event; every child terminal before its
    parent (§12.4). The parent's journal names its children — CHILD_SPAWNED, CHILD_COMPLETED — but
    "the child was terminal first" is a statement about the *children's* timestamps, and the
    collector supplies one journal per trial. N/A says so rather than passing on the parent alone;
    the conformance cells hold the whole tree and judge it there.
    """
    if f.journal is None:
        v.add("S8", "N/A", "the runtime exposes no journal")
        return
    if not any(e["type"] == "CHILD_SPAWNED" for e in f.journal):
        v.add("S8", "N/A", "this workload delegates nothing")
        return
    v.add("S8", "N/A", "needs the children's journals; the collector supplies the parent's only")


# --- consistency -------------------------------------------------------------
def _c1_replay_determinism(f: TrialFacts, v: Verdicts) -> None:
    """VERIFY reproduces the step sequence, and for a terminal run the projection hash (§15).

    This is the invariant that makes "it recovered" mean something stronger than "it finished".
    A run can end COMPLETED with the right world and still have taken a path its own journal does
    not describe — and every other invariant here would pass it. C1 is the one that re-executes the
    program against the recorded past and insists the two agree.

    N/A where the runtime offers no replay: a framework that keeps no journal has nothing to
    reproduce, and calling that a pass would let the arm with the weakest guarantee score the
    cleanest column.
    """
    if f.replay is None:
        v.add("C1", "N/A", "the runtime exposes no replay mode")
        return
    if not f.replay.get("ok"):
        v.add(
            "C1",
            "FAIL",
            f.replay.get("error") or "VERIFY did not reproduce the journal",
            {"diff": f.replay.get("diff"), "projection": f.replay.get("projection_hash")},
        )
        return
    if f.replay.get("projection_matches") is False:
        v.add("C1", "FAIL", "terminal projection hash differs from the trial's",
              {"projection": f.replay.get("projection_hash")})
        return
    stopped = f.replay.get("stopped")
    v.add("C1", "PASS", f"replayed {f.replay.get('replayed_steps')} steps"
          + (f"; stopped at {stopped}" if stopped else ""))


def _s7_approval_binding(f: TrialFacts, v: Verdicts) -> None:
    """Every approval-gated effect has exactly one GRANTED approval; ≤ 1 applied effect per
    approval (§12.4). Judged per `approval_id`, and against the World:

    - an approval decided more than once fails;
    - a gated tool resolved by `assume_failed` fails — it re-fires under one approval (§9.4);
    - more than one applied effect under one approval fails. A runtime can decide correctly and
      still apply the gated effect twice, and no other invariant sees it: there is no duplicate
      *key*, the second application is a different effect that nobody approved;
    - a bound effect applied when its approval was rejected, expired or never decided fails;
    - a gated tool applied with no approval to account for it fails. That is the violation that
      matters most, and a check driven by the APPROVAL_REQUESTED events alone cannot see it — so
      the workload's gated tools drive it, not the journal.

    The binding is read through the runtime's own effect ledger: `binds_effect_key` names the
    effect row, the row names its World label (`external_ref`), and the World says how often that
    label was applied. A bound effect with no label in the ledger (never started, or started and
    never resolved) is accounted for on the gated endpoint instead: each GRANTED approval may
    account for one application there, and anything beyond that is unapproved.
    """
    if f.journal is None:
        v.add("S7", "N/A", "the runtime exposes no journal with APPROVAL_REQUESTED/DECIDED to bind an "
              "applied effect to")
        return
    requested = [e for e in f.journal if e["type"] == "APPROVAL_REQUESTED"]
    gated_endpoints = set(f.gated_tools.values())
    if not requested and not gated_endpoints:
        v.add("S7", "N/A", "this workload gates nothing")
        return

    decisions: dict[str, list[str]] = {}
    for e in f.journal:
        if e["type"] == "APPROVAL_DECIDED":
            decisions.setdefault(str(e["body"]["approval_id"]), []).append(str(e["body"].get("decision")))
    twice = {aid: len(d) for aid, d in decisions.items() if len(d) > 1}
    if twice:
        v.add("S7", "FAIL", "an approval was decided more than once", {"approval_id": twice})
        return

    gated_steps = {e["body"]["step_index"] + 1 for e in requested if e["body"].get("binds_effect_key")}
    for e in f.journal:
        if (
            e["type"] == "STEP_RESOLVED"
            and e.get("step_index") in gated_steps
            and e["body"].get("method") == "assume_failed"
        ):
            v.add("S7", "FAIL", "a gated tool resolved by assume_failed, which re-fires under one "
                  "approval", {"step_index": e["step_index"]})
            return

    labels = {row.get("effect_key"): row.get("external_ref") for row in f.sut_effects or []}
    over, ungranted, bound, unlabelled_grants = {}, {}, set(), 0
    for e in requested:
        key = e["body"].get("binds_effect_key")
        if not key:
            continue  # a bare `ctx.approve` is a durable wait and binds nothing
        aid = str(e["body"]["approval_id"])
        decision = (decisions.get(aid) or [None])[0]
        label = labels.get(key)
        if label is None:
            unlabelled_grants += decision == "granted"
            continue
        bound.add(label)
        applied = f.world_applied.get(label, 0)
        if applied > 1:
            over[aid] = {label: applied}
        if applied >= 1 and decision != "granted":
            ungranted[aid] = {"decision": decision or "undecided", label: applied}
    if over:
        v.add("S7", "FAIL", "more than one applied effect under one approval", {"approval_id": over})
        return
    if ungranted:
        v.add("S7", "FAIL", "a bound effect applied without a GRANTED approval", {"approval_id": ungranted})
        return

    stray = {
        label: n
        for label, n in f.world_applied.items()
        if n >= 1 and label not in bound and str(label).rpartition("#")[0] in gated_endpoints
    }
    if sum(stray.values()) > unlabelled_grants:
        v.add("S7", "FAIL", "a gated tool applied with no GRANTED approval bound to it",
              {"applied": stray, "unaccounted_grants": unlabelled_grants})
        return
    v.add("S7", "PASS", f"{len(requested)} approval(s), each decided at most once; every applied "
          "gated effect granted, at most once")


# --- safety ------------------------------------------------------------------
def _s1_no_duplicate_applied_effect(f: TrialFacts, v: Verdicts) -> None:
    """Per logical effect, World-applied count ≤ 1 when the claim says so. The raw count is
    published either way, because a duplicate an adapter *claimed* is still a duplicate."""
    claim = f.claims.get(f.effect_class, "none")
    duplicates = {label: n for label, n in f.world_applied.items() if n > 1}
    if claim not in AT_MOST_ONE_APPLIED:
        v.add("S1", "PASS", f"claim={claim}; duplicates reported raw: {duplicates or 'none'}")
        return
    if duplicates:
        v.add("S1", "FAIL", f"claim={claim} but applied more than once", {"applied": duplicates})
        return
    v.add("S1", "PASS", f"claim={claim}")


def _s2_no_lost_effect(f: TrialFacts, v: Verdicts) -> None:
    """Every effect the SUT reports COMMITTED exists in the World. A runtime that cannot say what
    it committed gets N/A — never a pass for having nothing to check."""
    if f.sut_committed is None:
        v.add("S2", "N/A", "the runtime exposes no per-effect committed set")
        return
    lost = sorted(label for label in f.sut_committed if label not in f.world_applied)
    if lost:
        v.add("S2", "FAIL", "committed by the runtime, absent from the World", {"lost": lost})
        return
    v.add("S2", "PASS", f"{len(f.sut_committed)} committed, all present")


def _s3_no_phantom_completion(f: TrialFacts, v: Verdicts) -> None:
    """COMPLETED implies every effect the workload requires actually exists. Claiming to have done
    the job without having done it is a safety violation, not a low score."""
    if f.status != "COMPLETED":
        v.add("S3", "PASS", f"status={f.status}; nothing was claimed")
        return
    missing = sorted(r for r in f.required_effects if f.world_applied.get(r, 0) < 1)
    if missing:
        v.add("S3", "FAIL", "COMPLETED without the effects it required", {"missing": missing})
        return
    v.add("S3", "PASS", f"required {list(f.required_effects)} all applied")


def _s4_no_unjournaled_effect(f: TrialFacts, v: Verdicts) -> None:
    """Every World receipt has a prior STEP_ATTEMPT_STARTED with an earlier timestamp. This is the
    write-ahead rule seen from outside: an action taken in the world with no record that it was
    ever attempted is the one failure the design refuses to have."""
    if f.journal is None:
        v.add("S4", "N/A", "the runtime exposes no per-attempt STARTED with timestamps")
        return
    starts = sorted(iso(e["ts"]) for e in f.journal if e["type"] == "STEP_ATTEMPT_STARTED")
    if not f.world_receipts:
        v.add("S4", "PASS", "no receipts to cover")
        return
    earliest = starts[0] if starts else None
    unjournaled = [
        r for r in f.world_receipts
        if earliest is None or iso(r["ts"]) < earliest
    ]
    if unjournaled:
        v.add("S4", "FAIL", "a receipt with no attempt committed before it",
              {"receipts": [r["logical_identity"] for r in unjournaled]})
        return
    v.add("S4", "PASS", f"{len(f.world_receipts)} receipts, all covered by {len(starts)} attempts")


def _s5_monotonic_step_state(f: TrialFacts, v: Verdicts) -> None:
    """Completed steps never regress. Half of this is enforced by partial unique indexes in the
    database; the half that is not — "no attempt after a completion" — is checked here."""
    if f.journal is None:
        v.add("S5", "N/A", "the runtime exposes no step lifecycle")
        return
    settled: dict[int, str] = {}
    for e in f.journal:
        step, kind = e.get("step_index"), e["type"]
        if step is None:
            continue
        if kind in ("STEP_COMPLETED", "STEP_RESOLVED") and e["body"].get("resolution") != "RESOLVED_FAILED":
            settled[step] = kind
        elif kind == "STEP_ATTEMPT_STARTED" and step in settled:
            v.add("S5", "FAIL", "an attempt after the step was settled",
                  {"step_index": step, "seq": e["seq"]})
            return
    v.add("S5", "PASS", f"{len(settled)} settled steps, none reopened")


# --- liveness ----------------------------------------------------------------
def _l1_recovery_completes(f: TrialFacts, v: Verdicts) -> None:
    """After the last injected fault the run reaches a terminal — or workload-legitimate waiting —
    state within the arm's T_recover. A run that is legitimately suspended because an ambiguity was
    surfaced has recovered; that is what surfacing is for."""
    if f.timed_out:
        v.add("L1", "FAIL", f"no terminal state within the timeout; status={f.status}")
        return
    legitimate = {"COMPLETED", "FAILED", "CANCELLED"} | {f.expected_status}
    if f.status in legitimate:
        v.add("L1", "PASS", f"status={f.status}")
        return
    v.add("L1", "FAIL", f"status={f.status}, expected one of {sorted(legitimate)}")


def _l2_bounded_recoveries(f: TrialFacts, v: Verdicts) -> None:
    """A runtime that keeps restarting is not recovering. The bound is the schedule's."""
    if f.restarts > f.max_recoveries:
        v.add("L2", "FAIL", f"{f.restarts} restarts exceeds max_recoveries={f.max_recoveries}")
        return
    v.add("L2", "PASS", f"{f.restarts}/{f.max_recoveries} restarts")


def iso(ts: Any) -> float:
    """World receipts carry unix seconds; journal events carry ISO strings. One scale here."""
    if isinstance(ts, (int, float)):
        return float(ts)
    from datetime import datetime

    return datetime.fromisoformat(str(ts)).timestamp()
