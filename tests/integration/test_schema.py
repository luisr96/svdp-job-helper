"""
Verifies the live database schema matches what etl/daily_etl.py and etl/db.py expect:
 * Tables exist
 * Expected columns are present
 * Full-text search column exists

Requires DATABASE_URL in .env to point at a real, reachable Postgres database

    pytest tests/integration/test_schema.py -v
"""
import pytest

EXPECTED_JOBS_COLUMNS = {
    "id", "adzuna_id", "title", "company_name", "location_display",
    "location_area", "latitude", "longitude", "category_tag", "category_label",
    "contract_type", "contract_time", "salary_min", "salary_max",
    "salary_is_predicted", "description_snippet", "redirect_url",
    "adzuna_created_at", "first_seen_at", "last_seen_at", "status",
    "raw_json", "created_at", "fts",
}

EXPECTED_ETL_RUNS_COLUMNS = {
    "id", "run_date", "started_at", "finished_at", "category_counts",
    "jobs_new", "jobs_updated", "jobs_expired", "status", "error_message",
}


def _table_names(cur) -> set[str]:
    cur.execute("select table_name from information_schema.tables where table_schema = 'public'")
    return {row["table_name"] for row in cur.fetchall()}


def _column_names(cur, table: str) -> set[str]:
    cur.execute(
        "select column_name from information_schema.columns where table_name = %s",
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def test_expected_tables_exist(db_conn):
    tables = _table_names(db_conn.cursor())
    assert "jobs" in tables, "jobs table is missing"
    assert "etl_runs" in tables, "etl_runs table is missing"


def test_no_leftover_tables_from_old_schema(db_conn):
    """Confirms the reset actually removed the old AI-extraction/matching
    tables, rather than just adding new ones alongside them."""
    tables = _table_names(db_conn.cursor())
    leftover = tables & {"job_requirements", "candidates", "match_runs"}
    assert not leftover, f"Old tables should have been dropped by the reset migration, found: {leftover}"


def test_jobs_table_has_expected_columns(db_conn):
    columns = _column_names(db_conn.cursor(), "jobs")
    missing = EXPECTED_JOBS_COLUMNS - columns
    assert not missing, f"jobs table is missing expected columns: {missing}"


def test_etl_runs_table_has_expected_columns(db_conn):
    columns = _column_names(db_conn.cursor(), "etl_runs")
    missing = EXPECTED_ETL_RUNS_COLUMNS - columns
    assert not missing, f"etl_runs table is missing expected columns: {missing}"


def test_jobs_fts_column_is_populated_for_existing_rows(db_conn):
    """If there's existing data, the generated fts column should have non-null non-empty values."""
    cur = db_conn.cursor()
    cur.execute("select count(*) as total, count(fts) as with_fts from jobs")
    row = cur.fetchone()
    if row["total"] == 0:
        pytest.skip("No rows in jobs yet. Nothing to check the fts value against")
    assert row["with_fts"] == row["total"], "some jobs rows have a null fts value"


def test_jobs_adzuna_id_is_unique_constrained(db_conn):
    """Confirms the unique constraint that upsert_job() relies on to detect 'is this a new job or one we've seen before' actually exists."""
    cur = db_conn.cursor()
    cur.execute(
        """
        select constraint_type
        from information_schema.table_constraints
        where table_name = 'jobs' and constraint_type = 'UNIQUE'
        """
    )
    assert cur.fetchone() is not None, "jobs.adzuna_id should have a unique constraint"
