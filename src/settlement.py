import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from src.ingest import OddsAPiclient
from src.database import Event

logger = logging.getLogger(__name__)

class SettlementEngine:
    def __init__(self, session: Session):
        self.client = OddsAPiclient()
        self.session = session

    def update_results(self, sport_key: str, days_back: int = 3):
        """
        Fetches 'scores' endpoint.
        Matches results to our Events table to determine the winner.
        """
        logger.info(f"Checking results for {sport_key} (last {days_back} days)...")
        
        # The Odds API 'daysFrom' usually supports up to 3 days.
        # For deeper history, you often need a CSV import, but this handles daily Ops.
        scores_data = self.client.get_results(sport_key, days_from=days_back)
        
        updates = 0
        for game in scores_data:
            if not game['completed']:
                continue
                
            # Find the event in our DB
            event = self.session.query(Event).filter_by(id=game['id']).first()
            if not event or event.completed:
                continue
            
            # Determine Winner
            # (Logic varies by sport, this is a generic Moneyline parser)
            h_score = None
            a_score = None
            
            # Parse score list usually looking like: [{"name": "Home", "score": "10"}, ...]
            if game['scores']:
                for s in game['scores']:
                    if s['name'] == event.home_team:
                        h_score = int(s['score'])
                    elif s['name'] == event.away_team:
                        a_score = int(s['score'])
            
            if h_score is not None and a_score is not None:
                event.home_score = h_score
                event.away_score = a_score
                event.completed = True
                
                if h_score > a_score:
                    event.winner = "Home"
                else:
                    event.winner = "Away"
                
                updates += 1
        
        self.session.commit()
        logger.info(f"Settled {updates} events for {sport_key}.")