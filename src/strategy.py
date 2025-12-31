import pandas as pd
from .features import calculate_kelly_fraction

class DecisionEngine:
    def __init__(self, bankroll, max_daily_stake_percent=0.05):
        self.bankroll = bankroll
        self.max_stake = bankroll * max_daily_stake_percent
    def select_positive_ev_bets(self, candidates_df):
        """
        Input: DataFrame of today's games with 'model_prob' and 'dk_price'.
        Output: DataFrame of all bets that pass gating and have positive EV, sorted by EV desc.
        """
        if candidates_df.empty:
            return pd.DataFrame()

        results = []

        for index, row in candidates_df.iterrows():
            # 1. Calculate Expected Value (EV)
            # EV = (Prob * (Decimal_Odds - 1)) - (1 - Prob)
            # Simplified: EV% = (Prob * Decimal_Odds) - 1
            ev_percent = (row['model_prob'] * row['dk_price']) - 1

            # GATE 1: Positive EV
            if ev_percent <= 0:
                continue

            # GATE 2: Credible Edge (The Upgrade)
            if row.get('clv_projected', 0) < row.get('p_implied', row.get('model_prob', 0)):
                # Market is steaming against us. The edge might be a mirage (lagging price).
                continue

            # GATE 3: Context Uncertainty
            if row.get('context_uncertainty_penalty', 0) > 0.5:
                if ev_percent < 0.10:  # Require 10% edge to risk injury chaos
                    continue

            # 3. Sizing: Fractional Kelly
            kelly_stake_pct = calculate_kelly_fraction(
                row['model_prob'],
                row['dk_price'],
                fractional_kelly=0.25
            )

            dollar_stake = self.bankroll * kelly_stake_pct

            # 4. Cap the stake
            final_stake = min(dollar_stake, self.max_stake)

            results.append({
                'event_id': row['event_id'],
                'selection': row['selection'],
                'odds': row['dk_price'],
                'model_prob': row['model_prob'],
                'ev': ev_percent,
                'stake': final_stake
            })

        if not results:
            return pd.DataFrame()

        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values(by='ev', ascending=False).reset_index(drop=True)

        return results_df