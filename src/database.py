from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from datetime import datetime
from .config import settings

Base = declarative_base()

# --- HELPER FUNCTIONS (#5) ---
_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.DATABASE_URL)
    return _engine

def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()

def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)

# --- MODELS ---

class Event(Base):
    __tablename__ = 'events'
    id = Column(String, primary_key=True)
    sport_key = Column(String)
    commence_time = Column(DateTime, index=True)
    home_team = Column(String)
    away_team = Column(String)
    
    # Settlement Fields (#4.2)
    completed = Column(Boolean, default=False)
    winner = Column(String, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    
    context_json = Column(String, nullable=True)
    
    # Relationships (#4.3)
    snapshots = relationship("OddsSnapshot", back_populates="event")
    features = relationship("MarketFeatures", back_populates="event")

class OddsSnapshot(Base):
    __tablename__ = 'odds_snapshots'
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey('events.id'), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    bookmaker = Column(String)
    market_key = Column(String)
    
    # Unified Schema Fields (#4.1)
    selection = Column(String)
    handicap = Column(Float, nullable=True)
    odds_decimal = Column(Float)
    
    event = relationship("Event", back_populates="snapshots")

class MarketFeatures(Base):
    __tablename__ = 'market_features'
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey('events.id'), index=True)
    timestamp = Column(DateTime, index=True)
    
    market_family = Column(String)
    selection = Column(String)
    book = Column(String)
    
    p_implied = Column(Float)
    p_fair_consensus = Column(Float)
    velocity = Column(Float)
    context_uncertainty = Column(Float)
    
    event = relationship("Event", back_populates="features")

class BetLog(Base):
    __tablename__ = 'bet_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_id = Column(String, ForeignKey('events.id'))
    selection = Column(String)
    price_taken = Column(Float)
    stake = Column(Float)
    model_prob = Column(Float)
    ev_per_dollar = Column(Float)
    result = Column(String, nullable=True)
    pnl = Column(Float, nullable=True)
def init_db():
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)