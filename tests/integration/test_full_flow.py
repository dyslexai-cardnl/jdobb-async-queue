"""Integration tests for full job processing workflows."""

import asyncio

import pytest

from jdobb_async_queue import Broadcaster, JobContext, JobQueue, JobStatus, Worker


@pytest.fixture
async def queue():
    """Create a fresh job queue for each test."""
    q = JobQueue(backend="memory")
    yield q
    await q.close()


class TestFullWorkflow:
    """Test complete job lifecycle: enqueue -> claim -> update -> complete."""

    async def test_basic_workflow(self, queue: JobQueue):
        """Test the basic producer-consumer workflow."""
        # Producer enqueues job
        job_id = await queue.enqueue("analyze", data={"input": "test data"})
        assert job_id is not None

        # Consumer claims job
        job = await queue.claim(["analyze"])
        assert job is not None
        assert job.id == job_id
        assert job.status == JobStatus.PROCESSING

        # Consumer updates progress
        await queue.update(job_id, progress=0.5, message="Halfway done")
        updated = await queue.get(job_id)
        assert updated.progress == 0.5
        assert updated.message == "Halfway done"

        # Consumer completes job
        await queue.complete(job_id, results={"output": "result"})
        final = await queue.get(job_id)
        assert final.status == JobStatus.COMPLETE
        assert final.results == {"output": "result"}
        assert final.progress == 1.0

    async def test_failure_workflow(self, queue: JobQueue):
        """Test job failure handling."""
        job_id = await queue.enqueue("risky_task")

        await queue.claim()
        await queue.fail(job_id, "Something went wrong")

        final = await queue.get(job_id)
        assert final.status == JobStatus.FAILED
        assert final.error == "Something went wrong"

    async def test_cancellation_workflow(self, queue: JobQueue):
        """Test job cancellation."""
        job_id = await queue.enqueue("long_task")

        await queue.cancel(job_id, "User requested cancellation")

        final = await queue.get(job_id)
        assert final.status == JobStatus.CANCELLED
        assert final.error == "User requested cancellation"


class TestWorkerWorkflow:
    """Test worker-based processing workflow."""

    async def test_worker_processes_jobs(self, queue: JobQueue):
        """Test that workers correctly process jobs."""
        results = []

        worker = Worker(queue, job_types=["process"], poll_interval=0.1)

        @worker.handler("process")
        async def handle_process(ctx: JobContext) -> dict:
            results.append(ctx.data)
            return {"processed": True}

        # Enqueue multiple jobs
        job_ids = []
        for i in range(3):
            job_id = await queue.enqueue("process", data={"value": i})
            job_ids.append(job_id)

        # Run worker
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(1.0)
        await worker.stop()
        await task

        # Verify all jobs processed
        assert len(results) == 3

        for job_id in job_ids:
            job = await queue.get(job_id)
            assert job.status == JobStatus.COMPLETE

    async def test_worker_handles_errors(self, queue: JobQueue):
        """Test that workers handle exceptions gracefully."""
        worker = Worker(queue, job_types=["fail"], poll_interval=0.1)

        @worker.handler("fail")
        async def handle_fail(ctx: JobContext) -> dict:
            raise RuntimeError("Intentional failure")

        job_id = await queue.enqueue("fail")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.5)
        await worker.stop()
        await task

        job = await queue.get(job_id)
        assert job.status == JobStatus.FAILED
        assert "Intentional failure" in job.error


class TestBroadcasterWorkflow:
    """Test broadcaster real-time update workflow."""

    async def test_broadcaster_receives_updates(self, queue: JobQueue):
        """Test that broadcaster receives job updates in real-time."""
        broadcaster = Broadcaster(queue)
        received_updates = []

        async def subscriber():
            async for update in broadcaster.subscribe("test-job"):
                received_updates.append(update)

        # Enqueue job with known ID
        await queue.enqueue("task", job_id="test-job")

        # Start subscriber
        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        # Send updates
        await queue.update("test-job", progress=0.25, message="Starting")
        await asyncio.sleep(0.05)
        await queue.update("test-job", progress=0.75, message="Almost done")
        await asyncio.sleep(0.05)
        await queue.complete("test-job", results={"done": True})

        await task

        assert len(received_updates) >= 3
        assert received_updates[-1].status == JobStatus.COMPLETE


class TestConcurrentWorkers:
    """Test multiple concurrent workers."""

    async def test_multiple_workers_no_duplicate_processing(self, queue: JobQueue):
        """Test that multiple workers don't process the same job twice."""
        processed_ids = []
        lock = asyncio.Lock()

        async def create_worker(name: str):
            worker = Worker(queue, job_types=["task"], poll_interval=0.05)

            @worker.handler("task")
            async def handle(ctx: JobContext) -> dict:
                async with lock:
                    processed_ids.append(ctx.id)
                await asyncio.sleep(0.1)  # Simulate work
                return {"worker": name}

            return worker

        # Create multiple workers
        workers = [await create_worker(f"worker-{i}") for i in range(3)]

        # Enqueue jobs
        for i in range(10):
            await queue.enqueue("task", job_id=f"job-{i}")

        # Run all workers concurrently
        tasks = [asyncio.create_task(w.run()) for w in workers]

        await asyncio.sleep(2.0)

        for w in workers:
            await w.stop()

        await asyncio.gather(*tasks)

        # Each job processed exactly once
        assert len(processed_ids) == 10
        assert len(set(processed_ids)) == 10


class TestErrorRecovery:
    """Test error recovery scenarios."""

    async def test_worker_continues_after_job_failure(self, queue: JobQueue):
        """Test that worker continues processing after a job fails."""
        processed = []

        worker = Worker(queue, poll_interval=0.1)

        @worker.handler("task")
        async def handle(ctx: JobContext) -> dict:
            if ctx.data.get("should_fail"):
                raise ValueError("Intentional failure")
            processed.append(ctx.id)
            return {}

        # Enqueue jobs: one that fails, two that succeed
        await queue.enqueue("task", data={"should_fail": True}, job_id="fail-job")
        await queue.enqueue("task", data={}, job_id="success-1")
        await queue.enqueue("task", data={}, job_id="success-2")

        task = asyncio.create_task(worker.run())
        await asyncio.sleep(1.0)
        await worker.stop()
        await task

        # Failed job should be marked failed
        fail_job = await queue.get("fail-job")
        assert fail_job.status == JobStatus.FAILED

        # Other jobs should complete
        assert "success-1" in processed
        assert "success-2" in processed


class TestSQLiteIntegration:
    """Test integration with SQLite backend."""

    async def test_sqlite_full_workflow(self, tmp_path):
        """Test complete workflow with SQLite backend."""
        try:
            import aiosqlite  # noqa: F401
        except ImportError:
            pytest.skip("aiosqlite not installed")

        db_path = tmp_path / "test.db"
        queue = JobQueue(backend="sqlite", url=f"sqlite:///{db_path}")

        try:
            # Full workflow
            job_id = await queue.enqueue("task", data={"key": "value"})

            job = await queue.claim()
            assert job is not None

            await queue.update(job_id, progress=0.5)
            await queue.complete(job_id, results={"done": True})

            final = await queue.get(job_id)
            assert final.status == JobStatus.COMPLETE
        finally:
            await queue.close()


class TestMultipleSubscribers:
    """Test multiple subscribers to same job."""

    async def test_multiple_subscribers_receive_all_updates(self, queue: JobQueue):
        """Test that all subscribers receive all updates."""
        broadcaster = Broadcaster(queue)
        results_1 = []
        results_2 = []

        async def sub1():
            async for update in broadcaster.subscribe("job-1"):
                results_1.append(update)

        async def sub2():
            async for update in broadcaster.subscribe("job-1"):
                results_2.append(update)

        await queue.enqueue("task", job_id="job-1")

        t1 = asyncio.create_task(sub1())
        t2 = asyncio.create_task(sub2())
        await asyncio.sleep(0.1)

        await queue.update("job-1", progress=0.5)
        await asyncio.sleep(0.05)
        await queue.complete("job-1")

        await t1
        await t2

        # Both should receive same updates
        assert len(results_1) >= 2
        assert len(results_2) >= 2
