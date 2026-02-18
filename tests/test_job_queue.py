"""Tests for JobQueue class."""

import pytest

from jdobb_async_queue import JobPriority, JobQueue, JobStatus


@pytest.fixture
async def queue():
    """Create a fresh job queue for each test."""
    q = JobQueue(backend="memory")
    yield q
    await q.close()


class TestJobQueueEnqueue:
    async def test_enqueue_returns_job_id(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    async def test_enqueue_with_data(self, queue: JobQueue):
        job_id = await queue.enqueue("test", data={"key": "value"})
        job = await queue.get(job_id)
        assert job.data == {"key": "value"}

    async def test_enqueue_with_priority(self, queue: JobQueue):
        job_id = await queue.enqueue("test", priority=JobPriority.HIGH)
        job = await queue.get(job_id)
        assert job.priority == JobPriority.HIGH

    async def test_enqueue_with_ttl(self, queue: JobQueue):
        job_id = await queue.enqueue("test", ttl=3600)
        job = await queue.get(job_id)
        assert job.ttl == 3600

    async def test_enqueue_with_metadata(self, queue: JobQueue):
        job_id = await queue.enqueue("test", metadata={"user": "alice"})
        job = await queue.get(job_id)
        assert job.metadata == {"user": "alice"}

    async def test_enqueue_with_custom_id(self, queue: JobQueue):
        job_id = await queue.enqueue("test", job_id="custom-123")
        assert job_id == "custom-123"

    async def test_default_ttl(self):
        queue = JobQueue(backend="memory", default_ttl=7200)
        try:
            job_id = await queue.enqueue("test")
            job = await queue.get(job_id)
            assert job.ttl == 7200
        finally:
            await queue.close()

    async def test_explicit_ttl_overrides_default(self):
        queue = JobQueue(backend="memory", default_ttl=7200)
        try:
            job_id = await queue.enqueue("test", ttl=1800)
            job = await queue.get(job_id)
            assert job.ttl == 1800
        finally:
            await queue.close()


class TestJobQueueGet:
    async def test_get_existing_job(self, queue: JobQueue):
        job_id = await queue.enqueue("test", data={"key": "value"})
        job = await queue.get(job_id)
        assert job is not None
        assert job.id == job_id
        assert job.job_type == "test"

    async def test_get_nonexistent_job(self, queue: JobQueue):
        job = await queue.get("nonexistent")
        assert job is None


class TestJobQueueClaim:
    async def test_claim_returns_job(self, queue: JobQueue):
        await queue.enqueue("test")
        job = await queue.claim()
        assert job is not None
        assert job.status == JobStatus.PROCESSING

    async def test_claim_empty_queue(self, queue: JobQueue):
        job = await queue.claim()
        assert job is None

    async def test_claim_with_type_filter(self, queue: JobQueue):
        await queue.enqueue("type_a")
        await queue.enqueue("type_b")

        job = await queue.claim(["type_b"])
        assert job.job_type == "type_b"

    async def test_claim_respects_priority(self, queue: JobQueue):
        await queue.enqueue("test", priority=JobPriority.LOW, job_id="low")
        await queue.enqueue("test", priority=JobPriority.HIGH, job_id="high")

        job = await queue.claim()
        assert job.id == "high"


class TestJobQueueUpdate:
    async def test_update_progress(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        await queue.claim()

        result = await queue.update(job_id, progress=0.5)
        assert result is True

        job = await queue.get(job_id)
        assert job.progress == 0.5

    async def test_update_message(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        await queue.claim()

        result = await queue.update(job_id, message="Processing...")
        assert result is True

        job = await queue.get(job_id)
        assert job.message == "Processing..."

    async def test_update_nonexistent_job(self, queue: JobQueue):
        result = await queue.update("nonexistent", progress=0.5)
        assert result is False


class TestJobQueueComplete:
    async def test_complete_job(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        await queue.claim()

        result = await queue.complete(job_id, results={"output": "done"})
        assert result is True

        job = await queue.get(job_id)
        assert job.status == JobStatus.COMPLETE
        assert job.progress == 1.0
        assert job.results == {"output": "done"}
        assert job.completed_at is not None

    async def test_complete_nonexistent_job(self, queue: JobQueue):
        result = await queue.complete("nonexistent")
        assert result is False


class TestJobQueueFail:
    async def test_fail_job(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        await queue.claim()

        result = await queue.fail(job_id, error="Something went wrong")
        assert result is True

        job = await queue.get(job_id)
        assert job.status == JobStatus.FAILED
        assert job.error == "Something went wrong"
        assert job.completed_at is not None

    async def test_fail_nonexistent_job(self, queue: JobQueue):
        result = await queue.fail("nonexistent", error="error")
        assert result is False


class TestJobQueueCancel:
    async def test_cancel_pending_job(self, queue: JobQueue):
        job_id = await queue.enqueue("test")

        result = await queue.cancel(job_id, reason="User requested")
        assert result is True

        job = await queue.get(job_id)
        assert job.status == JobStatus.CANCELLED
        assert job.error == "User requested"

    async def test_cancel_processing_job(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        await queue.claim()

        result = await queue.cancel(job_id, reason="Timeout")
        assert result is True

        job = await queue.get(job_id)
        assert job.status == JobStatus.CANCELLED

    async def test_cancel_already_complete(self, queue: JobQueue):
        job_id = await queue.enqueue("test")
        await queue.claim()
        await queue.complete(job_id)

        result = await queue.cancel(job_id)
        assert result is False

    async def test_cancel_nonexistent_job(self, queue: JobQueue):
        result = await queue.cancel("nonexistent")
        assert result is False


class TestJobQueueBackend:
    async def test_backend_property(self, queue: JobQueue):
        from jdobb_async_queue.backends.memory import MemoryBackend

        assert isinstance(queue.backend, MemoryBackend)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            JobQueue(backend="unknown")


class TestJobQueueClose:
    async def test_close(self, queue: JobQueue):
        await queue.enqueue("test")
        await queue.close()
        # After close, operations may not work (implementation specific)
