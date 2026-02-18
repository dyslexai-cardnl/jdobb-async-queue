# ADR-F004: Redis as Primary Backend

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
A job queue library needs a production-ready storage backend that provides:
- Persistence across restarts
- Distributed access (multiple workers on multiple machines)
- Atomic operations (prevent double-claiming)
- Real-time notifications (pub/sub for job updates)
- TTL support (automatic job expiration)

### Current State
The `spatial-vision-app` uses Redis for job management via `job_manager.py`. This works well in production.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| Atomic operations | Must Have | WATCH/MULTI/EXEC pattern |
| Pub/Sub | Must Have | Real-time job updates |
| TTL support | Must Have | Automatic cleanup |
| Distributed access | Must Have | Multiple workers/machines |
| Persistence | Should Have | Survive restarts |
| High throughput | Should Have | 1000+ ops/sec |

## Decision

**We will use Redis as the primary production backend, with Memory backend for testing and SQLite for lightweight persistent deployments.**

Redis provides all required features natively:
- `WATCH/MULTI/EXEC` for atomic claiming
- `PUBLISH/SUBSCRIBE` for real-time updates
- `SETEX` for TTL
- Distributed by design
- High performance

## Alternatives Considered

### Option A: PostgreSQL
**Description:** Use PostgreSQL with `SELECT FOR UPDATE`

**Pros:**
- ACID transactions
- Complex queries possible
- Already used by many apps
- Row-level locking

**Cons:**
- Heavier than Redis
- No native pub/sub (need LISTEN/NOTIFY or polling)
- Overkill for simple key-value job storage
- Connection pool management

### Option B: Redis (Chosen)
**Description:** In-memory data store with persistence options

**Pros:**
- Native pub/sub
- Atomic operations via WATCH
- Built-in TTL
- Extremely fast
- Simple data model
- Widely used for queues

**Cons:**
- Additional infrastructure
- Memory-bound
- Less query flexibility than SQL

### Option C: RabbitMQ
**Description:** Dedicated message broker

**Pros:**
- Purpose-built for queues
- Advanced routing
- Acknowledgment patterns
- Clustering support

**Cons:**
- Heavier infrastructure
- Different paradigm (messages vs jobs)
- Can't easily query job state
- Overkill for job queue pattern

### Option D: SQLite Only
**Description:** Use SQLite as only backend

**Pros:**
- Zero infrastructure
- Single file
- SQL queries

**Cons:**
- Single-writer limitation
- No native distributed access
- No native pub/sub
- Not suitable for high throughput

## Comparison Matrix

| Criteria | Weight | PostgreSQL | Redis | RabbitMQ | SQLite |
|----------|--------|------------|-------|----------|--------|
| Atomic Operations | High | 4/5 | 5/5 | 4/5 | 3/5 |
| Pub/Sub | High | 2/5 | 5/5 | 5/5 | 1/5 |
| Performance | High | 3/5 | 5/5 | 4/5 | 2/5 |
| Simplicity | Medium | 3/5 | 4/5 | 2/5 | 5/5 |
| Distributed | Medium | 4/5 | 5/5 | 5/5 | 1/5 |
| Infrastructure | Low | 3/5 | 4/5 | 2/5 | 5/5 |
| **Weighted Total** | | 3.2 | **4.7** | 3.8 | 2.5 |

## Consequences

### Positive
- Atomic job claiming prevents race conditions
- Real-time updates via pub/sub
- High throughput for production workloads
- Industry-standard choice for queues
- TTL handles automatic cleanup

### Negative
- Requires Redis server infrastructure
- Memory-bound storage
- Additional operational complexity

### Neutral
- Memory backend sufficient for testing
- SQLite available for single-machine deployments

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Native pub/sub | Zero infrastructure |
| Atomic operations | SQL query flexibility |
| High performance | Complex queries |

## When to Reconsider

This decision should be revisited if:
- Redis cloud costs become prohibitive
- A new distributed key-value store offers better features
- PostgreSQL LISTEN/NOTIFY becomes more ergonomic

## Validation Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Claim throughput | 1000+ ops/sec | Benchmark with Redis |
| Atomic correctness | 0 double-claims | Concurrent worker tests |
| Pub/Sub latency | <100ms | Measure update delivery |

## Implementation Notes

### Redis Key Schema

```
{namespace}:job:{id}       - Job data (JSON string)
{namespace}:pending:{type} - Sorted set of pending job IDs by priority
{namespace}:updates:{id}   - Pub/sub channel for job updates
```

### Atomic Claim Pattern

```python
async def claim_pending_job(self, job_types):
    # WATCH the job key
    async with self._client.pipeline(transaction=True) as pipe:
        await pipe.watch(job_key)

        # Read job, verify still pending
        job = await self._client.get(job_key)
        if job.status != "pending":
            await pipe.unwatch()
            continue

        # Atomic update
        pipe.multi()
        pipe.set(job_key, updated_job)
        pipe.zrem(pending_key, job_id)
        await pipe.execute()
```

### Code Locations
- `src/jdobb_async_queue/backends/redis.py` - Full implementation
- `src/jdobb_async_queue/backends/memory.py` - Testing alternative
- `src/jdobb_async_queue/backends/sqlite.py` - Lightweight alternative

### Dependencies
- `redis>=5.0` (optional, for Redis backend)

## References

- [Redis WATCH documentation](https://redis.io/commands/watch/)
- [Redis Pub/Sub documentation](https://redis.io/docs/interact/pubsub/)
- [redis-py async documentation](https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html)

## Related ADRs

- ADR-F003: Backend Abstraction Layer (Redis implements interface)
- ADR-001: Atomic Job Claiming (Redis WATCH/MULTI/EXEC pattern)
- ADR-003: Pub/Sub Broadcasting (Redis pub/sub)

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
