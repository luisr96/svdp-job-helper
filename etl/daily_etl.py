"""
Daily job ETL: pull Adzuna listings, dedupe, expire stale ones
"""
import logging
from datetime import datetime, timezone

import psycopg2.extras

import db
from adzuna_client import AdzunaClient, normalize_job
from config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily_etl")


def pull_category(cur, adzuna: AdzunaClient, category: dict) -> tuple[int, int]:
    """Page through one category's listings. Returns (jobs_seen, jobs_new)."""
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
    adzuna = AdzunaClient(config)

    log.info("Connecting to database...")
    with db.get_connection(config) as conn:
        log.info("Connected.")
        cur = conn.cursor()
        run = db.get_or_create_today_run(cur)
        conn.commit()

        try:
            log.info("Fetching Adzuna category list...")
            categories = adzuna.get_categories()
            log.info("Got %d categories. Pulling listings (one Adzuna request per "
                     "category per page, up to %d pages each)...",
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

            db.update_run(
                cur,
                run["id"],
                jobs_new=jobs_new,
                jobs_updated=jobs_updated,
                jobs_expired=jobs_expired,
                category_counts=psycopg2.extras.Json(category_counts),
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
