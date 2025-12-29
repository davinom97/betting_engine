import numpy as np
import pandas as pd
from typing import List, Dict
from .schemas import UnifiedBet
from .plugins import get_plugin

# --- (#1) ADDED KELLY FUNCTION ---
def calculate_kelly_fraction(prob, decimal_odds, fractional_kelly=0.25):
    if decimal_odds <= 1: return 0.0
    b = decimal_odds - 1
    q = 1 - prob
    f_star = (b * prob - q) / b
    return max(0.0, f_star) * fractional_kelly

class UnifiedFeatureEngine: # (#3) Renamed in main.py import instead
    def __init__(self):
        self.history_buffer: Dict[str, List[UnifiedBet]] = {} 

    def classify_market(self, market_key: str) -> str:
        if 'player' in market_key: return 'PROP'
        if 'period' in market_key or 'q1' in market_key: return 'PERIOD'
        if 'futures' in market_key: return 'FUTURE'
        return 'MAIN'

    def process_snapshots(self, snapshots_df: pd.DataFrame, context_data: dict = None) -> pd.DataFrame:
        if context_data is None: context_data = {}
        features_output = []
        snapshots_df = snapshots_df.sort_values('timestamp')

        for _, row in snapshots_df.iterrows():
            market_fam = self.classify_market(row['market_key'])
            
            # (#2) Pass sport_key if available in row, else unknown
            bet = UnifiedBet(
                event_id=str(row['event_id']),
                sport_key=row.get('sport_key', 'unknown'),
                selection=row['selection'],
                market_key=row['market_key'],
                market_family=market_fam,
                handicap=row.get('handicap'), 
                bookmaker=row['bookmaker'],
                odds_decimal=float(row['odds_decimal']), # (#8) Unified Name
                timestamp=row['timestamp'],
                is_player_prop=(market_fam == 'PROP'),
                player_name=row['selection'] if market_fam == 'PROP' else None
            )
            
            key = f"{bet.event_id}_{bet.market_key}_{bet.selection}_{bet.handicap}"
            if key not in self.history_buffer: self.history_buffer[key] = []
            
            plugin = get_plugin(market_fam)
            
            # (#9) Context Plumbing
            # We assume context_data now has 'live_odds' injected by main.py
            evt_context = {
                'market_snapshot': context_data.get('live_odds', {}).get(bet.event_id, {}),
                'injuries': context_data.get('injuries', {}).get(bet.event_id, {})
            }
            
            feats = plugin.calculate_features(bet, self.history_buffer[key], evt_context)
            self.history_buffer[key].append(bet)
            if len(self.history_buffer[key]) > 5: self.history_buffer[key].pop(0)
            
            features_output.append({
                'event_id': bet.event_id,
                'market_family': bet.market_family,
                'selection': bet.selection,
                'book': bet.bookmaker,
                'timestamp': bet.timestamp,
                'p_implied': bet.implied_prob,
                'p_fair_consensus': feats['p_fair_consensus'],
                'velocity': feats['velocity'],
                'context_uncertainty': feats['context_uncertainty_penalty']
            })
            
        return pd.DataFrame(features_output)


# --- BACKWARD COMPATIBILITY WRAPPER ---
def generate_features_for_backtest(raw_snapshots_df):
    engine = UnifiedFeatureEngine()
    return engine.process_snapshots(raw_snapshots_df, context_data={})