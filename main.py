import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from src.features import UnifiedFeatureEngine as MarketStreamEngine
from src.database import init_db, get_session, BetLog, OddsSnapshot, Event
from src.ingest import IngestionEngine
from src.ml_engine import BettingModel
from src.settlement import SettlementEngine
from src.strategy import DecisionEngine
from src.config import settings
from src.injuries import InjuryIngestor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main_decision_loop")


def get_live_market_snapshot(session, event_ids):
    """Helper to fetch the absolute latest odds for consensus calc.
    Returns: {event_id: {book: odds, ...}}"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    snaps = session.query(OddsSnapshot).filter(
        OddsSnapshot.event_id.in_(event_ids),
        OddsSnapshot.timestamp >= cutoff
    ).all()

    live_odds = {}
    for s in snaps:
        if s.event_id not in live_odds:
            live_odds[s.event_id] = {}
        live_odds[s.event_id][s.bookmaker] = s.odds_decimal
    return live_odds


def run_daily_cycle():
    logger.info(f"--- STARTING DECISION ENGINE: {datetime.now()} ---")

    init_db()
    session = get_session()

    try:
        settler = SettlementEngine(session)
        for sport in settings.TARGET_SPORTS:
            settler.update_results(sport, days_back=3)

        model = BettingModel(session)
        model.load_and_train()

        logger.info("Fetching latest live odds...")
        ingestor = IngestionEngine(session)
        ingestor.run_daily_ingest()

        now = datetime.now(timezone.utc)
        lookahead = now + timedelta(hours=30)
        upcoming = session.query(Event).filter(
            Event.commence_time >= now,
            Event.commence_time <= lookahead
        ).all()
        if not upcoming:
            logger.info("No upcoming events; stopping.")
            return

        event_ids = [e.id for e in upcoming]
        snaps = session.query(OddsSnapshot).filter(
            OddsSnapshot.event_id.in_(event_ids)
        ).order_by(OddsSnapshot.timestamp.asc()).all()

        rows = []
        for s in snaps:
            rows.append({
                'event_id': s.event_id,
                'sport_key': getattr(s, 'sport_key', 'unknown'),
                'market_key': s.market_key,
                'selection': s.selection,
                'bookmaker': s.bookmaker,
                'odds_decimal': s.odds_decimal,
                'timestamp': s.timestamp,
                'handicap': s.handicap
            })

        if not rows:
            logger.warning("No snapshot rows to process.")
            return

        raw_df = pd.DataFrame(rows)

        unique_event_ids = raw_df['event_id'].unique().tolist()
        live_odds_map = get_live_market_snapshot(session, unique_event_ids)

        try:
            injestor = InjuryIngestor(session)
            injuries_map = injestor.fetch_all_injuries(unique_event_ids)
        except Exception:
            injuries_map = {}

        context_data = {'live_odds': live_odds_map, 'injuries': injuries_map}

        engine = MarketStreamEngine()
        candidates_df = engine.process_snapshots(raw_df, context_data=context_data)

        if candidates_df.empty:
            logger.warning("No candidates found after feature computation.")
            return

        try:
            preds = model.predict(candidates_df['p_fair_consensus'].values)
            candidates_df['model_prob'] = preds
        except Exception:
            candidates_df['model_prob'] = candidates_df.apply(
                lambda x: model.predict_row({'p_fair_sharp': x['p_fair_consensus']}), axis=1
            )

        scored_candidates = []
        for _, row in candidates_df.iterrows():
            price_decimal = 1.0 / row['p_implied'] if row.get('p_implied') and row['p_implied'] > 0 else None
            scored_candidates.append({
                'event_id': row['event_id'],
                'selection': row['selection'],
                'model_prob': row['model_prob'],
                'dk_price': price_decimal,
                'velocity': row.get('velocity'),
                'is_jumpy': row.get('is_jumpy', False)
            })
        scored_df = pd.DataFrame(scored_candidates)

        strategy = DecisionEngine(bankroll=settings.BANKROLL)
        best_bet = strategy.select_best_bet(scored_df)

        if best_bet is not None:
            print("\n" + "="*40)
            print(f"🏆 BET OF THE DAY: {best_bet['selection']}")
            print(f"Event ID: {best_bet['event_id']}")
            print(f"Odds:     {best_bet['odds']:.2f}")
            print(f"Edge:     {best_bet['ev']:.2%}")
            print(f"Stake:    ${best_bet['stake']:.2f}")
            print("="*40 + "\n")

            log_entry = BetLog(
                event_id=best_bet['event_id'],
                selection=best_bet['selection'],
                price_taken=best_bet['odds'],
                stake=best_bet['stake'],
                model_prob=best_bet['model_prob'],
                ev_per_dollar=best_bet['ev'],
                result=None
            )
            session.add(log_entry)
            session.commit()
            logger.info("Bet logged successfully.")
        else:
            print("\n🚫 No bets found meeting Edge/Kelly criteria today.")

    except Exception as e:
        logger.error(f"Critical Error in Main Loop: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    run_daily_cycle()