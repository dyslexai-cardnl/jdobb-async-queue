"""Worker implementation for processing jobs."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from jdobb_async_queue.job_queue import JobQueue
from jdobb_async_queue.schemas import Job

logger = structlog.get_logger()


@dataclass
class JobContext:
    """Context provided to job handlers.

    Provides access to the job data and methods to update progress.
    """

    job: Job
    _queue: JobQueue

    @property
    def id(self) -> str:
        """Job ID."""
        return self.job.id

    @property
    def job_type(self) -> str:
        """Job type."""
        return self.job.job_type

    @property
    def data(self) -> dict[str, Any]:
        """Job payload data."""
        return self.job.data

    @property
    def metadata(self) -> dict[str, Any]:
        """Job metadata."""
        return self.job.metadata

    async def update(
        self, progress: float | None = None, message: str | None = None
    ) -> None:
        """Update job progress.

        Args:
            progress: Progress value 0.0 to 1.0.
            message: Status message.
        """
        await self._queue.update(self.job.id, progress=progress, message=message)


HandlerFunc = Callable[[JobContext], Awaitable[dict[str, Any] | None]]


class Worker:
    """Polling worker that processes jobs from a queue.

    Example:
        queue = JobQueue(backend="memory")
        worker = Worker(queue, job_types=["task"])

        @worker.handler("task")
        async def handle_task(ctx: JobContext) -> dict:
            await ctx.update(progress=0.5, message="Working...")
            return {"result": "done"}

        await worker.run()  # Blocks, polls for jobs
    """

    def __init__(
        self,
        queue: JobQueue,
        *,
        job_types: list[str] | None = None,
        poll_interval: float = 1.0,
        max_concurrent: int = 1,
    ) -> None:
        """Initialize worker.

        Args:
            queue: JobQueue instance to poll.
            job_types: List of job types to process. If None, processes all types.
            poll_interval: Seconds between poll attempts when no jobs available.
            max_concurrent: Maximum number of concurrent jobs (default 1).
        """
        self.queue = queue
        self.job_types = job_types
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent

        self._handlers: dict[str, HandlerFunc] = {}
        self._running = False
        self._stop_event = asyncio.Event()
        self._active_jobs = 0
        self._active_lock = asyncio.Lock()

    def handler(self, job_type: str) -> Callable[[HandlerFunc], HandlerFunc]:
        """Decorator to register a job handler.

        Args:
            job_type: The job type this handler processes.

        Example:
            @worker.handler("process")
            async def handle_process(ctx: JobContext) -> dict:
                return {"result": "done"}
        """

        def decorator(func: HandlerFunc) -> HandlerFunc:
            self._handlers[job_type] = func
            return func

        return decorator

    def register_handler(self, job_type: str, handler: HandlerFunc) -> None:
        """Register a job handler programmatically.

        Args:
            job_type: The job type this handler processes.
            handler: The handler function.
        """
        self._handlers[job_type] = handler

    async def run(self) -> None:
        """Run the worker loop.

        This method blocks until stop() is called. It polls for jobs
        and processes them using registered handlers.
        """
        self._running = True
        self._stop_event.clear()

        logger.info(
            "Worker started",
            job_types=self.job_types,
            poll_interval=self.poll_interval,
            max_concurrent=self.max_concurrent,
        )

        try:
            while not self._stop_event.is_set():
                # Check if we can accept more jobs and claim atomically
                async with self._active_lock:
                    if self._active_jobs >= self.max_concurrent:
                        pass  # Will sleep below
                    else:
                        types_to_claim = self.job_types or list(self._handlers.keys())
                        if types_to_claim:
                            job = await self.queue.claim(types_to_claim)
                            if job is not None:
                                # Increment count while still holding lock
                                self._active_jobs += 1
                                # Process job in background task
                                asyncio.create_task(self._process_job(job))
                                continue

                await asyncio.sleep(self.poll_interval)

        finally:
            self._running = False
            logger.info("Worker stopped")

    async def stop(self) -> None:
        """Gracefully stop the worker.

        Signals the worker to stop polling and waits for active jobs to complete.
        """
        logger.info("Worker stopping...")
        self._stop_event.set()

        # Wait for active jobs to complete
        while True:
            async with self._active_lock:
                if self._active_jobs == 0:
                    break
            await asyncio.sleep(0.1)

    @property
    def is_running(self) -> bool:
        """Whether the worker is currently running."""
        return self._running

    async def _process_job(self, job: Job) -> None:
        """Process a single job.

        Note: _active_jobs is incremented by run() before this is called.
        """
        try:
            handler = self._handlers.get(job.job_type)
            if handler is None:
                logger.error(
                    "No handler for job type", job_type=job.job_type, job_id=job.id
                )
                await self.queue.fail(
                    job.id, f"No handler for job type: {job.job_type}"
                )
                return

            logger.debug("Processing job", job_id=job.id, job_type=job.job_type)

            ctx = JobContext(job=job, _queue=self.queue)

            try:
                results = await handler(ctx)
                await self.queue.complete(job.id, results=results)
                logger.debug("Job completed", job_id=job.id)

            except Exception as e:
                error_msg = str(e)
                logger.exception("Job failed", job_id=job.id, error=error_msg)
                await self.queue.fail(job.id, error_msg)

        finally:
            async with self._active_lock:
                self._active_jobs -= 1
