# API Reference

Complete API documentation for `jdobb-async-queue`.

## Installation

```bash
pip install jdobb-async-queue

# With Redis support
pip install jdobb-async-queue[redis]

# With SQLite support
pip install jdobb-async-queue[sqlite]

# With all backends
pip install jdobb-async-queue[all]
```

## Quick Example

```python
import asyncio
from jdobb_async_queue import JobQueue, Worker, JobContext, JobPriority

async def main():
    # Create queue
    queue = JobQueue(backend="memory")

    # Create worker
    worker = Worker(queue, job_types=["task"])

    @worker.handler("task")
    async def handle_task(ctx: JobContext) -> dict:
        print(f"Processing: {ctx.data}")
        await ctx.update(progress=0.5, message="Working...")
        return {"result": "done"}

    # Enqueue a job
    job_id = await queue.enqueue("task", data={"input": "test"})
    print(f"Enqueued: {job_id}")

    # Run worker (in real app, run in background)
    import asyncio
    worker_task = asyncio.create_task(worker.run())

    await asyncio.sleep(1)  # Let worker process

    await worker.stop()
    await queue.close()

asyncio.run(main())
```

---

## Core Classes

### JobQueue

Main interface for queue operations.

#### Constructor

```python
JobQueue(
    backend: QueueBackend | str = "memory",
    *,
    url: str | None = None,
    namespace: str = "default",
    default_ttl: int | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | `QueueBackend \| str` | `"memory"` | Backend instance or name (`"memory"`, `"redis"`, `"sqlite"`) |
| `url` | `str \| None` | `None` | Connection URL for redis/sqlite |
| `namespace` | `str` | `"default"` | Key prefix for Redis backend |
| `default_ttl` | `int \| None` | `None` | Default job TTL in seconds |

#### Methods

##### `enqueue()`
```python
async def enqueue(
    job_type: str,
    data: dict[str, Any] | None = None,
    *,
    priority: JobPriority = JobPriority.NORMAL,
    ttl: int | None = None,
    metadata: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> str
```

Enqueue a new job. Returns the job ID.

##### `get()`
```python
async def get(job_id: str) -> Job | None
```

Get a job by ID. Returns `None` if not found.

##### `claim()`
```python
async def claim(job_types: list[str] | None = None) -> Job | None
```

Atomically claim a pending job. Returns `None` if no jobs available.

##### `update()`
```python
async def update(
    job_id: str,
    progress: float | None = None,
    message: str | None = None,
) -> bool
```

Update job progress. Returns `True` if updated.

##### `complete()`
```python
async def complete(
    job_id: str,
    results: dict[str, Any] | None = None,
) -> bool
```

Mark job as complete. Returns `True` if completed.

##### `fail()`
```python
async def fail(job_id: str, error: str) -> bool
```

Mark job as failed. Returns `True` if marked.

##### `cancel()`
```python
async def cancel(job_id: str, reason: str | None = None) -> bool
```

Cancel a pending/processing job. Returns `True` if cancelled.

##### `close()`
```python
async def close() -> None
```

Close the queue and release resources.

---

### Worker

Polling worker that processes jobs.

#### Constructor

```python
Worker(
    queue: JobQueue,
    *,
    job_types: list[str] | None = None,
    poll_interval: float = 1.0,
    max_concurrent: int = 1,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `queue` | `JobQueue` | required | Queue to poll |
| `job_types` | `list[str] \| None` | `None` | Job types to process (None = from handlers) |
| `poll_interval` | `float` | `1.0` | Seconds between polls |
| `max_concurrent` | `int` | `1` | Max concurrent jobs |

#### Methods

##### `handler()` decorator
```python
@worker.handler("job_type")
async def handle(ctx: JobContext) -> dict | None:
    return {"result": "..."}
```

Register a handler for a job type. Return value becomes job results.

##### `register_handler()`
```python
def register_handler(job_type: str, handler: HandlerFunc) -> None
```

Programmatic handler registration.

##### `run()`
```python
async def run() -> None
```

Start the worker loop. Blocks until `stop()` is called.

##### `stop()`
```python
async def stop() -> None
```

Gracefully stop the worker. Waits for active jobs to complete.

#### Properties

##### `is_running`
```python
@property
def is_running(self) -> bool
```

Whether the worker is currently running.

---

### JobContext

Context passed to job handlers.

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | Job ID |
| `job_type` | `str` | Job type |
| `data` | `dict[str, Any]` | Job payload |
| `metadata` | `dict[str, Any]` | Job metadata |
| `job` | `Job` | Full job object |

#### Methods

##### `update()`
```python
async def update(
    progress: float | None = None,
    message: str | None = None,
) -> None
```

Update job progress from within handler.

---

### Broadcaster

Real-time update subscriptions.

#### Constructor

```python
Broadcaster(queue: JobQueue)
```

#### Methods

##### `subscribe()`
```python
async def subscribe(job_id: str) -> AsyncIterator[JobUpdate]
```

Subscribe to job updates. Yields `JobUpdate` objects until job reaches terminal state.

```python
async for update in broadcaster.subscribe(job_id):
    print(f"Progress: {update.progress}")
    # Loop ends on COMPLETE/FAILED/CANCELLED
```

##### `send()`
```python
async def send(
    job_id: str,
    *,
    progress: float | None = None,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> bool
```

Send a custom update. Returns `True` if sent.

---

## Data Models

### Job

```python
class Job(BaseModel):
    id: str
    job_type: str
    data: dict[str, Any] = {}
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    progress: float = 0.0  # 0.0 to 1.0
    message: str | None = None
    results: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    ttl: int | None = None  # seconds
```

### JobStatus

```python
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### JobPriority

```python
class JobPriority(str, Enum):
    LOW = "low"      # weight: 1
    NORMAL = "normal"  # weight: 5
    HIGH = "high"    # weight: 10
```

### JobUpdate

```python
class JobUpdate(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = 0.0
    message: str | None = None
    results: dict[str, Any] | None = None
    error: str | None = None
    timestamp: datetime
```

---

## Backend Configuration

### Memory (Testing)
```python
queue = JobQueue(backend="memory")
```

### Redis (Production)
```python
queue = JobQueue(
    backend="redis",
    url="redis://localhost:6379",
    namespace="myapp",
)
```

### SQLite (Lightweight)
```python
queue = JobQueue(
    backend="sqlite",
    url="sqlite:///jobs.db",
)
# or in-memory
queue = JobQueue(
    backend="sqlite",
    url="sqlite:///:memory:",
)
```

---

**Update When:** API changes or new features added.
