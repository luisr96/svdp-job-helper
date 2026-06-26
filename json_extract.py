"""
Shared helper for pulling JSON out of an LLM response that doesn't follow
"return ONLY JSON" perfectly. The most common failure mode -- and the one
that actually happened here -- is the model wrapping its answer in a
markdown code fence (```json ... ```) even when explicitly told not to.
A bare json.loads() fails on every single one of those, identically, which
is exactly what "100% of results skipped" looks like in practice.

Used by both etl/extraction.py (job postings) and intake/resume_extraction.py
(resumes), since both prompts are vulnerable to the same failure mode.
"""
import json


def extract_json(text: str) -> dict | None:
    text = text.strip()

    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1:] if first_newline != -1 else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Last resort: grab the outermost {...} block, in case there's stray
    # commentary before or after the JSON itself.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            return None
    return None
