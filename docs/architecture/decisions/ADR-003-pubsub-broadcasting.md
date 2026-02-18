# ADR-003: Pub/Sub Broadcasting

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
Clients need real-time updates about job progress:
- Web UI showing progress bars
- WebSocket connections receiving status changes
- Monitoring dashboards tracking throughput

Polling the job state is inefficient and introduces latency. A push-based notification system is needed.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| Real-time updates | Must Have | <100ms latency |
| Multiple subscribers | Must Have | Many clients per job |
| Auto-unsubscribe on completion | Should Have | Clean up after job ends |
| Backend agnostic | Should Have | Works in all backends |

## Decision

**We will implement pub/sub using Redis native pub/sub for Redis backend, and in-memory asyncio.Queue for Memory/SQLite backends.**

Each backend implements:
- `publish_update(update)` - Send update to all subscribers
- `subscribe_updates(job_id)` - Async generator yielding updates

The `Broadcaster` class provides a high-level interface:
- `subscribe(job_id)` - Subscribe to job updates
- `send(job_id, ...)` - Publish custom update

Subscriptions automatically end when the job reaches a terminal state (COMPLETE, FAILED, CANCELLED).

## Implementation

### Redis Pub/Sub

```python
async def publish_update(self, update: JobUpdate) -> None:
    channel = self._channel_key(update.job_id)
    await self._client.publish(channel, update.model_dump_json())

async def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]:
    pubsub = self._client.pubsub()
    channel = self._channel_key(job_id)

    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0
            )
            if message and message["type"] == "message":
                update = JobUpdate.model_validate_json(message["data"])
                yield update

                if update.status in TERMINAL_STATES:
                    break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
```

### Memory/SQLite In-Memory Pub/Sub

```python
async def publish_update(self, update: JobUpdate) -> None:
    async with self._lock:
        queues = self._subscribers.get(update.job_id, [])
        for queue in queues:
            await queue.put(update)

        if update.status in TERMINAL_STATES:
            for queue in queues:
                await queue.put(None)  # Signal end

async def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]:
    queue = asyncio.Queue()

    async with self._lock:
        self._subscribers.setdefault(job_id, []).append(queue)

    try:
        while True:
            update = await queue.get()
            if update is None:
                break
            yield update
    finally:
        async with self._lock:
            self._subscribers[job_id].remove(queue)
```

### Broadcaster Usage

```python
broadcaster = Broadcaster(queue)

# Subscribe to updates
async for update in broadcaster.subscribe(job_id):
    print(f"Progress: {update.progress}")
    # Loop ends on COMPLETE/FAILED/CANCELLED

# Send custom update
await broadcaster.send(job_id, progress=0.5, message="Working...")
```

## Consequences

### Positive
- Real-time updates with minimal latency
- Multiple clients can subscribe to same job
- Automatic cleanup on job completion
- Redis pub/sub scales across machines

### Negative
- Memory/SQLite pub/sub is single-process only
- Redis pub/sub messages can be lost if no subscribers

### Neutral
- Updates are not persisted (ephemeral)

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Real-time push | Polling simplicity |
| Multiple subscribers | Single-observer pattern |
| Redis scalability | Guaranteed delivery |

## When to Reconsider

- If message delivery guarantees become critical
- If WebSocket frameworks have better native patterns

## Related ADRs

- ADR-F003: Backend Abstraction Layer (pub/sub in interface)
- ADR-F004: Redis as Primary Backend (native pub/sub)

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
