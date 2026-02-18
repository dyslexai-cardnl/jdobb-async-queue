"""Tests for schema models."""

from datetime import UTC, datetime

import pytest

from jdobb_async_queue.schemas import Job, JobPriority, JobStatus, JobUpdate


class TestJobStatus:
    def test_values(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.PROCESSING.value == "processing"
        assert JobStatus.COMPLETE.value == "complete"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"

    def test_is_string_enum(self):
        assert isinstance(JobStatus.PENDING, str)
        assert JobStatus.PENDING == "pending"


class TestJobPriority:
    def test_values(self):
        assert JobPriority.LOW.value == "low"
        assert JobPriority.NORMAL.value == "normal"
        assert JobPriority.HIGH.value == "high"

    def test_weights(self):
        assert JobPriority.LOW.weight == 1
        assert JobPriority.NORMAL.weight == 5
        assert JobPriority.HIGH.weight == 10

    def test_weight_ordering(self):
        assert JobPriority.LOW.weight < JobPriority.NORMAL.weight
        assert JobPriority.NORMAL.weight < JobPriority.HIGH.weight


class TestJob:
    def test_minimal_creation(self):
        job = Job(id="test-1", job_type="process")
        assert job.id == "test-1"
        assert job.job_type == "process"
        assert job.data == {}
        assert job.status == JobStatus.PENDING
        assert job.priority == JobPriority.NORMAL
        assert job.progress == 0.0
        assert job.message is None
        assert job.results is None
        assert job.error is None
        assert job.metadata == {}
        assert isinstance(job.created_at, datetime)
        assert isinstance(job.updated_at, datetime)
        assert job.completed_at is None
        assert job.ttl is None

    def test_full_creation(self):
        now = datetime.now(UTC)
        job = Job(
            id="job-123",
            job_type="analyze",
            data={"input": "test"},
            status=JobStatus.PROCESSING,
            priority=JobPriority.HIGH,
            progress=0.5,
            message="Halfway done",
            results=None,
            error=None,
            metadata={"user": "alice"},
            created_at=now,
            updated_at=now,
            completed_at=None,
            ttl=3600,
        )
        assert job.id == "job-123"
        assert job.data == {"input": "test"}
        assert job.priority == JobPriority.HIGH
        assert job.progress == 0.5
        assert job.metadata == {"user": "alice"}
        assert job.ttl == 3600

    def test_progress_bounds(self):
        with pytest.raises(ValueError):
            Job(id="test", job_type="x", progress=-0.1)
        with pytest.raises(ValueError):
            Job(id="test", job_type="x", progress=1.1)

    def test_progress_valid_bounds(self):
        job_min = Job(id="test", job_type="x", progress=0.0)
        job_max = Job(id="test", job_type="x", progress=1.0)
        assert job_min.progress == 0.0
        assert job_max.progress == 1.0

    def test_mutable_by_default(self):
        job = Job(id="test", job_type="x")
        job.status = JobStatus.PROCESSING
        job.progress = 0.5
        assert job.status == JobStatus.PROCESSING
        assert job.progress == 0.5

    def test_serialization(self):
        job = Job(id="test", job_type="x", data={"key": "value"})
        data = job.model_dump()
        assert data["id"] == "test"
        assert data["job_type"] == "x"
        assert data["data"] == {"key": "value"}
        assert data["status"] == "pending"

    def test_json_serialization(self):
        job = Job(id="test", job_type="x")
        json_str = job.model_dump_json()
        assert "test" in json_str
        assert "pending" in json_str


class TestJobUpdate:
    def test_minimal_creation(self):
        update = JobUpdate(job_id="job-1", status=JobStatus.PROCESSING)
        assert update.job_id == "job-1"
        assert update.status == JobStatus.PROCESSING
        assert update.progress == 0.0
        assert update.message is None
        assert update.results is None
        assert update.error is None
        assert isinstance(update.timestamp, datetime)

    def test_full_creation(self):
        update = JobUpdate(
            job_id="job-1",
            status=JobStatus.COMPLETE,
            progress=1.0,
            message="Done",
            results={"output": "result"},
            error=None,
        )
        assert update.progress == 1.0
        assert update.message == "Done"
        assert update.results == {"output": "result"}

    def test_error_update(self):
        update = JobUpdate(
            job_id="job-1",
            status=JobStatus.FAILED,
            error="Something went wrong",
        )
        assert update.status == JobStatus.FAILED
        assert update.error == "Something went wrong"
