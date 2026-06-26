"""
Daily job ETL: pull Adzuna listings, dedupe/expire, queue Haiku extraction.

Run once a day from cron. Single script, no orchestration framework -- this
is a linear pull -> upsert -> expire -> extract pipeline with no branching
or retry loops, so plain Python is the right tool (LangGraph is reserved for
the resume generate -> verify -> retry phase later, where there's an actual
decision graph).

    python etl/daily_etl.py

This file lives in etl/, but db.py and config.py are shared across every
phase of the project (resume intake, matching, tailoring will all need them
too), so they stay one level up at the project root. The sys.path line below
makes that work regardless of which directory you run this from or whether
you use `python etl/daily_etl.py` or `python -m etl.daily_etl` -- no need to
remember which invocation style applies here, both just work.

Each major step commits on its own, so a failure partway through (e.g. the
extraction batch submission times out) doesn't roll back the jobs that were
already pulled and saved that day.
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for db.py / config.py

import anthropic
import psycopg2.extras

import db
from adzuna_client import AdzunaClient, normalize_job
from config import load_config
from extraction import build_batch_requests, collect_batch_results, get_batch_status, submit_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily_etl")


def collect_pending_batch(cur, client, config) -> None:
    """Step 1: if a previous run's extraction batch has finished, collect it
    before doing anything else today."""
    pending = db.get_pending_batch(cur)
    if not pending:
        log.info("No extraction batch pending from a previous run.")
        return

    batch_id = pending["extraction_batch_id"]
    log.info("Checking status of pending extraction batch %s...", batch_id)
    status = get_batch_status(client, batch_id)
    if status != "ended":
        log.info("Batch %s still processing (status=%s); will check again next run.", batch_id, status)
        return

    collected = 0
    skipped = 0
    for job_id, parsed in collect_batch_results(client, batch_id):
        if parsed is None:
            skipped += 1
            continue
        db.upsert_job_requirements(cur, job_id, parsed, config.extraction_model)
        collected += 1

    db.update_run(cur, pending["id"], extraction_batch_status="collected")
    log.info("Collected %d extraction results from batch %s (%d skipped)", collected, batch_id, skipped)


def pull_category(cur, adzuna: AdzunaClient, category: dict) -> tuple[int, int]:
    """Step 2: page through one category's listings. Returns (jobs_seen, jobs_new)."""
    seen = 0
    new = 0
    consecutive_duplicate_pages = 0

    for page in range(1, adzuna.config.adzuna_max_pages_per_category + 1):
        results = adzuna.search_page(category["tag"], page)
        if not results:
            break

        page_new = 0
        for raw in results:
            job = normalize_job(raw, category["tag"], category["label"])
            if db.upsert_job(cur, job):
                new += 1
                page_new += 1
            seen += 1

        if page_new == 0:
            consecutive_duplicate_pages += 1
            if consecutive_duplicate_pages >= 2:
                # Two full pages of nothing-but-repeats means we've caught up
                # to what we already have for this category -- stop paging.
                break
        else:
            consecutive_duplicate_pages = 0

    return seen, new


def main() -> None:
    log.info("Starting daily ETL run...")
    config = load_config()
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    adzuna = AdzunaClient(config)

    log.info("Connecting to database...")
    with db.get_connection(config) as conn:
        log.info("Connected.")
        cur = conn.cursor()
        run = db.get_or_create_today_run(cur)
        conn.commit()

        try:
            collect_pending_batch(cur, client, config)
            conn.commit()

            log.info("Fetching Adzuna category list...")
            categories = adzuna.get_categories()
            log.info("Got %d categories. Pulling listings (this is the slow part -- one Adzuna "
                     "request per category per page, up to %d pages each)...",
                     len(categories), config.adzuna_max_pages_per_category)

            category_counts = {}
            jobs_new = 0
            jobs_updated = 0
            for i, category in enumerate(categories, start=1):
                try:
                    seen, new = pull_category(cur, adzuna, category)
                    category_counts[category["tag"]] = {"seen": seen, "new": new}
                    jobs_new += new
                    jobs_updated += seen - new
                    conn.commit()  # commit per category so one bad category can't lose the rest
                    log.info("  [%d/%d] %s: %d seen, %d new", i, len(categories), category["tag"], seen, new)
                except Exception:
                    conn.rollback()
                    log.exception("  [%d/%d] %s: failed after retries -- skipping it for today, "
                                  "continuing with the rest", i, len(categories), category["tag"])
                    category_counts[category["tag"]] = {"error": True}

                # Keep etl_runs current after every category, not just at the
                # very end -- so if something does crash later, today's run
                # still shows accurate partial progress instead of zeros.
                db.update_run(
                    cur, run["id"],
                    jobs_new=jobs_new, jobs_updated=jobs_updated,
                    category_counts=psycopg2.extras.Json(category_counts),
                )
                conn.commit()

            log.info("Pulled %d categories: %d new jobs, %d re-seen", len(category_counts), jobs_new, jobs_updated)

            jobs_expired = db.mark_expired(cur, config.expiry_days)
            conn.commit()
            log.info("Marked %d jobs expired (unseen for %d+ days)", jobs_expired, config.expiry_days)

            to_extract = db.get_jobs_needing_extraction(cur, config.extraction_model)
            batch_id = None
            if to_extract:
                batch_requests = build_batch_requests(to_extract, config.extraction_model)
                batch_id = submit_batch(client, batch_requests)
                log.info("Submitted extraction batch %s for %d jobs", batch_id, len(to_extract))
            else:
                log.info("No jobs need extraction today")

            db.update_run(
                cur,
                run["id"],
                jobs_new=jobs_new,
                jobs_updated=jobs_updated,
                jobs_expired=jobs_expired,
                category_counts=psycopg2.extras.Json(category_counts),
                extraction_batch_id=batch_id,
                extraction_batch_status="in_progress" if batch_id else None,
                status="success",
                finished_at=datetime.now(timezone.utc),
            )
            conn.commit()
            log.info("Daily ETL run complete.")

        except Exception as exc:
            conn.rollback()
            db.update_run(
                cur,
                run["id"],
                status="failed",
                error_message=str(exc),
                finished_at=datetime.now(timezone.utc),
            )
            conn.commit()
            log.exception("Daily ETL run failed")
            raise


if __name__ == "__main__":
    main()
