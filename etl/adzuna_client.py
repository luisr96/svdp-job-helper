"""
Thin wrapper around the two Adzuna endpoints we use, plus the function that
turns Adzuna's raw job dict into the shape our `jobs` table expects.

Note on `salary_is_predicted`: Adzuna returns it as the string "0"/"1", not
a real boolean -- normalize_job() converts it.
"""
import psycopg2.extras
import requests

ADZUNA_BASE = "https://api.adzuna.com/v1/api"


class AdzunaClient:
    def __init__(self, config):
        self.config = config

    def _params(self, **extra):
        params = {
            "app_id": self.config.adzuna_app_id,
            "app_key": self.config.adzuna_app_key,
            "content-type": "application/json",
        }
        params.update(extra)
        return params

    def get_categories(self) -> list[dict]:
        """Fetch the current category list live -- not persisted anywhere,
        since it's cheap to call and we don't want a stale hardcoded list."""
        url = f"{ADZUNA_BASE}/jobs/{self.config.adzuna_country}/categories"
        resp = requests.get(url, params=self._params(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [{"tag": c["tag"], "label": c["label"]} for c in data.get("results", [])]

    def search_page(self, category_tag: str, page: int) -> list[dict]:
        url = f"{ADZUNA_BASE}/jobs/{self.config.adzuna_country}/search/{page}"
        params = self._params(
            category=category_tag,
            where=self.config.adzuna_where,
            distance=self.config.adzuna_distance_km,
            results_per_page=self.config.adzuna_results_per_page,
            sort_by="date",
        )
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("results", [])


def normalize_job(raw: dict, category_tag: str, category_label: str) -> dict:
    """Convert one raw Adzuna job dict into the param dict db.upsert_job() expects."""
    location = raw.get("location") or {}
    company = raw.get("company") or {}
    return {
        "adzuna_id": raw["id"],
        "title": raw.get("title"),
        "company_name": company.get("display_name"),
        "location_display": location.get("display_name"),
        "location_area": psycopg2.extras.Json(location.get("area", [])),
        "latitude": raw.get("latitude"),
        "longitude": raw.get("longitude"),
        "category_tag": category_tag,
        "category_label": category_label,
        "contract_type": raw.get("contract_type"),
        "contract_time": raw.get("contract_time"),
        "salary_min": raw.get("salary_min"),
        "salary_max": raw.get("salary_max"),
        "salary_is_predicted": str(raw.get("salary_is_predicted")) == "1",
        "description_snippet": raw.get("description"),
        "redirect_url": raw.get("redirect_url"),
        "adzuna_created_at": raw.get("created"),
        "raw_json": psycopg2.extras.Json(raw),
    }
