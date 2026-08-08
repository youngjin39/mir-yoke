# Bluebrick: Capability Provenance

## Purpose

Materialize explicitly selected plugin and agent assets from one trusted Git source.

## Public Interface

`mir capability status|check|sync|update|attest|finalize`, capability source configuration, and the
local lock.

## Rules and Hazards

Status and check are read-only. Mutation requires an explicit apply flag. Hashes prove only source,
lock, receipt, cache, and TOCTOU integrity. Preserve local divergence and prior state on failure.

## Dependencies and Validation

Depends on Contract. Validate with capability CLI and security tests.
