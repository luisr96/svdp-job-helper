"""
Config for the job ETL pipeline (dataclass and a loader function)
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    # postgresql://postgres:[password]@[host]:5432/postgres
    database_url: str

    # Adzuna
    adzuna_app_id: str
    adzuna_app_key: str
    adzuna_country: str          # e.g. "us"
    adzuna_where: str            # zip code or place name, e.g. "34104"
    adzuna_distance_km: int      # search radius around `adzuna_where`
    adzuna_max_pages_per_category: int
    adzuna_results_per_page: int

    # ETL behavior
    expiry_days: int             # days a listing can go unseen before we mark it expired


def load_config() -> Config:
    return Config(
        database_url=_require("DATABASE_URL"),
        adzuna_app_id=_require("ADZUNA_APP_ID"),
        adzuna_app_key=_require("ADZUNA_APP_KEY"),
        adzuna_country=os.environ.get("ADZUNA_COUNTRY", "us"),
        adzuna_where=os.environ.get("ADZUNA_WHERE", "34104"),
        adzuna_distance_km=int(os.environ.get("ADZUNA_DISTANCE_KM", "20")),
        adzuna_max_pages_per_category=int(os.environ.get("ADZUNA_MAX_PAGES", "5")),
        adzuna_results_per_page=int(os.environ.get("ADZUNA_RESULTS_PER_PAGE", "50")),
        expiry_days=int(os.environ.get("EXPIRY_DAYS", "10")),
    )
