import click
import logging
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy.orm import Session

# Import our internal modules
from src.database import init_db, get_session, OddsSnapshot, MarketFeatures, Event
from src.ingest import IngestionEngine

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@click.group()
def cli():
    """The Betting Engine CLI Control Tool"""
    pass

@cli.command()
def setup():
    """Creates the SQLite database and tables."""
    init_db()
    click.echo("✅ Database setup complete.")

@cli.command()
def scrape():
    """
    Pulls live odds from The Odds API.
    """
    session = get_session()
    try:
        engine = IngestionEngine(session)
        logger.info("🚀 Starting Scraper...")
        engine.run_daily_ingest()
        click.echo("✅ Scraping complete. Data saved to 'odds_snapshots'.")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise
    finally:
        session.close()

@cli.command()
@click.option('--hours', default=24, help='Lookback window in hours')
def compute_features(hours):
    """
    Runs the Bayesian Feature Loop on recent raw snapshots.
    Populates the 'market_features' table.
    """
    session = get_session()
    
    # 1. Load Raw Snapshots from DB
    logger.info("loading raw snapshots...")
    query = session.query(OddsSnapshot, Event).join(Event).all()
    
    if not query:
        click.echo("No snapshots found. Run 'scrape' first.")
        return

    # Convert to DataFrame for the Engine
    data = []
    for snap, evt in query:
        # Flattening the data for the engine
        # We create two rows per snapshot (Home and Away)
        data.append({
            'event_id': snap.event_id,
            'selection': 'Home', # Simplified; in prod use team name
            'bookmaker': snap.bookmaker,
            'price': snap.odds_decimal, # Unified Schema uses odds_decimal
            'timestamp': snap.timestamp,
            'market_key': snap.market_key, # Critical for feature engine
            'handicap': snap.handicap,
            'event_id': snap.event_id,
            'sport_key': evt.sport_key # Pass sport key for classification
        })
        # Note: Unified schema stores one row per outcome, so we don't need to manually 
        # split Home/Away here if we iterate directly.
        # However, the loop above iterates Snapshot objects which ARE one per outcome.
        # So we just need to map the attributes correctly.
    
    # RE-MAPPING for Unified Schema (Corrected Logic)
    # The previous logic assumed the old 'home_price/away_price' schema. 
    # With unified schema, we just dump the rows directly.
    
    unified_data = []
    for snap, evt in query:
        unified_data.append({
            'event_id': snap.event_id,
            'sport_key': evt.sport_key,
            'selection': snap.selection,
            'bookmaker': snap.bookmaker,
            'market_key': snap.market_key,
            'handicap': snap.handicap,
            'odds_decimal': snap.odds_decimal,
            'timestamp': snap.timestamp
        })
        
    df = pd.DataFrame(unified_data)
    if df.empty:
        click.echo("DataFrame empty. No data to process.")
        return

    df = df.sort_values('timestamp')
    
    # 2. Run the Feature Engine
    logger.info("⚙️ Running Kinematic Kalman Filter...")
    # Using the function we wrote in features.py
    from src.features import generate_features_for_backtest
    
    # The feature engine expects specific column names, ensure they match schemas.py/UnifiedBet
    feature_df = generate_features_for_backtest(df)
    
    if feature_df.empty:
        click.echo("No features generated (need more data history?).")
        return

    # 3. Save to DB
    logger.info(f"Saving {len(feature_df)} feature rows to DB...")
    
    new_features = 0
    for _, row in feature_df.iterrows():
        # Check uniqueness to avoid duplicates (naive check)
        exists = session.query(MarketFeatures).filter_by(
            event_id=row['event_id'],
            timestamp=row['timestamp'], # engine output uses 'timestamp'
            selection=row['selection'],
            book=row['book']
        ).first()
        
        if not exists:
            feat = MarketFeatures(
                event_id=row['event_id'],
                timestamp=row['timestamp'],
                selection=row['selection'],
                market_family=row['market_family'],
                book=row['book'],
                p_implied=row['p_implied'],
                p_fair_consensus=row['p_fair_consensus'],
                velocity=row['velocity'],
                context_uncertainty=row['context_uncertainty']
            )
            session.add(feat)
            new_features += 1
            
    session.commit()
    session.close()
    click.echo(f"✅ Feature computation complete. {new_features} new rows inserted.")

@cli.command()
def view_data():
    """Quick peek at the latest data in the DB."""
    session = get_session()
    
    click.echo("\n--- Latest 5 Snapshots ---")
    snaps = session.query(OddsSnapshot).order_by(OddsSnapshot.timestamp.desc()).limit(5).all()
    for s in snaps:
        print(f"[{s.timestamp}] {s.bookmaker} | {s.market_key} | {s.selection} @ {s.odds_decimal}")
        
    click.echo("\n--- Latest 5 Features ---")
    feats = session.query(MarketFeatures).order_by(MarketFeatures.timestamp.desc()).limit(5).all()
    for f in feats:
        print(f"[{f.timestamp}] {f.selection} | P_Fair: {f.p_fair_consensus:.3f} | Velo: {f.velocity:.3f}")
    
    session.close()

@cli.command()
def backfill_results():
    """Fetches past scores for settlement."""
    session = get_session()
    # Logic placeholder - in production this would fetch scores from API
    click.echo("Backfill results command is a placeholder in this version.")
    session.close()

if __name__ == '__main__':
    cli()
