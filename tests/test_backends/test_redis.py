"""Tests for Redis backend.

These tests require a running Redis server. They are skipped if Redis is unavailable.
"""

import asyncio
import os

import pytest

from jdobb_async_queue.schemas import Job, JobPriority, JobStatus, JobUpdate

# Skip all tests if Redis is not available
redis_url = os.environ.get("REDIS_URL", "redis://localhost")

try:
    import redis.asyncio as redis

    _redis_available = True
except ImportError:
    _redis_available = False

pytestmark = pytest.mark.skipif(
    not _redis_available, reason="redis package not installed"
)


async def _check_redis_connection():
    """Check if Redis is actually running."""
    try:
        client = redis.from_url(redis_url)
        await client.ping()
        await client.close()
        return True
    except Exception:
        return False


@pytest.fixture
async def backend():
    """Create a fresh Redis backend for each test."""
    if not await _check_redis_connection():
        pytest.skip("Redis server not available")

    from jdobb_async_queue.backends.redis import RedisBackend

    # Use unique namespace per test to avoid conflicts
    namespace = f"test_{os.urandom(4).hex()}"
    b = RedisBackend(url=redis_url, namespace=namespace)

    yield b

    # Cleanup: delete all keys in namespace
    client = b._client
    pattern = f"{namespace}:*"
    async for key in client.scan_iter(match=pattern):
        await client.delete(key)

    await b.close()


class TestRedisBackendStorage:
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

    async def test_store_with_ttl(self, backend):
        job = Job(id="job-1", job_type="test", ttl=10)
        await backend.store_job(job)

        # Check TTL is set
        ttl = await backend._client.ttl(backend._job_key("job-1"))
        assert ttl > 0
        assert ttl <= 10


class TestRedisBackendUpdate:
    async def test_update_job(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        job.status = JobStatus.PROCESSING
        job.progress = 0.5
        await backend.update_job(job)

        retrieved = await backend.get_job("job-1")
        assert retrieved.status == JobStatus.PROCESSING
        assert retrieved.progress == 0.5

    async def test_update_preserves_ttl(self, backend):
        job = Job(id="job-1", job_type="test", ttl=30)
        await backend.store_job(job)

        original_ttl = await backend._client.ttl(backend._job_key("job-1"))

        job.status = JobStatus.PROCESSING
        await backend.update_job(job)

        new_ttl = await backend._client.ttl(backend._job_key("job-1"))
        # TTL should be preserved (may have decreased slightly)
        assert new_ttl > 0
        assert new_ttl <= original_ttl


class TestRedisBackendDelete:
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

    async def test_delete_removes_from_pending(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        # Verify in pending set
        pending_key = backend._key("pending", "test")
        count = await backend._client.zcard(pending_key)
        assert count == 1

        await backend.delete_job("job-1")

        # Should be removed from pending set
        count = await backend._client.zcard(pending_key)
        assert count == 0


class TestRedisBackendClaim:
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

    async def test_claim_removes_from_pending_set(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        pending_key = backend._key("pending", "test")
        count_before = await backend._client.zcard(pending_key)
        assert count_before == 1

        await backend.claim_pending_job()

        count_after = await backend._client.zcard(pending_key)
        assert count_after == 0

    async def test_claim_is_atomic(self, backend):
        """Test that concurrent claims don't result in duplicate processing."""
        for i in range(10):
            job = Job(id=f"job-{i}", job_type="test")
            await backend.store_job(job)

        claimed_ids = []
        lock = asyncio.Lock()

        async def claim_worker():
            while True:
                job = await backend.claim_pending_job()
                if job is None:
                    break
                async with lock:
                    claimed_ids.append(job.id)

        # Run multiple workers concurrently
        await asyncio.gather(*[claim_worker() for _ in range(5)])

        # Each job should be claimed exactly once
        assert len(claimed_ids) == 10
        assert len(set(claimed_ids)) == 10


class TestRedisBackendPubSub:
    async def test_publish_and_subscribe(self, backend):
        received = []

        async def subscriber():
            async for update in backend.subscribe_updates("job-1"):
                received.append(update)

        task = asyncio.create_task(subscriber())

        # Small delay to ensure subscriber is ready
        await asyncio.sleep(0.1)

        update = JobUpdate(job_id="job-1", status=JobStatus.PROCESSING, progress=0.5)
        await backend.publish_update(update)

        # Publish terminal state to end subscription
        final_update = JobUpdate(
            job_id="job-1", status=JobStatus.COMPLETE, progress=1.0
        )
        await backend.publish_update(final_update)

        await asyncio.wait_for(task, timeout=5.0)

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
        await asyncio.sleep(0.1)

        # Publish FAILED status (terminal)
        update = JobUpdate(job_id="job-1", status=JobStatus.FAILED, error="oops")
        await backend.publish_update(update)

        updates = await asyncio.wait_for(task, timeout=5.0)
        assert len(updates) == 1
        assert updates[0].status == JobStatus.FAILED


class TestRedisBackendClose:
    async def test_close(self, backend):
        job = Job(id="job-1", job_type="test")
        await backend.store_job(job)

        await backend.close()
        # Connection should be closed
