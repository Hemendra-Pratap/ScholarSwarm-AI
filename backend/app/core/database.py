from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.core.config import settings


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints on SQLite connections."""
    # Only execute pragma on SQLite connections
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
    finally:
        cursor.close()


def get_engine_args(url: str) -> dict:
    args = {}
    if url.startswith("sqlite"):
        args["connect_args"] = {"check_same_thread": False}
    return args


engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    **get_engine_args(settings.DATABASE_URL),
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions with safe lifecycle management."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None) -> None:
    """Create all tables in the database if they do not exist."""
    import app.models  # noqa: F401 - ensure all declarative models are registered on Base.metadata
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)
