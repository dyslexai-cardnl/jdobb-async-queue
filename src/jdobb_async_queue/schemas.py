"""Pydantic models for async job queue."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


class JobStatus(str, Enum):
    """Status of a job in the queue."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(str, Enum):
    """Priority level for jobs. Higher priority jobs are claimed first."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    @property
    def weight(self) -> int:
        """Return numeric weight for priority comparison."""
        weights = {"low": 1, "normal": 5, "high": 10}
        return weights[self.value]


class Job(BaseModel):
    """A job in the queue."""

    id: str = Field(..., description="Unique job identifier")
    job_type: str = Field(..., description="Type of job for handler routing")
    data: dict[str, Any] = Field(default_factory=dict, description="Job payload data")
    status: JobStatus = Field(
        default=JobStatus.PENDING, description="Current job status"
    )
    priority: JobPriority = Field(
        default=JobPriority.NORMAL, description="Job priority"
    )
    progress: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Progress 0.0 to 1.0"
    )
    message: str | None = Field(default=None, description="Status message")
    results: dict[str, Any] | None = Field(
        default=None, description="Job results on completion"
    )
    error: str | None = Field(default=None, description="Error message on failure")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary metadata"
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = Field(default=None)
    ttl: int | None = Field(default=None, description="Time-to-live in seconds")

    model_config = {"frozen": False}


class JobUpdate(BaseModel):
    """Update event for a job, used in pub/sub."""

    job_id: str
    status: JobStatus
    progress: float = 0.0
    message: str | None = None
    results: dict[str, Any] | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=_utcnow)
