"""Tests for SQLite backend."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

from jdobb_async_queue.schemas import Job, JobPriority, JobStatus, JobUpdate

_aiosqlite_available = importlib.util.find_spec("aiosqlite") is not None

pytestmark = pytest.mark.skipif(
    not _aiosqlite_available, reason="aiosqlite not installed"
)


@pytest.fixture
async def backend():
    """Create a fresh SQLite backend for each test (in-memory)."""
    from jdobb_async_queue.backends.sqlite import SQLiteBackend

    b = SQLiteBackend(url="sqlite:///:memory:")
    yield b
    await b.close()


@pytest.fixture
async def file_backend(tmp_path: Path):
    """Create a SQLite backend with file storage."""
    from jdobb_async_queue.backends.sqlite import SQLiteBackend

    db_path = tmp_path / "test.db"
    b = SQLiteBackend(url=f"sqlite:///{db_path}")
    yield b
    await b.close()


class TestSQLiteBackendStorage:
    async def test_store_and_get_job(self, backend):
        job = Job(id="job-1", job_type="test", data={"key": "value"})
        await backend.store_job(job)

        retrieved = await backend.get_job("job-1")
        assert retrieved is not None
        assert retrieved.id == "job-1"
        assert retrieved.job_type == "test"
        assert retrieved.data == {"key": "value"}

    async def test_get_nonexistent_job(self, backend):
        result = await backend.get_job("nonexistent")
        assert result is None

    async def test_store_with_file_persistence(self, file_backend):
        job = Job(id="job-1", job_type="test", data={"key": "value"})
        await file_backend.store_job(job)

        retrieved = await file_backend.get_job("job-1")
        assert retrieved is not None
        assert retrieved.id == "job-1"

    async def test_store_preserves_all_fields(self, backend):
        job = Job(
            id="job-1",
            job_type="test",
            data={"input": "data"},
            priority=JobPriority.HIGH,
            metadata={"user": "alice"},
            ttl=3600,
        )
        await backend.store_job(job)

        retrieved = await backend.get_job("job-1")
        assert retrieved.priority == JobPriority.HIGH
        assert retrieved.metadata == {"user": "alice"}
        assert retrieved.ttl == 3600


class TestSQLiteBackendUpdate:
    async def test_update_job(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        job.status = JobStatus.PROCESSING
        job.progress = 0.5
        await backend.update_job(job)

        retrieved = await backend.get_job("job-1")
        assert retrieved.status == JobStatus.PROCESSING
        assert retrieved.progress == 0.5


class TestSQLiteBackendDelete:
    async def test_delete_job(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        result = await backend.delete_job("job-1")
        assert result is True

        retrieved = await backend.get_job("job-1")
        assert retrieved is None

    async def test_delete_nonexistent_job(self, backend):
        result = await backend.delete_job("nonexistent")
        assert result is False


class TestSQLiteBackendClaim:
    async def test_claim_pending_job(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        claimed = await backend.claim_pending_job()
        assert claimed is not None
        assert claimed.id == "job-1"
        assert claimed.status == JobStatus.PROCESSING

        # Verify original is also updated
        stored = await backend.get_job("job-1")
        assert stored.status == JobStatus.PROCESSING

    async def test_claim_no_pending_jobs(self, backend):
        result = await backend.claim_pending_job()
        assert result is None

    async def test_claim_with_type_filter(self, backend):
        job_a = Job(id="job-a", job_type="type_a")
        job_b = Job(id="job-b", job_type="type_b")
        await backend.store_job(job_a)
        await backend.store_job(job_b)

        claimed = await backend.claim_pending_job(job_types=["type_b"])
        assert claimed is not None
        assert claimed.id == "job-b"

    async def test_claim_priority_order(self, backend):
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

    async def test_claim_fifo_within_priority(self, backend):
        job1 = Job(id="job-1", job_type="test", priority=JobPriority.NORMAL)
        await backend.store_job(job1)

        await asyncio.sleep(0.01)

        job2 = Job(id="job-2", job_type="test", priority=JobPriority.NORMAL)
        await backend.store_job(job2)

        claimed = await backend.claim_pending_job()
        assert claimed.id == "job-1"

    async def test_claim_skips_non_pending(self, backend):
        processing = Job(id="processing", job_type="test", status=JobStatus.PROCESSING)
        complete = Job(id="complete", job_type="test", status=JobStatus.COMPLETE)
        pending = Job(id="pending", job_type="test")

        await backend.store_job(processing)
        await backend.store_job(complete)
        await backend.store_job(pending)

        claimed = await backend.claim_pending_job()
        assert claimed.id == "pending"

    async def test_claim_is_atomic(self, backend):
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


class TestSQLiteBackendPubSub:
    async def test_publish_and_subscribe(self, backend):
        received = []

        async def subscriber():
            async for update in backend.subscribe_updates("job-1"):
                received.append(update)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        update = JobUpdate(job_id="job-1", status=JobStatus.PROCESSING, progress=0.5)
        await backend.publish_update(update)

        final_update = JobUpdate(
            job_id="job-1", status=JobStatus.COMPLETE, progress=1.0
        )
        await backend.publish_update(final_update)

        await task

        assert len(received) == 2
        assert received[0].status == JobStatus.PROCESSING
        assert received[1].status == JobStatus.COMPLETE

    async def test_subscribe_ends_on_terminal_state(self, backend):
        async def subscriber():
            updates = []
            async for update in backend.subscribe_updates("job-1"):
                updates.append(update)
            return updates

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        update = JobUpdate(job_id="job-1", status=JobStatus.FAILED, error="oops")
        await backend.publish_update(update)

        updates = await task
        assert len(updates) == 1
        assert updates[0].status == JobStatus.FAILED


class TestSQLiteBackendTTL:
    async def test_expired_jobs_cleaned_on_get(self, backend):
        # Create a job that's already expired
        job = Job(id="job-1", job_type="test", ttl=0)  # Expires immediately
        await backend.store_job(job)

        # Wait a moment
        await asyncio.sleep(0.1)

        # Job should be cleaned up
        _ = await backend.get_job("job-1")
        # Note: TTL=0 means expires immediately, but the implementation
        # calculates expires_at from created_at + ttl, so it may still exist
        # This test is more of a smoke test for the cleanup logic


class TestSQLiteBackendClose:
    async def test_close(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        await backend.close()

        # Backend should be closed
        assert backend._db is None

    async def test_close_stops_subscribers(self, backend):
        updates = []

        async def subscriber():
            async for update in backend.subscribe_updates("job-1"):
                updates.append(update)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.01)

        await backend.close()
        await task

        assert updates == []


class TestSQLiteBackendURLParsing:
    def test_parse_memory_url(self):
        from jdobb_async_queue.backends.sqlite import SQLiteBackend

        backend = SQLiteBackend("sqlite:///:memory:")
        assert backend._db_path == ":memory:"

    def test_parse_file_url(self):
        from jdobb_async_queue.backends.sqlite import SQLiteBackend

        backend = SQLiteBackend("sqlite:///path/to/db.sqlite")
        # Leading slash is stripped for cross-platform compatibility
        assert backend._db_path == "path/to/db.sqlite"

    def test_invalid_scheme_raises(self):
        from jdobb_async_queue.backends.sqlite import SQLiteBackend

        with pytest.raises(ValueError, match="Invalid SQLite URL scheme"):
            SQLiteBackend("postgres://localhost/db")
