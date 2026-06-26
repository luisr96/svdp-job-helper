"""
Embeddings for the matching layer, via Voyage AI -- Anthropic doesn't offer
its own embedding model and recommends Voyage as the standard pairing.

Two canonical-text builders (one per side of the match) and a thin Voyage
wrapper that batches requests. The actual narrowing query lives in db.py
since it's just SQL (`ORDER BY embedding <=> %s LIMIT N`).
"""
import psycopg2.extras
import voyageai

EMBEDDING_MODEL = "voyage-4"
EMBEDDING_BATCH_SIZE = 100  # keep well under Voyage's per-request limits


def build_job_embedding_text(title: str, category_label: str, requirements: dict) -> str:
    """Canonical text for a job, built from the structured fields we already
    extracted -- not the raw description, which is full of boilerplate
    ("DEPARTMENT: 26194... WORK SCHEDULE: 12 Hour Night...") that's noise
    for matching purposes."""
    parts = [title or "", category_label or ""]
    if requirements.get("employment_type"):
        parts.append(requirements["employment_type"])
    if requirements.get("education_level"):
        parts.append(requirements["education_level"])
    if requirements.get("skills"):
        parts.append("Skills: " + ", ".join(requirements["skills"]))
    if requirements.get("licenses_certifications"):
        parts.append("Licenses/certifications: " + ", ".join(requirements["licenses_certifications"]))
    return ". ".join(p for p in parts if p)


def build_candidate_embedding_text(candidate: dict) -> str:
    """Canonical text for a candidate, built from their confirmed profile."""
    parts = []
    if candidate.get("summary"):
        parts.append(candidate["summary"])
    for entry in candidate.get("work_history") or []:
        title = entry.get("title") or ""
        employer = entry.get("employer") or ""
        desc = entry.get("description") or ""
        parts.append(f"{title} at {employer}. {desc}".strip())
    for entry in candidate.get("education") or []:
        credential = entry.get("credential") or ""
        field = entry.get("field_of_study") or ""
        parts.append(f"{credential} in {field}".strip())
    if candidate.get("skills"):
        parts.append("Skills: " + ", ".join(candidate["skills"]))
    if candidate.get("certifications_licenses"):
        parts.append("Licenses/certifications: " + ", ".join(candidate["certifications_licenses"]))
    return ". ".join(p for p in parts if p)


def embed_texts(client: voyageai.Client, texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed a list of texts, batching to stay well under Voyage's per-request
    limits. input_type is the same ("document") for both jobs and candidates
    here -- this is a symmetric profile-to-profile comparison, not a short
    query against long documents, so Voyage's asymmetric query/document
    tuning doesn't apply the way it would for a search use case."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i: i + EMBEDDING_BATCH_SIZE]
        result = client.embed(batch, model=EMBEDDING_MODEL, input_type=input_type)
        all_embeddings.extend(result.embeddings)
    return all_embeddings


def backfill_job_embeddings(cur, client: voyageai.Client) -> int:
    """Embed any job_requirements rows that don't have one yet -- covers
    both the initial backfill and, since this is also called from the daily
    ETL run, every day's newly-extracted jobs going forward. Returns the
    count embedded."""
    cur.execute(
        """
        select r.job_id, j.title, j.category_label, r.skills, r.education_level,
               r.employment_type, r.licenses_certifications
        from job_requirements r
        join jobs j on j.id = r.job_id
        where r.embedding is null
        """
    )
    rows = cur.fetchall()
    if not rows:
        return 0

    texts = [
        build_job_embedding_text(
            row["title"], row["category_label"],
            {
                "skills": row["skills"],
                "education_level": row["education_level"],
                "employment_type": row["employment_type"],
                "licenses_certifications": row["licenses_certifications"],
            },
        )
        for row in rows
    ]
    embeddings = embed_texts(client, texts, input_type="document")

    for row, embedding in zip(rows, embeddings):
        cur.execute(
            "update job_requirements set embedding = %s where job_id = %s",
            (embedding, row["job_id"]),
        )
    return len(rows)


def embed_candidate(cur, client: voyageai.Client, candidate: dict) -> None:
    """Embed one candidate's confirmed profile and store it. `candidate`
    should already be the up-to-date row (post any reviewer edits)."""
    text = build_candidate_embedding_text(candidate)
    embedding = embed_texts(client, [text], input_type="document")[0]
    cur.execute(
        "update candidates set embedding = %s where id = %s",
        (embedding, candidate["id"]),
    )


def backfill_candidate_embeddings(cur, client: voyageai.Client) -> int:
    """Embed any confirmed candidates that don't have one yet -- covers
    anyone confirmed before this feature existed. Returns the count embedded."""
    cur.execute(
        "select * from candidates where review_status = 'confirmed' and embedding is null"
    )
    candidates = cur.fetchall()
    for candidate in candidates:
        embed_candidate(cur, client, candidate)
    return len(candidates)
