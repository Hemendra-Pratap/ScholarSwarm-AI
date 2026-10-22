from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    StudentProfileModel,
    OpportunityModel,
    EvidenceSourceModel,
    EligibilityAssessmentModel,
    ResearchRunModel,
)
from app.schemas.opportunity import FundingType, VerificationStatus
from app.schemas.evidence_source import SourceVerificationStatus
from app.schemas.eligibility_assessment import EligibilityStatus, CriterionType
from app.schemas.research_run import ResearchRunStatus


# ==============================================================================
# Database Initialization and CRUD Tests
# ==============================================================================

def test_database_initialization(db_session: Session):
    """Verify that database tables are successfully initialized."""
    # Queries should succeed without table errors
    profiles = db_session.execute(select(StudentProfileModel)).scalars().all()
    assert profiles == []
    opps = db_session.execute(select(OpportunityModel)).scalars().all()
    assert opps == []


def test_app_lifespan_initializes_database_tables(tmp_path, monkeypatch):
    """Verify that FastAPI application lifespan initializes all required database tables."""
    from sqlalchemy import create_engine, inspect
    from fastapi.testclient import TestClient
    from app.main import app
    import app.core.database as db_mod

    db_file = tmp_path / "lifespan_test.db"
    test_engine = create_engine(f"sqlite:///{db_file}")

    monkeypatch.setattr(db_mod, "engine", test_engine)

    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    inspector = inspect(test_engine)
    table_names = set(inspector.get_table_names())
    expected_tables = {
        "student_profiles",
        "opportunities",
        "evidence_sources",
        "research_runs",
        "eligibility_assessments",
    }
    assert expected_tables.issubset(table_names)



def test_create_and_retrieve_student_profile(db_session: Session):
    """Verify round-trip persistence of a student profile with structured JSON data."""
    profile_id = uuid.uuid4()
    profile = StudentProfileModel(
        id=profile_id,
        name="Elena Rostova",
        degree_program="B.Eng. Mechanical Engineering",
        field_of_study="Robotics & Autonomous Systems",
        institution="Technical University of Sofia",
        country="Bulgaria",
        academic_stage="graduate",
        academic_score={"score": 5.85, "scale": 6.0},
        target_destinations=["Germany", "Netherlands"],
        academic_interests=["Computer Vision", "SLAM", "Robotic Manipulation"],
        projects_experiences=[
            {
                "title": "Autonomous Drone Navigation",
                "role": "Team Lead",
                "summary": "Implemented visual-inertial odometry using ROS2",
                "technologies": ["ROS2", "C++", "OpenCV"],
            }
        ],
        budget_constraint={
            "max_annual_budget": 8000.0,
            "currency": "EUR",
            "requires_full_funding": False,
            "notes": "Can cover living costs, needs tuition waiver",
        },
        public_profile_urls=["https://github.com/erostova", "https://linkedin.com/in/erostova"],
    )
    db_session.add(profile)
    db_session.commit()

    retrieved = db_session.get(StudentProfileModel, profile_id)
    assert retrieved is not None
    assert retrieved.name == "Elena Rostova"
    assert retrieved.country == "Bulgaria"
    assert retrieved.academic_score["score"] == 5.85
    assert retrieved.academic_score["scale"] == 6.0
    assert len(retrieved.target_destinations) == 2
    assert retrieved.projects_experiences[0]["title"] == "Autonomous Drone Navigation"
    assert retrieved.budget_constraint["max_annual_budget"] == 8000.0
    assert len(retrieved.public_profile_urls) == 2
    assert retrieved.created_at.tzinfo is not None  # Verifies UTC timezone awareness
    assert retrieved.updated_at.tzinfo is not None


def test_create_and_retrieve_opportunity(db_session: Session):
    """Verify round-trip persistence of an opportunity with enum and JSON fields."""
    opp_id = uuid.uuid4()
    opp = OpportunityModel(
        id=opp_id,
        name="Erasmus Mundus Joint Master in Cyber Security",
        institution="Consortium of European Universities",
        destination_country="Estonia",
        official_url="https://cybersecurity.ut.ee",
        funding={
            "funding_type": FundingType.FULL.value,
            "amount": 1400.0,
            "currency": "EUR",
            "period": "per_month",
        },
        deadline=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    db_session.add(opp)
    db_session.commit()

    retrieved = db_session.get(OpportunityModel, opp_id)
    assert retrieved is not None
    assert retrieved.name == "Erasmus Mundus Joint Master in Cyber Security"
    assert retrieved.funding["funding_type"] == FundingType.FULL.value
    assert retrieved.verification_status == VerificationStatus.VERIFIED
    assert retrieved.deadline.tzinfo is not None
    assert retrieved.deadline.year == 2026


def test_evidence_source_foreign_key_and_cascade(db_session: Session):
    """Verify foreign key linking and cascade deletion of evidence sources."""
    opp = OpportunityModel(
        id=uuid.uuid4(),
        name="TUM Master Scholarship",
        institution="TUM",
        destination_country="Germany",
    )
    db_session.add(opp)
    db_session.commit()

    source = EvidenceSourceModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        source_url="https://tum.de/scholarship-info",
        title="TUM Scholarship Portal",
        claim_supported="Full tuition waiver for eligible candidates",
        excerpt="The scholarship waives all tuition fees for semester 1-4.",
        retrieved_at=datetime.now(timezone.utc),
        verification_status=SourceVerificationStatus.VERIFIED,
    )
    db_session.add(source)
    db_session.commit()

    # Retrieve source
    retrieved_source = db_session.get(EvidenceSourceModel, source.id)
    assert retrieved_source is not None
    assert retrieved_source.opportunity.name == "TUM Master Scholarship"

    # Test cascade delete
    db_session.delete(opp)
    db_session.commit()

    # Source should have been cascade deleted
    assert db_session.get(EvidenceSourceModel, source.id) is None


def test_evidence_source_foreign_key_violation(db_session: Session):
    """Verify that referencing a non-existent opportunity raises an IntegrityError."""
    fake_opp_id = uuid.uuid4()
    source = EvidenceSourceModel(
        id=uuid.uuid4(),
        opportunity_id=fake_opp_id,
        source_url="https://example.com",
        claim_supported="Some claim",
        excerpt="Some excerpt",
        retrieved_at=datetime.now(timezone.utc),
    )
    db_session.add(source)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_eligibility_assessment_uniqueness_constraint(db_session: Session):
    """Verify unique constraint on (opportunity_id, student_profile_id)."""
    profile = StudentProfileModel(id=uuid.uuid4(), name="Test Student")
    opp = OpportunityModel(id=uuid.uuid4(), name="Test Opp", institution="Inst", destination_country="DE")
    db_session.add_all([profile, opp])
    db_session.commit()

    assessment1 = EligibilityAssessmentModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        student_profile_id=profile.id,
        criteria=[
            {
                "criterion_id": str(uuid.uuid4()),
                "requirement": "Min CGPA 8.0",
                "status": EligibilityStatus.MET.value,
                "criterion_type": CriterionType.ADMISSION.value,
            }
        ],
    )
    db_session.add(assessment1)
    db_session.commit()

    # Attempting to add a duplicate assessment for the same (opp, profile) pair must fail
    assessment2 = EligibilityAssessmentModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        student_profile_id=profile.id,
        criteria=[],
    )
    db_session.add(assessment2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_research_run_persistence_and_relationships(db_session: Session):
    """Verify research run creation, status updates, and relationship with student profile."""
    profile = StudentProfileModel(id=uuid.uuid4(), name="Research Profile")
    db_session.add(profile)
    db_session.commit()

    run = ResearchRunModel(
        id=uuid.uuid4(),
        profile_id=profile.id,
        status=ResearchRunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()

    retrieved_run = db_session.get(ResearchRunModel, run.id)
    assert retrieved_run is not None
    assert retrieved_run.status == ResearchRunStatus.RUNNING
    assert retrieved_run.student_profile.name == "Research Profile"

    # Update lifecycle to completed
    retrieved_run.status = ResearchRunStatus.COMPLETED
    retrieved_run.ended_at = datetime.now(timezone.utc)
    db_session.commit()

    updated = db_session.get(ResearchRunModel, run.id)
    assert updated.status == ResearchRunStatus.COMPLETED
    assert updated.ended_at is not None


def test_research_run_without_profile(db_session: Session):
    """Verify research run can be created independently without an associated profile."""
    run = ResearchRunModel(
        id=uuid.uuid4(),
        profile_id=None,
        status=ResearchRunStatus.QUEUED,
    )
    db_session.add(run)
    db_session.commit()

    retrieved = db_session.get(ResearchRunModel, run.id)
    assert retrieved is not None
    assert retrieved.profile_id is None
    assert retrieved.status == ResearchRunStatus.QUEUED
