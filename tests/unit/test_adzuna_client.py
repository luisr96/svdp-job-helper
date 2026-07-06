"""
Unit test for adzuna_client.normalize_job() -- pure field-mapping logic,
no DB connection or network call involved, so this belongs in tests/unit/
rather than tests/integration/.

    pytest tests/unit/test_adzuna_client.py -v
"""
from etl.adzuna_client import normalize_job

# A representative raw Adzuna job payload, based on the fields normalize_job() reads
RAW_JOB = {
    "id": "4567890123",
    "title": "Registered Nurse - Night Shift",
    "company": {"display_name": "Example Health System"},
    "location": {
        "display_name": "Fort Myers, FL",
        "area": ["US", "Florida", "Lee County", "Fort Myers"],
    },
    "latitude": 26.6406,
    "longitude": -81.8723,
    "contract_type": "permanent",
    "contract_time": "full_time",
    "salary_min": 65000.0,
    "salary_max": 85000.0,
    "salary_is_predicted": "1",
    "description": "Seeking an experienced RN for our night shift team...",
    "redirect_url": "https://example.com/jobs/4567890123",
    "created": "2026-07-01T12:00:00Z",
}


def test_normalize_job_maps_basic_fields():
    job = normalize_job(RAW_JOB, category_tag="healthcare-nursing-jobs", category_label="Healthcare & Nursing Jobs")

    assert job["adzuna_id"] == "4567890123"
    assert job["title"] == "Registered Nurse - Night Shift"
    assert job["company_name"] == "Example Health System"
    assert job["location_display"] == "Fort Myers, FL"
    assert job["latitude"] == 26.6406
    assert job["longitude"] == -81.8723
    assert job["category_tag"] == "healthcare-nursing-jobs"
    assert job["category_label"] == "Healthcare & Nursing Jobs"
    assert job["contract_type"] == "permanent"
    assert job["contract_time"] == "full_time"
    assert job["salary_min"] == 65000.0
    assert job["salary_max"] == 85000.0
    assert job["description_snippet"] == RAW_JOB["description"]
    assert job["redirect_url"] == "https://example.com/jobs/4567890123"
    assert job["adzuna_created_at"] == "2026-07-01T12:00:00Z"


def test_normalize_job_converts_salary_is_predicted_string_to_bool():
    """Adzuna returns this as the string '0'/'1', not a real boolean --
    this is the one field normalize_job() specifically has to convert."""
    job_predicted = normalize_job({**RAW_JOB, "salary_is_predicted": "1"}, "tag", "Label")
    job_not_predicted = normalize_job({**RAW_JOB, "salary_is_predicted": "0"}, "tag", "Label")

    assert job_predicted["salary_is_predicted"] is True
    assert job_not_predicted["salary_is_predicted"] is False


def test_normalize_job_wraps_location_area_and_raw_json_for_jsonb():
    """location_area and raw_json get wrapped in psycopg2.extras.Json(...)
    so they round-trip correctly as jsonb columns -- confirm the wrapping
    happened and the underlying value is what we expect."""
    job = normalize_job(RAW_JOB, "tag", "Label")

    # psycopg2.extras.Json stores the original object on .adapted
    assert job["location_area"].adapted == ["US", "Florida", "Lee County", "Fort Myers"]
    assert job["raw_json"].adapted == RAW_JOB


def test_normalize_job_handles_missing_optional_fields():
    """Adzuna doesn't guarantee every field is present -- missing location/
    company/etc. should produce None values, not raise a KeyError."""
    minimal_raw = {"id": "111", "title": "Some Job"}

    job = normalize_job(minimal_raw, "tag", "Label")

    assert job["adzuna_id"] == "111"
    assert job["title"] == "Some Job"
    assert job["company_name"] is None
    assert job["location_display"] is None
    assert job["latitude"] is None
    assert job["longitude"] is None
    assert job["salary_min"] is None
    assert job["salary_is_predicted"] is False  # str(None) != "1"
    assert job["location_area"].adapted == []
