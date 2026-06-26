"""
Structured requirement extraction via Haiku 4.5, submitted through the
Batch API (50% cheaper, ~24h turnaround is fine here -- see daily_etl.py
for how a single daily cron collects yesterday's batch before submitting
today's).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for json_extract.py

from json_extract import extract_json

EXTRACTION_SYSTEM_PROMPT = """\
You extract structured requirements from job postings for a job-matching system.

You will be given a job title, category, and description. The description may
be cut off mid-sentence because of an upstream length limit on the source --
this is expected and not an error on your part.

Return ONLY a JSON object (no markdown, no commentary, no code fences) with
exactly these keys:
- "skills": array of specific skills or competencies stated or clearly implied (empty array if none found)
- "experience_years_min": integer minimum years of experience required, or null if not stated
- "experience_years_max": integer maximum years of experience required, or null if not stated
- "education_level": string describing required education (e.g. "Associate's Degree in Nursing"), or null if not stated
- "employment_type": one of "full_time", "part_time", "contract", "temporary", or null if not stated
- "licenses_certifications": array of required professional licenses or certifications (e.g. "RN", "CDL-A") (empty array if none found)

Only include information that is explicitly stated or very clearly implied.
Do not guess years of experience from a job title alone. If the description
is truncated before reaching the qualifications section, most fields will
legitimately be null or empty -- that is the correct answer, not a failure.
"""


def build_batch_requests(jobs: list[dict], model: str) -> list[dict]:
    requests = []
    for job in jobs:
        user_content = (
            f"Title: {job['title']}\n"
            f"Category: {job['category_label']}\n"
            f"Description: {job['description_snippet']}"
        )
        requests.append(
            {
                "custom_id": str(job["id"]),
                "params": {
                    "model": model,
                    "max_tokens": 400,
                    "system": EXTRACTION_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": user_content}],
                },
            }
        )
    return requests


def submit_batch(client, requests: list[dict]) -> str:
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def get_batch_status(client, batch_id: str) -> str:
    """Returns 'in_progress', 'canceling', or 'ended'."""
    return client.messages.batches.retrieve(batch_id).processing_status


def collect_batch_results(client, batch_id: str):
    """Yields (job_id, parsed_dict_or_None, raw_text) for every request in
    the batch. raw_text is included even on success so a caller can log a
    sample on failure -- exactly the kind of bug (model wrapping JSON in a
    markdown fence despite being told not to) that's invisible until you
    actually look at the raw output, which is what happened here."""
    for entry in client.messages.batches.results(batch_id):
        job_id = entry.custom_id
        if entry.result.type != "succeeded":
            yield job_id, None, f"(request {entry.result.type}, no text returned)"
            continue

        text = "".join(
            block.text for block in entry.result.message.content if block.type == "text"
        )
        yield job_id, extract_json(text), text
