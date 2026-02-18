# jdobb-async-queue

Async job queue library for Python with Redis, Memory, and SQLite backends.

## Features

- **Async-first** - All operations use `async/await`
- **Multiple backends** - Redis (production), Memory (testing), SQLite (lightweight)
- **Atomic claiming** - Prevents duplicate job processing
- **Priority queuing** - HIGH, NORMAL, LOW priority levels
- **Real-time updates** - Pub/sub for job progress notifications
- **Worker pattern** - Polling workers with handler decorators
- **Type-safe** - Pydantic models with full type hints

## Installation

```bash
# Basic (memory backend only)
pip install jdobb-async-queue

# With Redis backend
pip install jdobb-async-queue[redis]

# With SQLite backend
pip install jdobb-async-queue[sqlite]

# With all backends
pip install jdobb-async-queue[all]
```

## Quick Start

```python
import asyncio
from jdobb_async_queue import JobQueue, Worker, JobContext, JobPriority

async def main():
    # Create queue with memory backend (for testing)
    queue = JobQueue(backend="memory")

    # Create worker
    worker = Worker(queue, job_types=["process"])

    @worker.handler("process")
    async def handle_process(ctx: JobContext) -> dict:
        print(f"Processing job {ctx.id}: {ctx.data}")
        await ctx.update(progress=0.5, message="Halfway done")
        return {"result": "success"}

    # Enqueue a job
    job_id = await queue.enqueue(
        "process",
        data={"input": "test"},
        priority=JobPriority.HIGH,
    )
    print(f"Enqueued job: {job_id}")

    # Run worker in background
    worker_task = asyncio.create_task(worker.run())

    # Wait for job to complete
    await asyncio.sleep(2)

    # Check result
    job = await queue.get(job_id)
    print(f"Job status: {job.status}, results: {job.results}")

    # Cleanup
    await worker.stop()
    await queue.close()

asyncio.run(main())
```

## Usage Patterns

### Producer (enqueue jobs)

```python
from jdobb_async_queue import JobQueue, JobPriority

queue = JobQueue(backend="redis", url="redis://localhost")

# Basic enqueue
job_id = await queue.enqueue("task", data={"key": "value"})

# With priority
job_id = await queue.enqueue("urgent", priority=JobPriority.HIGH)

# With TTL (auto-expire after 1 hour)
job_id = await queue.enqueue("temp", ttl=3600)

# With metadata
job_id = await queue.enqueue("task", metadata={"user_id": "123"})
```

### Consumer (process jobs)

```python
from jdobb_async_queue import JobQueue, Worker, JobContext

queue = JobQueue(backend="redis", url="redis://localhost")
worker = Worker(queue, job_types=["task"], poll_interval=1.0)

@worker.handler("task")
async def handle_task(ctx: JobContext) -> dict:
    # Access job data
    input_data = ctx.data["key"]

    # Update progress
    await ctx.update(progress=0.5, message="Processing...")

    # Return results (auto-completes job)
    return {"output": "result"}

# Run worker (blocks until stop() called)
await worker.run()
```

### Real-time Updates

```python
from jdobb_async_queue import JobQueue, Broadcaster

queue = JobQueue(backend="redis", url="redis://localhost")
broadcaster = Broadcaster(queue)

# Subscribe to job updates
async for update in broadcaster.subscribe(job_id):
    print(f"Progress: {update.progress}, Status: {update.status}")
    # Loop ends when job completes/fails/cancels
```

## Backend Selection

| Backend | Use Case | Persistence | Distributed |
|---------|----------|-------------|-------------|
| `memory` | Testing, development | No | No |
| `redis` | Production | Yes | Yes |
| `sqlite` | Lightweight, single-node | Yes | No |

```python
# Memory (default, for testing)
queue = JobQueue(backend="memory")

# Redis (production)
queue = JobQueue(
    backend="redis",
    url="redis://localhost:6379",
    namespace="myapp",
)

# SQLite (lightweight persistence)
queue = JobQueue(
    backend="sqlite",
    url="sqlite:///jobs.db",
)
```

## Documentation

- [Architecture Overview](docs/architecture/ARCHITECTURE_OVERVIEW.md)
- [API Reference](docs/api/API_REFERENCE.md)
- [Development Setup](docs/guides/DEVELOPMENT_SETUP.md)
- [Architecture Decisions](docs/architecture/decisions/README.md)

## Requirements

- Python 3.10+
- pydantic >= 2.0
- structlog >= 23.0
- redis >= 5.0 (for Redis backend)
- aiosqlite >= 0.19 (for SQLite backend)

## License

Apache-2.0
