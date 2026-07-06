-- Combined reset + rebuild migration.
--
-- Part 1: drop everything from the old schema (jobs, job_requirements,
-- etl_runs, candidates, match_runs, the vector extension). Destructive and
-- irreversible on purpose -- this is a deliberate "start fresh" reset.
--
-- Part 2: recreate the trimmed schema -- jobs + etl_runs only.
--
-- Part 3: add full-text search (generated tsvector column + GIN index) so
-- search works without needing embeddings.

-- ---------------------------------------------------------------------------
-- Part 1: reset
-- ---------------------------------------------------------------------------

drop table if exists match_runs;
drop table if exists candidates;
drop table if exists job_requirements;
drop table if exists jobs;
drop table if exists etl_runs;
drop extension if exists vector;

-- ---------------------------------------------------------------------------
-- Part 2: trimmed schema
-- ---------------------------------------------------------------------------

create extension if not exists pgcrypto; -- harmless no-op if gen_random_uuid() is already built in

create table jobs (
    id                   uuid primary key default gen_random_uuid(),
    adzuna_id            text not null unique,
    title                text not null,
    company_name         text,
    location_display     text,
    location_area        jsonb,          -- Adzuna's area hierarchy array, e.g. ["US","Florida","Lee County","Estero"]
    latitude             numeric,
    longitude            numeric,
    category_tag         text,
    category_label       text,
    contract_type        text,           -- permanent / contract
    contract_time        text,           -- full_time / part_time
    salary_min           numeric,
    salary_max           numeric,
    salary_is_predicted  boolean,
    description_snippet  text,           -- Adzuna truncates this -- see README
    redirect_url         text,
    adzuna_created_at    timestamptz,
    first_seen_at        timestamptz not null default now(),
    last_seen_at         timestamptz not null default now(),
    status               text not null default 'active' check (status in ('active', 'expired')),
    raw_json             jsonb not null, -- full payload, cheap insurance against schema gaps
    created_at           timestamptz not null default now()
);

create index idx_jobs_status on jobs (status);
create index idx_jobs_category on jobs (category_tag);
create index idx_jobs_last_seen on jobs (last_seen_at);

create table etl_runs (
    id                       uuid primary key default gen_random_uuid(),
    run_date                 date not null unique,
    started_at               timestamptz not null default now(),
    finished_at              timestamptz,
    category_counts          jsonb,        -- {"it-jobs": {"seen": 42, "new": 7}, ...}
    jobs_new                 int default 0,
    jobs_updated             int default 0,
    jobs_expired             int default 0,
    status                   text default 'running' check (status in ('running', 'success', 'failed')),
    error_message            text
);

-- ---------------------------------------------------------------------------
-- Part 3: full-text search
-- ---------------------------------------------------------------------------

alter table jobs add column fts tsvector
    generated always as (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(description_snippet, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(company_name, '')), 'C')
    ) stored;

create index idx_jobs_fts on jobs using gin (fts);

-- Example query once this is in place:
--
--   select id, title, company_name, location_display,
--          ts_rank(fts, websearch_to_tsquery('english', 'registered nurse night shift')) as rank
--   from jobs
--   where status = 'active'
--     and fts @@ websearch_to_tsquery('english', 'registered nurse night shift')
--   order by rank desc
--   limit 25;
