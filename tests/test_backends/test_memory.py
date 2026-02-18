"""Tests for in-memory backend."""

import asyncio

import pytest

from jdobb_async_queue.backends.memory import MemoryBackend
from jdobb_async_queue.schemas import Job, JobPriority, JobStatus, JobUpdate


@pytest.fixture
async def backend():
    """Create a fresh memory backend for each test."""
    b = MemoryBackend()
    yield b
    await b.close()


class TestMemoryBackendStorage:
    async def test_store_and_get_job(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test", data={"key": "value"})
        await backend.store_job(job)

        retrieved = await backend.get_job("job-1")
        assert retrieved is not None
        assert retrieved.id == "job-1"
        assert retrieved.job_type == "test"
        assert retrieved.data == {"key": "value"}

    async def test_get_nonexistent_job(self, backend: MemoryBackend):
        result = await backend.get_job("nonexistent")
        assert result is None

    async def test_store_returns_copy(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        # Modify original
        job.status = JobStatus.PROCESSING

        # Retrieved should still be PENDING
        retrieved = await backend.get_job("job-1")
        assert retrieved.status == JobStatus.PENDING

    async def test_get_returns_copy(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        retrieved = await backend.get_job("job-1")
        retrieved.status = JobStatus.PROCESSING

        # Original should still be PENDING
        retrieved_again = await backend.get_job("job-1")
        assert retrieved_again.status == JobStatus.PENDING


class TestMemoryBackendUpdate:
    async def test_update_job(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        job.status = JobStatus.PROCESSING
        job.progress = 0.5
        await backend.update_job(job)

        retrieved = await backend.get_job("job-1")
        assert retrieved.status == JobStatus.PROCESSING
        assert retrieved.progress == 0.5

    async def test_update_nonexistent_job_no_error(self, backend: MemoryBackend):
        job = Job(id="nonexistent", job_type="test")
        await backend.update_job(job)  # Should not raise


class TestMemoryBackendDelete:
    async def test_delete_job(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        result = await backend.delete_job("job-1")
        assert result is True

        retrieved = await backend.get_job("job-1")
        assert retrieved is None

    async def test_delete_nonexistent_job(self, backend: MemoryBackend):
        result = await backend.delete_job("nonexistent")
        assert result is False


class TestMemoryBackendClaim:
    async def test_claim_pending_job(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        claimed = await backend.claim_pending_job()
        assert claimed is not None
        assert claimed.id == "job-1"
        assert claimed.status == JobStatus.PROCESSING

        # Verify original is also updated
        stored = await backend.get_job("job-1")
        assert stored.status == JobStatus.PROCESSING

    async def test_claim_no_pending_jobs(self, backend: MemoryBackend):
        result = await backend.claim_pending_job()
        assert result is None

    async def test_claim_with_type_filter(self, backend: MemoryBackend):
        job_a = Job(id="job-a", job_type="type_a")
        job_b = Job(id="job-b", job_type="type_b")
        await backend.store_job(job_a)
        await backend.store_job(job_b)

        claimed = await backend.claim_pending_job(job_types=["type_b"])
        assert claimed is not None
        assert claimed.id == "job-b"

    async def test_claim_priority_order(self, backend: MemoryBackend):
        low = Job(id="low", job_type="test", priority=JobPriority.LOW)
        normal = Job(id="normal", job_type="test", priority=JobPriority.NORMAL)
        high = Job(id="high", job_type="test", priority=JobPriority.HIGH)

        await backend.store_job(low)
        await backend.store_job(normal)
        await backend.store_job(high)

        claimed = await backend.claim_pending_job()
        assert claimed.id == "high"

        claimed = await backend.claim_pending_job()
        assert claimed.id == "normal"

        claimed = await backend.claim_pending_job()
        assert claimed.id == "low"

    async def test_claim_fifo_within_priority(self, backend: MemoryBackend):
        job1 = Job(id="job-1", job_type="test", priority=JobPriority.NORMAL)
        await backend.store_job(job1)

        # Small delay to ensure different created_at times
        await asyncio.sleep(0.01)

        job2 = Job(id="job-2", job_type="test", priority=JobPriority.NORMAL)
        await backend.store_job(job2)

        claimed = await backend.claim_pending_job()
        assert claimed.id == "job-1"

    async def test_claim_skips_non_pending(self, backend: MemoryBackend):
        processing = Job(id="processing", job_type="test", status=JobStatus.PROCESSING)
        complete = Job(id="complete", job_type="test", status=JobStatus.COMPLETE)
        pending = Job(id="pending", job_type="test")

        await backend.store_job(processing)
        await backend.store_job(complete)
        await backend.store_job(pending)

        claimed = await backend.claim_pending_job()
        assert claimed.id == "pending"

    async def test_claim_is_atomic(self, backend: MemoryBackend):
        """Test that concurrent claims don't result in duplicate processing."""
        for i in range(10):
            job = Job(id=f"job-{i}", job_type="test")
            await backend.store_job(job)

        claimed_ids = []

        async def claim_worker():
            while True:
                job = await backend.claim_pending_job()
                if job is None:
                    break
                claimed_ids.append(job.id)

        # Run multiple workers concurrently
        await asyncio.gather(*[claim_worker() for _ in range(5)])

        # Each job should be claimed exactly once
        assert len(claimed_ids) == 10
        assert len(set(claimed_ids)) == 10


class TestMemoryBackendPubSub:
    async def test_publish_and_subscribe(self, backend: MemoryBackend):
        received = []

        async def subscriber():
            async for update in backend.subscribe_updates("job-1"):
                received.append(update)

        task = asyncio.create_task(subscriber())

        # Small delay to ensure subscriber is ready
        await asyncio.sleep(0.01)

        update = JobUpdate(job_id="job-1", status=JobStatus.PROCESSING, progress=0.5)
        await backend.publish_update(update)

        # Publish terminal state to end subscription
        final_update = JobUpdate(
            job_id="job-1", status=JobStatus.COMPLETE, progress=1.0
        )
        await backend.publish_update(final_update)

        await task

        assert len(received) == 2
        assert received[0].status == JobStatus.PROCESSING
        assert received[1].status == JobStatus.COMPLETE

    async def test_subscribe_ends_on_terminal_state(self, backend: MemoryBackend):
        async def subscriber():
            updates = []
            async for update in backend.subscribe_updates("job-1"):
                updates.append(update)
            return updates

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        # Publish FAILED status (terminal)
        update = JobUpdate(job_id="job-1", status=JobStatus.FAILED, error="oops")
        await backend.publish_update(update)

        updates = await task
        assert len(updates) == 1
        assert updates[0].status == JobStatus.FAILED

    async def test_multiple_subscribers(self, backend: MemoryBackend):
        results_1 = []
        results_2 = []

        async def sub1():
            async for update in backend.subscribe_updates("job-1"):
                results_1.append(update)

        async def sub2():
            async for update in backend.subscribe_updates("job-1"):
                results_2.append(update)

        t1 = asyncio.create_task(sub1())
        t2 = asyncio.create_task(sub2())
        await asyncio.sleep(0.01)

        update = JobUpdate(job_id="job-1", status=JobStatus.COMPLETE)
        await backend.publish_update(update)

        await t1
        await t2

        assert len(results_1) == 1
        assert len(results_2) == 1


class TestMemoryBackendClose:
    async def test_close_clears_jobs(self, backend: MemoryBackend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        await backend.close()

        result = await backend.get_job("job-1")
        assert result is None

    async def test_close_stops_subscribers(self, backend: MemoryBackend):
        updates = []

        async def subscriber():
            async for update in backend.subscribe_updates("job-1"):
                updates.append(update)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        await backend.close()
        await task

        assert updates == []
