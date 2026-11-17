"""
Database engine and session setup.

For local dev this defaults to SQLite so you can run it with zero setup.
Point DATABASE_URL at Postgres before you go anywhere near real data —
SQLite won't enforce the native ENUM types or numeric precision the same way.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

def normalize_database_url(url: str) -> str:
    """Hosting providers hand out postgres:// or postgresql:// URLs; SQLAlchemy needs to be told which driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = normalize_database_url(os.environ.get("DATABASE_URL", "sqlite:///./escrow_dev.db"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
