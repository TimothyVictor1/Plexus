-- Runs once on first Postgres boot. Extensions only; schema lands with Phase 1 migrations.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
