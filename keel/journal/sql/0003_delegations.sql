-- Delegation (§17), week 2. Two ordinals CHILD_SPAWNED carries, mirrored on the parent-owned row,
-- and the natural key that turns a re-executed spawn into a unique violation rather than a twin
-- (§7.6.1). `delegation_id` is derived from the same four values, so the primary key would catch
-- it too; the index is what a reader greps for.
ALTER TABLE delegations ADD COLUMN IF NOT EXISTS child_ordinal int NOT NULL DEFAULT 0;
ALTER TABLE delegations ADD COLUMN IF NOT EXISTS retry_no      int NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS delegations_contract_key
  ON delegations (parent_run_id, parent_step_index, child_ordinal, retry_no);
CREATE INDEX IF NOT EXISTS delegations_parent_idx ON delegations (parent_run_id, parent_step_index);
