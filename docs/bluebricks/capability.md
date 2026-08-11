# Bluebrick: Capability Provenance

## Purpose

Provide optional namespaced plugins and the installed v0.8-compatible CLI capability lifecycle
without turning host availability into target readiness or authority.

## Public Interface

`plugins/*`, marketplace metadata, `mir capability status|check|sync|update|attest|finalize`,
capability source configuration, and the local lock.

## Rules and Hazards

Status and check are read-only. Mutation requires an explicit apply flag and the user's named scope.
Installing `mir` authorizes nothing. Hashes prove only source, lock, receipt, cache, and TOCTOU
integrity. Preserve local divergence and prior state on failure. The standard Project Agent Kit
does not copy this CLI or require a plugin.

## Dependencies and Validation

Depends on Contract. Validate with capability CLI and security tests.
