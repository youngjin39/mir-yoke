# Bluebrick: Distribution

## Purpose

Transform validated Source Plane files into Git-independent, deterministic release artifacts.

## Public Interface

`yoke build`, `config/product-planes.json`, `packs/*/pack.json`, `manifest.json`, `SHA256SUMS`, and
`provenance.json`.

## Rules and Hazards

The core archive contains exactly the four starter Markdown files. Each pack archive contains its
manifest, readme, consumer payload, and declared preserved source. Archive order, metadata, and
gzip timestamp are normalized. Source paths must be repository-relative real files and may not be
symlinks. Every artifact receives a SHA-256 digest. Distribution output is ignored and does not
become Source Plane state.

## Dependencies and Validation

Depends on Contract, pack schemas, and Maintenance. Validate schemas, missing paths, symlink
rejection, exact core contents, artifact inventory, sidecars, and repeated-build digest equality.
