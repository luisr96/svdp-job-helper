-- Job ETL schema
-- Run this once against the Supabase Postgres database (SQL editor, or psql).
--
-- Three tables, on purpose:
--   jobs              raw-ish data pulled from Adzuna, one row per listing
--   job_requirements  structured fields Haiku extracts from each listing's description
--   etl_runs          one row per daily pipeline run, for visibility/debugging
--
-- Deliberately NOT here: a categories table, a companies table, a locations
-- table, a pgvector column. See the design discussion for why -- short
-- version is none of them are earning their keep yet at this scale.

create extension if not exists pgcrypto; -- harmless no-op if gen_random_uuid() is already built in

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
    description_snippet  text,           -- Adzuna truncates this -- see README
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

create table if not exists job_requirements (
    job_id                   uuid primary key references jobs (id) on delete cascade,
    skills                   text[] not null default '{}',
    experience_years_min    int,
    experience_years_max    int,
    education_level         text,
    employment_type         text,
    licenses_certifications text[] not null default '{}',
    raw_extraction           jsonb,       -- full Haiku output, so the field set can evolve without a migration
    extraction_model        text not null,
    extracted_at             timestamptz not null default now()
);

create table if not exists etl_runs (
    id                       uuid primary key default gen_random_uuid(),
    run_date                 date not null unique,
    started_at               timestamptz not null default now(),
    finished_at              timestamptz,
    category_counts          jsonb,        -- {"it-jobs": {"seen": 42, "new": 7}, ...}
    jobs_new                 int default 0,
    jobs_updated             int default 0,
    jobs_expired             int default 0,
    extraction_batch_id      text,
    extraction_batch_status  text,         -- in_progress | collected
    status                   text default 'running' check (status in ('running', 'success', 'failed')),
    error_message            text
);
