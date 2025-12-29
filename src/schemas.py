from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal

class UnifiedBet(BaseModel):
    # Identity
    event_id: str
    sport_key: Optional[str] = "unknown"
    selection: str

    # Market
    market_key: str
    market_family: Literal['MAIN', 'PERIOD', 'PROP', 'FUTURE']
    handicap: Optional[float] = None

    # Price
    bookmaker: str
    odds_decimal: float
    timestamp: datetime

    # Context
    is_player_prop: bool = False
    player_name: Optional[str] = None

    @property
    def implied_prob(self) -> float:
        return 1.0 / self.odds_decimal if self.odds_decimal > 0 else 0.0