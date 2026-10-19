from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime


class ResearchRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ResearchRunBase(BaseModel):
    """Base schema for research execution record."""
    profile_id: uuid.UUID | None = Field(default=None, description="Associated student profile ID when available")
    status: ResearchRunStatus = Field(default=ResearchRunStatus.QUEUED, description="Lifecycle execution status")
    started_at: UTCDateTime | None = Field(default=None, description="Run start timestamp")
    ended_at: UTCDateTime | None = Field(default=None, description="Run completion or termination timestamp")
    failure_summary: str | None = Field(default=None, max_length=1000, description="Concise failure summary when failed or partial")

    model_config = ConfigDict(extra="forbid")


class ResearchRunCreate(ResearchRunBase):
    id: uuid.UUID | None = Field(default=None, description="Optional client-specified UUID")


class ResearchRunUpdate(BaseModel):
    status: ResearchRunStatus | None = None
    started_at: UTCDateTime | None = None
    ended_at: UTCDateTime | None = None
    failure_summary: str | None = None

    model_config = ConfigDict(extra="forbid")


class ResearchRunRead(ResearchRunBase):
    id: uuid.UUID
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
