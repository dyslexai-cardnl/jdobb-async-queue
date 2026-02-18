"""Shared fixtures for tests."""

import os

import pytest

from jdobb_async_queue import JobQueue
from jdobb_async_queue.backends.memory import MemoryBackend


@pytest.fixture
async def memory_backend():
    """Create a fresh memory backend."""
    backend = MemoryBackend()
    yield backend
    await backend.close()


@pytest.fixture
async def memory_queue():
    """Create a job queue with memory backend."""
    queue = JobQueue(backend="memory")
    yield queue
    await queue.close()


@pytest.fixture
async def sqlite_queue(tmp_path):
    """Create a job queue with SQLite backend."""
    try:
        import aiosqlite  # noqa: F401
    except ImportError:
        pytest.skip("aiosqlite not installed")

    db_path = tmp_path / "test.db"
    queue = JobQueue(backend="sqlite", url=f"sqlite:///{db_path}")
    yield queue
    await queue.close()


@pytest.fixture
async def redis_queue():
    """Create a job queue with Redis backend (skipped if unavailable)."""
    try:
        import redis.asyncio as redis
    except ImportError:
        pytest.skip("redis not installed")

    redis_url = os.environ.get("REDIS_URL", "redis://localhost")

    # Check if Redis is available
    try:
        client = redis.from_url(redis_url)
        await client.ping()
        await client.close()
    except Exception:
        pytest.skip("Redis server not available")

    # Use unique namespace per test
    namespace = f"test_{os.urandom(4).hex()}"
    queue = JobQueue(backend="redis", url=redis_url, namespace=namespace)

    yield queue

    # Cleanup
    backend = queue.backend
    client = backend._client
    pattern = f"{namespace}:*"
    async for key in client.scan_iter(match=pattern):
        await client.delete(key)

    await queue.close()
