-- Migration 003 — Mir-specific tables + schema_meta + audit.
-- design §5.3 (Mir additional tables) + §9.8 (schema versioning).

CREATE TABLE schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- Engine-minted session UUID (v0.5.3 R2).
CREATE TABLE sessions (
  id               INTEGER PRIMARY KEY,
  uuid             TEXT NOT NULL UNIQUE,
  role             TEXT NOT NULL,
  minted_at        TEXT NOT NULL,
  released_at      TEXT,
  started_at       TEXT,
  ended_at         TEXT,
  conductor_model  TEXT,
  profile          TEXT,
  failure_count    INTEGER NOT NULL DEFAULT 0,
  clarify_turns    INTEGER NOT NULL DEFAULT 0     -- §9.10.2.1
);

CREATE TABLE tasks (
  id            INTEGER PRIMARY KEY,
  session_id    INTEGER REFERENCES sessions(id),
  taskspec_json TEXT,
  status        TEXT,                             -- 'pending'|'running'|'done'|'failed'
  failure_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE circuit_state (
  tool_name     TEXT PRIMARY KEY,
  state         TEXT NOT NULL,                    -- 'closed'|'open'|'half_open'
  failure_count INTEGER NOT NULL DEFAULT 0,
  opened_at     TEXT
);

CREATE TABLE reviews (
  id              INTEGER PRIMARY KEY,
  task_id         INTEGER NOT NULL REFERENCES tasks(id),
  reviewer_role   TEXT NOT NULL,                  -- 'plan' | 'design' | 'adversarial'
  reviewer_model  TEXT NOT NULL,
  writer_model    TEXT,
  verdict         TEXT NOT NULL,                  -- 'pass' | 'fail'
  verdict_json    TEXT,
  created_at      TEXT NOT NULL,
  UNIQUE (task_id, reviewer_role, reviewer_model)
);

-- Conductor FSM with row-level transition lock (v0.5.3 H11).
CREATE TABLE conductor_mode (
  session_id              INTEGER PRIMARY KEY REFERENCES sessions(id),
  mode                    TEXT NOT NULL,
  entered_at              TEXT,
  triggered_by            TEXT,
  pending_diff_sha        TEXT,
  timeout_at              TEXT,
  transition_lock_holder  TEXT,
  transition_started_at   TEXT,
  transition_attempt_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE meta_mode_approvals (
  id             INTEGER PRIMARY KEY,
  user_id        TEXT NOT NULL,
  requested_at   TEXT NOT NULL,
  approved_at    TEXT,
  change_summary TEXT,
  diff           TEXT NOT NULL,
  diff_sha256    TEXT NOT NULL,
  signature      TEXT,
  status         TEXT NOT NULL DEFAULT 'pending'  -- 'pending'|'approved'|'applied'|'aborted'
);

-- v0.5.3 R5: one-shot nuke tokens.
CREATE TABLE nuke_tokens (
  nonce       TEXT PRIMARY KEY,
  instance_id TEXT NOT NULL,
  issued_at   TEXT NOT NULL,
  consumed_at TEXT
);

-- v0.5.3 R7: provider supply-chain pins.
CREATE TABLE dist_pins (
  name          TEXT PRIMARY KEY,
  source        TEXT NOT NULL,                    -- 'vendored' | 'pypi'
  dist          TEXT,
  version       TEXT,
  sha256        TEXT,
  vendored_path TEXT,
  added_at      TEXT NOT NULL,
  verified_at   TEXT
);

-- v0.5.3 R6: hash-chained audit log + daily anchors.
CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY,
  ts          TEXT NOT NULL,
  event       TEXT NOT NULL,
  payload     TEXT NOT NULL,                      -- canonical_json blob
  prev_hash   TEXT NOT NULL,
  hash        TEXT NOT NULL,
  signature   TEXT
);

CREATE TABLE audit_anchors (
  day         TEXT PRIMARY KEY,                   -- YYYY-MM-DD
  head_hash   TEXT NOT NULL,
  anchored_at TEXT NOT NULL,
  channel     TEXT                                -- 'discord_dm' etc.
);
