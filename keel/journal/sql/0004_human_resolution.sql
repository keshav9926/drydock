-- Human resolution (§7.3, §7.4), week 3. `effects.resolution` names *how* an ambiguous effect was
-- resolved, and a RESOLVED_UNKNOWN row now has a way out that is not a tool's declared method: a
-- human's decision (STEP_RESOLVED{method=human}).
ALTER TABLE effects DROP CONSTRAINT IF EXISTS effects_resolution_check;
ALTER TABLE effects ADD CONSTRAINT effects_resolution_check
  CHECK (resolution IN ('probe','assume_failed','assume_succeeded','escalate','human'));
