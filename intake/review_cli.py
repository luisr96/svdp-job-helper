"""
Reviewer tool: walks through every candidate with review_status =
'pending_review', shows the extracted profile next to the independently-
extracted resume text, and lets the reviewer confirm, edit, skip, or reject.

    python intake/review_cli.py

Editing a scalar field (name, email, etc.) happens with a simple prompt.
Editing a nested field (work_history, education, skills) opens it as JSON
in your default text editor, the same pattern as `git commit` opening
$EDITOR -- simplest way to let someone edit a structured list without
building a custom interactive editor for it.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, for db.py / config.py

import psycopg2.extras

import db
from config import load_config

SCALAR_FIELDS = ["full_name", "email", "phone", "location_text", "summary"]
LIST_FIELDS = ["skills", "certifications_licenses"]
JSON_FIELDS = ["work_history", "education"]


def print_candidate(candidate: dict) -> None:
    print("\n" + "=" * 70)
    print(f"Candidate {candidate['id']}  (submitted {candidate['created_at']})")
    print(f"Source file: {candidate.get('source_filename')}")
    print("-" * 70)
    print("EXTRACTED PROFILE:")
    for field in SCALAR_FIELDS:
        print(f"  {field}: {candidate.get(field)}")
    print(f"  skills: {candidate.get('skills')}")
    print(f"  certifications_licenses: {candidate.get('certifications_licenses')}")

    print("  work_history:")
    for entry in candidate.get("work_history") or []:
        end = "present" if entry.get("is_current") else (entry.get("end_date") or "unspecified")
        print(f"    - {entry.get('title')} at {entry.get('employer')} "
              f"({entry.get('start_date') or 'unspecified'} - {end})")
        if entry.get("description"):
            # Full text, not truncated -- this is exactly what the reviewer
            # needs to check against the source. Cutting it short defeats
            # the point of the comparison.
            print(f"      {entry['description']}")

    print("  education:")
    for entry in candidate.get("education") or []:
        print(f"    - {entry.get('credential') or 'unspecified credential'} "
              f"in {entry.get('field_of_study') or 'unspecified field'}, {entry.get('institution')} "
              f"({entry.get('start_date') or 'unspecified'} - {entry.get('end_date') or 'unspecified'})")

    print("-" * 70)
    print("ORIGINAL RESUME TEXT (independently extracted -- compare against the above):")
    text = candidate.get("raw_resume_text") or "(none)"
    print(text)
    print("=" * 70)


def edit_in_editor(value):
    """Dump a JSON value to a temp file, open it in the user's editor, and
    read it back once they've saved and pressed Enter."""
    editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(value, f, indent=2)
        temp_path = f.name

    subprocess.run([editor, temp_path])
    input(f"Editing {temp_path} -- save it, then press Enter here to continue...")

    with open(temp_path, "r", encoding="utf-8") as f:
        edited = json.load(f)
    os.unlink(temp_path)
    return edited


def review_candidate(cur, candidate: dict, reviewer: str) -> str:
    """Returns 'confirmed', 'rejected', 'skipped', or 'quit'."""
    print_candidate(candidate)
    while True:
        choice = input("\n[y]es looks good / [e]dit / [s]kip / [r]eject / [q]uit: ").strip().lower()

        if choice == "y":
            db.set_review_status(cur, candidate["id"], "confirmed", reviewer)
            return "confirmed"

        if choice == "e":
            updates = {}
            for field in SCALAR_FIELDS:
                new_value = input(f"  {field} [{candidate.get(field)}] (Enter to keep): ").strip()
                if new_value:
                    updates[field] = new_value
            for field in LIST_FIELDS:
                if input(f"  Edit {field} {candidate.get(field)}? (y/N): ").strip().lower() == "y":
                    updates[field] = edit_in_editor(candidate.get(field) or [])
            for field in JSON_FIELDS:
                count = len(candidate.get(field) or [])
                if input(f"  Edit {field} ({count} entries)? (y/N): ").strip().lower() == "y":
                    updates[field] = psycopg2.extras.Json(edit_in_editor(candidate.get(field) or []))
            if updates:
                db.update_candidate_fields(cur, candidate["id"], updates)
            db.set_review_status(cur, candidate["id"], "confirmed", reviewer)
            return "confirmed"

        if choice == "s":
            return "skipped"

        if choice == "r":
            db.set_review_status(cur, candidate["id"], "rejected", reviewer)
            return "rejected"

        if choice == "q":
            return "quit"

        print("  Please enter y, e, s, r, or q.")


def main() -> None:
    config = load_config()
    reviewer = input("Reviewer name: ").strip() or "unknown"

    with db.get_connection(config) as conn:
        cur = conn.cursor()
        pending = db.get_pending_candidates(cur)
        if not pending:
            print("No candidates waiting for review.")
            return

        print(f"{len(pending)} candidate(s) waiting for review.")
        confirmed = rejected = skipped = 0
        for candidate in pending:
            result = review_candidate(cur, candidate, reviewer)
            conn.commit()
            if result == "confirmed":
                confirmed += 1
            elif result == "rejected":
                rejected += 1
            elif result == "skipped":
                skipped += 1
            elif result == "quit":
                break

        print(f"\nDone. Confirmed: {confirmed}, Rejected: {rejected}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
