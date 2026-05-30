# Architecture note: all transaction control inside the dependency, never in middleware
# Avoids: Pitfall 1 - FastAPI 0.106+ tears down Depends before middleware runs

from database import SessionLocal
from sqlalchemy.orm import Session
from typing import Generator

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
