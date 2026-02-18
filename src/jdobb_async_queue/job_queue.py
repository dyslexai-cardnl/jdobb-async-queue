"""Main JobQueue facade class."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from jdobb_async_queue.backends.base import QueueBackend
from jdobb_async_queue.backends.memory import MemoryBackend
from jdobb_async_queue.schemas import Job, JobPriority, JobStatus, JobUpdate

logger = structlog.get_logger()


class JobQueue:
    """Main interface for job queue operations.

    Provides a high-level API for enqueueing jobs, claiming them for processing,
    and updating their status.

    Example:
        queue = JobQueue(backend="memory")

        # Producer
        job_id = await queue.enqueue("process", data={"input": "test"})

        # Consumer
        job = await queue.claim(["process"])
        await queue.update(job.id, progress=0.5)
        await queue.complete(job.id, results={"output": "done"})
    """

    def __init__(
        self,
        backend: QueueBackend | str = "memory",
        *,
        url: str | None = None,
        namespace: str = "default",
        default_ttl: int | None = None,
    ) -> None:
        """Initialize JobQueue.

        Args:
            backend: Backend instance or string ("memory", "redis", "sqlite").
            url: Connection URL for redis/sqlite backends.
            namespace: Namespace prefix for keys (used by redis backend).
            default_ttl: Default TTL in seconds for jobs.
        """
        self.namespace = namespace
        self.default_ttl = default_ttl

        if isinstance(backend, QueueBackend):
            self._backend = backend
        elif backend == "memory":
            self._backend = MemoryBackend()
        elif backend == "redis":
            from jdobb_async_queue.backends.redis import RedisBackend

            self._backend = RedisBackend(
                url=url or "redis://localhost", namespace=namespace
            )
        elif backend == "sqlite":
            from jdobb_async_queue.backends.sqlite import SQLiteBackend

            self._backend = SQLiteBackend(url=url or "sqlite:///:memory:")
        else:
            raise ValueError(f"Unknown backend: {backend}")

    @property
    def backend(self) -> QueueBackend:
        """Return the underlying backend."""
        return self._backend

    async def enqueue(
        self,
        job_type: str,
        data: dict[str, Any] | None = None,
        *,
        priority: JobPriority = JobPriority.NORMAL,
        ttl: int | None = None,
        metadata: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> str:
        """Enqueue a new job.

        Args:
            job_type: Type of job for handler routing.
            data: Job payload data.
            priority: Job priority level.
            ttl: Time-to-live in seconds (overrides default_ttl).
            metadata: Arbitrary metadata to attach to job.
            job_id: Optional custom job ID. Auto-generated if not provided.

        Returns:
            The job ID.
        """
        job = Job(
            id=job_id or str(uuid.uuid4()),
            job_type=job_type,
            data=data or {},
            priority=priority,
            ttl=ttl if ttl is not None else self.default_ttl,
            metadata=metadata or {},
        )

        await self._backend.store_job(job)
        logger.debug(
            "Job enqueued", job_id=job.id, job_type=job_type, priority=priority.value
        )

        return job.id

    async def get(self, job_id: str) -> Job | None:
        """Get a job by ID.

        Args:
            job_id: The job ID.

        Returns:
            The job if found, None otherwise.
        """
        return await self._backend.get_job(job_id)

    async def cancel(self, job_id: str, reason: str | None = None) -> bool:
        """Cancel a pending or processing job.

        Args:
            job_id: The job ID to cancel.
            reason: Optional cancellation reason.

        Returns:
            True if cancelled, False if job not found or already terminal.
        """
        job = await self._backend.get_job(job_id)
        if job is None:
            return False

        if job.status in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        job.status = JobStatus.CANCELLED
        job.error = reason
        job.updated_at = datetime.now(UTC)
        job.completed_at = datetime.now(UTC)

        await self._backend.update_job(job)

        update = JobUpdate(
            job_id=job_id,
            status=JobStatus.CANCELLED,
            error=reason,
        )
        await self._backend.publish_update(update)

        logger.info("Job cancelled", job_id=job_id, reason=reason)
        return True

    async def claim(self, job_types: list[str] | None = None) -> Job | None:
        """Atomically claim a pending job for processing.

        Args:
            job_types: Optional list of job types to filter.

        Returns:
            The claimed job with status PROCESSING, or None if no jobs available.
        """
        job = await self._backend.claim_pending_job(job_types)
        if job:
            logger.debug("Job claimed", job_id=job.id, job_type=job.job_type)
        return job

    async def update(
        self,
        job_id: str,
        progress: float | None = None,
        message: str | None = None,
    ) -> bool:
        """Update job progress.

        Args:
            job_id: The job ID.
            progress: Progress value 0.0 to 1.0.
            message: Status message.

        Returns:
            True if updated, False if job not found.
        """
        job = await self._backend.get_job(job_id)
        if job is None:
            return False

        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        job.updated_at = datetime.now(UTC)

        await self._backend.update_job(job)

        update = JobUpdate(
            job_id=job_id,
            status=job.status,
            progress=job.progress,
            message=job.message,
        )
        await self._backend.publish_update(update)

        logger.debug("Job updated", job_id=job_id, progress=progress, message=message)
        return True

    async def complete(
        self, job_id: str, results: dict[str, Any] | None = None
    ) -> bool:
        """Mark job as complete.

        Args:
            job_id: The job ID.
            results: Optional results data.

        Returns:
            True if completed, False if job not found.
        """
        job = await self._backend.get_job(job_id)
        if job is None:
            return False

        job.status = JobStatus.COMPLETE
        job.progress = 1.0
        job.results = results
        job.updated_at = datetime.now(UTC)
        job.completed_at = datetime.now(UTC)

        await self._backend.update_job(job)

        update = JobUpdate(
            job_id=job_id,
            status=JobStatus.COMPLETE,
            progress=1.0,
            results=results,
        )
        await self._backend.publish_update(update)

        logger.info("Job completed", job_id=job_id)
        return True

    async def fail(self, job_id: str, error: str) -> bool:
        """Mark job as failed.

        Args:
            job_id: The job ID.
            error: Error message.

        Returns:
            True if marked failed, False if job not found.
        """
        job = await self._backend.get_job(job_id)
        if job is None:
            return False

        job.status = JobStatus.FAILED
        job.error = error
        job.updated_at = datetime.now(UTC)
        job.completed_at = datetime.now(UTC)

        await self._backend.update_job(job)

        update = JobUpdate(
            job_id=job_id,
            status=JobStatus.FAILED,
            error=error,
        )
        await self._backend.publish_update(update)

        logger.warning("Job failed", job_id=job_id, error=error)
        return True

    async def close(self) -> None:
        """Close the queue and release resources."""
        await self._backend.close()
        logger.debug("JobQueue closed")
