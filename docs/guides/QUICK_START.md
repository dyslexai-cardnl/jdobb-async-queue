# Quick Start Guide

Get up and running with `jdobb-async-queue` in 5 minutes.

## Installation

```bash
pip install jdobb-async-queue[all]
```

## Basic Usage

### 1. Create a Queue

```python
from jdobb_async_queue import JobQueue

# Memory backend (for testing)
queue = JobQueue(backend="memory")

# Redis backend (for production)
queue = JobQueue(backend="redis", url="redis://localhost")

# SQLite backend (for lightweight persistence)
queue = JobQueue(backend="sqlite", url="sqlite:///jobs.db")
```

### 2. Enqueue a Job

```python
job_id = await queue.enqueue(
    "process_image",
    data={"image_url": "https://example.com/image.jpg"},
)
print(f"Job created: {job_id}")
```

### 3. Process Jobs with a Worker

```python
from jdobb_async_queue import Worker, JobContext

worker = Worker(queue, job_types=["process_image"])

@worker.handler("process_image")
async def process_image(ctx: JobContext) -> dict:
    url = ctx.data["image_url"]

    # Update progress
    await ctx.update(progress=0.25, message="Downloading...")
    # ... download image ...

    await ctx.update(progress=0.75, message="Processing...")
    # ... process image ...

    # Return results (auto-completes job)
    return {"thumbnail_url": "https://example.com/thumb.jpg"}

# Run worker (blocks until stopped)
await worker.run()
```

### 4. Monitor Job Status

```python
job = await queue.get(job_id)
print(f"Status: {job.status}")
print(f"Progress: {job.progress}")
print(f"Results: {job.results}")
```

### 5. Real-time Updates

```python
from jdobb_async_queue import Broadcaster

broadcaster = Broadcaster(queue)

async for update in broadcaster.subscribe(job_id):
    print(f"Progress: {update.progress * 100}%")
    print(f"Message: {update.message}")
    # Loop ends when job completes
```

## Complete Example

```python
import asyncio
from jdobb_async_queue import JobQueue, Worker, JobContext, Broadcaster

async def main():
    # Setup
    queue = JobQueue(backend="memory")
    worker = Worker(queue, job_types=["task"])

    @worker.handler("task")
    async def handle_task(ctx: JobContext) -> dict:
        for i in range(1, 5):
            await ctx.update(progress=i/4, message=f"Step {i}/4")
            await asyncio.sleep(0.5)
        return {"completed": True}

    # Start worker in background
    worker_task = asyncio.create_task(worker.run())

    # Enqueue job
    job_id = await queue.enqueue("task", data={"input": "test"})
    print(f"Created job: {job_id}")

    # Monitor progress
    broadcaster = Broadcaster(queue)
    async for update in broadcaster.subscribe(job_id):
        print(f"[{update.status}] {update.progress*100:.0f}% - {update.message}")

    # Get final result
    job = await queue.get(job_id)
    print(f"Results: {job.results}")

    # Cleanup
    await worker.stop()
    await queue.close()

asyncio.run(main())
```

Output:
```
Created job: abc123...
[processing] 25% - Step 1/4
[processing] 50% - Step 2/4
[processing] 75% - Step 3/4
[processing] 100% - Step 4/4
[complete] 100% - None
Results: {'completed': True}
```

## Next Steps

- [API Reference](../api/API_REFERENCE.md) - Full API documentation
- [Development Setup](DEVELOPMENT_SETUP.md) - Contributing to the library
- [Architecture Overview](../architecture/ARCHITECTURE_OVERVIEW.md) - How it works

---

**Update When:** API changes or better examples available.
