"""In-memory queue backend for testing."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from jdobb_async_queue.backends.base import QueueBackend
from jdobb_async_queue.schemas import Job, JobStatus, JobUpdate


class MemoryBackend(QueueBackend):
    """In-memory implementation of queue backend for testing.

    Thread-safe using asyncio.Lock for atomic operations.
    Uses asyncio.Queue for pub/sub simulation.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue[JobUpdate | None]]] = {}

    async def store_job(self, job: Job) -> None:
        """Store a job in memory."""
        async with self._lock:
            self._jobs[job.id] = job.model_copy()

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by ID."""
        async with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy() if job else None

    async def update_job(self, job: Job) -> None:
        """Update an existing job."""
        async with self._lock:
            if job.id in self._jobs:
                job.updated_at = datetime.now(UTC)
                self._jobs[job.id] = job.model_copy()

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        async with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    async def claim_pending_job(self, job_types: list[str] | None = None) -> Job | None:
        """Atomically claim a pending job for processing.

        Jobs are claimed in priority order (HIGH > NORMAL > LOW), then by creation time.
        """
        async with self._lock:
            # Find all pending jobs matching type filter
            pending = [
                job
                for job in self._jobs.values()
                if job.status == JobStatus.PENDING
                and (job_types is None or job.job_type in job_types)
            ]

            if not pending:
                return None

            # Sort by priority (descending by weight) then by creation time (ascending)
            pending.sort(key=lambda j: (-j.priority.weight, j.created_at))

            # Claim the highest priority job
            job = pending[0]
            job.status = JobStatus.PROCESSING
            job.updated_at = datetime.now(UTC)
            self._jobs[job.id] = job

            return job.model_copy()

    async def publish_update(self, update: JobUpdate) -> None:
        """Publish a job update to all subscribers."""
        async with self._lock:
            queues = self._subscribers.get(update.job_id, [])
            for queue in queues:
                await queue.put(update)

            # If job is terminal, signal end to subscribers
            if update.status in (
                JobStatus.COMPLETE,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ):
                for queue in queues:
                    await queue.put(None)

    async def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]:
        """Subscribe to updates for a specific job."""
        queue: asyncio.Queue[JobUpdate | None] = asyncio.Queue()

        async with self._lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = []
            self._subscribers[job_id].append(queue)

        try:
            while True:
                update = await queue.get()
                if update is None:
                    break
                yield update
        finally:
            async with self._lock:
                if job_id in self._subscribers:
                    try:
                        self._subscribers[job_id].remove(queue)
                    except ValueError:
                        pass
                    if not self._subscribers[job_id]:
                        del self._subscribers[job_id]

    async def close(self) -> None:
        """Close and cleanup resources."""
        async with self._lock:
            # Signal all subscribers to stop
            for queues in self._subscribers.values():
                for queue in queues:
                    await queue.put(None)
            self._subscribers.clear()
            self._jobs.clear()
