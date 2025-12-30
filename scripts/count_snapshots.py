from src.database import get_session, OddsSnapshot
s = get_session()
print('Snapshot count:', s.query(OddsSnapshot).count())
s.close()
