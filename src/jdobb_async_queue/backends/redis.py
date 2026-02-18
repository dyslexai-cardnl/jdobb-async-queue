"""Redis queue backend for production use."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from jdobb_async_queue.backends.base import QueueBackend
from jdobb_async_queue.schemas import Job, JobStatus, JobUpdate

try:
    import redis.asyncio as redis
    from redis.asyncio.client import PubSub
except ImportError as e:
    raise ImportError("redis package required. Install with: pip install redis") from e


class RedisBackend(QueueBackend):
    """Redis implementation of queue backend.

    Uses Redis for storage with TTL support, WATCH/MULTI/EXEC for atomic
    claims, and Pub/Sub for real-time updates.
    """

    def __init__(
        self,
        url: str = "redis://localhost",
        namespace: str = "default",
        *,
        client: redis.Redis | None = None,
    ) -> None:
        """Initialize Redis backend.

        Args:
            url: Redis connection URL.
            namespace: Namespace prefix for all keys.
            client: Optional pre-configured Redis client.
        """
        self.url = url
        self.namespace = namespace
        self._client = client or redis.from_url(url, decode_responses=True)
        self._pubsub: PubSub | None = None
        self._subscriber_tasks: dict[str, asyncio.Task] = {}

    def _key(self, *parts: str) -> str:
        """Build a namespaced key."""
        return ":".join([self.namespace, *parts])

    def _job_key(self, job_id: str) -> str:
        """Build job storage key."""
        return self._key("job", job_id)

    def _channel_key(self, job_id: str) -> str:
        """Build pub/sub channel key."""
        return self._key("updates", job_id)

    def _serialize_job(self, job: Job) -> str:
        """Serialize job to JSON string."""
        return job.model_dump_json()

    def _deserialize_job(self, data: str) -> Job:
        """Deserialize job from JSON string."""
        return Job.model_validate_json(data)

    async def store_job(self, job: Job) -> None:
        """Store a job in Redis with optional TTL."""
        key = self._job_key(job.id)
        data = self._serialize_job(job)

        if job.ttl:
            await self._client.setex(key, job.ttl, data)
        else:
            await self._client.set(key, data)

        # Add to pending set for efficient lookup
        if job.status == JobStatus.PENDING:
            score = self._priority_score(job)
            await self._client.zadd(self._key("pending", job.job_type), {job.id: score})

    def _priority_score(self, job: Job) -> float:
        """Calculate priority score for sorted set.

        Higher priority and older jobs get lower scores (claimed first).
        Score = -priority_weight * 1e12 + timestamp
        """
        timestamp = job.created_at.timestamp()
        return -job.priority.weight * 1e12 + timestamp

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by ID from Redis."""
        key = self._job_key(job_id)
        data = await self._client.get(key)
        if data is None:
            return None
        return self._deserialize_job(data)

    async def update_job(self, job: Job) -> None:
        """Update an existing job, preserving TTL."""
        key = self._job_key(job.id)

        # Get remaining TTL
        ttl = await self._client.ttl(key)

        job.updated_at = datetime.now(UTC)
        data = self._serialize_job(job)

        if ttl > 0:
            await self._client.setex(key, ttl, data)
        elif ttl == -1:  # No expiry
            await self._client.set(key, data)
        # If ttl == -2, key doesn't exist, still store it
        else:
            if job.ttl:
                await self._client.setex(key, job.ttl, data)
            else:
                await self._client.set(key, data)

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job from Redis."""
        key = self._job_key(job_id)

        # Get job first to remove from pending set
        job = await self.get_job(job_id)
        if job:
            await self._client.zrem(self._key("pending", job.job_type), job_id)

        result = await self._client.delete(key)
        return result > 0

    async def claim_pending_job(self, job_types: list[str] | None = None) -> Job | None:
        """Atomically claim a pending job using WATCH/MULTI/EXEC.

        This prevents race conditions when multiple workers try to claim
        the same job.
        """
        # Get all pending keys to check
        if job_types:
            pending_keys = [self._key("pending", jt) for jt in job_types]
        else:
            # Scan for all pending:* keys
            pattern = self._key("pending", "*")
            pending_keys = []
            async for key in self._client.scan_iter(match=pattern):
                pending_keys.append(key)

        if not pending_keys:
            return None

        # Try each pending set until we successfully claim a job
        for pending_key in pending_keys:
            # Get highest priority job (lowest score)
            candidates = await self._client.zrange(pending_key, 0, 0)
            if not candidates:
                continue

            job_id = candidates[0]
            job_key = self._job_key(job_id)

            # Use WATCH for optimistic locking
            async with self._client.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(job_key)

                    # Re-fetch job under watch
                    data = await self._client.get(job_key)
                    if data is None:
                        await pipe.unwatch()
                        continue

                    job = self._deserialize_job(data)
                    if job.status != JobStatus.PENDING:
                        await pipe.unwatch()
                        continue

                    # Update job status
                    job.status = JobStatus.PROCESSING
                    job.updated_at = datetime.now(UTC)

                    # Execute atomic update
                    pipe.multi()

                    # Get TTL and preserve it
                    ttl = await self._client.ttl(job_key)
                    if ttl > 0:
                        pipe.setex(job_key, ttl, self._serialize_job(job))
                    else:
                        pipe.set(job_key, self._serialize_job(job))

                    # Remove from pending set
                    pipe.zrem(pending_key, job_id)

                    await pipe.execute()
                    return job

                except redis.WatchError:
                    # Another worker claimed this job, try next
                    continue

        return None

    async def publish_update(self, update: JobUpdate) -> None:
        """Publish a job update via Redis Pub/Sub."""
        channel = self._channel_key(update.job_id)
        data = update.model_dump_json()
        await self._client.publish(channel, data)

    async def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]:
        """Subscribe to updates for a specific job via Redis Pub/Sub."""
        pubsub = self._client.pubsub()
        channel = self._channel_key(job_id)

        try:
            await pubsub.subscribe(channel)

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is None:
                    continue

                if message["type"] == "message":
                    data = message["data"]
                    update = JobUpdate.model_validate_json(data)
                    yield update

                    # Stop on terminal states
                    if update.status in (
                        JobStatus.COMPLETE,
                        JobStatus.FAILED,
                        JobStatus.CANCELLED,
                    ):
                        break

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def close(self) -> None:
        """Close Redis connections."""
        if self._pubsub:
            await self._pubsub.close()
        await self._client.close()
