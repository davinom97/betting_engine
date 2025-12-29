import requests
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception,
)

from .config import settings
from .database import Event, OddsSnapshot

logger = logging.getLogger(__name__)


# (#11) Rate Limit Checker
def is_rate_limited(exception):
    return isinstance(exception, requests.HTTPError) and getattr(exception.response, 'status_code', None) == 429


class OddsAPiclient:
    """
    Wrapper for The Odds API v4.
    Handles rate limiting, sessions, and url construction.
    """
    def __init__(self):
        self.api_key = settings.ODDS_API_KEY
        self.host = settings.ODDS_API_HOST
        self.session = requests.Session()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout))
        | retry_if_exception(is_rate_limited)
    )
    def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Any:
        url = f"{self.host}{endpoint}"
        final_params = {"apiKey": self.api_key}
        if params:
            final_params.update(params)

        try:
            response = self.session.get(url, params=final_params, timeout=10)
            response.raise_for_status()

            # Optional: log remaining quota if provided
            remaining = response.headers.get("x-requests-remaining")
            if remaining is not None:
                try:
                    if int(remaining) < 50:
                        logger.warning(f"Low API quota remaining: {remaining}")
                except Exception:
                    pass

            return response.json()
        except requests.HTTPError as e:
            if getattr(e.response, 'status_code', None) == 401:
                logger.error("Invalid API Key.")
            elif getattr(e.response, 'status_code', None) == 429:
                logger.error("Rate limit exceeded.")
            raise

    def get_upcoming_odds(self, sport_key: str) -> List[Dict]:
        """Fetch live/upcoming odds for a specific sport."""
        endpoint = f"/v4/sports/{sport_key}/odds"
        params = {
            "regions": settings.TARGET_REGIONS,
            "markets": settings.TARGET_MARKETS,
            "oddsFormat": "decimal",
        }
        data = self._get(endpoint, params)
        logger.info(f"Fetched {len(data)} events for {sport_key}")
        return data

    def get_results(self, sport_key: str, days_from: int = 3) -> List[Dict]:
        endpoint = f"/v4/sports/{sport_key}/scores"
        params = {"daysFrom": days_from}
        return self._get(endpoint, params)


class IngestionEngine:
    """Orchestrates fetching data from API and persisting to DB."""
    def __init__(self, db_session: Session):
        self.client = OddsAPiclient()
        self.db = db_session

    def run_daily_ingest(self):
        logger.info("Starting ingestion cycle...")
        for sport in settings.TARGET_SPORTS:
            try:
                self.process_sport(sport)
            except Exception as e:
                logger.error(f"Failed to ingest {sport}: {str(e)}", exc_info=True)
        logger.info("Ingestion cycle complete.")

    def process_sport(self, sport_key: str):
        odds_data = self.client.get_upcoming_odds(sport_key)
        new_snapshots = 0

        try:
            for game_json in odds_data:
                self._upsert_event(game_json, sport_key)
                new_snapshots += self._save_snapshots(game_json)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        logger.info(f"Saved {new_snapshots} new snapshots for {sport_key}")

    def _upsert_event(self, data: Dict, sport_key: str):
        event_id = data['id']
        commence_time = datetime.fromisoformat(data['commence_time'].replace('Z', '+00:00'))

        existing_event = self.db.query(Event).filter(Event.id == event_id).first()
        if not existing_event:
            event = Event(
                id=event_id,
                sport_key=sport_key,
                commence_time=commence_time,
                home_team=data.get('home_team'),
                away_team=data.get('away_team')
            )
            self.db.add(event)
        else:
            existing_event.commence_time = commence_time

    def _save_snapshots(self, data: Dict) -> int:
        count = 0
        event_id = data['id']
        ts = datetime.now(timezone.utc)

        for book in data.get('bookmakers', []):
            if settings.TARGET_BOOKMAKERS and book.get('key') not in settings.TARGET_BOOKMAKERS:
                continue

            for market in book.get('markets', []):
                for outcome in market.get('outcomes', []):
                    last_snap = self.db.query(OddsSnapshot).filter_by(
                        event_id=event_id,
                        bookmaker=book.get('key'),
                        market_key=market.get('key'),
                        selection=outcome.get('name'),
                        handicap=outcome.get('point')
                    ).order_by(OddsSnapshot.timestamp.desc()).first()

                    if last_snap and last_snap.odds_decimal == outcome.get('price'):
                        continue

                    snap = OddsSnapshot(
                        event_id=event_id,
                        timestamp=ts,
                        bookmaker=book.get('key'),
                        market_key=market.get('key'),
                        selection=outcome.get('name'),
                        handicap=outcome.get('point'),
                        odds_decimal=outcome.get('price')
                    )
                    self.db.add(snap)
                    count += 1
        return count


if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    ingestor = IngestionEngine(session)
    ingestor.run_daily_ingest()