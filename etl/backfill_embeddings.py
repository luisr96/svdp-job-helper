"""
One-off: embed every existing job_requirements row that doesn't have an
embedding yet. You only need to run this once, right after adding the
matching layer to backfill your existing job corpus -- from then on,
daily_etl.py embeds new jobs automatically as part of its regular run.

    python etl/backfill_embeddings.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for db.py / config.py / embeddings.py

import voyageai

import db
from config import load_config
from embeddings import backfill_candidate_embeddings, backfill_job_embeddings


def main() -> None:
    config = load_config()
    voyage_client = voyageai.Client(api_key=config.voyage_api_key)

    with db.get_connection(config) as conn:
        cur = conn.cursor()

        print("Embedding existing jobs that don't have one yet (this may take a moment)...")
        job_count = backfill_job_embeddings(cur, voyage_client)
        conn.commit()
        print(f"Embedded {job_count} job(s).")

        print("Embedding any confirmed candidates that don't have one yet...")
        candidate_count = backfill_candidate_embeddings(cur, voyage_client)
        conn.commit()
        print(f"Embedded {candidate_count} candidate(s).")


if __name__ == "__main__":
    main()
