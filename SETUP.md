# Setup Guide

This document provides both human-readable and machine-readable instructions for integrating `jdobb-async-queue` into your project.

---

## Human Instructions

### Step 1: Install the Package

```bash
pip install jdobb-async-queue[all]
```

Or for specific backends:
- `pip install jdobb-async-queue` - Memory only
- `pip install jdobb-async-queue[redis]` - Redis support
- `pip install jdobb-async-queue[sqlite]` - SQLite support

### Step 2: Choose Your Backend

| Scenario | Backend | Why |
|----------|---------|-----|
| Testing/Development | `memory` | Fast, no setup required |
| Production (distributed) | `redis` | Persistent, multi-worker |
| Production (single-node) | `sqlite` | Persistent, zero-config |

### Step 3: Create Queue and Worker

```python
from jdobb_async_queue import JobQueue, Worker, JobContext

# Initialize
queue = JobQueue(backend="memory")  # or "redis", "sqlite"
worker = Worker(queue, job_types=["my_task"])

# Define handler
@worker.handler("my_task")
async def handle_my_task(ctx: JobContext) -> dict:
    # Your processing logic here
    return {"status": "done"}

# In your app startup:
# await worker.run()  # Blocks and processes jobs
```

### Step 4: Enqueue Jobs

```python
job_id = await queue.enqueue("my_task", data={"input": "value"})
```

---

## Machine-Readable Instructions

The following sections are formatted for AI agents and automated tools.

### AGENT_INTEGRATION_PROMPT

```
You are integrating the jdobb-async-queue library into a Python application.

LIBRARY OVERVIEW:
- jdobb-async-queue provides async job queuing with Redis/Memory/SQLite backends
- All methods are async and must be awaited
- Jobs have: id, job_type, data, status, priority, progress
- Workers poll for jobs and process them via handler functions

INSTALLATION:
pip install jdobb-async-queue[all]

REQUIRED IMPORTS:
from jdobb_async_queue import JobQueue, Worker, JobContext, Broadcaster
from jdobb_async_queue import Job, JobStatus, JobPriority, JobUpdate

INITIALIZATION PATTERN:
1. Create JobQueue with chosen backend
2. Create Worker with queue reference
3. Register handlers for each job_type
4. Call worker.run() in your app startup

PRODUCER PATTERN (enqueueing jobs):
```python
queue = JobQueue(backend="redis", url="redis://localhost")
job_id = await queue.enqueue(
    "job_type_name",
    data={"key": "value"},
    priority=JobPriority.NORMAL,  # HIGH, NORMAL, LOW
    ttl=3600,  # optional, seconds
    metadata={"user_id": "123"},  # optional
)
```

CONSUMER PATTERN (processing jobs):
```python
worker = Worker(queue, job_types=["job_type_name"], poll_interval=1.0)

@worker.handler("job_type_name")
async def handle(ctx: JobContext) -> dict:
    # Access: ctx.id, ctx.job_type, ctx.data, ctx.metadata
    await ctx.update(progress=0.5, message="Working...")
    # Return value becomes job.results
    return {"output": "result"}

# Start worker (blocks)
await worker.run()

# Stop gracefully
await worker.stop()
```

REAL-TIME UPDATES PATTERN:
```python
broadcaster = Broadcaster(queue)
async for update in broadcaster.subscribe(job_id):
    # update.status, update.progress, update.message
    pass  # Loop ends on COMPLETE/FAILED/CANCELLED
```

BACKEND SELECTION:
- memory: JobQueue(backend="memory") - testing only
- redis: JobQueue(backend="redis", url="redis://host:port", namespace="app")
- sqlite: JobQueue(backend="sqlite", url="sqlite:///path.db")

KEY RULES:
1. Always await async methods
2. Always call queue.close() when done
3. Worker handlers must be async functions
4. Handler return value becomes job.results
5. Use ctx.update() for progress, return for results

COMMON INTEGRATION POINTS:
- FastAPI: Create queue/worker in lifespan, run worker as background task
- Standalone: Use asyncio.run() to start worker
- Testing: Use memory backend, no external dependencies
```

### STRUCTURED_INTEGRATION_SPEC

```yaml
library:
  name: jdobb-async-queue
  import_name: jdobb_async_queue
  python_version: ">=3.10"
  license: Apache-2.0

installation:
  minimal: "pip install jdobb-async-queue"
  redis: "pip install jdobb-async-queue[redis]"
  sqlite: "pip install jdobb-async-queue[sqlite]"
  full: "pip install jdobb-async-queue[all]"

exports:
  - name: JobQueue
    type: class
    purpose: Main queue interface
    methods:
      - enqueue(job_type, data, priority, ttl, metadata) -> str
      - get(job_id) -> Job | None
      - claim(job_types) -> Job | None
      - update(job_id, progress, message) -> bool
      - complete(job_id, results) -> bool
      - fail(job_id, error) -> bool
      - cancel(job_id, reason) -> bool
      - close() -> None

  - name: Worker
    type: class
    purpose: Job processing worker
    methods:
      - handler(job_type) -> decorator
      - run() -> None  # blocks
      - stop() -> None  # graceful

  - name: Broadcaster
    type: class
    purpose: Real-time updates
    methods:
      - subscribe(job_id) -> AsyncIterator[JobUpdate]
      - send(job_id, progress, message, data) -> bool

  - name: JobContext
    type: class
    purpose: Handler context
    properties: [id, job_type, data, metadata, job]
    methods:
      - update(progress, message) -> None

  - name: Job
    type: pydantic_model
    fields:
      - id: str
      - job_type: str
      - data: dict
      - status: JobStatus
      - priority: JobPriority
      - progress: float  # 0.0-1.0
      - message: str | None
      - results: dict | None
      - error: str | None
      - metadata: dict
      - created_at: datetime
      - updated_at: datetime
      - completed_at: datetime | None
      - ttl: int | None

  - name: JobStatus
    type: enum
    values: [PENDING, PROCESSING, COMPLETE, FAILED, CANCELLED]

  - name: JobPriority
    type: enum
    values: [LOW, NORMAL, HIGH]
    weights: {LOW: 1, NORMAL: 5, HIGH: 10}

backends:
  memory:
    config: 'JobQueue(backend="memory")'
    persistence: false
    distributed: false
    use_case: testing

  redis:
    config: 'JobQueue(backend="redis", url="redis://host:port", namespace="app")'
    persistence: true
    distributed: true
    use_case: production
    dependency: redis>=5.0

  sqlite:
    config: 'JobQueue(backend="sqlite", url="sqlite:///path.db")'
    persistence: true
    distributed: false
    use_case: lightweight_production
    dependency: aiosqlite>=0.19

patterns:
  fastapi_integration: |
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from jdobb_async_queue import JobQueue, Worker, JobContext
    import asyncio

    queue: JobQueue
    worker: Worker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global queue, worker
        queue = JobQueue(backend="redis", url="redis://localhost")
        worker = Worker(queue, job_types=["task"])

        @worker.handler("task")
        async def handle(ctx: JobContext) -> dict:
            return {"done": True}

        worker_task = asyncio.create_task(worker.run())
        yield
        await worker.stop()
        await queue.close()

    app = FastAPI(lifespan=lifespan)

    @app.post("/jobs")
    async def create_job(data: dict):
        job_id = await queue.enqueue("task", data=data)
        return {"job_id": job_id}

  standalone_worker: |
    import asyncio
    from jdobb_async_queue import JobQueue, Worker, JobContext

    async def main():
        queue = JobQueue(backend="redis", url="redis://localhost")
        worker = Worker(queue, job_types=["task"])

        @worker.handler("task")
        async def handle(ctx: JobContext) -> dict:
            return {"done": True}

        try:
            await worker.run()
        except KeyboardInterrupt:
            await worker.stop()
        finally:
            await queue.close()

    asyncio.run(main())

  testing: |
    import pytest
    from jdobb_async_queue import JobQueue, JobStatus

    @pytest.fixture
    async def queue():
        q = JobQueue(backend="memory")
        yield q
        await q.close()

    async def test_job_lifecycle(queue):
        job_id = await queue.enqueue("test", data={"x": 1})
        job = await queue.claim(["test"])
        assert job.status == JobStatus.PROCESSING
        await queue.complete(job_id, results={"y": 2})
        final = await queue.get(job_id)
        assert final.status == JobStatus.COMPLETE
```

---

## Integration Checklist

Use this checklist when integrating into a new project:

- [ ] Install package with appropriate backend extras
- [ ] Choose backend based on deployment scenario
- [ ] Create `JobQueue` instance with correct configuration
- [ ] Create `Worker` instance with job types to process
- [ ] Define handler functions for each job type
- [ ] Set up worker startup in application lifecycle
- [ ] Set up graceful shutdown (call `worker.stop()` and `queue.close()`)
- [ ] Add error handling in handlers (exceptions mark job as failed)
- [ ] Optionally set up `Broadcaster` for real-time updates
- [ ] Write tests using memory backend

---

## Troubleshooting

### Common Issues

**"ModuleNotFoundError: No module named 'redis'"**
```bash
pip install jdobb-async-queue[redis]
```

**"ModuleNotFoundError: No module named 'aiosqlite'"**
```bash
pip install jdobb-async-queue[sqlite]
```

**Jobs not being processed**
- Check worker is running (`await worker.run()`)
- Check job_types match between enqueue and worker
- Check handler is registered for the job_type

**Duplicate job processing**
- This should not happen with atomic claiming
- If using custom backend, ensure `claim_pending_job` is atomic

---

**Update When:** Installation process changes or new integration patterns discovered.
