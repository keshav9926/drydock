"""Static per-(provider, model) price tables, pinned by id at RUN_CREATED (§16.4).

A price change in October must not re-value a run that finished in September, so a run never reads
"the current price": `runs.model_config.pricing_ref` names one of these tables when the run is
created, and every MODEL attempt of the run is priced from that table. A shipped table is never
edited — a new price is a new table with a new id, and `CURRENT` moves to it for new runs only.

A binding with no entry is *unpriced*: its attempts journal no rate, the run's projection reads
`usd_priced=false`, `max_usd` admission is skipped from then on, and `keel show` prints the gap. A
guessed number here would end up inside an S9 claim.
"""

from __future__ import annotations

#: USD per million tokens, (input, output), per (provider, model); model "*" matches any model.
TABLES: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
    # The scripted provider's own model. A fixture rate, not anybody's list price: it exists so a
    # dollar budget means something in a test or a benchmark trial.
    "scripted-2026-09": {("scripted", "*"): (3.0, 15.0)},
}

#: The table a new run pins, per provider.
CURRENT: dict[str, str] = {"scripted": "scripted-2026-09"}


def current_ref(provider: str) -> str | None:
    return CURRENT.get(provider)


def rate(ref: str | None, provider: str, model: str | None) -> tuple[float, float] | None:
    """The pinned (input, output) rate for this binding, or None: unpriced."""
    table = TABLES.get(ref or "")
    if table is None:
        return None
    return table.get((provider, model or "*")) or table.get((provider, "*"))
