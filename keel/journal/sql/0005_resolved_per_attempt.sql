-- A resolution's natural key is the attempt it resolves (§6.2, amended after the v1 confirmation
-- tier). A probe that answers ABSENT closes attempt n and starts n+1 under the same key (§7.4); when
-- n+1 goes ambiguous in turn, it is probed in turn. Keyed on (step_index, method) the second probe
-- row was a unique violation and the run FAILED where it should have resolved. Escalate then human
-- is still two rows for one attempt, and no attempt is resolved twice by the same method.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'events_resolved_once' AND indexdef NOT LIKE '%attempt_no%') THEN
    DROP INDEX events_resolved_once;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS events_resolved_once ON events (run_id, step_index, attempt_no, (payload->>'method'))
  WHERE type = 'STEP_RESOLVED';
