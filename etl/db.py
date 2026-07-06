"""
All SQL for the ETL pipeline lives in this one file. Uses plain psycopg2

Connections use RealDictCursor so rows come back as dicts.
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

psycopg2.extras.register_uuid()  # uuid columns come back as UUID objects, not raw strings


@contextmanager
def get_connection(config):
    conn = psycopg2.connect(
        config.database_url,
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=10,  # fail loudly within 10s
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
        # Refresh the fields most likely to actually change . No need to rewrite every column on a re-see.
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
    """Mark anything not seen in `expiry_days` days as expired. Returns the count.
    """
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
# etl_runs
# ---------------------------------------------------------------------------

def get_or_create_today_run(cur) -> dict:
    cur.execute("select * from etl_runs where run_date = current_date")
    row = cur.fetchone()
    if row:
        return row
    cur.execute("insert into etl_runs (run_date) values (current_date) returning *")
    return cur.fetchone()


def update_run(cur, run_id: str, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{key} = %({key})s" for key in fields)
    fields = dict(fields, run_id=run_id)
    cur.execute(f"update etl_runs set {set_clause} where id = %(run_id)s", fields)
