
        CREATE TABLE IF NOT EXISTS jobs (
            job_id             TEXT    PRIMARY KEY,
            change_id          TEXT    NOT NULL,
            category           TEXT    NOT NULL,
            family             TEXT,
            repo_root          TEXT    NOT NULL,
            codex_args         TEXT    NOT NULL,
            dispatch_brief_path TEXT,
            allow_harness_self_modify INTEGER NOT NULL DEFAULT 0,
            resume_count       INTEGER NOT NULL DEFAULT 0,
            last_resumed_at    TEXT,
            timeout_seconds    INTEGER NOT NULL,
            status             TEXT    NOT NULL,
            exit_code          INTEGER,
            stdout             TEXT,
            stderr             TEXT,
            duration_seconds   REAL,
            started_at         TEXT    NOT NULL,
            completed_at       TEXT,
            cancel_requested   INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE TABLE IF NOT EXISTS artifact_sweeps (
            job_id TEXT NOT NULL, path TEXT NOT NULL, files INTEGER NOT NULL,
            bytes INTEGER NOT NULL, swept_at TEXT NOT NULL
        );
        