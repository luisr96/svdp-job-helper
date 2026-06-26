"""
Resume intake: reads a candidate's resume PDF, extracts a structured profile
via Claude, and saves it as pending_review.

    python intake/run_intake.py path/to/resume.pdf
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for db.py / config.py

import anthropic

import db
from config import load_config
from pdf_text import extract_plain_text
from resume_extraction import extract_resume


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python intake/run_intake.py path/to/resume.pdf")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    config = load_config()
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    print(f"Reading {pdf_path.name}...")
    pdf_bytes = pdf_path.read_bytes()
    raw_text = extract_plain_text(str(pdf_path))

    print("Extracting structured profile via Claude...")
    extracted = extract_resume(client, config.resume_extraction_model, pdf_bytes)

    with db.get_connection(config) as conn:
        cur = conn.cursor()
        candidate_id = db.insert_candidate(
            cur, extracted, raw_text, pdf_path.name, config.resume_extraction_model
        )
        conn.commit()

    print(f"Saved candidate {candidate_id} as pending_review.")
    print("Run `python intake/review_cli.py` to confirm it.")


if __name__ == "__main__":
    main()
