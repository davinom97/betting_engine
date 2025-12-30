import click
import requests
import logging
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.database import get_engine, OddsSnapshot, Event

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")

class HistoryLoader:
    def __init__(self):
        self.session = sessionmaker(bind=get_engine())()
        self.api_key = settings.ODDS_API_KEY
        self.host = settings.ODDS_API_HOST

    def get_historical_odds(self, sport, date_iso):
        """
        Fetches odds for a specific sport at a specific historical timestamp.
        Endpoint: /v4/sports/{sport}/odds-history
        """
        url = f"{self.host}/v4/sports/{sport}/odds-history"
        params = {
            "apiKey": self.api_key,
            "regions": settings.TARGET_REGIONS,
            "markets": settings.TARGET_MARKETS,
            "date": date_iso, # The specific historical moment
            "oddsFormat": "decimal"
        }
        
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Failed to fetch {date_iso} for {sport}: {e}")
            return None

    import click
    import requests
    import logging
    import time
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm import sessionmaker
    from src.config import settings
    from src.database import get_engine, OddsSnapshot, Event

    # Setup Logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("backfill")


    class HistoryLoader:
        def __init__(self):
            self.session = sessionmaker(bind=get_engine())()
            self.api_key = settings.ODDS_API_KEY
            self.host = settings.ODDS_API_HOST

        def get_historical_odds(self, sport, date_iso):
            """
            Fetches odds for a specific sport at a specific historical timestamp.
            Endpoint: /v4/sports/{sport}/odds-history
            """
            url = f"{self.host}/v4/sports/{sport}/odds-history"
            params = {
                "apiKey": self.api_key,
                "regions": settings.TARGET_REGIONS,
                "markets": settings.TARGET_MARKETS,
                "date": date_iso,  # The specific historical moment
                "oddsFormat": "decimal",
            }

            try:
                r = requests.get(url, params=params, timeout=15)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                logger.error(f"Failed to fetch {date_iso} for {sport}: {e}")
                return None

        def save_snapshot(self, data, sport_key):
            """
            Parses the historical response using the UNIFIED schema (Row-Per-Outcome).
            Handles H2H, Spreads, Totals, and Props generically.
            """
            count = 0
            # data is { timestamp: "...", previous_timestamp: "...", data: [ ...events... ] }
            # Parse the snapshot timestamp safely
            try:
                snapshot_ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                snapshot_ts = datetime.now(timezone.utc)

            for game in data.get("data", []):
                # 1. Upsert Event
                event_id = game["id"]
                commence_time = datetime.fromisoformat(game["commence_time"].replace("Z", "+00:00"))

                # Check if event exists (cache this in memory for speed in prod)
                existing = self.session.query(Event).filter_by(id=event_id).first()
                if not existing:
                    evt = Event(
                        id=event_id,
                        sport_key=sport_key,
                        commence_time=commence_time,
                        home_team=game.get("home_team"),
                        away_team=game.get("away_team"),
                    )
                    self.session.add(evt)
                else:
                    # Update commence time if it changed (common in history)
                    existing.commence_time = commence_time

                # 2. Save Odds (Iterate ALL Bookmakers -> ALL Markets -> ALL Outcomes)
                for book in game.get("bookmakers", []):
                    if settings.TARGET_BOOKMAKERS and book.get("key") not in settings.TARGET_BOOKMAKERS:
                        continue

                    for market in book.get("markets", []):
                        # No longer filtering for just 'h2h'.
                        # This loop now handles 'h2h', 'spreads', 'totals' automatically.

                        for outcome in market.get("outcomes", []):
                            # Create one row per outcome (Unified Schema)
                            snap = OddsSnapshot(
                                event_id=event_id,
                                bookmaker=book.get("key"),
                                market_key=market.get("key"),
                                timestamp=snapshot_ts,
                                selection=outcome.get("name"),
                                handicap=outcome.get("point"),  # Handles Spreads/Totals
                                odds_decimal=outcome.get("price"),
                            )
                            self.session.add(snap)
                            count += 1

            self.session.commit()
            return count

        def run_backfill(self, sport, start_date, end_date, interval_hours=24):
            """
            Iterates from start to end.
            interval_hours=24 gets 1 snapshot/day.
            """
            current = start_date
            total_snapshots = 0

            while current <= end_date:
                iso_str = current.strftime("%Y-%m-%dT%H:%M:%SZ")
                logger.info(f"Fetching history for {sport} at {iso_str}...")

                response = self.get_historical_odds(sport, iso_str)

                if response and "data" in response:
                    count = self.save_snapshot(response, sport)
                    total_snapshots += count
                    logger.info(f"Saved {count} snapshots.")
                elif response:
                    logger.warning(f"No data found for {sport} at {iso_str}")

                # Move forward
                current += timedelta(hours=interval_hours)

                # Rate limit protection (don't hammer the history endpoint)
                time.sleep(1.5)

            logger.info(f"Backfill Complete. Total: {total_snapshots}")


    @click.command()
    @click.option("--sport", default="basketball_nba", help="Sport Key")
    @click.option("--days", default=30, help="How many days back to go")
    @click.option("--interval", default=24, help="Hours between snapshots (24=Daily)")
    def cli(sport, days, interval):
        """Backfills historical odds data."""
        loader = HistoryLoader()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Round to nearest hour
        start_date = start_date.replace(minute=0, second=0, microsecond=0)

        print(f"--- STARTING BACKFILL: {sport} ---")
        print(f"From: {start_date}")
        print(f"To:   {end_date}")
        print(f"Interval: Every {interval} hours")

        loader.run_backfill(sport, start_date, end_date, interval)


    if __name__ == "__main__":
        cli()