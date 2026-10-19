from datetime import datetime, timezone
from typing import Any
import uuid
from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, CHAR
from app.core.database import Base
from app.schemas.opportunity import FundingType, VerificationStatus
from app.schemas.evidence_source import SourceVerificationStatus
from app.schemas.eligibility_assessment import EligibilityStatus, CriterionType
from app.schemas.research_run import ResearchRunStatus


class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.
    Stores as string(36) in SQLite, native UUID in PostgreSQL.
    """
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class UTCDateTimeType(TypeDecorator):
    """Timezone-aware UTC DateTime type.
    Ensures datetimes are stored and retrieved with UTC timezone.
    In SQLite, datetimes are stored as strings without timezone; this decorator enforces UTC.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudentProfileModel(Base):
    """SQLAlchemy model for student profiles."""
    __tablename__ = "student_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    degree_program: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    academic_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Structured values stored as JSON
    academic_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_destinations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    academic_interests: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    projects_experiences: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    budget_constraint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    public_profile_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    eligibility_assessments: Mapped[list["EligibilityAssessmentModel"]] = relationship(
        "EligibilityAssessmentModel",
        back_populates="student_profile",
        cascade="all, delete-orphan",
    )
    research_runs: Mapped[list["ResearchRunModel"]] = relationship(
        "ResearchRunModel",
        back_populates="student_profile",
    )


class OpportunityModel(Base):
    """SQLAlchemy model for scholarships and university opportunities."""
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    institution: Mapped[str] = mapped_column(String(500), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    official_url: Mapped[str | None] = mapped_column(String(2083), nullable=True)

    # Funding structured information
    funding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTimeType, nullable=True, index=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False, length=50),
        default=VerificationStatus.UNVERIFIED,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    evidence_sources: Mapped[list["EvidenceSourceModel"]] = relationship(
        "EvidenceSourceModel",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )
    eligibility_assessments: Mapped[list["EligibilityAssessmentModel"]] = relationship(
        "EligibilityAssessmentModel",
        back_populates="opportunity",
        cascade="all, delete-orphan",
    )


class EvidenceSourceModel(Base):
    """SQLAlchemy model for source evidence associated with an opportunity."""
    __tablename__ = "evidence_sources"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(String(2083), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    claim_supported: Mapped[str] = mapped_column(String(500), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTimeType, nullable=False)
    published_date: Mapped[datetime | None] = mapped_column(UTCDateTimeType, nullable=True)
    verification_status: Mapped[SourceVerificationStatus] = mapped_column(
        SAEnum(SourceVerificationStatus, native_enum=False, length=50),
        default=SourceVerificationStatus.UNVERIFIED,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, nullable=False)

    # Relationship
    opportunity: Mapped["OpportunityModel"] = relationship(
        "OpportunityModel",
        back_populates="evidence_sources",
    )


class EligibilityAssessmentModel(Base):
    """SQLAlchemy model for student-opportunity eligibility assessment."""
    __tablename__ = "eligibility_assessments"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Structured criteria list
    criteria: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    opportunity: Mapped["OpportunityModel"] = relationship(
        "OpportunityModel",
        back_populates="eligibility_assessments",
    )
    student_profile: Mapped["StudentProfileModel"] = relationship(
        "StudentProfileModel",
        back_populates="eligibility_assessments",
    )

    __table_args__ = (
        Index("ix_assessment_opp_student", "opportunity_id", "student_profile_id", unique=True),
    )


class ResearchRunModel(Base):
    """SQLAlchemy model for research execution runs."""
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("student_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ResearchRunStatus] = mapped_column(
        SAEnum(ResearchRunStatus, native_enum=False, length=50),
        default=ResearchRunStatus.QUEUED,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTimeType, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTimeType, nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTimeType, default=utcnow, nullable=False)

    # Relationship
    student_profile: Mapped["StudentProfileModel | None"] = relationship(
        "StudentProfileModel",
        back_populates="research_runs",
    )
