"""
All SQL for the ETL pipeline lives in this one file. Plain psycopg2,
no ORM -- there isn't enough going on here to justify one.

Connections use RealDictCursor so rows come back as dicts.
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


@contextmanager
def get_connection(config):
    conn = psycopg2.connect(
        config.database_url,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=10,  # fail loudly within 10s rather than hanging on a bad host/network
    )
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def upsert_job(cur, job: dict) -> bool:
    """Insert a new job, or refresh an existing one's last_seen_at/status.

    Returns True if this was a brand-new adzuna_id, False if it already existed.
    Two queries instead of a single clever upsert, on purpose -- it's easier
    to read and to know which branch ran, and the volume here doesn't need
    the extra cleverness.
    """
    cur.execute("select 1 from jobs where adzuna_id = %(adzuna_id)s", job)
    is_new = cur.fetchone() is None

    if is_new:
        cur.execute(
            """
            insert into jobs (
                adzuna_id, title, company_name, location_display, location_area,
                latitude, longitude, category_tag, category_label,
                contract_type, contract_time, salary_min, salary_max,
                salary_is_predicted, description_snippet, redirect_url,
                adzuna_created_at, raw_json
            ) values (
                %(adzuna_id)s, %(title)s, %(company_name)s, %(location_display)s, %(location_area)s,
                %(latitude)s, %(longitude)s, %(category_tag)s, %(category_label)s,
                %(contract_type)s, %(contract_time)s, %(salary_min)s, %(salary_max)s,
                %(salary_is_predicted)s, %(description_snippet)s, %(redirect_url)s,
                %(adzuna_created_at)s, %(raw_json)s
            )
            """,
            job,
        )
    else:
        # Refresh the fields most likely to actually change (an employer can
        # edit a live posting); no need to rewrite every column on a re-see.
        cur.execute(
            """
            update jobs set
                last_seen_at = now(),
                status = 'active',
                title = %(title)s,
                salary_min = %(salary_min)s,
                salary_max = %(salary_max)s,
                description_snippet = %(description_snippet)s,
                raw_json = %(raw_json)s
            where adzuna_id = %(adzuna_id)s
            """,
            job,
        )
    return is_new


def mark_expired(cur, expiry_days: int) -> int:
    """Mark anything not seen in `expiry_days` days as expired. Returns the count."""
    cur.execute(
        """
        update jobs
        set status = 'expired'
        where status = 'active'
          and last_seen_at < now() - (%s || ' days')::interval
        """,
        (expiry_days,),
    )
    return cur.rowcount


# ---------------------------------------------------------------------------
# job_requirements
# ---------------------------------------------------------------------------

def get_jobs_needing_extraction(cur, extraction_model: str) -> list[dict]:
    """Active jobs with no requirements row yet, or one extracted by a
    different (older) prompt/model version."""
    cur.execute(
        """
        select j.id, j.title, j.category_label, j.description_snippet
        from jobs j
        left join job_requirements r on r.job_id = j.id
        where j.status = 'active'
          and (r.job_id is null or r.extraction_model <> %s)
        """,
        (extraction_model,),
    )
    return cur.fetchall()


def upsert_job_requirements(cur, job_id: str, extracted: dict, extraction_model: str) -> None:
    cur.execute(
        """
        insert into job_requirements (
            job_id, skills, experience_years_min, experience_years_max,
            education_level, employment_type, licenses_certifications,
            raw_extraction, extraction_model
        ) values (
            %(job_id)s, %(skills)s, %(experience_years_min)s, %(experience_years_max)s,
            %(education_level)s, %(employment_type)s, %(licenses_certifications)s,
            %(raw_extraction)s, %(extraction_model)s
        )
        on conflict (job_id) do update set
            skills = excluded.skills,
            experience_years_min = excluded.experience_years_min,
            experience_years_max = excluded.experience_years_max,
            education_level = excluded.education_level,
            employment_type = excluded.employment_type,
            licenses_certifications = excluded.licenses_certifications,
            raw_extraction = excluded.raw_extraction,
            extraction_model = excluded.extraction_model,
            extracted_at = now()
        """,
        {
            "job_id": job_id,
            "skills": extracted.get("skills") or [],
            "experience_years_min": extracted.get("experience_years_min"),
            "experience_years_max": extracted.get("experience_years_max"),
            "education_level": extracted.get("education_level"),
            "employment_type": extracted.get("employment_type"),
            "licenses_certifications": extracted.get("licenses_certifications") or [],
            "raw_extraction": psycopg2.extras.Json(extracted),
            "extraction_model": extraction_model,
        },
    )


# ---------------------------------------------------------------------------
# etl_runs
# ---------------------------------------------------------------------------

def get_or_create_today_run(cur) -> dict:
    cur.execute("select * from etl_runs where run_date = current_date")
    row = cur.fetchone()
    if row:
        return row
    cur.execute("insert into etl_runs (run_date) values (current_date) returning *")
    return cur.fetchone()


def get_pending_batch(cur) -> dict | None:
    """The most recent run with an extraction batch we haven't collected yet, if any."""
    cur.execute(
        """
        select id, run_date, extraction_batch_id
        from etl_runs
        where extraction_batch_id is not null
          and extraction_batch_status = 'in_progress'
        order by run_date desc
        limit 1
        """
    )
    return cur.fetchone()


def update_run(cur, run_id: str, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{key} = %({key})s" for key in fields)
    fields = dict(fields, run_id=run_id)
    cur.execute(f"update etl_runs set {set_clause} where id = %(run_id)s", fields)


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------

def insert_candidate(cur, extracted: dict, raw_resume_text: str, source_filename: str, extraction_model: str) -> str:
    cur.execute(
        """
        insert into candidates (
            full_name, email, phone, location_text, summary,
            work_history, education, skills, certifications_licenses,
            raw_extraction, extraction_model, source_filename, raw_resume_text
        ) values (
            %(full_name)s, %(email)s, %(phone)s, %(location_text)s, %(summary)s,
            %(work_history)s, %(education)s, %(skills)s, %(certifications_licenses)s,
            %(raw_extraction)s, %(extraction_model)s, %(source_filename)s, %(raw_resume_text)s
        )
        returning id
        """,
        {
            "full_name": extracted.get("full_name"),
            "email": extracted.get("email"),
            "phone": extracted.get("phone"),
            "location_text": extracted.get("location"),
            "summary": extracted.get("summary"),
            "work_history": psycopg2.extras.Json(extracted.get("work_history") or []),
            "education": psycopg2.extras.Json(extracted.get("education") or []),
            "skills": extracted.get("skills") or [],
            "certifications_licenses": extracted.get("certifications_licenses") or [],
            "raw_extraction": psycopg2.extras.Json(extracted),
            "extraction_model": extraction_model,
            "source_filename": source_filename,
            "raw_resume_text": raw_resume_text,
        },
    )
    return cur.fetchone()["id"]


def get_pending_candidates(cur) -> list[dict]:
    cur.execute("select * from candidates where review_status = 'pending_review' order by created_at")
    return cur.fetchall()


def update_candidate_fields(cur, candidate_id: str, fields: dict) -> None:
    """`fields` values for work_history/education must already be wrapped in
    psycopg2.extras.Json(...) by the caller -- same convention as update_run."""
    if not fields:
        return
    set_clause = ", ".join(f"{key} = %({key})s" for key in fields)
    fields = dict(fields, candidate_id=candidate_id)
    cur.execute(
        f"update candidates set {set_clause}, updated_at = now() where id = %(candidate_id)s",
        fields,
    )


def set_review_status(cur, candidate_id: str, status: str, reviewed_by: str) -> None:
    cur.execute(
        """
        update candidates
        set review_status = %s, reviewed_by = %s, reviewed_at = now(), updated_at = now()
        where id = %s
        """,
        (status, reviewed_by, candidate_id),
    )
