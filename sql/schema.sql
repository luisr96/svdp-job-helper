-- Job ETL schema
--
-- Two tables:
--   jobs        raw-ish data pulled from Adzuna, one row per listing
--   etl_runs    one row per daily pipeline run, for visibility/debugging

create extension if not exists pgcrypto; -- no-op if gen_random_uuid() is already built in

create table if not exists jobs (
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
    description_snippet  text,           -- Adzuna truncates this
    redirect_url         text,
    adzuna_created_at    timestamptz,
    first_seen_at        timestamptz not null default now(),
    last_seen_at         timestamptz not null default now(),
    status               text not null default 'active' check (status in ('active', 'expired')),
    raw_json             jsonb not null, -- full payload, cheap insurance against schema gaps
    created_at           timestamptz not null default now()
);

create index if not exists idx_jobs_status on jobs (status);
create index if not exists idx_jobs_category on jobs (category_tag);
create index if not exists idx_jobs_last_seen on jobs (last_seen_at);

create table if not exists etl_runs (
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
