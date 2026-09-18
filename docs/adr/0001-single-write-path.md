# ADR-0001: One write path, enforced structurally

Date: 2026-09-18 · Status: accepted

## Context

The brief's first principle is "read is free, write is earned". Any code path that writes to a
customer system must go through the Action Pipeline. A rule that lives only in a document
erodes; it needs to be checked by the build.

## Decision

- `core/action/executor.py` is the only module that may call an adapter's `write` method,
  construct a `WriteOp`, or call the PII boundary's `restore`.
- `tests/architecture/test_import_boundaries.py` parses every Python file with `ast` and fails
  the build on any violation. It runs in CI and as a pre-commit hook.
- In Phase 0 the executor is a placeholder that raises `WritePathNotImplemented`, so no write
  can happen before the pipeline (plan → simulate → verify → approve/auto → execute → record)
  exists.
- Phase 3 adds the database-level guarantee: `executions.verdict_id` is a `NOT NULL` foreign
  key, so an execution row cannot exist without a stored verdict.

## Consequences

- Adapters implement `write` but never call it on each other; generated adapters ship with
  `capabilities.write = False`.
- Any future "quick fix" that writes directly is a red CI run, not a code review discussion.
- The AST check is heuristic for method calls (it flags `.write(` on receivers whose name
  contains "adapter"); the DB constraint and the executor's own tests are the hard guarantee.
