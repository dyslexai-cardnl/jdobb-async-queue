"""Real-time update broadcasting."""

from collections.abc import AsyncIterator
from typing import Any

import structlog

from jdobb_async_queue.job_queue import JobQueue
from jdobb_async_queue.schemas import JobStatus, JobUpdate

logger = structlog.get_logger()


class Broadcaster:
    """Broadcasts job updates to subscribers.

    Provides an interface for clients to subscribe to real-time updates
    for specific jobs. Useful for WebSocket integrations.

    Example:
        broadcaster = Broadcaster(queue)

        # Subscribe to job updates
        async for update in broadcaster.subscribe(job_id):
            print(f"Job {update.job_id}: {update.progress}%")
            # Loop ends on COMPLETE/FAILED/CANCELLED

        # Send custom update
        await broadcaster.send(job_id, progress=0.5, message="Working...")
    """

    def __init__(self, queue: JobQueue) -> None:
        """Initialize broadcaster.

        Args:
            queue: JobQueue instance to subscribe to.
        """
        self.queue = queue

    async def subscribe(self, job_id: str) -> AsyncIterator[JobUpdate]:
        """Subscribe to updates for a specific job.

        Yields JobUpdate objects as they are published. The iteration
        ends when the job reaches a terminal state (COMPLETE, FAILED, or CANCELLED).

        Args:
            job_id: The job ID to subscribe to.

        Yields:
            JobUpdate objects for the job.
        """
        logger.debug("Subscribing to job updates", job_id=job_id)

        try:
            async for update in self.queue.backend.subscribe_updates(job_id):
                yield update

                if update.status in (
                    JobStatus.COMPLETE,
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                ):
                    break
        finally:
            logger.debug("Unsubscribed from job updates", job_id=job_id)

    async def send(
        self,
        job_id: str,
        *,
        progress: float | None = None,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Send a custom update for a job.

        This publishes an update without modifying the job's stored state.
        Useful for sending intermediate updates that don't need to be persisted.

        Args:
            job_id: The job ID to send update for.
            progress: Optional progress value 0.0 to 1.0.
            message: Optional status message.
            data: Optional custom data (stored in results field).

        Returns:
            True if sent, False if job not found.
        """
        job = await self.queue.get(job_id)
        if job is None:
            return False

        update = JobUpdate(
            job_id=job_id,
            status=job.status,
            progress=progress if progress is not None else job.progress,
            message=message if message is not None else job.message,
            results=data,
        )

        await self.queue.backend.publish_update(update)
        logger.debug("Sent update", job_id=job_id, progress=progress, message=message)
        return True

    async def subscribe_with_timeout(
        self,
        job_id: str,
        timeout: float,
    ) -> AsyncIterator[JobUpdate]:
        """Subscribe to updates with a timeout.

        Like subscribe(), but raises asyncio.TimeoutError if no update
        is received within the timeout period.

        Args:
            job_id: The job ID to subscribe to.
            timeout: Timeout in seconds between updates.

        Yields:
            JobUpdate objects for the job.

        Raises:
            asyncio.TimeoutError: If no update received within timeout.
        """
        logger.debug("Subscribing with timeout", job_id=job_id, timeout=timeout)

        async for update in self.queue.backend.subscribe_updates(job_id):
            yield update

            if update.status in (
                JobStatus.COMPLETE,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ):
                break
