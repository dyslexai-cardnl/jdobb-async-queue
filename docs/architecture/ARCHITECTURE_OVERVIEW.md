# Architecture Overview

**One-sentence summary:** `jdobb-async-queue` is an async Python library that provides Redis-backed job queuing with atomic claiming, priority handling, and real-time progress updates.

## The Post Office Metaphor

Think of the job queue as a **post office**:

| Role | Component | Responsibility |
|------|-----------|----------------|
| **Mailbox** | `JobQueue` | Central hub where jobs are deposited and picked up |
| **Letters** | `Job` | Work items with addresses (job_type) and contents (data) |
| **Postal Workers** | `Worker` | Pick up letters and deliver them (process jobs) |
| **Tracking System** | `Broadcaster` | Real-time notifications about delivery status |
| **Sorting Bins** | Priority Levels | HIGH/NORMAL/LOW determine pickup order |
| **Storage Room** | Backend | Where letters wait (Redis/Memory/SQLite) |

## System Diagram

```
                                    +------------------+
                                    |   Your App       |
                                    | (Producer)       |
                                    +--------+---------+
                                             |
                                    enqueue(job_type, data)
                                             |
                                             v
+------------------+              +------------------+              +------------------+
|   Worker 1       |    claim     |    JobQueue      |   subscribe  |   Broadcaster    |
|   (Consumer)     | <----------> |                  | <----------> |   (Real-time)    |
+------------------+              |   +----------+   |              +--------+---------+
                                  |   | Backend  |   |                       |
+------------------+              |   +----------+   |              +--------v---------+
|   Worker 2       |    claim     |   | Redis    |   |              |   WebSocket      |
|   (Consumer)     | <----------> |   | Memory   |   |              |   Clients        |
+------------------+              |   | SQLite   |   |              +------------------+
                                  +------------------+
```

## Data Flow: Job Lifecycle

### Step 1: Job Creation
```
Producer                    JobQueue                     Backend
   |                           |                            |
   |---enqueue("analyze",----->|                            |
   |     data={...})           |                            |
   |                           |---store_job(Job)---------->|
   |                           |                            |
   |<----job_id="abc123"-------|                            |
```

### Step 2: Job Claiming
```
Worker                      JobQueue                     Backend
   |                           |                            |
   |---claim(["analyze"])----->|                            |
   |                           |---claim_pending_job()----->|
   |                           |      (atomic operation)    |
   |                           |<---Job(status=PROCESSING)--|
   |<---Job(id="abc123")-------|                            |
```

### Step 3: Progress Updates
```
Worker                      JobQueue                     Backend        Subscribers
   |                           |                            |                |
   |---update(progress=0.5)--->|                            |                |
   |                           |---update_job(...)--------->|                |
   |                           |---publish_update(...)----->|---JobUpdate--->|
   |                           |                            |                |
```

### Step 4: Completion
```
Worker                      JobQueue                     Backend        Subscribers
   |                           |                            |                |
   |---complete(results={})---> |                           |                |
   |                           |---update_job(COMPLETE)---->|                |
   |                           |---publish_update(...)----->|---JobUpdate--->|
   |                           |                            |    (status=COMPLETE)
```

## Key Components

### JobQueue (The Mailbox)
Central facade that coordinates all operations.

```python
queue = JobQueue(backend="redis", url="redis://localhost")

# Producer API
job_id = await queue.enqueue("task", data={...}, priority=JobPriority.HIGH)

# Consumer API
job = await queue.claim(["task"])
await queue.update(job.id, progress=0.5)
await queue.complete(job.id, results={...})
```

### Job (The Letter)
Pydantic model representing a unit of work.

```python
Job(
    id="abc123",
    job_type="analyze",
    data={"input": "..."},
    status=JobStatus.PENDING,
    priority=JobPriority.NORMAL,
    progress=0.0,
    message=None,
    results=None,
    error=None,
    metadata={"user_id": "..."},
    created_at=datetime(...),
    ttl=3600,
)
```

### Worker (The Postal Worker)
Polling worker that claims and processes jobs.

```python
worker = Worker(queue, job_types=["analyze"], poll_interval=1.0)

@worker.handler("analyze")
async def handle_analyze(ctx: JobContext) -> dict:
    await ctx.update(progress=0.5, message="Processing...")
    result = do_work(ctx.data)
    return {"output": result}  # Auto-completes job

await worker.run()  # Blocks, polls for jobs
```

### Broadcaster (The Tracking System)
Real-time subscriptions to job updates.

```python
broadcaster = Broadcaster(queue)

async for update in broadcaster.subscribe(job_id):
    print(f"Status: {update.status}, Progress: {update.progress}")
    # Loop ends when job completes/fails/cancels
```

### Backend (The Storage Room)
Abstract storage interface with three implementations:

| Backend | Use Case | Persistence | Distributed | Pub/Sub |
|---------|----------|-------------|-------------|---------|
| Memory | Testing | No | No | In-process |
| Redis | Production | Yes | Yes | Native |
| SQLite | Lightweight | Yes | No | In-process |

## Priority System

Jobs have three priority levels with weighted scoring:

```
HIGH (weight=10)   -> Claimed first
NORMAL (weight=5)  -> Default
LOW (weight=1)     -> Claimed last
```

Within the same priority, jobs are processed FIFO (first in, first out).

## Atomic Claiming

The `claim_pending_job()` operation is atomic to prevent duplicate processing:

```
Worker A                 Redis                    Worker B
   |                       |                         |
   |---WATCH job:123------>|                         |
   |                       |<----WATCH job:123-------|
   |---GET job:123-------->|                         |
   |<--{status:pending}----|                         |
   |                       |---GET job:123---------->|
   |                       |--{status:pending}------>|
   |---MULTI-------------->|                         |
   |---SET job:123-------->|                         |
   |---EXEC--------------->|                         |
   |<------OK--------------|                         |
   |                       |<----MULTI---------------|
   |                       |<----SET job:123---------|
   |                       |<----EXEC----------------|
   |                       |-------WatchError------->|
   |                       |                         |
```

Worker B's transaction fails because Worker A modified the key first. Worker B retries with the next available job.

## Technology Summary

| Layer | Technology | Why |
|-------|------------|-----|
| Language | Python 3.10+ | Modern async support |
| Schemas | Pydantic v2 | Validation + JSON |
| Async | asyncio | Non-blocking I/O |
| Primary Backend | Redis | Distributed, pub/sub |
| Logging | structlog | Structured output |

## Related Documents

- [ADR Index](decisions/README.md) - All architecture decisions
- [API Reference](../api/API_REFERENCE.md) - Detailed API documentation
- [Development Setup](../guides/DEVELOPMENT_SETUP.md) - Getting started
- [Implementation Checklist](../implementation/IMPLEMENTATION_CHECKLIST.md) - How this was built

---

**Update When:** Component responsibilities change, new backends added, or data flow modified.
