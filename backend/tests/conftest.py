from collections.abc import Generator
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, set_sqlite_pragma
from app.models import (
    StudentProfileModel,
    OpportunityModel,
    EvidenceSourceModel,
    EligibilityAssessmentModel,
    ResearchRunModel,
)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create an isolated, in-memory SQLite database session with PRAGMA foreign_keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Ensure foreign keys are enabled
    with engine.connect() as conn:
        set_sqlite_pragma(conn.connection.dbapi_connection, None)

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
