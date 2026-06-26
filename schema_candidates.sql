-- Candidates schema -- run this once against the same Supabase Postgres
-- database as schema.sql (it's additive, doesn't touch the jobs/ tables).
--
-- One table, on purpose -- same reasoning as the jobs table: work_history
-- and education are jsonb arrays rather than separate normalized tables,
-- since nothing here needs to query *into* an individual job/degree entry
-- yet, and a candidate's resume facts belong only to them (no cross-
-- candidate relationships to model).

create table if not exists candidates (
    id                       uuid primary key default gen_random_uuid(),

    -- core facts
    full_name                text,
    email                    text,
    phone                    text,
    location_text            text,                  -- free text as written, e.g. "Fort Myers, FL"
    summary                  text,                   -- resume's own objective/summary blurb, if present

    -- structured resume content
    work_history             jsonb not null default '[]',  -- [{employer, title, start_date, end_date, is_current, description}, ...]
    education                jsonb not null default '[]',  -- [{institution, credential, field_of_study, start_date, end_date}, ...]
    skills                   text[] not null default '{}',
    certifications_licenses  text[] not null default '{}',

    -- audit trail: exactly what Claude returned, before any human edits
    raw_extraction           jsonb not null,
    extraction_model         text not null,

    -- source
    source_filename          text,                   -- original PDF filename, for reviewer reference
    raw_resume_text          text,                    -- deterministically extracted (NOT by Claude) -- see README note

    -- every candidate gets reviewed before this profile is trusted anywhere
    -- downstream (matching, tailoring) -- not confidence-gated like the
    -- later tailoring phase will be, since this is establishing ground truth
    review_status            text not null default 'pending_review'
                              check (review_status in ('pending_review', 'confirmed', 'rejected')),
    reviewed_by               text,
    reviewed_at               timestamptz,

    created_at                timestamptz not null default now(),
    updated_at                timestamptz not null default now()
);

create index if not exists idx_candidates_review_status on candidates (review_status);
