"""Abstract base class for queue backends."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from jdobb_async_queue.schemas import Job, JobUpdate


class QueueBackend(ABC):
    """Abstract interface for queue storage backends."""

    @abstractmethod
    async def store_job(self, job: Job) -> None:
        """Store a job in the backend."""
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by ID. Returns None if not found."""
        ...

    @abstractmethod
    async def update_job(self, job: Job) -> None:
        """Update an existing job."""
        ...

    @abstractmethod
    async def delete_job(self, job_id: str) -> bool:
        """Delete a job. Returns True if deleted, False if not found."""
        ...

    @abstractmethod
    async def claim_pending_job(self, job_types: list[str] | None = None) -> Job | None:
        """
        Atomically claim a pending job for processing.

        This must be atomic to prevent race conditions when multiple workers
        try to claim the same job. The job's status should be changed from
        PENDING to PROCESSING.

        Args:
            job_types: Optional list of job types to filter. If None, any type is claimed.

        Returns:
            The claimed job with status set to PROCESSING, or None if no jobs available.
        """
        ...

    @abstractmethod
    async def publish_update(self, update: JobUpdate) -> None:
        """Publish a job update for subscribers."""
        ...

    @abstractmethod
    def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]:
        """
        Subscribe to updates for a specific job.

        Yields JobUpdate objects as they are published.
        Should stop yielding when job reaches terminal state (COMPLETE/FAILED/CANCELLED).
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        ...
