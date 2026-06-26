"""
Find the best job matches for a confirmed candidate.

    python matching/find_matches.py <candidate_id>

Three stages: a cheap SQL filter (active jobs only), embedding similarity
to narrow ~3,000 jobs down to a shortlist of 25, then Sonnet reasoning over
just that shortlist. Logs the run to match_runs for an audit trail.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for db.py / config.py / etc.

import anthropic
import voyageai

import db
from config import load_config
from matching_reasoning import find_matches

SHORTLIST_SIZE = 25


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python matching/find_matches.py <candidate_id>")
        sys.exit(1)

    candidate_id = sys.argv[1]
    try:
        uuid.UUID(candidate_id)
    except ValueError:
        print(f"'{candidate_id}' doesn't look like a valid candidate id (expected a UUID).")
        sys.exit(1)

    config = load_config()
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    voyage_client = voyageai.Client(api_key=config.voyage_api_key)

    with db.get_connection(config) as conn:
        cur = conn.cursor()

        candidate = db.get_confirmed_candidate(cur, candidate_id)
        if not candidate:
            print(f"No confirmed candidate found with id {candidate_id}")
            print("(Either the id is wrong, or this candidate hasn't been reviewed/confirmed yet.)")
            sys.exit(1)

        if candidate["embedding"] is None:
            print(f"Candidate {candidate['full_name']} has no embedding yet.")
            print("This shouldn't happen for anyone confirmed through review_cli.py --")
            print("if this candidate was confirmed before the matching layer existed,")
            print("re-run review_cli.py's confirm step, or ask for a one-off backfill.")
            sys.exit(1)

        print(f"Finding matches for {candidate['full_name']}...")
        shortlist = db.get_shortlist_for_candidate(cur, candidate["embedding"], limit=SHORTLIST_SIZE)
        if not shortlist:
            print("No active jobs with embeddings found -- has the ETL pipeline run yet?")
            sys.exit(1)
        print(f"Narrowed {SHORTLIST_SIZE} closest jobs by embedding similarity; asking Claude to rank them...")

        result = find_matches(client, config.matching_model, candidate, shortlist)
        ranked = result.get("ranked_matches", [])

        shortlist_by_id = {str(job["id"]): job for job in shortlist}
        print(f"\n{len(ranked)} match(es) found for {candidate['full_name']}:\n")
        for i, match in enumerate(ranked, start=1):
            job = shortlist_by_id.get(str(match.get("job_id")))
            if not job:
                continue  # Claude returned a job_id not in the shortlist -- skip rather than show garbage
            print(f"{i}. {job['title']} at {job.get('company_name') or 'unknown company'}")
            if job.get("redirect_url"):
                print(f"   {job['redirect_url']}")
            print(f"   {match.get('reasoning', '')}")
            print()

        db.insert_match_run(
            cur,
            candidate_id=candidate["id"],
            shortlist_job_ids=[job["id"] for job in shortlist],
            llm_model=config.matching_model,
            llm_output=result,
        )
        conn.commit()
        print("(Logged to match_runs for the record.)")


if __name__ == "__main__":
    main()
