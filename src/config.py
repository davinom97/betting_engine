from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent


def _default_db_url() -> str:
    return f"sqlite:///{BASE_DIR}/data/betting.db"


class Settings(BaseSettings):
    # --- API ---
    ODDS_API_KEY: str
    ODDS_API_HOST: str = "https://api.the-odds-api.com"
    # Keep these as comma-separated strings in .env to avoid JSON decoding issues
    TARGET_SPORTS: str = "basketball_nba,americanfootball_nfl,icehockey_nhl"
    TARGET_MARKETS: str = "h2h,spreads,totals,player_points"
    TARGET_REGIONS: str = "us,us2"
    TARGET_BOOKMAKERS: str = "draftkings,pinnacle,fanduel,betmgm"

    # --- DATABASE ---
    DATABASE_URL: str = _default_db_url()
    
    # --- STRATEGY & RISK ---
    BANKROLL: float = 10000.0
    MAX_DAILY_STAKE_PERCENT: float = 0.05
    KELLY_FRACTION: float = 0.25
    
    # --- MODELING CONSTANTS ---
    FEATURE_HISTORY_BUFFER_SIZE: int = 5
    INJURY_EDGE_THRESHOLD: float = 0.10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _default_database_url(cls, v):
        # If .env contains an empty DATABASE_URL, fall back to the default
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return _default_db_url()
        return v


settings = Settings()

# Normalize comma-separated env fields into Python lists for runtime convenience.
def _to_list(value: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [s.strip() for s in str(value).split(",") if s.strip()]

settings.TARGET_SPORTS = _to_list(settings.TARGET_SPORTS)
settings.TARGET_MARKETS = _to_list(settings.TARGET_MARKETS)
settings.TARGET_REGIONS = _to_list(settings.TARGET_REGIONS)
settings.TARGET_BOOKMAKERS = _to_list(settings.TARGET_BOOKMAKERS)