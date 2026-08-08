# Bluebrick: Adoption

## Purpose

Provide separate greenfield and existing-repository adoption paths.

## Public Interface

`mir bootstrap`, `mir bootstrap-adoption`, `BOOTSTRAP.md`, and the adoption receipt schema.

## Rules and Hazards

One explicit invocation owns one local root. Existing-repository assessment is read-only by
default; successful apply writes only the atomic machine-local receipt. Never reconstruct local
policy or specifications.

## Dependencies and Validation

Depends on Contract. Validate with the bootstrap and existing-repository adoption test suites.
