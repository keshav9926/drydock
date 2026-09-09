-- Keel schema, §5. Journal (events, blobs) | control plane (runs lease columns, signals,
-- recoveries, replays, programs, artifacts) | materialised mirrors (effects, delegations).
-- Tables the MVP does not yet write (signals, delegations, replays, artifacts) are created here
-- because they are cheap now and expensive to retrofit onto a live journal (§27.3).

CREATE TABLE IF NOT EXISTS programs (
  program           text NOT NULL,
  program_version   text NOT NULL,          -- 'declared+codehash'
  declared_version  text NOT NULL,
  code_hash         text NOT NULL,
  entrypoint        text NOT NULL,          -- 'pkg.module:prog'
  keel_version      text NOT NULL,
  tools             jsonb NOT NULL DEFAULT '{}'::jsonb,
  state_schema      jsonb,
  patches           text[] NOT NULL DEFAULT '{}',
  registered_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (program, program_version)
);

CREATE TABLE IF NOT EXISTS runs (
  run_id            uuid PRIMARY KEY,
  run_root_id       uuid NOT NULL,
  parent_run_id     uuid REFERENCES runs(run_id),
  fork_of_run_id    uuid REFERENCES runs(run_id),
  fork_seq          bigint,
  program           text NOT NULL,
  program_version   text NOT NULL,
  keel_version      text NOT NULL,
  model_config      jsonb NOT NULL DEFAULT '{}'::jsonb,
  args              jsonb NOT NULL DEFAULT '{}'::jsonb,
  budget            jsonb NOT NULL DEFAULT '{}'::jsonb,
  trace_id          uuid NOT NULL,
  phase             text NOT NULL DEFAULT 'CREATED',   -- CACHE of the journal phase (§5.4)
  -- control plane: never in the journal
  lease_owner       text,
  lease_epoch       bigint NOT NULL DEFAULT 0,         -- fencing token
  lease_expires_at  timestamptz,                       -- NULL = released; < now() = lapsed
  runnable_at       timestamptz,
  runnable_reason   text,
  wake_at           timestamptz,
  orphaned_at       timestamptz,
  paused_at         timestamptz,
  terminal_at       timestamptz,
  attempt_deadline  timestamptz,                       -- open non-PURE attempt's deadline
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT runs_phase_chk CHECK (phase IN ('CREATED','RUNNING','WAITING_APPROVAL','WAITING_CHILDREN',
    'SLEEPING','WAITING_SIGNAL','WAITING_RESOLUTION','PAUSED','SUSPENDED',
    'COMPLETED','FAILED','CANCELLED','SUPERSEDED')),
  CONSTRAINT runs_reason_chk CHECK (runnable_reason IN ('START','WAKE','DRAIN','RESUME','ORPHANED')),
  CONSTRAINT runs_fork_chk   CHECK ((fork_of_run_id IS NULL) = (fork_seq IS NULL)),
  FOREIGN KEY (program, program_version) REFERENCES programs(program, program_version)
);

CREATE TABLE IF NOT EXISTS events (
  run_id          uuid        NOT NULL REFERENCES runs(run_id),
  seq             bigint      NOT NULL,                -- per-run, assigned by the lease holder
  ts              timestamptz NOT NULL DEFAULT now(),  -- Postgres clock, never the worker's
  type            text        NOT NULL,
  schema_version  smallint    NOT NULL,
  lease_epoch     bigint      NOT NULL,                -- 0 only for RUN_CREATED
  program_version text        NOT NULL,
  causation_seq   bigint,
  trace_id        uuid        NOT NULL,
  step_index      int,                                 -- denormalised from payload
  attempt_no      smallint,                            -- denormalised from payload
  payload         jsonb       NOT NULL,
  blob_ids        text[]      NOT NULL DEFAULT '{}',   -- sha256 hex keys into blobs
  PRIMARY KEY (run_id, seq),
  FOREIGN KEY (run_id, causation_seq) REFERENCES events(run_id, seq)
);

CREATE TABLE IF NOT EXISTS blobs (
  blob_id     text    PRIMARY KEY,                -- sha256(content) hex
  size_bytes  int     NOT NULL,
  media_type  text    NOT NULL,
  encoding    text    NOT NULL DEFAULT 'identity',
  content     bytea   NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS effects (
  effect_key        char(32) PRIMARY KEY,
  run_id            uuid NOT NULL REFERENCES runs(run_id),
  run_root_id       uuid NOT NULL,
  step_index        int  NOT NULL,
  tool              text NOT NULL,
  class             text NOT NULL CHECK (class IN ('PURE','IDEMPOTENT','EXTERNAL','TRANSACTIONAL')),
  modifiers         text[] NOT NULL DEFAULT '{}',
  status            text NOT NULL CHECK (status IN ('INTENDED','STARTED','COMMITTED','ABSENT','AMBIGUOUS',
                      'RESOLVED_COMMITTED','RESOLVED_ABSENT','RESOLVED_UNKNOWN','CANCELLED','DENIED')),
  attempt_no        smallint NOT NULL DEFAULT 0,
  intent_seq        bigint NOT NULL,
  started_seq       bigint,
  outcome_seq       bigint,
  attempt_deadline  timestamptz,
  resolution        text CHECK (resolution IN ('probe','assume_failed','assume_succeeded','escalate')),
  external_ref      text,
  approval_id       uuid,
  synthetic         boolean NOT NULL DEFAULT false,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, step_index),
  FOREIGN KEY (run_id, intent_seq) REFERENCES events(run_id, seq)
);

CREATE TABLE IF NOT EXISTS signals (
  signal_id     uuid PRIMARY KEY,
  run_id        uuid NOT NULL REFERENCES runs(run_id),
  type          text NOT NULL CHECK (type IN ('approve','reject','cancel','pause','resume','rebind',
                                              'child_result','timer','custom')),
  payload       jsonb NOT NULL,
  client_key    text,
  source        text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  consumed_seq  bigint,
  FOREIGN KEY (run_id, consumed_seq) REFERENCES events(run_id, seq)
);

CREATE TABLE IF NOT EXISTS delegations (
  delegation_id      uuid PRIMARY KEY,
  parent_run_id      uuid NOT NULL REFERENCES runs(run_id),
  parent_step_index  int  NOT NULL,
  child_run_id       uuid NOT NULL UNIQUE REFERENCES runs(run_id),
  role               text NOT NULL CHECK (role IN ('worker','verifier')),
  contract           jsonb NOT NULL,
  budget_reserved    jsonb NOT NULL,
  status             text NOT NULL CHECK (status IN ('SPAWNED','COMPLETED','FAILED','CANCELLED')),
  usage_settled      jsonb,
  spawned_seq        bigint NOT NULL,
  settled_seq        bigint,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recoveries (
  run_id          uuid NOT NULL REFERENCES runs(run_id),
  lease_epoch     bigint NOT NULL,
  worker_id       text NOT NULL,
  cause           text NOT NULL CHECK (cause IN ('START','WAKE','ORPHANED','RESUME','DRAIN')),
  acquired_at     timestamptz NOT NULL DEFAULT now(),
  from_seq        bigint NOT NULL,
  from_segment    int NOT NULL DEFAULT 0,
  verified        boolean NOT NULL DEFAULT false,
  started_seq     bigint,
  completed_seq   bigint,
  completed_at    timestamptz,
  live_from_step  int,
  replayed_steps  int,
  replay_ms       int,
  outcome         text CHECK (outcome IN ('LIVE','WAITING','TERMINAL','SUSPENDED','FENCED','RELEASED',
                                          'CRASHED','FORCED_CANCEL')),
  released_at     timestamptz,
  PRIMARY KEY (run_id, lease_epoch)
);

CREATE TABLE IF NOT EXISTS replays (
  replay_id        uuid PRIMARY KEY,
  run_id           uuid NOT NULL REFERENCES runs(run_id),
  mode             text NOT NULL CHECK (mode IN ('VERIFY','FORK')),
  requested_by     text NOT NULL,
  program_version  text NOT NULL,
  base_seq         bigint NOT NULL,
  fork_run_id      uuid REFERENCES runs(run_id),
  result           text CHECK (result IN ('PASS','NONDETERMINISM','PROMPT_DRIFT','STATE_SCHEMA_MISMATCH','ERROR','SPAWNED')),
  replayed_steps   int,
  elapsed_ms       int,
  projection_hash  text,
  diff_blob_id     text,
  started_at       timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz
);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id  uuid PRIMARY KEY,
  run_id       uuid NOT NULL REFERENCES runs(run_id),
  step_index   int,
  lease_epoch  bigint,
  kind         text NOT NULL CHECK (kind IN ('result','workspace_snapshot','export','report','diff')),
  name         text NOT NULL,
  blob_id      text NOT NULL REFERENCES blobs(blob_id),
  media_type   text NOT NULL,
  size_bytes   int NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
