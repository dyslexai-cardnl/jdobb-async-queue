"""Tests for Broadcaster class."""

import asyncio

import pytest

from jdobb_async_queue import Broadcaster, JobQueue, JobStatus


@pytest.fixture
async def queue():
    """Create a fresh job queue for each test."""
    q = JobQueue(backend="memory")
    yield q
    await q.close()


@pytest.fixture
def broadcaster(queue: JobQueue):
    """Create a broadcaster for the queue."""
    return Broadcaster(queue)


class TestBroadcasterSubscribe:
    async def test_subscribe_receives_updates(
        self, queue: JobQueue, broadcaster: Broadcaster
    ):
        job_id = await queue.enqueue("test")
        received = []

        async def subscriber():
            async for update in broadcaster.subscribe(job_id):
                received.append(update)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        # Send some updates
        await queue.update(job_id, progress=0.5, message="Working")
        await asyncio.sleep(0.05)

        # Complete the job to end subscription
        await queue.complete(job_id, results={"done": True})
        await task

        assert len(received) >= 2
        # Last update should be complete
        assert received[-1].status == JobStatus.COMPLETE

    async def test_subscribe_ends_on_complete(
        self, queue: JobQueue, broadcaster: Broadcaster
    ):
        job_id = await queue.enqueue("test")

        async def subscriber():
            updates = []
            async for update in broadcaster.subscribe(job_id):
                updates.append(update)
            return updates

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        await queue.complete(job_id)
        updates = await task

        assert len(updates) == 1
        assert updates[0].status == JobStatus.COMPLETE

    async def test_subscribe_ends_on_failed(
        self, queue: JobQueue, broadcaster: Broadcaster
    ):
        job_id = await queue.enqueue("test")

        async def subscriber():
            updates = []
            async for update in broadcaster.subscribe(job_id):
                updates.append(update)
            return updates

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        await queue.fail(job_id, "Error occurred")
        updates = await task

        assert len(updates) == 1
        assert updates[0].status == JobStatus.FAILED

    async def test_subscribe_ends_on_cancelled(
        self, queue: JobQueue, broadcaster: Broadcaster
    ):
        job_id = await queue.enqueue("test")

        async def subscriber():
            updates = []
            async for update in broadcaster.subscribe(job_id):
                updates.append(update)
            return updates

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        await queue.cancel(job_id, "User cancelled")
        updates = await task

        assert len(updates) == 1
        assert updates[0].status == JobStatus.CANCELLED


class TestBroadcasterSend:
    async def test_send_update(self, queue: JobQueue, broadcaster: Broadcaster):
        job_id = await queue.enqueue("test")
        received = []

        async def subscriber():
            async for update in broadcaster.subscribe(job_id):
                received.append(update)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        # Send custom update
        result = await broadcaster.send(job_id, progress=0.75, message="Custom message")
        assert result is True

        await asyncio.sleep(0.1)

        # Complete to end subscription
        await queue.complete(job_id)
        await task

        # Should have received the custom update
        assert any(u.message == "Custom message" for u in received)

    async def test_send_with_data(self, queue: JobQueue, broadcaster: Broadcaster):
        job_id = await queue.enqueue("test")
        received = []

        async def subscriber():
            async for update in broadcaster.subscribe(job_id):
                received.append(update)

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)

        result = await broadcaster.send(job_id, data={"custom": "data"})
        assert result is True

        await asyncio.sleep(0.1)
        await queue.complete(job_id)
        await task

        # Check custom data was received
        assert any(u.results == {"custom": "data"} for u in received)

    async def test_send_nonexistent_job(
        self, queue: JobQueue, broadcaster: Broadcaster
    ):
        result = await broadcaster.send("nonexistent", progress=0.5)
        assert result is False


class TestBroadcasterMultipleSubscribers:
    async def test_multiple_subscribers(
        self, queue: JobQueue, broadcaster: Broadcaster
    ):
        job_id = await queue.enqueue("test")
        received_1 = []
        received_2 = []

        async def sub1():
            async for update in broadcaster.subscribe(job_id):
                received_1.append(update)

        async def sub2():
            async for update in broadcaster.subscribe(job_id):
                received_2.append(update)

        t1 = asyncio.create_task(sub1())
        t2 = asyncio.create_task(sub2())
        await asyncio.sleep(0.1)

        await queue.update(job_id, progress=0.5)
        await asyncio.sleep(0.05)
        await queue.complete(job_id)

        await t1
        await t2

        # Both subscribers should receive updates
        assert len(received_1) >= 2
        assert len(received_2) >= 2
