"""
Plain, deterministic text extraction -- no LLM involved.

This exists purely to give a human reviewer an independent reference to
check Claude's structured extraction against. If Claude misreads the PDF,
that's a problem this function does NOT share, because it never sees
Claude's interpretation -- it just pulls the text layer straight out of
the PDF. That independence is the whole point: it's what makes the
reviewer's "does this match?" check meaningful instead of circular.
"""
from pypdf import PdfReader


def extract_plain_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages).strip()
    if not text:
        # Pure image scan with no text layer -- Claude may still be able to
        # read it via vision, but we have nothing independent to show a
        # reviewer. Surface that plainly rather than silently showing blank.
        return "(no extractable text layer found in this PDF -- likely a scanned image; review against the original file directly)"
    return text
