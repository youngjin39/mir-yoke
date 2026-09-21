---
title: SRR code relations
status: active
type: reference
maintenance_owner: mir-yoke maintainers
scope: current maintained implementation, verification, and direct dependencies
memory_relations:
  - subject: SRR-MEMORY-RELATIONS
    predicate: realized_by
    object: MIR-MEMORY-RELATIONS
    summary: The memory relation reader supplies SRR from the canonical memory database.
    reason: It validates current source-owned facts and traverses them for the supported SRR purposes.
  - subject: SRR-MEMORY-RELATIONS
    predicate: realized_by
    object: MIR-RELATIONS-CLI
    summary: The relations CLI exposes SRR memory retrieval.
    reason: Its --memory branch dispatches query and bundle requests to the memory relation reader.
  - subject: MIR-MEMORY-RELATIONS
    predicate: implemented_in
    object: src/mir/core/memory_relations.py
    summary: Bounded reader for current declared memory relations.
    reason: This module validates relation provenance and performs immutable memory traversal.
  - subject: MIR-RELATIONS-CLI
    predicate: implemented_in
    object: src/mir/cli/relations.py
    summary: CLI adapter for declared relation retrieval.
    reason: This module selects graph or memory retrieval and renders the bounded result.
  - subject: SRR-MEMORY-RELATIONS
    predicate: verified_by
    object: tests/test_memory_relation_workflow.py
    summary: Workflow tests cover ingest, memory query, bundle, and direct dependencies.
    reason: The tests assert memory-backed results and unchanged source files during retrieval.
  - subject: SRR-MEMORY-RELATIONS
    predicate: verified_by
    object: tests/test_srr_memory_selection_parity.py
    summary: Parity tests compare memory traversal with declared graph traversal.
    reason: The tests assert the same selected implementation, verification, and dependency edges.
  - subject: MIR-MEMORY-RELATIONS
    predicate: depends_on
    object: MIR-RELATIONS-CORE
    summary: The reader reuses shared relation traversal and safety rules.
    reason: The module calls the relation core for bounded traversal, endpoint validation, and result rendering.
  - subject: MIR-MEMORY-RELATIONS
    predicate: depends_on
    object: MIR-RELATION-FACTS
    summary: The reader relies on the declared relation fact contract.
    reason: The module uses its relation schema, predicate allowlist, and source declaration parser.
  - subject: MIR-RELATIONS-CLI
    predicate: depends_on
    object: MIR-MEMORY-RELATIONS
    summary: The CLI delegates --memory requests to the memory reader.
    reason: The CLI imports and invokes query_memory_relations and bundle_memory_relations.
  - subject: MIR-RELATIONS-CORE
    predicate: implemented_in
    object: src/mir/core/relations.py
    summary: Shared bounded relation traversal and validation.
    reason: This module defines SRR purposes, edge traversal, protection checks, and result rendering.
  - subject: MIR-RELATION-FACTS
    predicate: implemented_in
    object: src/mir/core/engine/memory/relation_facts.py
    summary: Source-owned declared relation parser and validator.
    reason: This module validates frontmatter declarations before the writer reconciles relation facts.
---

# SRR code relations

This active reference records the maintained SRR code boundary. Update its declarations when the public reader, writer contract, listed tests, or direct dependencies change. It does not describe historical graphs or authorize graph-wide ingestion.
