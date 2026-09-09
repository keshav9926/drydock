-- Every index exists because one hot statement in §5/§8 needs it (§23.1, superset per §27.3).

-- natural-key guards: a duplicate append is a constraint violation, never a silent second row (§5.3)
CREATE UNIQUE INDEX IF NOT EXISTS events_intent_once     ON events (run_id, step_index)             WHERE type = 'STEP_INTENDED';
CREATE UNIQUE INDEX IF NOT EXISTS events_attempt_once    ON events (run_id, step_index, attempt_no) WHERE type = 'STEP_ATTEMPT_STARTED';
CREATE UNIQUE INDEX IF NOT EXISTS events_outcome_once    ON events (run_id, step_index, attempt_no)
  WHERE type IN ('STEP_COMPLETED','STEP_FAILED','STEP_AMBIGUOUS');
CREATE UNIQUE INDEX IF NOT EXISTS events_recovery_once   ON events (run_id, lease_epoch)            WHERE type = 'RECOVERY_STARTED';
CREATE UNIQUE INDEX IF NOT EXISTS events_terminal_once   ON events (run_id)                         WHERE type IN ('RUN_COMPLETED','RUN_FAILED','RUN_CANCELLED');
CREATE UNIQUE INDEX IF NOT EXISTS events_superseded_once ON events (run_id)                         WHERE type = 'RUN_SUPERSEDED';
CREATE UNIQUE INDEX IF NOT EXISTS events_segment_once    ON events (run_id, (payload->>'segment_no')) WHERE type = 'SEGMENT_STARTED';
CREATE UNIQUE INDEX IF NOT EXISTS events_approval_once   ON events (run_id, step_index)             WHERE type = 'APPROVAL_REQUESTED';
CREATE UNIQUE INDEX IF NOT EXISTS events_resolved_once   ON events (run_id, step_index, (payload->>'method'))
  WHERE type = 'STEP_RESOLVED';
CREATE UNIQUE INDEX IF NOT EXISTS events_patch_once      ON events (run_id, (payload->>'name'))     WHERE type = 'PATCH_APPLIED';

-- seek paths
CREATE INDEX IF NOT EXISTS events_by_step  ON events (run_id, step_index) WHERE step_index IS NOT NULL;  -- recovery table, `keel steps`
CREATE INDEX IF NOT EXISTS events_trace    ON events (trace_id, ts);
CREATE INDEX IF NOT EXISTS runs_claim_idx  ON runs (runnable_at)      WHERE runnable_at IS NOT NULL AND terminal_at IS NULL;  -- SKIP LOCKED claim
CREATE INDEX IF NOT EXISTS runs_wake       ON runs (wake_at)          WHERE wake_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS runs_expiring   ON runs (lease_expires_at) WHERE lease_expires_at IS NOT NULL;  -- reaper, first conjunct
CREATE INDEX IF NOT EXISTS runs_parent_idx ON runs (parent_run_id)    WHERE parent_run_id IS NOT NULL AND terminal_at IS NULL;
CREATE INDEX IF NOT EXISTS runs_root_idx   ON runs (run_root_id);
CREATE INDEX IF NOT EXISTS effects_open    ON effects (run_id)        WHERE status = 'STARTED' AND class <> 'PURE';  -- reaper
CREATE INDEX IF NOT EXISTS effects_by_step ON effects (run_id, step_index);
CREATE INDEX IF NOT EXISTS effects_pending ON effects (status)        WHERE status IN ('AMBIGUOUS','RESOLVED_UNKNOWN');
CREATE UNIQUE INDEX IF NOT EXISTS signals_client_key ON signals (run_id, client_key) WHERE client_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS signals_pending ON signals (run_id)        WHERE consumed_seq IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS artifacts_name_idx ON artifacts (run_id, kind, name, coalesce(lease_epoch, 0));
