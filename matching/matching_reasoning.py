"""
Stage 3: Sonnet reasoning over a candidate's embedding-narrowed shortlist.
Synchronous call -- someone's generally waiting to see results for a
specific candidate, the same reasoning as resume intake.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for json_extract.py

from json_extract import extract_json

MATCHING_SYSTEM_PROMPT = """\
You help match a job-seeker to open positions for a nonprofit job placement program.

You will be given a candidate's confirmed profile and a shortlist of job
postings that already passed a semantic-similarity filter. Pick and rank the
best-fitting jobs from the shortlist, with brief reasoning for each.

Return ONLY a JSON object (no markdown, no commentary, no code fences) with
this shape:
{
  "ranked_matches": [
    {"job_id": "<uuid from the shortlist>", "reasoning": "<1-2 sentences, specific to this candidate and this job>"},
    ...
  ]
}

Rules:
- Only include jobs from the given shortlist. Never invent a job_id.
- Rank by genuine fit between the candidate's actual stated skills/experience
  and the job's actual stated requirements. Do not guess at things neither
  side mentions.
- Do NOT penalize employment gaps, short tenures, or career changes in the
  candidate's history. A nonlinear work history is not a weakness to call out.
- Do NOT comment on anything about the candidate other than job fit (no
  assumptions about reliability, life circumstances, etc.).
- Include at most 10 matches. If fewer than 10 are genuinely good fits,
  return fewer -- don't pad the list with weak matches.
- It is fine to return an empty list if nothing in the shortlist is a
  reasonable fit.
"""


def build_candidate_summary(candidate: dict) -> str:
    lines = [f"Name: {candidate.get('full_name')}"]
    if candidate.get("summary"):
        lines.append(f"Summary: {candidate['summary']}")
    if candidate.get("skills"):
        lines.append(f"Skills: {', '.join(candidate['skills'])}")
    if candidate.get("certifications_licenses"):
        lines.append(f"Licenses/certifications: {', '.join(candidate['certifications_licenses'])}")
    for entry in candidate.get("work_history") or []:
        title = entry.get("title") or ""
        employer = entry.get("employer") or ""
        dates = f"{entry.get('start_date') or 'unspecified'} - " + (
            "present" if entry.get("is_current") else (entry.get("end_date") or "unspecified")
        )
        desc = entry.get("description") or ""
        lines.append(f"- {title} at {employer} ({dates}): {desc}")
    for entry in candidate.get("education") or []:
        lines.append(f"- {entry.get('credential') or ''} in {entry.get('field_of_study') or ''}, "
                     f"{entry.get('institution') or ''}")
    return "\n".join(lines)


def build_shortlist_summary(shortlist: list[dict]) -> str:
    lines = []
    for job in shortlist:
        lines.append(
            f"- job_id: {job['id']}\n"
            f"  title: {job['title']} at {job.get('company_name') or 'unknown company'}\n"
            f"  employment_type: {job.get('employment_type') or 'unspecified'}\n"
            f"  skills: {', '.join(job.get('skills') or [])}\n"
            f"  licenses_certifications: {', '.join(job.get('licenses_certifications') or [])}\n"
            f"  education_level: {job.get('education_level') or 'unspecified'}"
        )
    return "\n".join(lines)


def find_matches(client, model: str, candidate: dict, shortlist: list[dict]) -> dict:
    user_content = (
        f"CANDIDATE PROFILE:\n{build_candidate_summary(candidate)}\n\n"
        f"SHORTLISTED JOBS:\n{build_shortlist_summary(shortlist)}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=MATCHING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    parsed = extract_json(text)
    if parsed is None:
        raise ValueError(f"Matching did not return valid JSON. Response started with: {text[:300]!r}")
    return parsed
