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


def verify(facts: TrialFacts) -> Verdicts:
    v = Verdicts()
    _s1_no_duplicate_applied_effect(facts, v)
    _s2_no_lost_effect(facts, v)
    _s3_no_phantom_completion(facts, v)
    _s4_no_unjournaled_effect(facts, v)
    _s5_monotonic_step_state(facts, v)
    _l1_recovery_completes(facts, v)
    _l2_bounded_recoveries(facts, v)
    return v


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
    starts = sorted(_iso(e["ts"]) for e in f.journal if e["type"] == "STEP_ATTEMPT_STARTED")
    if not f.world_receipts:
        v.add("S4", "PASS", "no receipts to cover")
        return
    earliest = starts[0] if starts else None
    unjournaled = [
        r for r in f.world_receipts
        if earliest is None or _iso(r["ts"]) < earliest
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


def _iso(ts: Any) -> float:
    """World receipts carry unix seconds; journal events carry ISO strings. One scale here."""
    if isinstance(ts, (int, float)):
        return float(ts)
    from datetime import datetime

    return datetime.fromisoformat(str(ts)).timestamp()
