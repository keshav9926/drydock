"""The audit trail is the journal plus the inbox (§20.7): SQL over the tables, no worker running.

There is no separate audit log. For any effect, §20.7's six questions are answered here by one query
each over `events`, `effects`, `signals` and `recoveries`, and S7's first half is the query §20.7
prints — with `gated` derived rather than stored:

    who decided it?    the MODEL outcome that preceded the TOOL intent — steps are strictly
                       sequential, so it is the latest MODEL/COMPACT step below its index (the
                       INTENT carries no `causation_seq` to the model turn), with its provider_meta
    was it allowed?    the INTENT's `policy_verdict`, then a STARTED (allowed) or an attempt-0
                       STEP_FAILED (refused: PolicyDenied, ApprovalRejected, …)
    who approved it?   APPROVAL_DECIDED{by, signal_id} for the approval binding this key → the
                       `signals` row (source, client_key, created_at). `by` is *claimed* identity
                       (§20.3): there is no authentication to verify it against
    which process, when, under which code?   each STARTED's `lease_epoch` → `recoveries.worker_id`,
                       its `started_at`, the outcome's `ts`, the INTENT's `program_version`
    did it happen?     `effects.status`, `external_ref`, and every STEP_RESOLVED's evidence
    what did the model see?   the deciding MODEL step's INTENT args — the request, as journaled

`gated` (§20.7 wants a column; §5.5 owns the DDL) is not a column here: an effect is gated when its
INTENT's `policy_verdict` is `require_approval` or an APPROVAL_REQUESTED binds its key. The first
half is what makes the query return the violation that matters most — a gated effect that started
with no request at all. S7's second half (≤ 1 *applied* effect per approval) is a fact about the
receiver and lives in the verifier, over the World log.

Postgres only: these are the operator's queries against the store, not a projection a worker folds.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

EFFECT = "SELECT * FROM effects WHERE effect_key = %(key)s"

INTENT = """
SELECT seq, ts, lease_epoch, program_version, payload->>'policy_verdict' AS policy_verdict
  FROM events
 WHERE run_id = %(run)s AND step_index = %(step)s AND type = 'STEP_INTENDED'
"""

DECIDED = """
SELECT c.step_index, i.payload->>'kind' AS kind, i.payload->>'name' AS name,
       c.payload->'provider_meta' AS provider_meta, i.payload->'args' AS request, c.ts
  FROM events c
  JOIN events i ON i.run_id = c.run_id AND i.step_index = c.step_index AND i.type = 'STEP_INTENDED'
 WHERE c.run_id = %(run)s AND c.type = 'STEP_COMPLETED' AND c.step_index < %(step)s
   AND i.payload->>'kind' IN ('MODEL', 'COMPACT')
 ORDER BY c.step_index DESC
 LIMIT 1
"""

ALLOWED = """
SELECT type, attempt_no, payload->>'error' AS error, ts
  FROM events
 WHERE run_id = %(run)s AND step_index = %(step)s
   AND (type = 'STEP_ATTEMPT_STARTED' OR (type = 'STEP_FAILED' AND attempt_no = 0))
 ORDER BY seq
"""

APPROVED = """
SELECT r.payload->>'approval_id' AS approval_id, r.step_index,
       d.payload->>'decision' AS decision, d.payload->>'by' AS by, d.ts AS decided_at,
       s.signal_id, s.type AS signal_type, s.source, s.client_key, s.created_at AS received_at
  FROM events r
  LEFT JOIN events d ON d.run_id = r.run_id AND d.type = 'APPROVAL_DECIDED'
                    AND d.payload->>'approval_id' = r.payload->>'approval_id'
  LEFT JOIN signals s ON s.signal_id::text = d.payload->>'signal_id'
 WHERE r.run_id = %(run)s AND r.type = 'APPROVAL_REQUESTED' AND r.payload->>'binds_effect_key' = %(key)s
"""

EXECUTED = """
SELECT a.attempt_no, a.lease_epoch, a.payload->>'started_at' AS started_at, rc.worker_id,
       o.type AS outcome, o.ts AS outcome_at
  FROM events a
  LEFT JOIN recoveries rc ON rc.run_id = a.run_id AND rc.lease_epoch = a.lease_epoch
  LEFT JOIN events o ON o.run_id = a.run_id AND o.step_index = a.step_index AND o.attempt_no = a.attempt_no
                    AND o.type IN ('STEP_COMPLETED', 'STEP_FAILED', 'STEP_AMBIGUOUS')
 WHERE a.run_id = %(run)s AND a.step_index = %(step)s AND a.type = 'STEP_ATTEMPT_STARTED'
 ORDER BY a.attempt_no
"""

RESOLVED = """
SELECT payload->>'resolution' AS resolution, payload->>'method' AS method, payload->'evidence' AS evidence, ts
  FROM events
 WHERE run_id = %(run)s AND step_index = %(step)s AND type = 'STEP_RESOLVED'
 ORDER BY seq
"""

#: §20.7's S7 query: gated effects that started without exactly one GRANTED approval binding their key.
S7_VIOLATIONS = """
WITH gated AS (
  SELECT e.run_id, e.effect_key, e.step_index, e.status
    FROM effects e
    JOIN events i ON i.run_id = e.run_id AND i.step_index = e.step_index AND i.type = 'STEP_INTENDED'
   WHERE e.status NOT IN ('INTENDED', 'DENIED')
     AND (i.payload->>'policy_verdict' = 'require_approval'
          OR EXISTS (SELECT 1 FROM events b
                      WHERE b.run_id = e.run_id AND b.type = 'APPROVAL_REQUESTED'
                        AND b.payload->>'binds_effect_key' = e.effect_key))
)
SELECT g.run_id, g.effect_key, g.step_index, g.status, count(d.seq) AS granted
  FROM gated g
  LEFT JOIN events r ON r.run_id = g.run_id AND r.type = 'APPROVAL_REQUESTED'
                    AND r.payload->>'binds_effect_key' = g.effect_key
  LEFT JOIN events d ON d.run_id = g.run_id AND d.type = 'APPROVAL_DECIDED'
                    AND d.payload->>'approval_id' = r.payload->>'approval_id'
                    AND d.payload->>'decision' = 'granted'
 GROUP BY g.run_id, g.effect_key, g.step_index, g.status
HAVING count(d.seq) <> 1
 ORDER BY g.run_id, g.step_index
"""


async def _rows(conn: Any, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return list(await cur.fetchall())


async def audit_effect(journal: Any, effect_key: str) -> dict[str, Any] | None:
    """§20.7's six answers for one effect, or None for a key the store has never seen."""
    pool = await journal._ready()
    async with pool.connection() as conn:
        effect = await _rows(conn, EFFECT, {"key": effect_key})
        if not effect:
            return None
        e = effect[0]
        p = {"run": e["run_id"], "step": e["step_index"], "key": effect_key}
        intent = (await _rows(conn, INTENT, p) or [None])[0]
        decided = (await _rows(conn, DECIDED, p) or [None])[0]
        allowed = await _rows(conn, ALLOWED, p)
        return {
            "effect": {k: e[k] for k in ("run_id", "step_index", "tool", "class", "status", "external_ref")},
            "decided_by": {k: v for k, v in decided.items() if k != "request"} if decided else None,
            "allowed": {
                "policy_verdict": intent["policy_verdict"] if intent else None,
                "started": any(r["type"] == "STEP_ATTEMPT_STARTED" for r in allowed),
                "refused": next((r["error"] for r in allowed if r["type"] == "STEP_FAILED"), None),
            },
            "approved_by": await _rows(conn, APPROVED, p),
            "executed": {
                "program_version": intent["program_version"] if intent else None,
                "attempts": await _rows(conn, EXECUTED, p),
            },
            "happened": {"status": e["status"], "external_ref": e["external_ref"],
                         "resolutions": await _rows(conn, RESOLVED, p)},
            "model_saw": decided["request"] if decided else None,
        }


async def s7_violations(journal: Any) -> list[dict[str, Any]]:
    """Every gated effect, in every run, that started without exactly one GRANTED approval."""
    pool = await journal._ready()
    async with pool.connection() as conn:
        return await _rows(conn, S7_VIOLATIONS, {})
