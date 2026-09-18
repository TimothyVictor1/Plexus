# Scripts

- `db/init/` — SQL executed on first Postgres boot (extensions only).
- `fixtures/` — Nordvik Konsult AB, the fictional 12-person company every acceptance test and demo
  runs against (brief §11). Generated in Phase 1 by `scripts/gen_fixtures.py`; ground-truth
  labels in `fixtures/labels/`. Never real customer data.
- `demo_phase1.sh` — Phase 1: seeds fixtures and answers three cross-system questions with citations.
