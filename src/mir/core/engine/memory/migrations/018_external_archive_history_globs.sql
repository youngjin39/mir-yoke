-- Migration 018 — ADR-84 archive-configured historical document globs.
-- Patterns are repository-logical, comma-separated globs. They are evaluated
-- during scan metadata classification; source Markdown stays authoritative.

ALTER TABLE external_archives ADD COLUMN historical_glob TEXT;
