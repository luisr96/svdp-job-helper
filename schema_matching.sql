-- Matching layer schema -- run once, additive to schema.sql / schema_candidates.sql.

create extension if not exists vector;

-- pgvector columns for the two embedding spots. 1024 dimensions matches
-- Voyage's voyage-4 model (Anthropic's recommended embeddings partner --
-- Anthropic doesn't offer its own embedding model). If you ever switch
-- embedding models to one with a different output size, this column needs
-- to be dropped and recreated at the new dimension, and everything
-- re-embedded -- the two are tied together.
alter table job_requirements add column if not exists embedding vector(1024);
alter table candidates add column if not exists embedding vector(1024);

-- No vector index (HNSW/IVFFlat) on either column on purpose -- at a few
-- thousand rows, a plain sequential scan computing exact cosine distance
-- is a few milliseconds and always exact. Add an index only if this table
-- grows into the tens of thousands and that scan actually shows up as slow.

-- Audit log of each matching run -- same append-only "what actually
-- happened" pattern as etl_runs, not a stateful matches/workflow table.
create table if not exists match_runs (
    id                  uuid primary key default gen_random_uuid(),
    candidate_id        uuid not null references candidates(id),
    run_at              timestamptz not null default now(),
    shortlist_job_ids   uuid[] not null,
    llm_model           text not null,
    llm_output          jsonb not null,
    error_message       text
);
create index if not exists idx_match_runs_candidate on match_runs (candidate_id);
