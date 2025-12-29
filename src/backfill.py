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

    def save_snapshot(self, data, sport_key):
        """
        Parses the historical response. 
        Note: The structure of the history endpoint is slightly different
        (it returns a 'timestamp' field for the snapshot time).
        """
        count = 0
        # data is { timestamp: "...", previous_timestamp: "...", data: [ ...events... ] }
        snapshot_ts = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        
        for game in data['data']:
            # 1. Upsert Event
            event_id = game['id']
            commence_time = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
            
            # Check if event exists (cache this in memory for speed in prod)
            existing = self.session.query(Event).filter_by(id=event_id).first()
            if not existing:
                evt = Event(
                    id=event_id,
                    sport_key=sport_key,
                    commence_time=commence_time,
                    home_team=game['home_team'],
                    away_team=game['away_team']
                )
                self.session.add(evt)

            # 2. Save Odds
            for book in game['bookmakers']:
                if settings.TARGET_BOOKMAKERS and book['key'] not in settings.TARGET_BOOKMAKERS:
                    continue

                for market in book['markets']:
                    # Simple H2H Parser (Expand for spreads if needed)
                    home_price, away_price = None, None
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            if outcome['name'] == game['home_team']:
                                home_price = outcome['price']
                            elif outcome['name'] == game['away_team']:
                                away_price = outcome['price']
                    
                    if home_price and away_price:
                        snap = OddsSnapshot(
                            event_id=event_id,
                            bookmaker=book['key'],
                            market_key=market['key'],
                            timestamp=snapshot_ts,
                            home_price=home_price,
                            away_price=away_price
                        )
                        self.session.add(snap)
                        count += 1
        
        self.session.commit()
        return count

    def run_backfill(self, sport, start_date, end_date, interval_hours=24):
        """
        Iterates from start to end.
        interval_hours=24 gets 1 snapshot/day.
        interval_hours=1 gets hourly data (expensive!).
        """
        current = start_date
        total_snapshots = 0
        
        while current <= end_date:
            iso_str = current.strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"Fetching history for {sport} at {iso_str}...")
            
            response = self.get_historical_odds(sport, iso_str)
            
            if response and 'data' in response:
                count = self.save_snapshot(response, sport)
                total_snapshots += count
                logger.info(f"Saved {count} snapshots.")
            
            # Move forward
            current += timedelta(hours=interval_hours)
            
            # Rate limit protection (don't hammer the history endpoint)
            time.sleep(1.5) 

        logger.info(f"Backfill Complete. Total: {total_snapshots}")

@click.command()
@click.option('--sport', default='basketball_nba', help='Sport Key')
@click.option('--days', default=30, help='How many days back to go')
@click.option('--interval', default=24, help='Hours between snapshots (24=Daily)')
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

if __name__ == '__main__':
    cli()