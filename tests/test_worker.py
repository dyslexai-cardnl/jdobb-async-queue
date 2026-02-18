"""Tests for Worker class."""

import asyncio

import pytest

from jdobb_async_queue import JobContext, JobQueue, JobStatus, Worker


@pytest.fixture
async def queue():
    """Create a fresh job queue for each test."""
    q = JobQueue(backend="memory")
    yield q
    await q.close()


class TestWorkerHandler:
    async def test_handler_decorator(self, queue: JobQueue):
        worker = Worker(queue)

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            return {"result": "done"}

        assert "test" in worker._handlers

    async def test_register_handler(self, queue: JobQueue):
        worker = Worker(queue)

        async def handle_test(ctx: JobContext) -> dict:
            return {"result": "done"}

        worker.register_handler("test", handle_test)
        assert "test" in worker._handlers


class TestWorkerProcessing:
    async def test_process_single_job(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)
        results_received = []

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            results_received.append(ctx.data)
            return {"output": "processed"}

        job_id = await queue.enqueue("test", data={"input": "data"})

        # Run worker in background
        task = asyncio.create_task(worker.run())

        # Wait for job to be processed
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        # Check results
        assert len(results_received) == 1
        assert results_received[0] == {"input": "data"}

        job = await queue.get(job_id)
        assert job.status == JobStatus.COMPLETE
        assert job.results == {"output": "processed"}

    async def test_process_multiple_jobs(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)
        processed = []

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            processed.append(ctx.id)
            return {}

        for i in range(5):
            await queue.enqueue("test", job_id=f"job-{i}")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(1.0)
        await worker.stop()
        await task

        assert len(processed) == 5

    async def test_job_handler_failure(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            raise ValueError("Something went wrong")

        job_id = await queue.enqueue("test")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        job = await queue.get(job_id)
        assert job.status == JobStatus.FAILED
        assert "Something went wrong" in job.error

    async def test_no_handler_for_job_type(self, queue: JobQueue):
        worker = Worker(queue, job_types=["unknown"], poll_interval=0.1)

        # Register a handler for a different type
        @worker.handler("other")
        async def handle_other(ctx: JobContext) -> dict:
            return {}

        job_id = await queue.enqueue("unknown")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        job = await queue.get(job_id)
        assert job.status == JobStatus.FAILED
        assert "No handler" in job.error


class TestWorkerJobTypes:
    async def test_filter_by_job_types(self, queue: JobQueue):
        worker = Worker(queue, job_types=["type_a"], poll_interval=0.1)
        processed = []

        @worker.handler("type_a")
        async def handle_a(ctx: JobContext) -> dict:
            processed.append(ctx.job_type)
            return {}

        await queue.enqueue("type_a", job_id="job-a")
        await queue.enqueue("type_b", job_id="job-b")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        assert processed == ["type_a"]

        # type_b should still be pending
        job_b = await queue.get("job-b")
        assert job_b.status == JobStatus.PENDING

    async def test_process_from_handlers_when_no_job_types(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)
        processed = []

        @worker.handler("type_a")
        async def handle_a(ctx: JobContext) -> dict:
            processed.append(ctx.job_type)
            return {}

        @worker.handler("type_b")
        async def handle_b(ctx: JobContext) -> dict:
            processed.append(ctx.job_type)
            return {}

        await queue.enqueue("type_a")
        await queue.enqueue("type_b")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        assert "type_a" in processed
        assert "type_b" in processed


class TestWorkerContext:
    async def test_context_properties(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)
        captured_ctx = None

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            nonlocal captured_ctx
            captured_ctx = ctx
            return {}

        await queue.enqueue(
            "test",
            data={"key": "value"},
            metadata={"user": "alice"},
            job_id="job-123",
        )

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        assert captured_ctx is not None
        assert captured_ctx.id == "job-123"
        assert captured_ctx.job_type == "test"
        assert captured_ctx.data == {"key": "value"}
        assert captured_ctx.metadata == {"user": "alice"}

    async def test_context_update_progress(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            await ctx.update(progress=0.25, message="Starting")
            await ctx.update(progress=0.75, message="Almost done")
            return {}

        job_id = await queue.enqueue("test")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        job = await queue.get(job_id)
        assert job.status == JobStatus.COMPLETE
        # Final progress should be 1.0 from completion
        assert job.progress == 1.0


class TestWorkerConcurrency:
    async def test_max_concurrent_jobs(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1, max_concurrent=2)
        concurrent_count = []
        max_concurrent_seen = 0

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            nonlocal max_concurrent_seen
            async with worker._active_lock:
                concurrent_count.append(worker._active_jobs)
                if worker._active_jobs > max_concurrent_seen:
                    max_concurrent_seen = worker._active_jobs
            await asyncio.sleep(0.2)
            return {}

        for i in range(5):
            await queue.enqueue("test", job_id=f"job-{i}")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(1.5)
        await worker.stop()
        await task

        # Should never exceed max_concurrent
        assert max_concurrent_seen <= 2


class TestWorkerLifecycle:
    async def test_is_running_property(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            return {}

        assert not worker.is_running

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.1)
        assert worker.is_running

        await worker.stop()
        await task
        assert not worker.is_running

    async def test_graceful_stop_waits_for_active_jobs(self, queue: JobQueue):
        worker = Worker(queue, poll_interval=0.1)
        job_completed = asyncio.Event()

        @worker.handler("test")
        async def handle_test(ctx: JobContext) -> dict:
            await asyncio.sleep(0.5)
            job_completed.set()
            return {}

        await queue.enqueue("test")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.1)  # Let worker claim the job

        # Stop should wait for job to complete
        await worker.stop()
        await task

        assert job_completed.is_set()
