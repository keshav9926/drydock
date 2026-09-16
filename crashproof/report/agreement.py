"""The proxy/shim agreement column (§29.1): the same cell, measured from two places.

A `shim` cell and its `proxy` twin are one trigger, one landmark, one set of seeds, with the
injector one process further out. §11.2's correspondence table says what precision that loses —
`before:tool_call` fires on a request that has already left the SUT, and `after:tool_return` is
meant to land before the SUT parses the bytes — but a kill from outside arrives only after
`taskkill`'s latency, often after the parse. This page says whether it changed anything. A cell where the two
agree on every safety verdict and every raw count is a window that is real and not an artefact of
where the instrument sat. A cell where they differ is a finding about the *instrument*, printed
with both numbers and never resolved in favour of either.

Paired on `(cell_id, seed)`. The spec hashes differ by construction — `mode` is in the hash — so
this is the one pairing in the harness that ignores them. It may only because nothing *else* varies
between the two sides, and that is checked rather than assumed: a twin whose sides ran at different
`keel_commit`s or under different `config_pin`s is printed with both and left out of the tally,
because a difference there could be the runtime changing rather than the instrument moving. No pin
key encodes the mode (it is a row column), so the pins are compared whole. Nothing here carries a
p-value. Agreement is a check on the harness, and a check is PASS or it names the cell.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from crashproof.report.matrix import CellSummary, fold

SAFETY = ("S1", "S2", "S3", "S4", "S5", "S7", "S8", "L1", "L2", "C1")
RAW = ("duplicate_effects", "duplicate_receipts", "missing_required")


@dataclass(slots=True)
class CellAgreement:
    cell_id: str
    n: int = 0
    shim_only: int = 0
    proxy_only: int = 0
    shim: CellSummary | None = None
    proxy: CellSummary | None = None
    #: What the folded trials ran at, per side: `keel_commit`s and canonical `config_pin`s.
    commits: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())
    pins: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())

    @property
    def twin(self) -> bool:
        return self.shim is not None and self.proxy is not None and self.n > 0

    @property
    def comparable(self) -> bool:
        """Same code, same configuration, both sides. Otherwise a difference is not the instrument's."""
        return self.commits[0] == self.commits[1] and self.pins[0] == self.pins[1]

    def why_not_comparable(self) -> str:
        out = []
        if self.commits[0] != self.commits[1]:
            out.append(f"keel_commit {_set(self.commits[0])} / {_set(self.commits[1])}")
        shim_pins = [json.loads(p) for p in sorted(self.pins[0])]
        proxy_pins = [json.loads(p) for p in sorted(self.pins[1])]
        for key in sorted({k for pin in shim_pins + proxy_pins for k in pin}):
            a = {json.dumps(pin.get(key), sort_keys=True) for pin in shim_pins}
            b = {json.dumps(pin.get(key), sort_keys=True) for pin in proxy_pins}
            if a != b:
                out.append(f"{key} {_set(a)} / {_set(b)}")
        return "; ".join(out)

    def differences(self) -> list[str]:
        """What the two instruments disagree on, by name. Empty is agreement."""
        if not self.twin:
            return []
        assert self.shim is not None and self.proxy is not None
        out: list[str] = []
        for name in SAFETY:
            a, b = self.shim.verdicts.get(name, "N/A"), self.proxy.verdicts.get(name, "N/A")
            # A column one side never had — C1 before replay existed, S7 on a workload that gates
            # nothing — is not a disagreement; it is a cell from before the column (§15.11).
            if "N/A" in (a, b):
                continue
            if a != b:
                out.append(f"{name} {a}/{b}")
        for name in RAW:
            a, b = getattr(self.shim, name), getattr(self.proxy, name)
            if a != b:
                out.append(f"{name} {a}/{b}")
        if self.shim.recovery_rate != self.proxy.recovery_rate:
            out.append(
                f"recovery {self.shim.recovery_rate[0]}/{self.shim.recovery_rate[1]} vs "
                f"{self.proxy.recovery_rate[0]}/{self.proxy.recovery_rate[1]}"
            )
        return out

    @property
    def agrees(self) -> bool:
        return self.twin and self.comparable and not self.differences()


@dataclass(slots=True)
class Agreement:
    shim_name: str = "shim"
    proxy_name: str = "proxy"
    cells: list[CellAgreement] = field(default_factory=list)

    @property
    def twins(self) -> list[CellAgreement]:
        return [c for c in self.cells if c.twin]

    @property
    def comparable(self) -> list[CellAgreement]:
        return [c for c in self.twins if c.comparable]

    @property
    def disagreeing(self) -> list[CellAgreement]:
        return [c for c in self.comparable if not c.agrees]


def agreement(
    shim_rows: list[dict[str, Any]],
    proxy_rows: list[dict[str, Any]],
    *,
    shim_name: str = "shim",
    proxy_name: str = "proxy",
) -> Agreement:
    """Fold each side over the seeds *both* sides ran, so a cell's two summaries describe the same
    trials. A seed only one side has is counted, not folded: it cannot agree with anything."""
    left = _latest(shim_rows)
    right = _latest(proxy_rows)
    cells = sorted({cell for cell, _ in left} | {cell for cell, _ in right})
    out = Agreement(shim_name=shim_name, proxy_name=proxy_name)
    for cell_id in cells:
        l_seeds = {seed for cell, seed in left if cell == cell_id}
        r_seeds = {seed for cell, seed in right if cell == cell_id}
        shared = l_seeds & r_seeds
        entry = CellAgreement(
            cell_id=cell_id,
            n=len(shared),
            shim_only=len(l_seeds - shared),
            proxy_only=len(r_seeds - shared),
        )
        # Folded over the shared seeds where there are any; where there are none, each side over
        # its own, so a cell both sides ran on disjoint seeds lists both rather than losing one.
        shim_rows = [left[(cell_id, s)] for s in sorted(shared or l_seeds)]
        proxy_rows = [right[(cell_id, s)] for s in sorted(shared or r_seeds)]
        if shim_rows:
            entry.shim = fold(shim_rows)[cell_id]
        if proxy_rows:
            entry.proxy = fold(proxy_rows)[cell_id]
        entry.commits = (_commits(shim_rows), _commits(proxy_rows))
        entry.pins = (_pins(shim_rows), _pins(proxy_rows))
        out.cells.append(entry)
    return out


def _commits(rows: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(r.get("keel_commit") or "(none)" for r in rows)


def _pins(rows: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(json.dumps(r.get("config_pin") or {}, sort_keys=True) for r in rows)


def _set(values: frozenset[str] | set[str]) -> str:
    return ",".join(sorted(values))


def _latest(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    """Last write wins per `(cell_id, seed)`, *then* void rows go — `fold`'s own order, applied
    before the pairing so a re-taken seed pairs with its retake, a void trial pairs with nothing,
    and a void retake of a valid trial voids it here exactly as it does on the matrix page."""
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        cell = canonical_cell(row["cell_id"])
        latest[(cell, row["seed"])] = {**row, "cell_id": cell}
    return {key: row for key, row in latest.items() if row.get("valid", True)}


def canonical_cell(cell_id: str) -> str:
    """`Matrix._fault` reads a bare boundary as a kill there — matrix v0 spells its cells
    `keel.default.EXTERNAL.after:tool_effect`, tier1p spells the same fault
    `kill@after:tool_effect`. One spelling, so the twins find each other."""
    head, _, trigger = cell_id.rpartition(".")
    if not head or trigger == "baseline":
        return cell_id
    # Per part: a composed trigger may spell one part bare and another explicitly.
    parts = trigger.split("+")
    return f"{head}.{'+'.join(p if '@' in p else f'kill@{p}' for p in parts)}"


# --- rendering ---------------------------------------------------------------
def render(a: Agreement, *, sources: list[tuple[str, list[dict[str, Any]]]] = ()) -> str:
    """`sources` is `(results directory, its rows)` for every directory on either side."""
    from crashproof.report.markdown import sources_block

    twins = a.twins
    lines = [
        f"# Proxy / shim agreement — `{a.shim_name}` vs `{a.proxy_name}`",
        "",
        "The same cells, measured from inside the SUT (`shim`) and from the network edge (`proxy`),",
        "paired on `(cell, seed)` and folded over the seeds both ran. §29.1's agreement column: a",
        "cell where the two instruments agree on every safety verdict and every raw count is a",
        "window that is real and not an artefact of where the instrument sat; a cell where they",
        "differ is a finding about the instrument, printed with both numbers.",
        "",
        "No p-values. Agreement is a check on the harness, not a hypothesis about runtimes. A twin",
        "whose two sides ran at different commits or under different config pins is printed with",
        "what differs and left out of the tally: its difference may be the runtime, not the instrument.",
        "`n` is the seeds both sides ran; seeds only one side ran are counted beside it and folded",
        "into neither.",
        "",
        *sources_block(sources),
        "",
        "| cell | n | safety (shim) | safety (proxy) | dup_eff | dup_rcpt | recovery | latency | agree |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in twins:
        assert c.shim is not None and c.proxy is not None
        diffs = c.differences()
        if not c.comparable:
            verdict = f"not comparable: pins differ — {c.why_not_comparable()}"
        else:
            verdict = "yes" if not diffs else "**no** — " + "; ".join(diffs)
        lines.append(
            f"| `{c.cell_id}` | {_n(c)} | {_safety(c.shim)} | {_safety(c.proxy)} "
            f"| {c.shim.duplicate_effects} / {c.proxy.duplicate_effects} "
            f"| {c.shim.duplicate_receipts} / {c.proxy.duplicate_receipts} "
            f"| {_rate(c.shim)} / {_rate(c.proxy)} "
            f"| {_latency(c.shim)} / {_latency(c.proxy)} "
            f"| {verdict} |"
        )
    if not twins:
        lines.append("| — | 0 | | | | | | | no twins: nothing to agree on |")

    singles = [c for c in a.cells if not c.twin]
    if singles:
        lines += [
            "",
            "## Cells with no twin",
            "",
            "A fault only one mode can deliver, or a cell one side has not run yet. Listed, never",
            "folded into the agreement count.",
            "",
            "| cell | side | n | why |",
            "|---|---|---|---|",
        ]
        for c in singles:
            if c.shim is not None and c.proxy is not None:
                lines.append(
                    f"| `{c.cell_id}` | {a.shim_name} / {a.proxy_name} | {c.shim_only} / {c.proxy_only} "
                    "| no shared seeds: both sides ran it, on different seeds |"
                )
                continue
            side = a.shim_name if c.shim is not None else a.proxy_name
            n = c.shim_only if c.shim is not None else c.proxy_only
            lines.append(f"| `{c.cell_id}` | {side} | {n} | {_why(c)} |")

    comparable = a.comparable
    agreeing = len(comparable) - len(a.disagreeing)
    not_comparable = len(twins) - len(comparable)
    lines += [
        "",
        "## Reading it",
        "",
        f"{agreeing} of {len(comparable)} comparable twinned cells agree."
        + (
            f" {not_comparable} of {len(twins)} twins are not comparable — their commits or config pins "
            "differ — and are counted in neither."
            if not_comparable
            else ""
        )
        + (
            " Every disagreement names what differs, in the order shim / proxy."
            if a.disagreeing
            else " Where the instrument sat did not change a verdict or a count."
            if comparable
            else ""
        ),
        "",
        "What the proxy realisation loses, per §11.2: `before:tool_call` fires on a request that",
        "has already left the SUT (the shim's fires with nothing sent); `after:tool_return` is meant",
        "to land before the SUT parses the bytes, but a kill from outside the process arrives only",
        "after `taskkill`'s latency — often after the parse, sometimes after the run has finished,",
        "which is what a proxy cell with fewer restarts than its shim twin shows (the shim's lands",
        "inside the checkpoint write, via `call_soon`); a freeze parks the request at the proxy and forwards it at the thaw, and the",
        "process frozen is the one named by `sut/pid-<n>` — which, in rows from before a Keel",
        "successor wrote its pid under its own name, may have been the idle successor rather than the",
        "worker holding the run. The `after:tool_effect` window — applied, receipted, nobody told —",
        "is the same window in both.",
        "",
    ]
    return "\n".join(lines)


def _safety(s: CellSummary) -> str:
    marks = {"PASS": "✓", "FAIL": "✗", "N/A": "·"}
    return " ".join(f"{n}{marks.get(s.verdicts.get(n, 'N/A'), '·')}" for n in SAFETY if s.verdicts.get(n, "N/A") != "N/A" or n in ("S1", "S3", "L1"))


def _n(c: CellAgreement) -> str:
    extra = [f"+{k} {side} only" for k, side in ((c.shim_only, "shim"), (c.proxy_only, "proxy")) if k]
    return f"{c.n} ({', '.join(extra)})" if extra else str(c.n)


def _rate(s: CellSummary) -> str:
    k, n = s.recovery_rate
    return f"{k}/{n}"


def _latency(s: CellSummary) -> str:
    return "—" if s.recovery_latency_ms is None else f"{s.recovery_latency_ms / 1000:.1f}s"


def _why(c: CellAgreement) -> str:
    trigger = c.cell_id.split(".", 3)[3] if c.cell_id.count(".") >= 3 else c.cell_id
    if trigger.startswith(("tool_dropped_response", "tool_malformed")):
        return "proxy-only: a shim sits inside the client and cannot do to a socket what a network does"
    if "model" in trigger or trigger.startswith("sigterm"):
        return "shim-only: model traffic does not cross the proxy; SIGTERM from outside is not built"
    return "the other side has not run this cell"
