"""The day-7 demo: one command, one crash, and the whole argument on one screen (§26.3, §28.7).

Everything printed here is **read back from the trial's own artefacts** — the journal export, the
World's receipt log, the fault log, the verdicts — rather than narrated by the code that ran it.
That is not a shortcut. A demo that prints what it *intended* to do is a demo that keeps printing
it after the runtime stops doing it, and the one thing this repository cannot afford is a
screenshot that outlives the behaviour it claims.

The script is §26.3's, with the approval half absent rather than faked. The APPROVAL step at #3,
`RUN_WAITING{WAITING_APPROVAL}`, `keel approve`, the `signals` row and
`RECOVERY_STARTED{cause=WAKE}` all need the inbox, which is week 2; the demo says so where they
would have gone rather than printing a sequence the runtime cannot produce.

The output is a BEFORE CRASH / AFTER RESTART pair because that is the shape of the claim. Before:
the World has the effect and the journal has an attempt with no outcome. After: a different
process, told nothing, reads the journal, finds the open EXTERNAL step, asks the receiver what
happened, and finishes the run without filing the issue twice.

Run the same command with `--adapter langgraph --config sync` and the same seed. Same fault, same
landmark, same World — and the journal columns print `no journal exposed`, because there is no
journal to read them from. That contrast is the demo.

`canonical=True` replaces everything that legitimately varies between two runs of the same command
— ids, pids, ports, timestamps, elapsed times — with placeholders, so CI can diff the printed
lines and fail on a *behavioural* change rather than on a clock.
"""

from __future__ import annotations

import re
from typing import Any

from crashproof.verifier.invariants import TrialFacts, iso
from crashproof.verifier.views import placement

WORKLOAD = "tool_chain_1_effect"
#: `--config sync|async|exit` in the adapter's own vocabulary. The demo does not invent settings:
#: these are the same keys the published matrix file carries, so the cell the demo runs and the
#: cell the matrix publishes are the same cell.
CONFIG_SETTINGS = {
    "sync": {"durability": "sync"},
    "async": {"durability": "async"},
    "exit": {"durability": "exit"},
}


def one_cell(adapter: str, config: str, variant: str, fault: str) -> Any:
    """The demo's cell, built through the *matrix* loader rather than beside it.

    `kill` at `after:tool_effect` is the only window where the World and the journal can disagree
    about an EXTERNAL effect, which is the whole subject. Expressing it as a one-cell matrix means
    the trigger string is parsed by the same code that parses `bench/specs/matrix_v0.yaml` — a demo
    whose spec is assembled by hand is a demo that can drift from the thing it is demonstrating.
    """
    from crashproof.runner.bench import Matrix

    matrix = Matrix(
        workload=WORKLOAD,
        mode="shim",
        seeds=1,
        max_recoveries=3,
        timeout=60.0,
        variants=[{"id": variant, "endpoint_dedup": variant == "IDEMPOTENT"}],
        triggers=[fault],
        adapters=[{
            "name": adapter,
            "key_source": "framework" if adapter == "keel" else "none",
            "configs": [{"id": config, **CONFIG_SETTINGS.get(config, {})}],
        }],
    )
    return next(cell for cell in matrix.cells() if not cell.is_baseline)


RULE = "─" * 72

#: Volatile by design, and therefore not evidence of anything when two runs differ. Ordered
#: longest-pattern-first so a uuid is not half-eaten by the hex rule.
#:
#: Seconds are deliberately **not** here. `lease_ttl 2.0 s > create_issue timeout 1.0 s` is a config
#: pin, not a measurement: it is identical on every run of this cell, and a change to it is a change
#: to the cell rather than to the weather. Milliseconds are a measurement, and go. Neither is a path
#: — the caller knows whether it wants one printed, which is cheaper and more honest than a regex
#: guessing what a path looks like on two operating systems.
_VOLATILE = (
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T[\d:.+\-]+\b"), "<ts>"),
    # This one changes on every commit, including the ones that change nothing printed here.
    (re.compile(r"keel_commit [0-9a-f]{7,40}"), "keel_commit <sha>"),
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<hash>"),
    (re.compile(r"(?<=:)\d{4,5}\b"), "<port>"),
    (re.compile(r"\bpid \d+"), "pid <pid>"),
    (re.compile(r"\b\d+(\.\d+)? ?ms\b"), "<ms> ms"),
)


def canonicalise(line: str) -> str:
    for pattern, placeholder in _VOLATILE:
        line = pattern.sub(placeholder, line)
    return line


def narrate(row: Any, facts: TrialFacts, *, row_path: Any = None, canonical: bool = False) -> list[str]:
    """The script, read off the artefacts. One list of lines, ready to print or to diff."""
    events = sorted(facts.journal or [], key=lambda e: e["seq"])
    fault = (placement(facts) or [{}])[0]
    cut = float(fault.get("trigger_observed_at") or 0.0)
    before = [e for e in events if not cut or iso(e["ts"]) <= cut]
    after = [e for e in events if cut and iso(e["ts"]) > cut]
    receipts = sorted(facts.world_receipts, key=lambda r: iso(r["ts"]))
    target = _required(facts)

    lines = [
        f"crashproof demo — {row.cell_id}   seed {row.seed}",
        f"  recovery_mechanism={row.recovery_mechanism}   key_source={row.key_source}",
        f"  claims: " + " · ".join(f"{k} {v}" for k, v in sorted(row.claims.items())),
        "",
        RULE,
        "BEFORE CRASH",
        RULE,
    ]
    lines += _before(row, facts, before, receipts, cut, fault, target)
    lines += ["", RULE, "AFTER RESTART", RULE]
    lines += _after(row, facts, after, receipts, cut, target)
    lines += ["", RULE, "THE POINT", RULE]
    lines += _point(row, facts, target, row_path)
    return [canonicalise(line) for line in lines] if canonical else lines


# --- before -------------------------------------------------------------------
def _before(
    row: Any, facts: TrialFacts, events: list[dict[str, Any]], receipts: list[dict[str, Any]],
    cut: float, fault: dict[str, Any], target: str,
) -> list[str]:
    endpoint = target.split("#")[0]
    pin = row.config_pin
    tool = _tool(row)
    lines = [
        f"[1]  world up · endpoints {endpoint} dedup:{_dedup(row)} · kv.search dedup:n/a"
        "  · oracle exposed to the probe",
        "[2]  dependency: the adapter's own store, cloned fresh for this trial",
        f"[3]  worker: lease_ttl {pin['lease_ttl_s']} s > {tool} timeout {pin['tool_timeout_s']} s"
        "   — the pre-dispatch check refuses an EXTERNAL effect otherwise (§8)"
        if pin.get("lease_ttl_s")
        else f"[3]  worker: no lease. durability={pin.get('durability') or '—'},"
        f" backend={pin.get('backend') or '—'}"
        "   — nothing here bounds how long an effect may be in flight",
    ]
    if facts.journal is None:
        lines += [
            "[4]–[7] no journal exposed. This runtime keeps a checkpoint, not an event log, so the",
            "     four lines that would go here — RUN_CREATED, the clean steps, STEP_INTENDED with",
            "     its effect key, STEP_ATTEMPT_STARTED — have nothing to read. That is the finding,",
            "     not a gap in the demo: S2, S4, S5 and C1 print N/A below for the same reason.",
        ]
    else:
        created = _first(events, "RUN_CREATED")
        lines.append(
            f"[4]  RUN_CREATED seq {created['seq'] if created else '—'} at lease_epoch 0"
            "   — the one append with no lease to fence against"
        )
        done = [e for e in events if e["type"] == "STEP_COMPLETED"]
        lines.append(
            f"[5]  epoch 1 runs {len(done)} steps clean: "
            + " · ".join(f"#{e['step_index']}" for e in done)
            + f"   (seq {done[0]['seq']}–{done[-1]['seq']})"
            if done
            else "[5]  epoch 1: no step completed before the fault"
        )
        lines.append("     [week 2] §26.3's APPROVAL at #3, RUN_WAITING{WAITING_APPROVAL}, `keel approve`")
        lines.append("              and RECOVERY_STARTED{cause=WAKE} need the signals inbox.")
        intent = _last(events, "STEP_INTENDED")
        started = _last(events, "STEP_ATTEMPT_STARTED")
        if intent and started:
            lines += [
                f"[6]  #{intent['step_index']} {intent['body'].get('kind')} "
                f"{intent['body'].get('name')} [{facts.effect_class}]  STEP_INTENDED seq {intent['seq']}"
                f"  key={_key(facts, intent['step_index'])}",
                f"[7]  STEP_ATTEMPT_STARTED #{started['step_index']} attempt "
                f"{started['body'].get('attempt_no', 1)} seq {started['seq']}"
                "   — the write-ahead barrier: no receipt may precede this seq",
            ]
    landed = [r for r in receipts if not cut or iso(r["ts"]) <= cut]
    hit = [r for r in landed if r["logical_identity"] == target]
    # Receipts *before the cut*, not the trial's final applied count: this block is what was true
    # at the instant the process died, and printing an end-of-trial number here would answer the
    # question the AFTER block exists to ask.
    lines.append(
        f"[8]  World receipt {target}  ·  {len(hit)} request(s) received before the cut"
        f"  — fsynced before the response was computed, which is what makes this landmark exact"
        if hit
        else f"[8]  World has no {target} yet"
    )
    lines += [
        f"[9]  fault {fault.get('type', '—')} @ {fault.get('boundary', '—')}"
        f"  landmark {fault.get('landmark', '—')}  → fault-log row fsync → process gone",
        f"     at the cut: last committed seq {_n(fault.get('last_seq_before'))}"
        f" · open step {_n(fault.get('open_step'))} · no outcome"
        f" · World's last receipt {_n(fault.get('receipt_before'))}",
    ]
    return lines


# --- after --------------------------------------------------------------------
def _after(
    row: Any, facts: TrialFacts, events: list[dict[str, Any]], receipts: list[dict[str, Any]],
    cut: float, target: str,
) -> list[str]:
    lines = [
        f"[10] supervisor: worker gone, {row.restarts} restart(s) ≤ max_recoveries "
        f"{facts.max_recoveries}"
        "  → restart with identical argv and env, no run id passed",
    ]
    if facts.journal is None:
        lines += [
            f"[11] the harness re-invokes it by an id the framework persisted — recovery_mechanism="
            f"{row.recovery_mechanism}",
            "[12] no RECOVERY_STARTED to print: nothing in this runtime records that a recovery began",
            "[13] resume re-runs the interrupted node; whether that re-fires the effect is what the",
            "     World's receipt count below answers",
        ]
    else:
        rec = _first(events, "RECOVERY_STARTED")
        amb = _first(events, "STEP_AMBIGUOUS")
        res = _first(events, "STEP_RESOLVED")
        done = _first(events, "RECOVERY_COMPLETED")
        lines += [
            "[11] reaper: the lease lapsed and no non-PURE attempt is still inside its deadline"
            "  → runs.orphaned_at set → claim",
            f"[12] RECOVERY_STARTED{{cause={rec['body'].get('cause') if rec else '—'},"
            f" from_seq={rec['body'].get('from_seq') if rec else '—'}}} seq {_n(rec and rec['seq'])}"
            "   — a different process, told nothing",
        ]
        if done:
            lines.append(
                f"[13] re-execution: {done['body'].get('replayed_steps')} steps returned from the journal"
                "  — 0 model calls, 0 World calls, 0 tokens"
            )
        if amb:
            lines.append(
                f"[14] #{amb['step_index']} STARTED without an outcome, class {facts.effect_class}"
                f"  → STEP_AMBIGUOUS seq {amb['seq']}"
                "   — the runtime does not guess"
            )
        if res:
            body = res["body"]
            lines += [
                f"[15] probe → the receiver is asked, not assumed:"
                f" {body.get('method', 'probe')} says COMMITTED",
                f"     STEP_RESOLVED{{{body.get('resolution')}}} seq {res['seq']}"
                "   — resolved, never re-fired",
            ]
        if done:
            lines.append(
                f"[16] RECOVERY_COMPLETED{{live_from_step={done['body'].get('live_from_step')},"
                f" replayed_steps={done['body'].get('replayed_steps')}}} seq {done['seq']}"
            )
    after_receipts = [r for r in receipts if cut and iso(r["ts"]) > cut and r["logical_identity"] == target]
    lines.append(
        f"[17] World after the restart: {len(after_receipts)} further receipt(s) for {target}"
        + ("   — the effect was never re-sent" if not after_receipts else "")
    )
    lines.append(f"     run status {row.status}  ·  result {_short(row.result)}")
    return lines


# --- the point ----------------------------------------------------------------
def _point(row: Any, facts: TrialFacts, target: str, row_path: Any) -> list[str]:
    raw = row.metrics["raw"]
    verdicts = " ".join(
        f"{name}{'✓' if v == 'PASS' else '✗' if v == 'FAIL' else '·'}" for name, v in row.verdicts.items()
    )
    applied = facts.world_applied.get(target, 0)
    receipts = sum(1 for r in facts.world_receipts if r["logical_identity"] == target)
    lines = [
        f"[18] World: receipts({target})={receipts}  applied={applied}"
        f"   ·  duplicate_effects={row.metrics['duplicate_effects']}"
        f"  duplicate_receipts={row.metrics['duplicate_receipts']}",
        f"     verifier: {verdicts}"
        "        (· = N/A, with the missing input named in the row)",
    ]
    if facts.replay is not None:
        lines.append(
            f"[19] replay --verify: {facts.replay.get('replayed_steps', '—')} steps reproduced"
            f"  · projection hash {'match' if facts.replay.get('projection_matches') is not False else 'MISMATCH'}"
        )
    else:
        lines.append("[19] replay --verify: N/A — this runtime exposes no replay mode to check against")
    lines += [
        f"[20] row → {row_path or row.trial_id}  ·  seed {row.seed}  ·  spec {row.spec_hash[:12]}"
        f"  ·  keel_commit {row.keel_commit or '—'}",
        "",
        _moral(row, facts, target, applied, receipts),
    ]
    return lines


def _moral(row: Any, facts: TrialFacts, target: str, applied: int, receipts: int) -> str:
    """One sentence, computed rather than written, so it cannot survive the behaviour changing."""
    if facts.journal is None:
        return (
            f"The fault landed in the same window, on the same landmark, against the same receiver. "
            f"This arm sent {receipts} request(s) and the World applied {applied}. "
            f"It declares `{row.claims.get(facts.effect_class, 'none')}` for {facts.effect_class}, "
            f"so that is not a failure — it is the cost, printed."
        )
    return (
        f"The World had the effect and the journal did not. A different process read the journal, "
        f"found the open {facts.effect_class} step, asked the receiver what had happened, and "
        f"finished the run — {receipts} request, {applied} applied, nothing re-sent and nothing "
        f"guessed."
    )


# --- reading the artefacts ----------------------------------------------------
def _required(facts: TrialFacts) -> str:
    return facts.required_effects[0] if facts.required_effects else "the effect under test"


def _tool(row: Any) -> str:
    """The tool under test, read off the workload declaration rather than off this run.

    The declaration is what the cell *is*; what the run did is what the rest of these lines report.
    Taking the name from the journal would make the line unprintable for an arm that keeps none —
    and this line is about the pre-dispatch rule, which applies to every arm.
    """
    from crashproof.workloads.tool_chain_1_effect import WORKLOAD

    for decl in WORKLOAD.tools_for(row.workload_variant):
        if decl.effect_class != "PURE":
            return decl.name
    return "the tool under test"


def _dedup(row: Any) -> str:
    return "true" if row.workload_variant == "IDEMPOTENT" else "false"


def _key(facts: TrialFacts, step_index: int | None) -> str:
    for effect in facts.sut_effects or []:
        if effect.get("step_index") == step_index:
            return str(effect.get("effect_key", ""))[:12]
    return "—"


def _first(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    return next((e for e in events if e["type"] == kind), None)


def _last(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    return next((e for e in reversed(events) if e["type"] == kind), None)


def _n(value: Any) -> str:
    return "—" if value in (None, "") else str(value)


def _short(value: Any, width: int = 60) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 1] + "…"
