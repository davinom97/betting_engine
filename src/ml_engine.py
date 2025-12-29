import pandas as pd
import numpy as np
from sklearn.isotonic import IsotonicRegression
from collections import defaultdict
import logging
from sqlalchemy.orm import Session
from src.database import MarketFeatures, Event

logger = logging.getLogger(__name__)

class HierarchicalCalibrator:
    """
    UPGRADE 2: Hierarchical Bayesian Calibration.
    Pools small markets, separates large ones.
    """
    def __init__(self):
        self.calibrators = {} # Key: "Sport_MarketFamily"
        self.global_calibrator = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
        self.min_samples_for_split = 50

    def fit(self, df: pd.DataFrame):
        """
        Expects DF with: ['sport_key', 'market_family', 'p_fair_sharp', 'outcome']
        """
        # 1. Global Fit (The Prior)
        X_global = df['p_fair_sharp'].values
        y_global = df['outcome'].values
        self.global_calibrator.fit(X_global, y_global)
        
        # 2. Hierarchical Splits
        groups = df.groupby(['sport_key', 'market_family'])
        
        for (sport, fam), group in groups:
            if len(group) > self.min_samples_for_split:
                # Train specific calibrator
                iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
                iso.fit(group['p_fair_sharp'].values, group['outcome'].values)
                self.calibrators[f"{sport}_{fam}"] = iso
                logger.info(f"Calibrated bucket: {sport}_{fam} (n={len(group)})")
            else:
                logger.info(f"Skipping bucket {sport}_{fam} (n={len(group)}), using global.")

    def predict(self, row):
        """
        Predicts using the most specific calibrator available.
        """
        key = f"{row['sport_key']}_{row['market_family']}"
        raw_prob = row['p_fair_sharp']
        
        if key in self.calibrators:
            return self.calibrators[key].predict([raw_prob])[0]
        else:
            return self.global_calibrator.predict([raw_prob])[0]

class BettingModel:
    def __init__(self, session: Session):
        self.session = session
        self.calibrator = HierarchicalCalibrator()
        self.is_trained = False
        
    def load_and_train(self):
        # ... (Same SQL loading logic as before) ...
        # Assume we load into DataFrame 'df' with columns: 
        # [sport_key, market_family, p_fair_sharp, outcome]
        
        logger.info("Loading training data from DB (hierarchical calibrator)...")
        data = []
        query = self.session.query(MarketFeatures, Event).join(Event).filter(Event.completed == True)
        for feat, evt in query:
            y = 0
            if feat.selection == 'Home' and evt.winner == 'Home':
                y = 1
            elif feat.selection == 'Away' and evt.winner == 'Away':
                y = 1

            # Attempt to derive sport_key & market_family if stored on feature
            sport_key = getattr(feat, 'sport_key', getattr(evt, 'sport_key', 'UNKNOWN'))
            market_family = getattr(feat, 'market_family', getattr(feat, 'market', 'UNKNOWN'))

            data.append({
                'sport_key': sport_key,
                'market_family': market_family,
                'p_fair_sharp': getattr(feat, 'p_fair_sharp', getattr(feat, 'p_bayesian', 0.5)),
                'outcome': y
            })

        if not data:
            logger.warning("No completed events found to train on. Model remains uncalibrated.")
            return

        df = pd.DataFrame(data)
        self.calibrator.fit(df)
        self.is_trained = True
        logger.info(f"✅ Hierarchical Calibrator trained on {len(df)} rows.")

    def predict_row(self, row_dict):
        """
        Accepts a dictionary row from the Feature Engine.
        """
        return self.calibrator.predict(row_dict)