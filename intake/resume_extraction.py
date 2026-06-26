"""
Structured fact extraction from a resume PDF via Claude Sonnet 4.6.

Synchronous call, not Batch -- at this volume someone is generally about to
review the result in the same sitting. Sonnet, not Haiku -- resumes vary
wildly in layout and this needs more judgment than the templated job
postings the ETL pipeline extracts from.
"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for json_extract.py

from json_extract import extract_json

RESUME_EXTRACTION_SYSTEM_PROMPT = """\
You extract structured facts from a candidate's resume PDF for a job-matching system.

Return ONLY a JSON object (no markdown, no commentary, no code fences) with
exactly these keys:
- "full_name": string, or null if not stated
- "email": string, or null if not stated
- "phone": string, or null if not stated
- "location": string, location as written on the resume (e.g. "Fort Myers, FL"), or null
- "summary": string, the resume's own summary/objective text if present, or null
- "work_history": array of objects, one per job, each with:
    - "employer": string
    - "title": string
    - "start_date": string exactly as written on the resume (e.g. "Jan 2020", "2018"), or null
    - "end_date": string exactly as written, or null
    - "is_current": boolean, true only if the resume itself indicates this is a current/present position
    - "description": string, the responsibilities/achievements text for that role, or null
- "education": array of objects, one per credential, each with:
    - "institution": string
    - "credential": string, the degree or certificate name, or null
    - "field_of_study": string, or null
    - "start_date": string exactly as written, or null
    - "end_date": string exactly as written, or null
- "skills": array of strings, specific skills stated on the resume
- "certifications_licenses": array of strings, professional licenses or certifications stated on the resume

Rules:
- Only extract what is explicitly stated on the resume. Never infer,
  calculate, or summarize anything not written there.
- Do NOT calculate total years of experience, employment gaps, or any other
  derived judgment about the candidate's history -- that is out of scope here.
- Preserve dates exactly as written. Do not convert them to a standardized
  date format, and do not guess a specific day or month that isn't stated.
- Use null (or an empty array, for list fields) for anything not present on
  the resume. Leaving something out is correct when the information isn't there.
"""


def _build_messages(pdf_bytes: bytes) -> list[dict]:
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                },
                {"type": "text", "text": "Extract this candidate's resume into the JSON format described."},
            ],
        }
    ]


def extract_resume(client, model: str, pdf_bytes: bytes, max_attempts: int = 2) -> dict:
    """Calls Claude to extract structured facts from a resume PDF. Retries
    once if nothing parseable comes back -- a deliberately simple bounded
    retry, not a verify/refine loop (that belongs to the later tailoring
    phase, where LangGraph actually earns its keep)."""
    last_text = None
    for _ in range(max_attempts):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=RESUME_EXTRACTION_SYSTEM_PROMPT,
            messages=_build_messages(pdf_bytes),
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        parsed = extract_json(text)
        if parsed is not None:
            return parsed
        last_text = text
    raise ValueError(
        f"Resume extraction did not return valid JSON after {max_attempts} attempts. "
        f"Last response started with: {last_text[:300]!r}"
    )
