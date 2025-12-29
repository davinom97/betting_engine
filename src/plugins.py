import numpy as np
from typing import Dict, List, Any
from .schemas import UnifiedBet

# --- CONFIG: Bookmaker Sharpness Weights ---
# (In prod, learn these from historical CLV accuracy)
SHARPNESS = {
    'pinnacle': 1.0,
    'circa': 0.9,
    'betonlineag': 0.8,
    'draftkings': 0.6, # Execution venue is usually softer
    'fanduel': 0.6,
    'mgm': 0.5
}

def to_logit(p):
    p = np.clip(p, 0.001, 0.999)
    return np.log(p / (1 - p))

def to_prob(l):
    return 1 / (1 + np.exp(-l))

class BaseFeaturePlugin:
    def calculate_features(self, bet: UnifiedBet, history: List[UnifiedBet], context: Dict) -> Dict:
        raise NotImplementedError

class MainMarketPlugin(BaseFeaturePlugin):
    """
    UPGRADE 1: Reference Price Layer.
    Uses inverse-variance weighting based on Book Sharpness.
    """
    def calculate_features(self, bet: UnifiedBet, history: List[UnifiedBet], context: Dict) -> Dict:
        # 1. Build Sharp Consensus
        # We need the MOST RECENT odds from every book for this event/selection
        # 'context' here is passed from the engine, containing the latest snapshot of the WHOLE market
        market_snapshot = context.get('market_snapshot', {}) # {book: odds}
        
        weighted_logit_sum = 0.0
        total_weight = 0.0
        
        # Add the execution book (bet itself)
        w_dk = SHARPNESS.get(bet.bookmaker, 0.5)
        weighted_logit_sum += w_dk * to_logit(bet.implied_prob)
        total_weight += w_dk
        
        # Add other books from snapshot
        for book, odds in market_snapshot.items():
            if book == bet.bookmaker: continue
            if odds <= 1.0: continue
            
            w = SHARPNESS.get(book, 0.5)
            p_imp = 1.0 / odds
            weighted_logit_sum += w * to_logit(p_imp)
            total_weight += w
            
        avg_logit = weighted_logit_sum / total_weight if total_weight > 0 else to_logit(bet.implied_prob)
        p_fair_sharp = to_prob(avg_logit)
        
        # 2. Calculate Projected CLV (Simple drift model)
        # If Velocity is high, project it continues for 1 hour
        velocity = 0.0
        if len(history) >= 2:
            dt = (bet.timestamp - history[-2].timestamp).total_seconds() / 3600
            if dt > 0:
                velocity = (to_logit(bet.implied_prob) - to_logit(history[-2].implied_prob)) / dt
        
        clv_proj = to_prob(avg_logit + (velocity * 1.0)) # 1 hr projection
        
        return {
            'p_fair_consensus': p_fair_sharp, # The new "Sharp" prior
            'velocity': velocity,
            'clv_projected': clv_proj,
            'player_availability_score': 1.0, # N/A for Main Markets
            'context_uncertainty_penalty': 0.0
        }

class PropMarketPlugin(BaseFeaturePlugin):
    """
    UPGRADE 3: Bayesian Injury Updates.
    Adjusts probability based on 'Questionable'/'Limited' tags.
    """
    def calculate_features(self, bet: UnifiedBet, history: List[UnifiedBet], context: Dict) -> Dict:
        player = bet.player_name
        injury_report = context.get('injuries', {})
        
        # Default Prior: Healthy (A=1)
        # logit(P(Play)) starts high (e.g., 95%)
        availability_logit = 3.0 
        
        status = injury_report.get(player, {}).get('status', 'Healthy')
        source_reliability = injury_report.get(player, {}).get('reliability', 0.5)
        
        # Bayesian Updates (Delta)
        if status == 'Questionable':
            # Official Q tag usually implies ~50-60% chance to play
            # We shift the logit DOWN massively
            availability_logit -= 2.5 
        elif status == 'Doubtful':
            availability_logit -= 4.0
        elif status == 'Limited Practice':
            # Plays, but minutes reduced.
            # We don't change availability, but we apply a penalty later
            availability_logit -= 0.5

        p_availability = to_prob(availability_logit)
        
        # Propagate to Stat Expectation
        # If P(Play) drops, the expected value of 'Over' drops (assuming DNP = Void or 0 depending on rules)
        # For this engine, we assume "Active but limited" risk
        
        p_adjusted = bet.implied_prob
        
        if 'Over' in bet.selection and status in ['Questionable', 'Limited Practice']:
            # Bayesian shrinkage of the stat projection
            # If limited, expect 85% of usual production
            p_adjusted = bet.implied_prob * (0.8 + 0.2 * p_availability)
            
        return {
            'p_fair_consensus': p_adjusted,
            'velocity': 0.0, # Props are too sparse for velocity
            'clv_projected': p_adjusted,
            'player_availability_score': p_availability,
            'context_uncertainty_penalty': (1.0 - p_availability) * source_reliability
        }

def get_plugin(market_family: str) -> BaseFeaturePlugin:
    if market_family == 'PROP':
        return PropMarketPlugin()
    return MainMarketPlugin()